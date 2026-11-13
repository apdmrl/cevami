"""Exact shared vocabulary, visibly distinct from person-specific translations."""
import hashlib
import json
from pathlib import Path
from .localization import LocalizationStore, record_digest
from .working import stable_id

DATA_FILE=Path(__file__).parent/'data/controlled-terms-tr-v1.json'
ALLOWED_FIELDS={'wasf_rotba','baladekama','baladwafa'}
DERIVATION_VERSION='controlled-rendering-v1'


def material():
    raw=DATA_FILE.read_bytes();data=json.loads(raw)
    checksum=hashlib.sha256(raw).hexdigest()
    snapshot=stable_id('snapshot','controlled-vocabulary',data['revision'],checksum)
    records={}
    seen=set()
    for term in data['terms']:
        if term['key'] in records or not term['allowed_fields'] or not set(term['allowed_fields'])<=ALLOWED_FIELDS:
            raise ValueError('Invalid controlled term key or field scope')
        for field in term['allowed_fields']:
            pair=(field,term['value'])
            if pair in seen: raise ValueError('Conflicting controlled term values')
            seen.add(pair)
        records[term['key']]={key:term[key] for key in ('key','value','allowed_fields')}
    return data,checksum,snapshot,records


def load_controlled_terms(working):
    data,checksum,snapshot,records=material()
    actual=working.add_snapshot('controlled-vocabulary',data['revision'],checksum,DATA_FILE.name)
    assert actual==snapshot
    local=LocalizationStore(working)
    for term in data['terms']:
        sources=[{**data['sources'][key],'support_scope':'terminology_only'} for key in term['sources']]
        local.add_claim(snapshot=snapshot,entity_type='controlled_term',entity_key=term['key'],
            source_record=records[term['key']],field='value',language=data['language'],text=term['text'],
            rendering_kind='translation',status=term['status'],actor_kind='assistant_source_review',
            sources=sources,rationale=term['rationale'])
    return {'revision':data['revision'],'terms':len(records),'source_snapshot_id':str(snapshot)}


def apply_controlled_terms(working, source_snapshot, records, localized, language):
    data,checksum,snapshot,terms=material()
    if language!=data['language'] or not records: return localized
    values=LocalizationStore(working).for_records(snapshot,'controlled_term',terms,language)
    lookup={}
    for key,record in terms.items():
        item=values[key];claims=item['fields'].get('value',[])
        if item['conflicting_fields'] or len(claims)!=1 or claims[0]['status']=='problem_detected': continue
        for field in record['allowed_fields']:lookup[(field,record['value'])]=(key,claims[0])
    output={}
    for key,record in records.items():
        previous=localized[key]
        item={**previous,'fields':dict(previous['fields'])}
        for field in ALLOWED_FIELDS:
            if item['fields'].get(field) or not isinstance(record.get(field),str): continue
            match=lookup.get((field,record[field]))
            if not match: continue
            term_key,term=match;source_hash=record_digest(record)
            identity=stable_id(DERIVATION_VERSION,str(source_snapshot),str(key),source_hash,field,term['id'])
            item['fields'][field]=[{**term,'id':str(identity),'derived_from_claim_id':term['id'],
                'status':'needs_review','actor_kind':'automated_check','expert_reviewed':False,
                'derivation_version':DERIVATION_VERSION,
                'translation_origin':'controlled_vocabulary','turkish_availability':'terminology_only',
                'source_binding':{'entity_type':'narrator','entity_key':str(key),'source_snapshot_id':str(source_snapshot),
                                  'source_record_sha256':source_hash,'field':field,'glossary_key':term_key,
                                  'glossary_artifact_sha256':checksum,'glossary_snapshot_id':str(snapshot)},
                'sources':[*term['sources'],{'url':f'gk45:narrator:{key}','title':'Cevâmiu’l-Kelim 4.5 — Arapça alan',
                    'locator':f'narrators.id={key}; alan={field}; kayıt sha256={source_hash}',
                    'accessed_on':data['reviewed_on'],'support_scope':'arabic_source_field'}],
                'rationale':'Tam Arapça alan değeri kaynaklı sözlükle birebir eşleşti. Otomatik terim aktarımıdır; '+
                            'kişiye özel Türkçe biyografi veya yeni ravi hükmü doğrulaması değildir. '+term['rationale']}]
        output[key]=item
    return output


def controlled_term_coverage(working, settings):
    from .source import open_readonly, SourceReader
    data,_,snapshot,records=material()
    localized=LocalizationStore(working).for_records(snapshot,'controlled_term',records,data['language'])
    counts=[];eligible=set()
    with open_readonly(settings.source_db) as c:
        for key,record in records.items():
            item=localized[key];claims=item['fields'].get('value',[])
            if item['conflicting_fields'] or len(claims)!=1 or claims[0]['status']=='problem_detected': continue
            for field in record['allowed_fields']:
                eligible.add((field,record['value']))
                count=c.execute(f'SELECT count(*) FROM narrators WHERE {field}=? AND id NOT IN (30000,30001,30002)',
                                (record['value'],)).fetchone()[0]
                counts.append({'glossary_key':key,'field':field,'matching_source_cells':count})
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    person_snapshot=stable_id('snapshot','gk45','4.5',manifest['database_sha256'])
    with working.connection() as c:
        people=c.execute("SELECT DISTINCT entity_key FROM localization_claims WHERE snapshot_id=%s "
                         "AND entity_type='narrator' AND language=%s AND field=ANY(%s)",
                         (person_snapshot,data['language'],list(ALLOWED_FIELDS))).fetchall()
    people_records=SourceReader(settings).narrator_records([row['entity_key'] for row in people])
    reviews=LocalizationStore(working).for_records(person_snapshot,'narrator',people_records,data['language'])
    compared=explicit=0
    for key,record in people_records.items():
        for field in ALLOWED_FIELDS:
            if (field,record.get(field)) not in eligible or field in reviews[key]['pending_fields']: continue
            claims=reviews[key]['fields'].get(field,[])
            if not claims: continue
            compared+=1
            if any(claim['actor_kind']=='assistant_source_review' and
                   any(ref.get('review_scope')=='arabic_field_translation' for ref in claim['sources']) for claim in claims):
                explicit+=1
    return {'terms_available':len({row['glossary_key'] for row in counts}),
            'potential_matching_cells':sum(row['matching_source_cells'] for row in counts),
            'source_compared_field_cells':compared,'assistant_reviewed_field_cells':explicit,
            'person_specific_reviews_completed':0,'scope':'automatic_terminology_only',
            'counts':counts}
