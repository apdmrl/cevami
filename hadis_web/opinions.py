"""Small, reviewed research batches, bound to complete Arabic opinion records."""
import json
from pathlib import Path
from .source import SourceReader
from .localization import LocalizationStore, opinion_record, opinion_key, record_digest
from .importer import verify_artifact
from .field_reviews import _validate_references

DATA_FOLDER=Path(__file__).parent/'data'


def read_batch(filename):
    if Path(filename).name!=filename or not filename.endswith('.json'):
        raise ValueError('Invalid opinion batch filename')
    return json.loads((DATA_FOLDER/filename).read_text(encoding='utf-8'))


def _load_files(working, settings, filenames, critic_names_file=None):
    if not filenames or len(set(filenames))!=len(filenames):
        raise ValueError('Invalid opinion batch coverage')
    datasets=[read_batch(filename) for filename in filenames]
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    names=read_batch(critic_names_file) if critic_names_file else None
    if any(data['source_artifact_sha256']!=manifest['database_sha256'] for data in datasets+([names] if names else [])):
        raise ValueError('Reviewed source snapshot changed; opinion import stopped')
    verify_artifact(settings.source_db,manifest['database_sha256'])
    source=SourceReader(settings)
    name_map={str(entry['alem_id']):entry for entry in names['critics']} if names else {}
    if names and len(name_map)!=len(names['critics']):
        raise ValueError('Duplicate critic identity')
    prepared=[];people=set();seen=set();opinion_count=0;critic_count=0
    for data in datasets:
        for person in data['narrators']:
            rows=[];offset=0
            while True:
                page=source.critic_opinions(person['id'],limit=100,offset=offset)
                if page is None: raise ValueError('Reviewed source person changed')
                rows.extend(page['items']);offset+=len(page['items'])
                if offset>=page['total']: break
                if not page['items']: raise ValueError('Reviewed source opinions changed during paging')
            records={opinion_key(record):record for row in rows if (record:=opinion_record(person['id'],row))}
            if len(records)!=person['expected_opinion_count']:
                raise ValueError('Reviewed source opinion count changed')
            keys=[entry['key'] for entry in person['opinions']]
            if len(keys)!=len(set(keys)) or set(keys)!=set(records) or seen.intersection(keys):
                raise ValueError('Reviewed source opinion changed; incomplete or duplicate batch coverage')
            seen.update(keys);people.add(person['id'])
            for entry in person['opinions']:
                record=records.get(entry['key'])
                if record is None or record_digest(record)!=entry['expected_record_sha256'] or record!=entry['expected_source']:
                    raise ValueError('Reviewed source opinion changed')
                prepared.append((record,entry,'opinion',data));opinion_count+=1
                name=name_map.get(str(record['alem_id']))
                if name:
                    if name['expected_arabic_name']!=record['critic']:
                        raise ValueError('Reviewed source critic identity changed')
                    prepared.append((record,{**name,'key':entry['key'],'expected_record_sha256':entry['expected_record_sha256']},'critic',names))
                    critic_count+=1
    resolved=[]
    for record,entry,field,data in prepared:
        if data.get('language','tr')!='tr':raise ValueError('Unexpected opinion language')
        if 'supersedes_id' in entry:raise ValueError('Opinion corrections must use the review loader')
        if entry['status'] not in ('needs_review','source_compared','problem_detected'):
            raise ValueError('Unexpected opinion status')
        kind=entry.get('rendering_kind','translation')
        if kind not in (('translation',) if field=='opinion' else ('name_form','translation','transliteration')):
            raise ValueError('Unexpected opinion rendering kind')
        if any(not isinstance(entry.get(k),str) or not entry[k].strip() for k in ('text','rationale')):
            raise ValueError('Empty opinion text or rationale')
        refs=[{**data['sources'][key],**scope} for key,scope in entry['source_support'].items()]
        refs.append({'url':f"gk45:critic_opinion:{entry['key']}",'title':'Cevâmiu’l-Kelim 4.5 — Arapça görüş kaydı',
                     'locator':f"critic_opinions.rawy_id={record['narrator_id']}; alem_id={record['alem_id']}; sha256={entry['expected_record_sha256']}",
                     'accessed_on':data['reviewed_on'],**entry['translation_provenance']})
        _validate_references(refs)
        resolved.append((record,entry,field,refs))
    # Source bindings and all metadata are checked before any snapshot or claim
    # is written; existing immutable payloads retain their original identities.
    snapshot=working.add_snapshot('gk45','4.5',manifest['database_sha256'],'jawami.db')
    local=LocalizationStore(working)
    for record,entry,field,refs in resolved:
        local.add_claim(snapshot=snapshot,entity_type='critic_opinion',entity_key=entry['key'],source_record=record,
                        field=field,language='tr',text=entry['text'],rendering_kind=entry.get('rendering_kind','translation'),status=entry['status'],
                        actor_kind='assistant_source_review',sources=refs,rationale=entry['rationale'])
    return {'narrators':len(people),'opinion_claims':opinion_count,'critic_claims':critic_count,'batches':len(datasets)}


def load_opinion_pilot(working, settings):
    result=_load_files(working,settings,['critic-opinions-tr-v1.json'])
    return {'revision':read_batch('critic-opinions-tr-v1.json')['revision'],
            'narrators':result['narrators'],'claims':result['opinion_claims']}


def load_opinion_batches(working, settings, include_critic_names=True):
    manifest=read_batch('opinion-batches.json')
    return _load_files(working,settings,manifest['files'],
                       manifest.get('critic_names') if include_critic_names else None)


def load_critic_names(working, settings):
    data=read_batch('critic-names-tr-v1.json')
    # The dictionary identifies people, not just spellings. Verify the entire
    # immutable source artifact before binding its full critic records.
    verify_artifact(settings.source_db,data['source_artifact_sha256'])
    ids=[str(entry['alem_id']) for entry in data['critics']]
    if len(set(ids))!=len(ids): raise ValueError('Duplicate critic identity')
    records=SourceReader(settings).critic_records(ids)
    for entry in data['critics']:
        record=records.get(str(entry['alem_id']))
        if not record or record['name']!=entry['expected_arabic_name']:
            raise ValueError('Reviewed source critic identity changed')
    snapshot=working.add_snapshot('gk45','4.5',data['source_artifact_sha256'],'jawami.db')
    local=LocalizationStore(working)
    for entry in data['critics']:
        record=records[str(entry['alem_id'])]
        refs=[{**data['sources'][key],**scope} for key,scope in entry['source_support'].items()]
        refs.append({'url':f"gk45:critic:{entry['alem_id']}",'title':'Cevâmiu’l-Kelim 4.5 — kayıtlı kişi kimliği',
                     'locator':f"critics.alem_id={entry['alem_id']}; sha256={record_digest(record)}",
                     'accessed_on':data['reviewed_on'],**entry['translation_provenance']})
        local.add_claim(snapshot=snapshot,entity_type='critic',entity_key=str(entry['alem_id']),source_record=record,
            field='name',language='tr',text=entry['text'],rendering_kind=entry['rendering_kind'],status=entry['status'],
            actor_kind='assistant_source_review',sources=refs,rationale=entry['rationale'])
    return {'critic_names':len(ids),'pending_critics':len(data.get('pending',[]))}
