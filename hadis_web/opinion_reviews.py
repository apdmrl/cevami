"""Append source-bound opinion reviews without replacing the original drafts."""
import datetime
import json
from pathlib import Path
import re
import uuid
from .importer import verify_artifact
from .localization import LocalizationStore, claim_identity, opinion_key, opinion_record, record_digest
from .source import SourceReader
from .working import stable_id

DATA_FOLDER = Path(__file__).parent / 'data'


def _read(filename):
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.json'):
        raise ValueError('Invalid opinion review filename')
    return json.loads((DATA_FOLDER / filename).read_text(encoding='utf-8'))


def _references(data, entry, record):
    refs = [{**data['sources'][key], **scope} for key, scope in entry['source_support'].items()]
    refs.append({'url': f"gk45:critic_opinion:{entry['key']}",
        'title': 'Cevâmiu’l-Kelim 4.5 — Arapça görüşün dil karşılaştırması',
        'locator': f"critic_opinions.rawy_id={record['narrator_id']}; alem_id={record['alem_id']}; sha256={record_digest(record)}",
        'accessed_on': data['reviewed_on'], 'review_scope': entry['review_scope'],
        'attribution_review': 'recorded_source_attribution_only', **entry['translation_provenance']})
    for ref in refs:
        if any(not isinstance(ref.get(k), str) or not ref[k].strip() for k in ('url', 'title', 'locator', 'accessed_on')):
            raise ValueError('Incomplete opinion review source reference')
        if not re.match(r'^(https?://|gk45:)', ref['url']):
            raise ValueError('Invalid opinion review source reference')
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', ref['accessed_on']): raise ValueError()
            datetime.date.fromisoformat(ref['accessed_on'])
        except ValueError:
            raise ValueError('Invalid opinion review source date') from None
    return refs


def load_opinion_reviews(working, settings):
    registry = _read('opinion-review-batches.json')
    revision = registry.get('revision')
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError('Missing opinion review registry revision')
    files = registry['files']
    if not isinstance(files, list) or not files or any(not isinstance(f, str) for f in files) or len(files) != len(set(files)):
        raise ValueError('Invalid opinion review coverage')
    datasets = [_read(f) for f in files]
    manifest = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text())
    if any(d['source_artifact_sha256'] != manifest['database_sha256'] for d in datasets):
        raise ValueError('Reviewed source snapshot changed')
    verify_artifact(settings.source_db, manifest['database_sha256'])
    snapshot = stable_id('snapshot', 'gk45', '4.5', manifest['database_sha256'])
    source = SourceReader(settings); records = {}; prepared = []; identities = set(); people = set()
    for data in datasets:
        if data.get('language') != 'tr': raise ValueError('Unexpected opinion review language')
        person_ids = [p['id'] for p in data['narrators']]
        if len(person_ids) != len(set(person_ids)): raise ValueError('Duplicate opinion review person')
        for person in data['narrators']:
            pid = person['id']; people.add(pid)
            if pid not in records:
                rows = []; offset = 0
                while True:
                    page = source.critic_opinions(pid, limit=100, offset=offset)
                    if page is None: raise ValueError('Reviewed source person changed')
                    rows.extend(page['items']); offset += len(page['items'])
                    if offset >= page['total']: break
                    if not page['items']: raise ValueError('Reviewed opinions changed during paging')
                records[pid] = {opinion_key(r): r for row in rows if (r := opinion_record(pid, row))}
            if len(records[pid]) != person['expected_opinion_count']:
                raise ValueError('Reviewed source opinion count changed')
            keys = [e['key'] for e in person['opinions']]
            if not keys or len(keys) != len(set(keys)): raise ValueError('Duplicate or empty opinion review')
            for entry in person['opinions']:
                record = records[pid].get(entry['key'])
                if record is None or record != entry['expected_source'] or record_digest(record) != entry['expected_record_sha256']:
                    raise ValueError('Reviewed source opinion changed')
                if (entry.get('field') != 'opinion' or entry.get('rendering_kind', 'translation') != 'translation'
                        or entry.get('review_scope') != 'arabic_opinion_translation'
                        or entry['status'] not in ('source_compared', 'problem_detected')):
                    raise ValueError('Unexpected opinion review scope or outcome')
                if any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in ('text', 'rationale')):
                    raise ValueError('Empty opinion review text or rationale')
                provenance = entry['translation_provenance']
                if (provenance.get('translation_origin') != 'assistant_reviewed_translation'
                        or provenance.get('turkish_availability') not in ('source_support_found', 'partial_support', 'not_found_in_checked_sources')):
                    raise ValueError('Unexpected opinion review provenance')
                try: parent = str(uuid.UUID(entry['supersedes_id']))
                except (ValueError, TypeError, KeyError): raise ValueError('Missing or invalid opinion review parent') from None
                args = dict(snapshot=snapshot, entity_type='critic_opinion', entity_key=entry['key'], source_record=record,
                    field='opinion', language='tr', text=entry['text'], rendering_kind='translation', status=entry['status'],
                    actor_kind='assistant_source_review', sources=_references(data, entry, record),
                    rationale=entry['rationale'], supersedes_id=parent)
                identity = str(claim_identity(**args))
                if identity in identities: raise ValueError('Duplicate opinion review version')
                identities.add(identity); prepared.append((identity, args))
    # Check every parent and existing branch before appending any claims. An
    # earlier proposed correction can be a parent; forward references cannot.
    parent_ids = list({a['supersedes_id'] for _, a in prepared})
    if not parent_ids: raise ValueError('Empty opinion review coverage')
    with working.connection() as c:
        parents = {str(r['id']): r for r in c.execute('SELECT * FROM localization_claims WHERE id=ANY(%s::uuid[])', (parent_ids,))}
        existing_children = {str(r['supersedes_id']): str(r['id']) for r in c.execute(
            'SELECT id,supersedes_id FROM localization_claims WHERE supersedes_id=ANY(%s::uuid[])', (parent_ids,))}
    seen = {}; heads = {}; children = {}
    for identity, args in prepared:
        parent_id = args['supersedes_id']; binding = args['entity_key']
        if parent_id in identities and parent_id not in seen:
            raise ValueError('Forward opinion review parent')
        parent = seen.get(parent_id, parents.get(parent_id))
        if parent is None: raise ValueError('Missing opinion review parent; import original opinions first')
        expected = {'snapshot_id': str(snapshot), 'entity_type': 'critic_opinion', 'entity_key': binding,
                    'source_record_sha256': record_digest(args['source_record']), 'field': 'opinion', 'language': 'tr'}
        if any(str(parent[k]) != v for k, v in expected.items()) or parent['source_record'] != args['source_record']:
            raise ValueError('Opinion review parent binding differs')
        if binding in heads and heads[binding] != parent_id:
            raise ValueError('Opinion review must follow current history; competing branch')
        if parent_id in children or existing_children.get(parent_id, identity) != identity:
            raise ValueError('Existing opinion correction branch differs from reviewed history')
        children[parent_id] = identity; heads[binding] = identity
        seen[identity] = {**expected, 'source_record': args['source_record']}
    local = LocalizationStore(working)
    for _, args in prepared: local.add_claim(**args)
    return {'revision': revision, 'batches': len(datasets), 'people': len(people),
            'claims': len(heads), 'claim_versions': len(prepared)}
