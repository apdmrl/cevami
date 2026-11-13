import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets,load_field_review_batches
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,opinion_record,opinion_key,record_digest,load_localization_pilot
FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(n):return json.loads((FOLDER/n).read_text(encoding='utf-8'))
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v24.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-sakik-seleme-tr-v1.json')['narrators'][0]['opinions']}

def test_seven_fields_keep_muhadram_generation_distinct_from_reliability_and_numeric_dates():
    f=fields();assert len(f)==7 and all(e['status']=='source_compared' for e in f.values())
    assert f['name']['text']=='Şakīk b. Seleme.' and f['konya']['text']=='Ebû Vâil.' and f['baladekama']['text']=='Kûfe.'
    assert 'muhadram' in f['wasf_rotba']['text'].lower() and 'müslüman olarak göremeyen' in f['wasf_rotba']['text']
    assert 'sika' not in f['wasf_rotba']['text'].lower() and 'derecesi değildir' in f['wasf_rotba']['rationale']
    support=[e['translation_provenance']['turkish_availability'] for e in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[6,1,0]
    raw=read('narrator-field-reviews-tr-v24.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'])==('1','82',81)
    assert not any(e.get('supersedes_id') for e in f.values())

def test_ten_complete_opinions_preserve_negations_both_books_and_lexical_witness_difference():
    e=opinions();assert len(e)==10 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'1268'}
    assert all(x in e['2821']['text'] for x in ('Sikadır','güvenilirliği','sorulmasına gerek yoktur'))
    assert 'onun gibisi bulunmaz' not in e['2821']['text'] and 'onun gibisi bulunmaz' in e['2821']['rationale']
    assert all(x in e['1125']['text'] for x in ('et-Târîhu’l-kebîr','dönemine yetişti','hiçbir şey işitmedi'))
    assert all(x in e['1268']['text'].lower() for x in ('el-kâşif','amel ehlinin','tezhîb','tâbiînin','görmedi'))
    assert 'من كبار العاملين' in e['1268']['expected_source']['opinion'] and 'من العلماء العاملين' in e['1268']['rationale']
    assert e['1268']['translation_provenance']['translation_origin']=='assistant_reviewed_translation'
    assert e['429']['text']=='Tedlîs yapmazdı.' and 'bütün' in e['429']['rationale'] and '319' in e['429']['rationale']
    assert all(x in e['431']['text'] for x in ('es-Sikât','dönemine yetişti','sahâbîliği yoktur'))
    assert 'ittifak' in e['1051']['text'] and e['779']['text']=='Sâlih bir kimsedir.'
    assert e['1051']['translation_provenance']['turkish_availability']==e['779']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[0,7,3]

def test_seventeen_complete_source_pairs_api_provenance_and_repeat_identity(environment):
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v24.json');ob=read('opinions-sakik-seleme-tr-v1.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=7)
    assert _load_files(store,settings,['opinions-sakik-seleme-tr-v1.json'])==dict(narrators=1,opinion_claims=10,critic_claims=0,batches=1)
    load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    reader=SourceReader(settings);raw=reader.narrator_records([3825])['3825'];p=fb['people'][0]
    assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/3825').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/3825/opinions?limit=100').json();assert page['total']==len(page['items'])==10
    live={opinion_key(r):r for row in reader.critic_opinions(3825,100)['items'] if (r:=opinion_record(3825,row))}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        assert row['localization']['fields']['critic'][0]['status']=='source_compared'
        if e['status']=='problem_detected':assert row['localization']['complete'] is False
    assert len(pairs)==17 and profile['localization']['complete'] is False and 'critic_opinions' in profile['localization']['pending_fields']
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT source_record,source_record_sha256,supersedes_id FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record) and bound['supersedes_id'] is None
    for b in (fb,ob):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-sakik-seleme-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}

def test_whole_field_registry_keeps_old_pilot_successors_and_seven_new_fields(environment):
    new=read('narrator-field-reviews-tr-v24.json');settings,store,_=environment;load_localization_pilot(store,settings)
    datasets=[read(n) for n in read("field-review-batches.json")["files"][:24]]; result={"batches":len(datasets),**_load_datasets(store,settings,datasets)};assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(24,102,933,955)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/3825').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1 and claims[0]['text']==e['text']
    adem=api.get('/api/narrator/2').json()
    with store.connection() as c:
        for field,parent in {'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}.items():
            claims=adem['localization']['fields'][field];assert len(claims)==1
            row=c.execute('SELECT supersedes_id FROM localization_claims WHERE id=%s',(claims[0]['id'],)).fetchone();assert str(row['supersedes_id'])==parent
