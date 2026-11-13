"""Source-bound field translations; a source note is never a full biography."""
import hashlib
import json
from pathlib import Path
from psycopg.types.json import Jsonb
from .working import stable_id

NARRATOR_FIELDS = ('name','shohra','badeel','konya','lakab','san3a','wasf','mazhab',
                   'nasab','wasf_rotba','baladekama','baladwafa','mawaaly','karaba')


def narrator_record(profile):
    return {k:v for k,v in profile.items() if k not in ('source','kind','opinions','opinions_total','opinions_limit','localization')}


def opinion_record(narrator_id, row):
    return {'narrator_id':int(narrator_id), **{field:row[field] for field in
            ('alem_id','critic','opinion','source_occurrences')}}


def opinion_key(record):
    return f"{record['narrator_id']}:{record['alem_id']}:{record_digest({'opinion':record['opinion']})}"


def record_digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(',',':')).encode()).hexdigest()


def empty_localization(record, language='tr', available=True, entity_type='narrator'):
    fields = ('critic','opinion') if entity_type=='critic_opinion' else ('name',) if entity_type=='critic' else ('value',) if entity_type=='controlled_term' else NARRATOR_FIELDS
    required = [field for field in fields if record.get(field)]
    return {'available':available,'language':language,'fields':{},'pending_fields':required,
            'conflicting_fields':[],'complete':False}


def translation_provenance(kind, sources):
    """Reading a source is different from taking a published translation."""
    scopes={ref.get('support_scope') for ref in sources}
    origins={ref['translation_origin'] for ref in sources if ref.get('translation_origin')}
    availability={ref['turkish_availability'] for ref in sources if ref.get('turkish_availability')}
    if kind=='source_summary':
        origin='assistant_source_summary'
    elif len(origins)==1:
        origin=next(iter(origins))
    elif origins:
        origin='unknown'
    elif 'supports_full_field' in scopes:
        origin='source_supported_rendering'
    elif scopes & {'supports_part_of_field','terminology_only','not_found'}:
        origin='assistant_draft'
    else:
        origin='unknown'
    if len(availability)==1:
        found=next(iter(availability))
    elif availability:
        found='unknown'
    elif scopes & {'supports_full_field','source_based_summary'}:
        found='source_support_found'
    elif scopes & {'supports_part_of_field','terminology_only'}:
        found='partial_support'
    elif 'not_found' in scopes:
        found='not_found_in_checked_sources'
    else:
        found='unknown'
    return {'translation_origin':origin,'turkish_availability':found,'verbatim_quote':False}


def merge_critic_name(data, source_name, record, name_data):
    """Reuse one verified identity only when its full Arabic name still matches."""
    if not record or record['name']!=source_name or data['fields'].get('critic') or not name_data['fields'].get('name'):
        return data
    data={**data,'fields':dict(data['fields']),'pending_fields':list(data['pending_fields']),
          'conflicting_fields':list(data['conflicting_fields'])}
    data['fields']['critic']=[{**claim,'source_binding':{'entity_type':'critic','entity_key':str(record['alem_id']),
                             'source_record_sha256':record_digest(record)}} for claim in name_data['fields']['name']]
    if 'name' in name_data['conflicting_fields']: data['conflicting_fields'].append('critic')
    if name_data['complete']: data['pending_fields']=[field for field in data['pending_fields'] if field!='critic']
    data['complete']=not data['pending_fields'] and not data['conflicting_fields']
    return data


def claim_identity(*, snapshot, entity_type, entity_key, source_record, field,
                   language, text, rendering_kind, status, actor_kind, sources,
                   rationale, supersedes_id=None):
    """The original immutable payload identity, shared with import prevalidation."""
    payload=[str(snapshot),entity_type,str(entity_key),source_record,field,language,text,
             rendering_kind,status,actor_kind,sources,rationale,str(supersedes_id) if supersedes_id else None]
    return stable_id('localization',json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))


