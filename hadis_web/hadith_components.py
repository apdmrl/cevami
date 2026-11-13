"""Immutable, source-bound translation components and conservative coverage reports."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import html
import json
import re
import uuid

from psycopg.types.json import Jsonb

from .field_reviews import _validate_references
from .importer import verify_artifact
from .source import SourceReader, open_readonly
from .working import REQUIRED_DIMENSIONS, stable_id, text_identity


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _digest(data):
    return sha(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


def _identity(case):
    return str(stable_id('hadith-component-set-v1', _digest(case)))


def _refs(refs):
    if not isinstance(refs, list) or not refs or any(not isinstance(r, dict) for r in refs):
        raise ValueError('Missing component source references')
    _validate_references(refs)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing ' + label)
    return value


def _review(review):
    if not isinstance(review, dict) or review.get('outcome') not in ('pass', 'pending', 'fail', 'not_applicable'):
        raise ValueError('Invalid component review outcome')
    if review.get('actor_kind') not in ('assistant_source_review', 'automated_check'):
        raise ValueError('Unsupported component review actor; expert approval is not created by this importer')
    if review['actor_kind'] == 'automated_check' and review['outcome'] in ('pass', 'not_applicable'):
        raise ValueError('Automated checks cannot approve translation meaning or absence')
    _text(review.get('rationale'), 'review rationale')
    _refs(review.get('sources'))


class _Sources:
    def __init__(self, conn, settings):
        self.conn, self.settings = conn, settings
        self.reader = SourceReader(settings)
        self.versions, self.documents = {}, {}
        self.manifest = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text(encoding='utf-8'))
        verify_artifact(settings.source_db, self.manifest['database_sha256'])

    def version(self, identity):
        try:
            identity = str(uuid.UUID(identity))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid component source version') from None
        if identity in self.versions:
            return self.versions[identity]
        row = self.conn.execute('SELECT v.*,u.namespace,u.source_key,s.provider,s.revision,s.artifact_sha256,s.artifact_name '
                                'FROM text_versions v JOIN text_units u ON u.id=v.unit_id '
                                'JOIN source_snapshots s ON s.id=v.snapshot_id WHERE v.id=%s', (identity,)).fetchone()
        if row is None or sha(row['raw_text']) != row['raw_sha256'] or row['derivation_version'] != 'reader-v1':
            raise ValueError('Missing or changed immutable component source')
        if row['provider'] == 'gk45':
            snapshot = stable_id('snapshot', 'gk45', '4.5', self.manifest['database_sha256'])
            live = self.reader.hadith(row['source_key'])
            if live is None or row['namespace'] != 'gk45:ar' or row['language'] != 'ar' or row['snapshot_id'] != snapshot:
                raise ValueError('Arabic source snapshot differs')
            if row['raw_text'] != live['arabic']['raw_text'] or row['display_text'] != live['arabic']['text']:
                raise ValueError('Arabic source content differs')
        elif row['provider'] == 'fawazahmed0':
            folder = self.settings.project_root / 'references/turkish/fawazahmed0'
            coverage = json.loads((folder / 'coverage.json').read_text(encoding='utf-8'))
            match = re.fullmatch(r'(ara|tur)-([a-z]+)\.json', row['artifact_name'])
            if match is None or row['revision'] != coverage['revision']:
                raise ValueError('External source revision differs')
            prefix, book = match.groups()
            collection = next((c for c in coverage['collections'] if c['book'] == book), None)
            if collection is None or collection[prefix]['sha256'] != row['artifact_sha256']:
                raise ValueError('External artifact digest differs')
            path = folder / row['artifact_name']
            verify_artifact(path, row['artifact_sha256'])
            if str(path) not in self.documents:
                self.documents[str(path)] = json.loads(path.read_text(encoding='utf-8'))['hadiths']
            pointer = row['locator'].get('json_pointer', '')
            if not re.fullmatch(r'/hadiths/\d+', pointer):
                raise ValueError('Invalid external source locator')
            entries = self.documents[str(path)]
            index = int(pointer.rsplit('/', 1)[1])
            if index >= len(entries):
                raise ValueError('External source locator outside artifact')
            entry = entries[index]
            if (str(entry['hadithnumber']) != row['source_key'] or entry['text'] != row['raw_text']
                    or html.unescape(re.sub('<[^>]+>', '', entry['text'])) != row['display_text']
                    or row['namespace'] != 'fawaz:' + row['artifact_name'][:-5]
                    or row['language'] != ('ar' if prefix == 'ara' else 'tr')):
                raise ValueError('External source content differs')
        elif row['provider'] == 'hadeethenc':
            from .hadeethenc import validate_hadeethenc_text
            validate_hadeethenc_text(self.settings, row)
        else:
            raise ValueError('Unsupported component source provider')
        self.versions[identity] = row
        return row


def _binding(binding, sources):
    row = sources.version(binding.get('text_version_id'))
    start, end = binding.get('start_codepoint'), binding.get('end_codepoint')
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(row['display_text'])
            or binding.get('raw_sha256') != row['raw_sha256']
            or binding.get('display_sha256') != sha(row['display_text'])):
        raise ValueError('Component Unicode range or source digest differs')
    return row, row['display_text'][start:end]


def _find_reuse(conn, component_id):
    for row in conn.execute('SELECT id,payload FROM hadith_component_sets ORDER BY created_at,id'):
        for comp in row['payload']['components']:
            identity = str(stable_id('hadith-component-v1', str(row['id']), comp['kind'], comp['ordinal']))
            if identity == component_id:
                return row['payload'], comp
    raise ValueError('Missing previously reviewed component')


def _assess_case(conn, sources, case, stack=()):
    if not isinstance(case, dict):
        raise ValueError('Invalid component case')
    identity = _identity(case)
    if identity in stack or len(stack) > 40:
        raise ValueError('Cyclic or excessive reuse depth')
    _text(case.get('segmentation_version'), 'segmentation version')
    if not re.fullmatch(r'[a-z]{2,3}(-[A-Za-z0-9]{2,8})*', case.get('language', '')) or case['language'].split('-')[0] == 'ar':
        raise ValueError('Invalid target language')
    target = sources.version(case.get('target_version_id'))
    if (target['namespace'] != 'gk45:ar' or target['source_key'] != case.get('bhid')
            or target['raw_sha256'] != case.get('target_raw_sha256')
            or sha(target['display_text']) != case.get('target_display_sha256')):
        raise ValueError('Target Arabic source binding differs')
    _refs(case.get('source_refs'))
    if not any(r['url'] == 'gk45:hadith:' + case['bhid'] and target['raw_sha256'] in r['locator'] for r in case['source_refs']):
        raise ValueError('References do not identify the complete Arabic source')
    with open_readonly(sources.settings.source_db) as c:
        sanads = [dict(r) for r in c.execute('SELECT * FROM sanad WHERE bhid=? ORDER BY sanad_id', (case['bhid'],))]
    if case.get('source_sanads') != sanads:
        raise ValueError('Complete source sanad records differ')
    components = case.get('components')
    if not isinstance(components, list) or not components:
        raise ValueError('Missing source components')
    items, blockers, seen = [], [], set()
    ranges, sanad_coverage = defaultdict(list), set()
    for comp in components:
        kind, ordinal = comp.get('kind'), comp.get('ordinal')
        if kind not in ('matn', 'isnad', 'notes', 'unclassified') or type(ordinal) is not int or ordinal < 0 or (kind, ordinal) in seen:
            raise ValueError('Invalid or duplicate source component')
        seen.add((kind, ordinal))
        bindings = comp.get('source_bindings')
        if not isinstance(bindings, list) or not bindings:
            raise ValueError('Missing component source bindings')
        arabic, translated = [], []
        for binding in bindings:
            row, text = _binding(binding, sources)
            version_id = str(row['id'])
            ranges[version_id].append((binding['start_codepoint'], binding['end_codepoint']))
            if version_id == case['target_version_id']:
                arabic.append(text)
            elif row['language'] == case['language']:
                translated.append(text)
        if not arabic and not (kind == 'notes' and translated):
            raise ValueError('Each component must identify its target Arabic range')
        reviews = comp.get('reviews', [])
        if not isinstance(reviews, list):
            raise ValueError('Invalid component review list')
        decisions = {}
        for review in reviews:
            _review(review)
            dimension = review.get('dimension')
            if dimension not in (*REQUIRED_DIMENSIONS, 'reuse_context') or dimension in decisions:
                raise ValueError('Unknown or duplicate component review dimension')
            decisions[dimension] = review['outcome']
        approved = all(decisions.get(d) == 'pass' for d in REQUIRED_DIMENSIONS)
        bibliography = comp.get('bibliography', {})
        bib_status = bibliography.get('status')
        if bib_status not in ('verified', 'unverified', 'unknown', 'not_applicable'):
            raise ValueError('Invalid component bibliography status')
        origin = comp.get('origin')
        if origin not in ('published_translation', 'assistant_translation', 'reused_rendering', 'unresolved'):
            raise ValueError('Invalid translation origin')
        text = comp.get('translation_text')
        bib_ok = False
        if origin == 'published_translation':
            _text(text, 'published translation')
            if text != ''.join(translated):
                raise ValueError('Published translation differs from its immutable source ranges')
            if bib_status == 'verified':
                for field in ('translator', 'publisher', 'edition'):
                    _text(bibliography.get(field), 'verified bibliography ' + field)
                _refs(bibliography.get('sources'))
                bib_ok = True
        elif origin == 'assistant_translation':
            _text(text, 'assistant translation')
            search = comp.get('source_search', {})
            _text(search.get('missing_scope'), 'checked-source gap description')
            _refs(search.get('sources'))
            if search.get('status') not in ('not_found_in_checked_sources', 'partial_support', 'candidate_unverified', 'candidate_inaccessible', 'unknown'):
                raise ValueError('Invalid checked-source search result')
            bib_ok = bib_status == 'not_applicable' and bool(bibliography.get('rationale'))
            if search['status'] not in ('not_found_in_checked_sources', 'partial_support'):
                blockers.append(f'{kind}:{ordinal}:turkish_source_search_pending')
        elif origin == 'reused_rendering':
            previous_case, previous = _find_reuse(conn, comp.get('reuses_component_id'))
            if previous_case['segmentation_version'] != case['segmentation_version']:
                raise ValueError('Segmentation version differs for reused translation')
            source_head = conn.execute('SELECT id FROM hadith_component_sets s WHERE target_version_id=%s AND language=%s '
                                       'AND NOT EXISTS(SELECT 1 FROM hadith_component_sets n WHERE n.supersedes_id=s.id)',
                                       (previous_case['target_version_id'], previous_case['language'])).fetchone()
            if source_head is None or str(source_head['id']) not in (_identity(previous_case), identity, *stack):
                raise ValueError('Superseded translation requires a fresh reuse decision against the current version')
            previous_report = _assess_case(conn, sources, previous_case, (*stack, identity))
            previous_id = comp['reuses_component_id']
            previous_item = next(i for i in previous_report['items'] if i['id'] == previous_id)
            if not previous_item['reusable']:
                raise ValueError('Previous component is not eligible for reviewed reuse')
            if (previous_item['status'] != 'source_compared' or previous_item['arabic_text'] != ''.join(arabic)
                    or previous['kind'] != kind or previous['translation_text'] != text or previous_case['language'] != case['language']
                    or previous.get('bibliography') != bibliography):
                raise ValueError('Reused component text, scope, language or provenance differs')
            bib_ok = previous_item['bibliography_ok']
            if decisions.get('reuse_context') != 'pass':
                blockers.append(f'{kind}:{ordinal}:reuse_context_pending')
        else:
            if approved:
                raise ValueError('Unresolved translation cannot carry complete meaning approval')
            blockers.append(f'{kind}:{ordinal}:translation_unresolved')
        if not approved:
            blockers.append(f'{kind}:{ordinal}:source_comparison_pending')
        if not bib_ok:
            blockers.append(f'{kind}:{ordinal}:bibliography_pending')
        if kind == 'unclassified':
            blockers.append('unclassified_source_part')
        sanad_ids = comp.get('source_sanad_ids', [])
        if not isinstance(sanad_ids, list) or any(type(i) is not int or i not in {s['sanad_id'] for s in sanads} for i in sanad_ids):
            raise ValueError('Component refers to a different source sanad')
        if kind == 'isnad':
            sanad_coverage.update(sanad_ids)
        status = 'problem_detected' if 'fail' in decisions.values() else 'source_compared' if approved else 'needs_review'
        items.append({**deepcopy(comp), 'id': str(stable_id('hadith-component-v1', identity, kind, ordinal)),
                      'arabic_text': ''.join(arabic), 'status': status,
                      'bibliography_ok': bib_ok, 'expert_reviewed': False,
                      'reusable': approved and bib_ok and kind != 'unclassified'
                          and not any(b.startswith(f'{kind}:{ordinal}:') for b in blockers)})
    if case['target_version_id'] not in ranges:
        blockers.append('target_source_not_covered')
    for version_id, spans in ranges.items():
        position = 0
        for start, end in sorted(spans):
            if start < position:
                raise ValueError('Overlapping component source ranges')
            if start > position:
                blockers.append('source_coverage_gap:' + version_id)
            position = end
        if position != len(sources.version(version_id)['display_text']):
            blockers.append('source_coverage_gap:' + version_id)
    if sanad_coverage != {s['sanad_id'] for s in sanads}:
        blockers.append('missing_sanad_coverage')
    coverage = {}
    for kind in ('matn', 'isnad', 'notes'):
        group = [i for i in items if i['kind'] == kind]
        if group:
            coverage[kind] = ('problem_detected' if any(i['status'] == 'problem_detected' for i in group)
                              else 'source_compared' if all(i['status'] == 'source_compared' for i in group) else 'needs_review')
        elif kind in ('isnad', 'notes'):
            decision = case.get(kind + '_absence_review')
            if decision is not None:
                _review(decision)
            absent = bool(decision and decision['outcome'] == 'not_applicable' and (kind != 'isnad' or not sanads))
            coverage[kind] = 'not_applicable' if absent else 'unknown'
            if not absent:
                blockers.append(kind + '_absence_not_reviewed')
        else:
            coverage[kind] = 'unknown'
            blockers.append('missing_matn')
    return {'available': True, 'set_id': identity, 'items': items, 'coverage': coverage,
            'source_sanads': sanads, 'hadith_core_complete': not blockers, 'blockers': sorted(set(blockers)),
            'language': case['language'], 'bhid': case['bhid'], 'expert_reviewed': False}


def validate_component_case(working, settings, case: dict) -> dict:
    with working.connection() as conn:
        return _assess_case(conn, _Sources(conn, settings), case)


def load_component_batch(working, settings, *, data: dict) -> dict:
    if (not isinstance(data, dict) or data.get('schema_version') != 'hadith-components-v1'
            or data.get('actor_kind') != 'assistant_source_review'
            or not isinstance(data.get('cases'), list) or not data['cases']):
        raise ValueError('Invalid component batch or actor')
    inserted, unchanged, seen = 0, 0, set()
    with working.connection() as conn:
        conn.execute('LOCK TABLE hadith_component_sets IN SHARE ROW EXCLUSIVE MODE')
        sources = _Sources(conn, settings)
        for case in data['cases']:
            if case.get('language') != data.get('language'):
                raise ValueError('Batch language differs from component case')
            result = _assess_case(conn, sources, case)
            identity = result['set_id']
            if identity in seen:
                raise ValueError('Duplicate component case in batch')
            seen.add(identity)
            existing = conn.execute('SELECT payload FROM hadith_component_sets WHERE id=%s', (identity,)).fetchone()
            if existing:
                if existing['payload'] != case:
                    raise ValueError('Component identity payload differs')
                unchanged += 1
                continue
            parent = case.get('supersedes_id')
            head = conn.execute('SELECT id FROM hadith_component_sets s WHERE target_version_id=%s AND language=%s '
                                'AND NOT EXISTS(SELECT 1 FROM hadith_component_sets n WHERE n.supersedes_id=s.id)',
                                (case['target_version_id'], case['language'])).fetchone()
            if (head is None and parent is not None) or (head is not None and str(head['id']) != parent):
                raise ValueError('Correction must reference the current source/language head')
            conn.execute('INSERT INTO hadith_component_sets(id,target_version_id,language,segmentation_version,payload_sha256,payload,supersedes_id) '
                         'VALUES(%s,%s,%s,%s,%s,%s,%s)', (identity, case['target_version_id'], case['language'],
                          case['segmentation_version'], _digest(case), Jsonb(case), parent))
            inserted += 1
    return {'cases': len(data['cases']), 'inserted': inserted, 'unchanged': unchanged}


def component_report(working, settings, bhid: str, language: str = 'tr') -> dict:
    empty = {'available': True, 'items': [], 'coverage': {}, 'hadith_core_complete': False,
             'blockers': ['no_component_review'], 'language': language, 'bhid': bhid}
    with working.connection() as conn:
        rows = conn.execute("SELECT s.payload,s.payload_sha256 FROM hadith_component_sets s "
                            "JOIN text_versions v ON v.id=s.target_version_id JOIN text_units u ON u.id=v.unit_id "
                            "WHERE u.namespace='gk45:ar' AND u.source_key=%s AND s.language=%s "
                            "AND NOT EXISTS(SELECT 1 FROM hadith_component_sets n WHERE n.supersedes_id=s.id)", (bhid, language)).fetchall()
        if not rows:
            return empty
        if len(rows) != 1:
            return {**empty, 'blockers': ['multiple_source_versions_require_review']}
        try:
            if _digest(rows[0]['payload']) != rows[0]['payload_sha256']:
                raise ValueError('Stored component payload digest differs')
            return _assess_case(conn, _Sources(conn, settings), rows[0]['payload'])
        except ValueError as error:
            return {**empty, 'blockers': ['source_binding_invalid'], 'binding_error': str(error)}


def component_progress(working, settings, snapshot, bhids=None) -> dict:
    """Count reviewed source units separately from individual compared components."""
    with working.connection() as conn:
        exists = conn.execute("SELECT to_regclass('hadith_component_sets') AS name").fetchone()['name']
        if exists is None:
            return {'fully_compared_targets': 0, 'reviewed_targets': 0, 'components': {}, 'matn_candidate_keys': []}
        rows = conn.execute("SELECT DISTINCT u.source_key FROM hadith_component_sets s "
                            "JOIN text_versions v ON v.id=s.target_version_id JOIN text_units u ON u.id=v.unit_id "
                            "WHERE u.namespace='gk45:ar' AND v.snapshot_id=%s AND s.language='tr' "
                            "AND NOT EXISTS(SELECT 1 FROM hadith_component_sets n WHERE n.supersedes_id=s.id)", (snapshot,)).fetchall()
    selected = set(bhids) if bhids is not None else None
    counts, full, total, matn_candidates = defaultdict(lambda: defaultdict(int)), 0, 0, []
    for row in rows:
        if selected is not None and row['source_key'] not in selected:
            continue
        report = component_report(working, settings, row['source_key'])
        total += 1
        full += bool(report['hadith_core_complete'])
        if any(i['kind'] in ('matn', 'unclassified') and i.get('translation_text') for i in report['items']):
            matn_candidates.append(row['source_key'])
        for item in report['items']:
            counts[item['kind']][item['status']] += 1
        counts['bibliography']['verified_components'] += sum(i['bibliography_ok'] for i in report['items'])
        counts['bibliography']['pending_components'] += sum(not i['bibliography_ok'] for i in report['items'])
    return {'fully_compared_targets': full, 'reviewed_targets': total,
            'components': {k: dict(v) for k, v in counts.items()}, 'matn_candidate_keys': sorted(matn_candidates)}
