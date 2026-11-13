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
def read(n):return json.loads((FOLDER/n).read_text(encoding='utf-8'))
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v22.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-adem-ebu-iyas-tr-v1.json')['narrators'][0]['opinions']}

def test_nine_places_and_two_vela_records_do_not_become_nine_confirmed_residences():
    f=fields();assert len(f)==11 and all(e['status']=='source_compared' for e in f.values())
    assert 'Abdurrahman b. Muhammed b. Şuayb' in f['name']['text'] and f['badeel']['text']=='Âdem b. Nâhiye.'
    assert f['karaba']['text']=='Ubeyd’in babası.' and f['karaba']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    assert all(x in f['baladekama']['text'] for x in ('Bağdat','Kûfe','Basra','Hicaz','Mısır','Şam','Askalân','Horasan','Merv'))
    assert f['baladekama']['person_fact_support']=='not_independently_confirmed' and f['baladwafa']['text']=='Askalân.'
    assert 'ikamet' in f['baladekama']['rationale'] and all(x in f['mawaaly']['text'] for x in ('Temîm','Teym'))
    s=[e['translation_provenance']['turkish_availability'] for e in f.values()];assert [s.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[5,3,3]
    raw=read('narrator-field-reviews-tr-v22.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'])==('132','220',88)

def test_full_critic_cautions_books_hearing_and_uncertain_six_or_seven_survive():
    e=opinions();assert len(e)==10 and all(v['status']=='source_compared' for v in e.values())
    assert all(x.lower() in e['2821']['text'].lower() for x in ('zayıf','bazen','Suâlâtü Osmân b. Tâlût el-Basrî','Sadûk','sika'))
    assert all(x.lower() in e['429']['text'].lower() for x in ('sadûk','me’mûn','müteabbid','Allah'))
    assert all(x in e['751']['text'] for x in ('altı veya yedi','Şu‘be','zabt')) and 'dört' not in e['751']['text']
    assert all(x in e['2463']['text'] for x in ('Şu‘be','çok','semâ')) and 'Takrîb' in e['1011']['text'] and 'es-Sikât' in e['431']['text']
    assert 'Lâ be’se bih' in e['767']['text']
    s=[v['translation_provenance']['turkish_availability'] for v in e.values()];assert [s.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[0,2,8]
    name=read('critic-name-reviews-tr-v10.json')['critics'][0];assert name['alem_id']=='459' and name['text']=='Ebû Dâvûd es-Sicistânî'
    assert name['expected_source']['rawy_id']=='3567' and name['expected_source']['death_date']=='275' and 'Tayâlisî' in name['rationale']

def test_entire_field_registry_replaces_two_pilot_heads_and_keeps_their_history(environment,monkeypatch):
    import hadis_web.field_reviews as field_reviews
    original=field_reviews._read_batch
    def pinned(name):
        value=original(name)
        if name=='field-review-batches.json':value={**value,'files':value['files'][:22]}
        return value
    monkeypatch.setattr(field_reviews,'_read_batch',pinned)
    from hadis_web.field_reviews import load_field_review_batches
    from hadis_web.localization import load_localization_pilot
    settings,store,_=environment
    load_localization_pilot(store,settings)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(22,100,916,938)
    with store.connection() as c:
        rows=c.execute("SELECT id,field,supersedes_id FROM localization_claims WHERE entity_type='narrator' AND entity_key='2'").fetchall()
    assert len(rows)==13
    parents={e['field']:e['supersedes_id'] for e in fields().values() if e.get('supersedes_id')}
    assert parents=={'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/2').json()
    for field,parent in parents.items():
        live=profile['localization']['fields'][field];assert len(live)==1 and live[0]['id']!=parent
        assert next(r for r in rows if str(r['id'])==live[0]['id'])['supersedes_id'] is not None
    assert load_field_review_batches(store,settings)==result

def test_all_twenty_two_pairs_bind_source_records_and_roundtrip_without_expert_claim(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:10]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v22.json');ob=read('opinions-adem-ebu-iyas-tr-v1.json');nb=read('critic-name-reviews-tr-v10.json')
    _load_datasets(store,settings,[read('narrator-field-reviews-tr-v1.json')])
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=11)
    assert _load_files(store,settings,['opinions-adem-ebu-iyas-tr-v1.json'])==dict(narrators=1,opinion_claims=10,critic_claims=0,batches=1)
    load_critic_names(store,settings);r=load_critic_name_reviews(store,settings);assert (r['batches'],r['critics'],r['claims'],r['claim_versions'])==(10,54,54,54)
    reader=SourceReader(settings);p=fb['people'][0];raw=reader.narrator_records([2])['2'];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/2').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/2/opinions?limit=100').json();assert page['total']==len(page['items'])==10
    live={opinion_key(r):r for row in reader.critic_opinions(2,100)['items'] if (r:=opinion_record(2,row))}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if record['alem_id']=='459':
            n=nb['critics'][0];assert reader.critic_records(['459'])['459']==n['expected_source'];pairs.append((row['localization']['fields']['critic'][0],n,n['expected_source']))
    assert len(pairs)==22 and profile['localization']['complete'] is True
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
    for b in (fb,ob,nb):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-adem-ebu-iyas-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