class LocalizationStore:
    def __init__(self, working):
        self.working = working

    def add_claim(self, *, snapshot, entity_type, entity_key, source_record, field,
                  language, text, rendering_kind, status, actor_kind, sources, rationale,
                  supersedes_id=None):
        if entity_type == 'narrator' and str(source_record.get('id')) != str(entity_key):
            raise ValueError('Source person identity differs')
        if entity_type == 'critic_opinion' and opinion_key(source_record) != str(entity_key):
            raise ValueError('Source opinion identity differs')
        if entity_type == 'critic' and str(source_record.get('alem_id')) != str(entity_key):
            raise ValueError('Source critic identity differs')
        if entity_type == 'controlled_term' and source_record.get('key')!=str(entity_key):
            raise ValueError('Controlled term identity differs')
        identity=claim_identity(snapshot=snapshot,entity_type=entity_type,entity_key=entity_key,
            source_record=source_record,field=field,language=language,text=text,rendering_kind=rendering_kind,
            status=status,actor_kind=actor_kind,sources=sources,rationale=rationale,supersedes_id=supersedes_id)
        with self.working.connection() as c:
            # The trigger validates correction links; avoid re-triggering an
            # already imported correction, while retaining its immutable ID.
            if c.execute('SELECT id FROM localization_claims WHERE id=%s',(identity,)).fetchone():
                return identity
            c.execute('INSERT INTO localization_claims '
                      '(id,snapshot_id,entity_type,entity_key,source_record,source_record_sha256,field,language,translated_text,rendering_kind,status,actor_kind,sources,rationale,supersedes_id) '
                      'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                      (identity,snapshot,entity_type,str(entity_key),Jsonb(source_record),record_digest(source_record),
                       field,language,text,rendering_kind,status,actor_kind,Jsonb(sources),rationale,supersedes_id))
        return identity

    def for_records(self, snapshot, entity_type, records, language):
        result = {key:empty_localization(record,language,entity_type=entity_type) for key,record in records.items()}
        if not records:
            return result
        with self.working.connection() as c:
            rows=c.execute('SELECT cl.* FROM localization_claims cl WHERE snapshot_id=%s AND entity_type=%s '
                           'AND entity_key=ANY(%s) AND language=%s AND NOT EXISTS '
                           '(SELECT 1 FROM localization_claims newer WHERE newer.supersedes_id=cl.id) '
                           'ORDER BY field,created_at,id',(snapshot,entity_type,list(records),language)).fetchall()
        hashes={key:record_digest(record) for key,record in records.items()}
        for row in rows:
            key=row['entity_key']
            if row['source_record_sha256'] != hashes[key]:
                continue
            claim={'id':str(row['id']),'text':row['translated_text'],'rendering_kind':row['rendering_kind'],
                   'status':row['status'],'actor_kind':row['actor_kind'],'sources':row['sources'],
                   'rationale':row['rationale'],'expert_reviewed':row['actor_kind']=='expert_review' and row['status']=='source_compared'}
            claim.update(translation_provenance(row['rendering_kind'],row['sources']))
            result[key]['fields'].setdefault(row['field'],[]).append(claim)
        for data in result.values():
            data['conflicting_fields']=[f for f,claims in data['fields'].items() if len({cl['text'] for cl in claims})>1]
            data['pending_fields']=[f for f in data['pending_fields'] if f in data['conflicting_fields'] or
                                    not data['fields'].get(f) or any(cl['status']!='source_compared' or
                                        cl['rendering_kind']=='source_summary' for cl in data['fields'][f])]
            data['complete']=not data['pending_fields'] and not data['conflicting_fields'] and bool(data['fields'])
        return result


def load_localization_pilot(working, settings):
    from .source import SourceReader
    folder=Path(__file__).parent/'data'
    data=json.loads((folder/'narrators-tr-v1.json').read_text(encoding='utf-8'))
    datasets=[]
    for name in data.get('history_files',[]):
        if Path(name).name!=name or not name.endswith('.json'):
            raise ValueError('Invalid localization history filename')
        datasets.append(json.loads((folder/name).read_text(encoding='utf-8')))
    datasets.append(data)
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    if any(manifest['database_sha256'] != version['source_artifact_sha256'] for version in datasets):
        raise ValueError('Reviewed source snapshot changed; localization import stopped')
    snapshot=working.add_snapshot('gk45','4.5',manifest['database_sha256'],'jawami.db')
    source=SourceReader(settings)
    local=LocalizationStore(working)
    # Validate the whole pilot before writing any field claims.
    records={}
    for version in datasets:
        for person in version['narrators']:
            record=narrator_record(source.narrator(person['id']))
            if record_digest(record) != person['expected_record_sha256']:
                raise ValueError(f"Reviewed source record changed for narrator {person['id']}")
            for field,expected in person['expected_source'].items():
                if record.get(field) != expected:
                    raise ValueError(f"Source identity changed for narrator {person['id']}, field {field}")
            records[str(person['id'])]=record
    for version in datasets:
        for person in version['narrators']:
            record=records[str(person['id'])]
            for entry in person['fields']:
                refs=[version['sources'][key] for key in entry['sources']]
                refs.append({'url':f"gk45:narrator:{person['id']}",'title':'Cevâmiu’l-Kelim 4.5',
                             'locator':f"narrators.id={person['id']}; alan={entry['field']}",'accessed_on':version['reviewed_on'],
                             **entry.get('translation_provenance',{})})
                local.add_claim(snapshot=snapshot,entity_type='narrator',entity_key=str(person['id']),
                    source_record=record,field=entry['field'],language='tr',text=entry['text'],
                    rendering_kind=entry['rendering_kind'],status=entry.get('status','source_compared'),
                    actor_kind='assistant_source_review',sources=refs,rationale=entry['rationale'],
                    supersedes_id=entry.get('supersedes_id'))
    return {'narrators':len(records),'pilot_claims':sum(len(p['fields']) for p in data['narrators']),
            'revision':data['revision']}
