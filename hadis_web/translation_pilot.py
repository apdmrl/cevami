"""Read-only, reproducible work inventory. Technical flags never approve a text."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from psycopg import sql

from .importer import verify_artifact
from .hadith_components import component_progress
from .source import STRUCTURAL_IDS, arabic_content, open_readonly
from .working import stable_id, text_identity


STATE_TABLES = ('source_snapshots', 'text_units', 'text_versions', 'text_segments',
                'alignment_cases', 'alignment_revisions', 'alignment_members',
                'comparison_evidence', 'review_events', 'narrator_records',
                'sanad_records', 'sanad_members', 'localization_claims')


def select_pilot_bhids(source_db: Path, book_id: str = '146', limit: int = 1000) -> list[str]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
        raise ValueError('Pilot limit must be between 1 and 10000')
    if not re.fullmatch(r'\d+', book_id):
        raise ValueError('Invalid book identifier')
    with open_readonly(source_db) as conn:
        return [row['bhid'] for row in conn.execute(
            'SELECT bhid FROM hadith_text WHERE book_id=? ORDER BY hadith_num,bhid LIMIT ?',
            (book_id, limit))]


def working_state(working) -> dict:
    """Full-row conservation fingerprints, not a public content-authenticity signature."""
    result = {}
    with working.connection() as conn:
        for table in STATE_TABLES:
            query = sql.SQL("SELECT count(*) AS count, md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS content_md5 "
                            "FROM (SELECT md5(to_jsonb(t)::text) AS h FROM {} t) rows").format(sql.Identifier(table))
            result[table] = dict(conn.execute(query).fetchone())
    return result


def _read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def build_pilot_inventory(working, settings, *, limit: int = 1000) -> dict:
    manifest = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text(encoding='utf-8'))
    verify_artifact(settings.source_db, manifest['database_sha256'])
    snapshot = stable_id('snapshot', 'gk45', '4.5', manifest['database_sha256'])
    selected = select_pilot_bhids(settings.source_db, limit=limit)
    selection = {'algorithm': 'existing-bukhari-numeric-order-v1', 'book_id': '146',
                 'source_snapshot_id': str(snapshot), 'source_sha256': manifest['database_sha256'],
                 'requested_limit': limit, 'bhids': selected}
    selection['selection_sha256'] = hashlib.sha256(json.dumps(selection, ensure_ascii=False, sort_keys=True,
                                                            separators=(',', ':')).encode()).hexdigest()
    targets = {}
    chains = defaultdict(list)
    with open_readonly(settings.source_db) as conn:
        for row in conn.execute('SELECT * FROM hadith_text WHERE book_id=? ORDER BY hadith_num,bhid', ('146',)):
            if row['bhid'] in set(selected):
                targets[row['bhid']] = dict(row)
        for row in conn.execute('SELECT * FROM sanad WHERE bhid IN (SELECT bhid FROM hadith_text WHERE book_id=?) ORDER BY sanad_id', ('146',)):
            if row['bhid'] in targets:
                chains[row['bhid']].append(dict(row))
    candidates = defaultdict(dict)
    with working.connection() as conn:
        rows = conn.execute("SELECT u.source_key,r.id AS revision_id,v.id AS version_id,"
                            "v.raw_sha256,tr.raw_sha256 AS translation_sha256,e.evidence "
                            "FROM alignment_members m JOIN text_versions v ON v.id=m.text_version_id "
                            "JOIN text_units u ON u.id=v.unit_id JOIN alignment_revisions r ON r.id=m.revision_id "
                            "JOIN alignment_members tm ON tm.revision_id=r.id AND tm.role='translation' "
                            "JOIN text_versions tr ON tr.id=tm.text_version_id "
                            "LEFT JOIN comparison_evidence e ON e.revision_id=r.id "
                            "WHERE m.role='target_arabic' AND v.snapshot_id=%s AND u.namespace='gk45:ar' "
                            "AND u.source_key=ANY(%s) AND r.sealed AND tr.language='tr'",
                            (snapshot, selected)).fetchall()
        for row in rows:
            candidates[row['source_key']][str(row['revision_id'])] = row
    comparisons = defaultdict(list)
    comparison_file = settings.project_root / 'research/bukhari-review/candidate-comparisons.jsonl'
    if comparison_file.is_file():
        for line in comparison_file.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['gk_bhid'] in targets:
                comparisons[row['gk_bhid']].append(row)
    summary_path = settings.project_root / 'research/bukhari-review/comparison-summary.json'
    diagnostic = _read_json(summary_path, {}).get('compound_diagnostic', {})
    items = []
    for bhid in selected:
        source = targets[bhid]
        display = arabic_content(source['raw_text'])
        _, version, raw_hash = text_identity(snapshot, 'gk45:ar', bhid, source['raw_text'], display['text'])
        current = {key: value for key, value in candidates[bhid].items()
                   if str(value['version_id']) == str(version) and value['raw_sha256'] == raw_hash}
        risks = []
        if not current:
            risks.append('no_candidate')
        if len(current) > 1:
            risks.append('multiple_candidates')
        if diagnostic.get('gk_bhid') == bhid:
            risks.append('possible_split_or_merge')
        tr_hashes = {value['translation_sha256'] for value in current.values()}
        bound_comparisons = [row for row in comparisons[bhid] if row['gk_raw_sha256'] == raw_hash
                             and row['source_turkish_sha256'] in tr_hashes]
        if any(row.get('translation_flags') for row in bound_comparisons):
            risks.append('editorial_or_navigation_text')
        if any(row['arabic_comparison'] == 'equal_concatenated_letters_but_word_boundaries_differ'
               for row in bound_comparisons):
            risks.append('word_boundary_difference')
        ids = {int(value) for chain in chains[bhid] for value in chain['rawy_ids'].split(',')
               if value.strip().isdigit() and int(value) not in STRUCTURAL_IDS}
        ids.update(value for value in display['inline_narrator_ids'] if value not in STRUCTURAL_IDS)
        items.append({'bhid': bhid, 'source_version_id': str(version), 'source_sha256': raw_hash,
                      'candidate_revision_ids': sorted(current), 'risk_flags': risks,
                      'component_coverage': {kind: 'unknown' for kind in ('matn', 'isnad', 'notes')},
                      'bibliography_status': 'unverified' if current else 'unknown',
                      'linked_narrator_ids': sorted(ids), 'source_sanad_ids': [row['sanad_id'] for row in chains[bhid]],
                      'status': 'requires_review'})
    risk_counts = Counter(flag for row in items for flag in row['risk_flags'])
    component_counts = component_progress(working, settings, snapshot, selected)
    return {'selection': selection, 'items': items,
            'summary': {'targets': len(items), 'targets_with_candidates': sum(bool(row['candidate_revision_ids']) for row in items),
                        'candidate_revisions': sum(len(row['candidate_revision_ids']) for row in items),
                        'risk_counts': dict(sorted(risk_counts.items())),
                        'fully_compared_targets': component_counts['fully_compared_targets'],
                        'semantic_assessment_performed': False},
            'existing_corpus_summary': _read_json(settings.project_root / 'research/corpus-review/comparison-summary.json', {}),
            'actor_kind': 'automated_check', 'purpose': 'work_inventory_only'}
