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
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v27.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-ibrahim-nehai-tr-v1.json')['narrators'][0]['opinions']}

def test_nine_fields_keep_six_part_lineage_one_eye_family_and_original_dates():
    f=fields();assert len(f)==9 and all(e['status']=='source_compared' for e in f.values())
    assert f['name']['text'].count(' b.')==5 and all(x in f['name']['text'] for x in ('Kays','Esved','Amr','Rebîa'))
    assert f['wasf']['text']=='Bir gözü görmeyen.' and 'kör' not in f['wasf']['text']
    assert all(x in f['karaba']['text'] for x in ('Müleyke','Yezîd','Esved','Abdurrahman','kız kardeşi'))
    assert all(x in f['karaba']['rationale'] for x in ('İbn Hibbân','ilişki','eklenmedi'))
    support=[v['translation_provenance']['turkish_availability'] for v in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[8,1,0]
    raw=read('narrator-field-reviews-tr-v27.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'],raw['tadleese'])==('50','96',46,0)


def test_nine_opinions_keep_mursal_qualifications_hearing_negatives_and_mizzi_correction():
    e=opinions();assert len(e)==9 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'1385','466'}
    assert all(x.casefold() in e['1011']['text'].casefold() for x in ('Takrîb','sika','fakih','ancak','çokça','mürsel'))
    assert all(x in e['1425']['text'] for x in ('Ali','yetişmemiştir','Ömer b. Hattâb','munkatıdır','İbn Mes‘ûd','işitmemiştir'))
    assert e['1708']['text']=='Hadis sarrafıdır.' and 'meslek' in e['1708']['rationale']
    assert 'es-Sikât' in e['431']['text'] and 'kitap' in e['431']['rationale']
    assert all(x in e['490']['text'] for x in ('Çokça mürsel','bir grup','sahih saymıştır'))
    assert all(x in e['490']['rationale'] for x in ('Beyhakī','İbn Mes‘ûd','bütün'))
    assert all(x.casefold() in e['779']['text'].casefold() for x in ('Kûfe','müftü','sâlih','fakih','ihtiyatlı','tekellüf'))
    assert all(x.casefold() in e['1268']['text'].casefold() for x in ('fakih','verâ','hayır','şöhret','ilim'))
    assert all(x in e['466']['rationale'] for x in ('375','264','Ahmed'))
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[2,6,1]
    names={n['alem_id']:n for n in read('critic-name-reviews-tr-v14.json')['critics']};assert set(names)=={'1385','1425','490'}
    m=names['1385'];assert m['supersedes_id']=='a0acd767-12c6-56fe-b04f-746a64fabf62' and m['status']=='problem_detected' and m['text']=='Mizzî'
    assert all(x in m['rationale'] for x in ('749','742','Abdurrahman','oğul'))
    assert m['expected_source']['rawy_id']=='51027' and m['expected_source']['death_date']=='749'
    assert names['1425']['expected_source']['rawy_id']=='67444' and names['1425']['expected_source']['death_date']=='807'
    assert names['490']['expected_source']['rawy_id']=='67919' and names['490']['expected_source']['death_date']=='761'


def test_twenty_one_complete_pairs_api_explicit_critic_parent_and_repeat_conservation(environment):
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v27.json');ob=read('opinions-ibrahim-nehai-tr-v1.json');nb=read('critic-name-reviews-tr-v14.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=9)
    assert _load_files(store,settings,['opinions-ibrahim-nehai-tr-v1.json'])==dict(narrators=1,opinion_claims=9,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(14,63,63,63)
    reader=SourceReader(settings);raw=reader.narrator_records([902])['902'];p=fb['people'][0];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/902').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/902/opinions?limit=100').json();assert page['total']==len(page['items'])==9
    live={opinion_key(r):r for row in reader.critic_opinions(902,100)['items'] if (r:=opinion_record(902,row))};names={n['alem_id']:n for n in nb['critics']}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if record['alem_id'] in names:
            n=names[record['alem_id']];assert reader.critic_records([n['alem_id']])[n['alem_id']]==n['expected_source'];pairs.append((row['localization']['fields']['critic'][0],n,n['expected_source']))
    assert len(pairs)==21 and profile['localization']['complete'] is False
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT source_record,source_record_sha256,supersedes_id FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record) and (str(bound['supersedes_id']) if bound['supersedes_id'] else None)==e.get('supersedes_id')
    with store.connection() as c:
        parent=c.execute('SELECT status,source_record FROM localization_claims WHERE id=%s',('a0acd767-12c6-56fe-b04f-746a64fabf62',)).fetchone()
        assert parent['status']=='source_compared' and parent['source_record']==names['1385']['expected_source']
        assert parent['source_record']['death_date']=='749'
    for b in (fb,ob,nb):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-ibrahim-nehai-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}

def test_whole_registry_keeps_all_old_pilot_successors_and_nine_new_heads(environment):
    new=read('narrator-field-reviews-tr-v27.json');settings,store,_=environment;load_localization_pilot(store,settings);datasets=[read(n) for n in read("field-review-batches.json")["files"][:27]];result={"batches":len(datasets),**_load_datasets(store,settings,datasets)}
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(27,105,965,987)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/902').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1 and claims[0]['text']==e['text']
    adem=api.get('/api/narrator/2').json()
    with store.connection() as c:
        for field,parent in {'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}.items():
            claims=adem['localization']['fields'][field];assert len(claims)==1
            row=c.execute('SELECT supersedes_id FROM localization_claims WHERE id=%s',(claims[0]['id'],)).fetchone();assert str(row['supersedes_id'])==parent
