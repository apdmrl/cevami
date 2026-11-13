"""Explicit person-by-person assistant comparisons, separate from glossary rules."""
import json
import datetime
import re
import uuid
from pathlib import Path
from .source import SourceReader
from .importer import verify_artifact
from .localization import LocalizationStore, record_digest, claim_identity, NARRATOR_FIELDS
from .working import stable_id

DATA_FOLDER=Path(__file__).parent/'data'
DATA_FILE=DATA_FOLDER/'narrator-field-reviews-tr-v1.json'


def _read_batch(filename):
    if not isinstance(filename,str) or Path(filename).name!=filename or not filename.endswith('.json'):
        raise ValueError('Invalid field review batch filename')
    return json.loads((DATA_FOLDER/filename).read_text(encoding='utf-8'))


def _revision(data):
    value=data.get('revision')
    if not isinstance(value,str) or not value.strip():
        raise ValueError('Missing field review registry revision')
    return value


def _validate_references(refs):
    for ref in refs:
        if any(not isinstance(ref.get(k),str) or not ref[k].strip() for k in ('url','title','locator','accessed_on')):
            raise ValueError('Incomplete field review source reference')
        if not re.match(r'^(https?://|gk45:)',ref['url']):
            raise ValueError('Invalid field review source reference')
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',ref['accessed_on']):raise ValueError()
            datetime.date.fromisoformat(ref['accessed_on'])
        except ValueError:
            raise ValueError('Invalid field review source date') from None


def _validate_history(working,prepared,entity_type='narrator'):
    identities=[str(claim_identity(**args)) for args in prepared]
    if len(set(identities))!=len(identities):raise ValueError('Duplicate field review version')
    proposed=set(identities);parent_ids=list({a['supersedes_id'] for a in prepared if a['supersedes_id']})
    parents={};existing_children={}
    if parent_ids:
        with working.connection() as c:
            parents={str(r['id']):r for r in c.execute('SELECT * FROM localization_claims WHERE id=ANY(%s::uuid[])',(parent_ids,))}
            existing_children={str(r['supersedes_id']):str(r['id']) for r in c.execute(
                'SELECT id,supersedes_id FROM localization_claims WHERE supersedes_id=ANY(%s::uuid[])',(parent_ids,))}
    seen={};heads={};children={}
    for identity,args in zip(identities,prepared):
        binding=(args['entity_key'],args['field']);parent_id=args['supersedes_id']
        expected={'snapshot_id':str(args['snapshot']),'entity_type':entity_type,'entity_key':args['entity_key'],
            'source_record_sha256':record_digest(args['source_record']),'field':args['field'],'language':args['language']}
        if parent_id:
            if parent_id in proposed and parent_id not in seen:
                raise ValueError('Forward field review parent')
            parent=seen.get(parent_id,parents.get(parent_id))
            if parent is None:raise ValueError('Missing field review parent; import original localization first')
            if any(str(parent[k])!=v for k,v in expected.items()) or parent['source_record']!=args['source_record']:
                raise ValueError('Field review parent binding differs')
            if binding in heads and heads[binding]!=parent_id:
                raise ValueError('Correction must follow current field history; competing branch')
            if parent_id in children or existing_children.get(parent_id,identity)!=identity:
                raise ValueError('Existing correction branch differs from reviewed history')
            children[parent_id]=identity
        elif binding in heads:
            raise ValueError('Reviewed source field changed or duplicated')
        seen[identity]={**expected,'source_record':args['source_record']};heads[binding]=identity
    return heads


