import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,opinion_record,opinion_key,record_digest
FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))
def field_batch():return read('narrator-field-reviews-tr-v19.json')
def op_batch():return read('opinions-ubeydullah-utba-tr-v1.json')

def test_short_turkish_biography_does_not_certify_full_genealogy_or_four_brothers():
    b=field_batch();p=b['people'][0];f={e['field']:e for e in p['fields']}
    assert p['id']==5409 and len(f)==9
    assert all(x in f['name']['text'] for x in ('Ubeydullah','Şemh','Mahzûm','Hüzeyl','Mudar'))
    assert f['name']['translation_provenance']['turkish_availability']=='partial_support'
    assert all(x in f['karaba']['text'] for x in ('Abdurrahman','Avn','Hamza','Nâciye'))
    assert 'dede' in f['karaba']['rationale'] and 'dört' in f['karaba']['rationale']
    assert f['karaba']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    assert f['konya']['text']=='Ebû Abdullah.' and f['baladekama']['text']=='Medine.'
    assert f['baladekama']['person_fact_support']=='not_independently_confirmed'
    assert f['baladekama']['source_support']['onuk']['support_scope']=='supports_part_of_field'
    support=[e['translation_provenance']['turkish_availability'] for e in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[3,4,2]
    assert '727–728' in b['sources']['onuk']['locator'] and '98/716' in b['sources']['onuk']['locator']
    assert p['expected_source']['death_year']=='94' and 'death_year' not in f
    for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']

def test_full_nested_opinion_attribution_and_old_critic_identity_remain_visible():
    e={v['expected_source']['alem_id']:v for v in op_batch()['narrators'][0]['opinions']}
    assert len(e)==5 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'466'}
    assert 'Takrîb' in e['1011']['text'] and all(x in e['1011']['text'] for x in ('Sika','fakih','sebt'))
    assert all(x in e['2463']['text'] for x in ('et-Tabakātü’l-kübrâ','Muhammed b. Ömer','şair','çok'))
    assert 'es-Sikât' in e['431']['text'] and e['466']['text']=='Sikadır, me’mûndur, imamdır.'
    assert '375' in e['466']['rationale'] and '9623' in e['466']['rationale'] and 'Ebû Zür‘a' in e['466']['rationale']
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[0,2,3]

def test_all_fourteen_source_bound_pairs_roundtrip_real_api_without_certifying_profile(environment):
    settings,store,_=environment;fields=field_batch();ops=op_batch();reader=SourceReader(settings)
    assert _load_datasets(store,settings,[fields])==dict(people=1,claims=9)
    assert _load_files(store,settings,['opinions-ubeydullah-utba-tr-v1.json'])==dict(narrators=1,opinion_claims=5,critic_claims=0,batches=1)
    load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/5409').json();raw=reader.narrator_records([5409])['5409'];p=fields['people'][0]
    assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/5409/opinions?limit=100').json();assert page['total']==len(page['items'])==5
    live={opinion_key(r):r for row in reader.critic_opinions(5409,100)['items'] if (r:=opinion_record(5409,row))}
    for e in ops['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id'])
        assert all(row[k]==record[k] for k in ('opinion','critic','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
    assert len(pairs)==14
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale']
        assert cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
    assert profile['localization']['complete'] is False and 'critic_opinions' in profile['localization']['pending_fields']
    registry=read('field-review-batches.json');assert registry['files'][18]=='narrator-field-reviews-tr-v19.json'
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fields]);_load_files(store,settings,['opinions-ubeydullah-utba-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
