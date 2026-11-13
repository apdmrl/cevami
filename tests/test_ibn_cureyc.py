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
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v21.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-ibn-cureyc-tr-v1.json')['narrators'][0]['opinions']}

def test_full_fields_keep_two_kunyas_own_sons_and_residence_support_bounds():
    f=fields();assert len(f)==11 and all(e['status']=='source_compared' for e in f.values())
    assert all(x in f['konya']['text'] for x in ('Ebü’l-Velîd','Ebû Hâlid'))
    assert all(x in f['karaba']['text'] for x in ('Velîd b. Abdülmelik','Abdülazîz b. Abdülmelik','babası'))
    assert f['baladekama']['text']=='Bağdat.' and f['baladekama']['person_fact_support']=='not_independently_confirmed'
    assert 'dedesi' in f['mawaaly']['rationale'].lower() and 'Ümeyye b. Hâlid' in f['mawaaly']['text']
    assert f['lakab']['translation_provenance']['turkish_availability']=='partial_support'
    s=[e['translation_provenance']['turkish_availability'] for e in f.values()];assert [s.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[7,3,1]
    raw=read('narrator-field-reviews-tr-v21.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'])==('74','150',76)

def test_every_book_and_written_condition_and_negative_remain_in_full_opinions():
    e=opinions();assert len(e)==18
    assert all(x in e['1011']['text'] for x in ('Takrîb','fazilet','tedlîs','irsâl'))
    assert all(x.lower() in e['1264']['text'].lower() for x in ('kaçın','yalnız','cerhedilmiş'))
    assert all(x.lower() in e['2804']['text'].lower() for x in ('emanet','kitabından','yararlanılmaz','yazılı','Nâfi‘'))
    assert all(x in e['2821']['text'] for x in ('beş','Amr b. Dînâr','kitaptan'))
    assert 'Şüyûhu Abdillâh b. Vehb' in e['281']['text']
    assert all(x in e['342']['text'] for x in ('Ma‘rifetü’s-sünen','es-Sünenü’l-kübrâ'))
    assert 'tedlîs' in e['431']['text'] and 'sika' in e['431']['text'].lower()
    assert all(x in e['769']['text'] for x in ('Eğer','bildirmezse','itibar edilmez'))
    assert 'kitaptan' in e['779']['text'] and 'özne' in e['924']['text'].lower() and 'Hepsi' in e['924']['text']

def test_two_corrected_readings_and_eight_open_attributions_do_not_repair_arabic():
    e=opinions();assert {k for k,v in e.items() if v['status']=='problem_detected'}=={'2136','2232','2804','2835','466','751','769','924'}
    assert 'صاحب عطاء' in e['2835']['expected_source']['opinion'] and 'صاحب غثاء' in e['2835']['rationale']
    assert 'çer çöp' in e['2835']['text'].lower() and 'وثبت الناس' in e['751']['expected_source']['opinion']
    assert 'أثبت الناس' in e['751']['rationale'] and 'altı yaşlı kadın' in e['751']['text']
    for key in ('751','2835'):assert e[key]['translation_provenance']['translation_origin']=='assistant_source_corrected_rendering'
    assert 'Yahyâ b. Saîd' in e['2136']['text'] and 'ortak özne' in e['2232']['rationale']
    assert 'Ensârî' in e['2804']['rationale'] and '375' in e['466']['rationale'] and '9885' in e['769']['rationale']
    assert 'كلهم قال' in e['924']['rationale'] and 'yeniden dizilmiş' in read('opinions-ibn-cureyc-tr-v1.json')['sources']['jarh_pdf']['locator']
    names=read('critic-name-reviews-tr-v9.json')['critics'];assert {n['alem_id'] for n in names}=={'2232','2835'} and all(n['status']=='source_compared' for n in names)
    s=[v['translation_provenance']['turkish_availability'] for v in e.values()];assert [s.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[3,9,6]

def test_all_thirty_one_pairs_bind_complete_source_records_and_repeat_real_api(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:9]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v21.json');ob=read('opinions-ibn-cureyc-tr-v1.json');nb=read('critic-name-reviews-tr-v9.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=11)
    assert _load_files(store,settings,['opinions-ibn-cureyc-tr-v1.json'])==dict(narrators=1,opinion_claims=18,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(9,53,53,53)
    reader=SourceReader(settings);p=fb['people'][0];raw=reader.narrator_records([5223])['5223'];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/5223').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/5223/opinions?limit=100').json();assert page['total']==len(page['items'])==18
    live={opinion_key(r):r for row in reader.critic_opinions(5223,100)['items'] if (r:=opinion_record(5223,row))};names={e['alem_id']:e for e in nb['critics']};checked=set()
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if record['alem_id'] in names:
            n=names[record['alem_id']];assert reader.critic_records([record['alem_id']])[record['alem_id']]==n['expected_source'];pairs.append((row['localization']['fields']['critic'][0],n,n['expected_source']));checked.add(record['alem_id'])
    assert len(pairs)==31 and checked==set(names) and profile['localization']['complete'] is False
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
    for b in (fb,ob,nb):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-ibn-cureyc-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