def _load_datasets(working,settings,datasets):
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    if any(data['source_artifact_sha256']!=manifest['database_sha256'] for data in datasets):
        raise ValueError('Reviewed source snapshot changed')
    verify_artifact(settings.source_db,manifest['database_sha256'])
    project=settings.project_root.resolve()
    for data in datasets:
        for artifact in data.get('review_artifacts',[]):
            relative=Path(artifact['path']);path=(project/relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(project):
                raise ValueError('Invalid review artifact path')
            verify_artifact(path,artifact['sha256'])
    snapshot=stable_id('snapshot','gk45','4.5',manifest['database_sha256'])
    ids={p['id'] for data in datasets for p in data['people']}
    records=SourceReader(settings).narrator_records(sorted(ids));prepared=[]
    for data in datasets:
        if data.get('language','tr')!='tr':raise ValueError('Unexpected field review language')
        batch_ids=[p['id'] for p in data['people']]
        if len(batch_ids)!=len(set(batch_ids)): raise ValueError('Duplicate person in review batch')
        for person in data['people']:
            record=records.get(str(person['id']))
            if record is None or record_digest(record)!=person['expected_record_sha256'] or record!=person['expected_source']:
                raise ValueError('Reviewed source record changed')
            for entry in person['fields']:
                field=entry['field']
                if field not in NARRATOR_FIELDS or not record.get(field) or record.get(field)!=entry['expected_arabic']:
                    raise ValueError('Reviewed source field changed or duplicated')
                parent=entry.get('supersedes_id')
                if 'supersedes_id' in entry:
                    try:parent=str(uuid.UUID(str(parent)))
                    except (ValueError,TypeError):raise ValueError('Invalid field review parent') from None
                if entry['review_scope']!='arabic_field_translation' or entry['status'] not in ('source_compared','problem_detected'):
                    raise ValueError('Unexpected field review scope or outcome')
                if entry['rendering_kind'] not in ('translation','transliteration','name_form'):
                    raise ValueError('Unexpected field review rendering kind')
                if any(not isinstance(entry.get(k),str) or not entry[k].strip() for k in ('text','rationale')):
                    raise ValueError('Empty field review text or rationale')
                refs=[{**data['sources'][key],**scope} for key,scope in entry['source_support'].items()]
                refs.append({'url':f"gk45:narrator:{person['id']}",'title':'Cevâmiu’l-Kelim 4.5 — kişi özelinde okunan Arapça alan',
                    'locator':f"narrators.id={person['id']}; alan={field}; sha256={record_digest(record)}",'accessed_on':data['reviewed_on'],
                    'review_scope':entry['review_scope'],'person_fact_support':entry['person_fact_support'],**entry['translation_provenance']})
                _validate_references(refs)
                arguments=dict(snapshot=snapshot,entity_type='narrator',entity_key=str(record['id']),source_record=record,
                    field=field,language='tr',text=entry['text'],rendering_kind=entry['rendering_kind'],
                    status=entry['status'],actor_kind='assistant_source_review',sources=refs,rationale=entry['rationale'],
                    supersedes_id=parent)
                prepared.append(arguments)
    heads=_validate_history(working,prepared)
    # No claim from an earlier file is written if a later source binding fails.
    snapshot=working.add_snapshot('gk45','4.5',manifest['database_sha256'],'jawami.db')
    local=LocalizationStore(working)
    for arguments in prepared:
        local.add_claim(**arguments)
    result={'people':len(ids),'claims':len(heads)}
    if len(heads)!=len(prepared):result['claim_versions']=len(prepared)
    return result


def load_field_reviews(working,settings):
    data=json.loads(DATA_FILE.read_text(encoding='utf-8'))
    revision=_revision(data)
    return {'revision':revision,**_load_datasets(working,settings,[data])}


def load_field_review_batches(working,settings):
    registry=_read_batch('field-review-batches.json');revision=_revision(registry);files=registry['files']
    if not isinstance(files,list) or not files or any(not isinstance(f,str) for f in files) or len(set(files))!=len(files):
        raise ValueError('Invalid field review batch coverage')
    datasets=[_read_batch(filename) for filename in files]
    return {'revision':revision,'batches':len(datasets),**_load_datasets(working,settings,datasets)}
