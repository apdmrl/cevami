"""Immutable comparisons of recorded critic names, including collective labels."""
import json
from pathlib import Path
import uuid
from .field_reviews import _revision, _validate_references, _validate_history
from .importer import verify_artifact
from .localization import LocalizationStore, claim_identity, record_digest
from .source import SourceReader
from .working import stable_id

DATA_FOLDER=Path(__file__).parent/'data'


def _read(filename):
    if not isinstance(filename,str) or Path(filename).name!=filename or not filename.endswith('.json'):
        raise ValueError('Invalid critic name review filename')
    return json.loads((DATA_FOLDER/filename).read_text(encoding='utf-8'))


def load_critic_name_reviews(working,settings):
    registry=_read('critic-name-review-batches.json');revision=_revision(registry);files=registry['files']
    if not isinstance(files,list) or not files or any(not isinstance(f,str) for f in files) or len(set(files))!=len(files):
        raise ValueError('Invalid critic name review coverage')
    datasets=[_read(f) for f in files]
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    checksum=manifest['database_sha256']
    if any(d['source_artifact_sha256']!=checksum for d in datasets):raise ValueError('Reviewed source snapshot changed')
    verify_artifact(settings.source_db,checksum)
    snapshot=stable_id('snapshot','gk45','4.5',checksum)
    ids={str(e['alem_id']) for d in datasets for e in d['critics']}
    if not ids:raise ValueError('Empty critic name review coverage')
    records=SourceReader(settings).critic_records(sorted(ids));prepared=[]
    for data in datasets:
        if data.get('language')!='tr':raise ValueError('Unexpected critic name review language')
        keys=[str(e['alem_id']) for e in data['critics']]
        if len(keys)!=len(set(keys)):raise ValueError('Duplicate critic name in batch')
        for entry in data['critics']:
            key=str(entry['alem_id']);record=records.get(key)
            if record is None or record!=entry['expected_source'] or record_digest(record)!=entry['expected_record_sha256']:
                raise ValueError('Reviewed source critic changed')
            if (entry.get('field')!='name' or entry.get('review_scope')!='arabic_critic_name'
                    or entry.get('rendering_kind') not in ('name_form','transliteration','translation')
                    or entry.get('status') not in ('source_compared','problem_detected')):
                raise ValueError('Unexpected critic name review scope or outcome')
            if any(not isinstance(entry.get(k),str) or not entry[k].strip() for k in ('text','rationale')):
                raise ValueError('Empty critic name review text or rationale')
            provenance=entry['translation_provenance']
            if (provenance.get('translation_origin')!='assistant_reviewed_translation'
                    or provenance.get('turkish_availability') not in ('source_support_found','partial_support','not_found_in_checked_sources','candidate_inaccessible')):
                raise ValueError('Unexpected critic name review provenance')
            parent=entry.get('supersedes_id')
            if 'supersedes_id' in entry:
                try:parent=str(uuid.UUID(str(parent)))
                except (ValueError,TypeError):raise ValueError('Invalid critic name review parent') from None
            refs=[{**data['sources'][k],**scope} for k,scope in entry['source_support'].items()]
            refs.append({'url':f'gk45:critic:{key}','title':'Cevâmiu’l-Kelim 4.5 — kayıtlı görüş sahibi adı',
                'locator':f'critics.alem_id={key}; sha256={record_digest(record)}','accessed_on':data['reviewed_on'],
                'review_scope':'arabic_critic_name',**provenance})
            _validate_references(refs)
            prepared.append(dict(snapshot=snapshot,entity_type='critic',entity_key=key,source_record=record,
                field='name',language='tr',text=entry['text'],rendering_kind=entry['rendering_kind'],status=entry['status'],
                actor_kind='assistant_source_review',sources=refs,rationale=entry['rationale'],supersedes_id=parent))
    # A newly introduced name must not silently create a second root beside a
    # pre-existing name claim. Re-importing the exact historical root is safe.
    with working.connection() as c:
        existing={}
        for row in c.execute("SELECT id,entity_key FROM localization_claims WHERE snapshot_id=%s AND entity_type='critic' AND field='name' AND language='tr' AND entity_key=ANY(%s)",(snapshot,list(ids))):
            existing.setdefault(row['entity_key'],set()).add(str(row['id']))
    for args in prepared:
        if not args['supersedes_id'] and existing.get(args['entity_key']) and str(claim_identity(**args)) not in existing[args['entity_key']]:
            raise ValueError('Existing critic name root requires an explicit correction parent')
    heads=_validate_history(working,prepared,entity_type='critic')
    working.add_snapshot('gk45','4.5',checksum,'jawami.db')
    local=LocalizationStore(working)
    for args in prepared:local.add_claim(**args)
    return {'revision':revision,'batches':len(datasets),'critics':len(ids),'claims':len(heads),'claim_versions':len(prepared)}
