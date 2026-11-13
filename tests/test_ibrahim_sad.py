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
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v23.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-ibrahim-sad-tr-v1.json')['narrators'][0]['opinions']}

def test_full_genealogy_mother_sons_grandson_and_distinct_judicial_offices_survive():
    f=fields();assert len(f)==10 and all(e['status']=='source_compared' for e in f.values())
    assert 'Abdurrahman b. Avf' in f['name']['text'] and f['baladekama']['text']=='Bağdat; Medine.' and f['baladwafa']['text']=='Bağdat.'
    assert all(x in f['karaba']['text'] for x in ('Ya‘kūb','Sa‘d','Muhammed b. Abdullah','Emetürrahman','Ahmed b. Sa‘d','dedesi'))
    assert 'Bağdat kadısı' in f['san3a']['text'] and f['san3a']['person_fact_support']=='not_independently_confirmed'
    assert 'babasının' in f['san3a']['rationale'].lower() and 'beytülmâl' in f['san3a']['rationale']
    assert all(x in f['wasf_rotba']['text'].lower() for x in ('sika','hüccet'))
    support=[e['translation_provenance']['turkish_availability'] for e in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[5,4,1]
    raw=read('narrator-field-reviews-tr-v23.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'])==('110','183',73)
    assert not any(e.get('supersedes_id') for e in f.values())

def test_four_attribution_reading_questions_and_two_linked_identity_questions_stay_open():
    e=opinions();assert len(e)==18 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'1268','1657','20','2769'}
    assert all(x in e['1011']['text'] for x in ('Takrîb','Hedyü’s-sârî','Ahmed','Yahyâ')) and 'tanımamıştı' in e['1011']['text'] and 'haber vermedi' not in e['1011']['text']
    assert 'فأداد' in e['1268']['expected_source']['opinion'] and 'فأداه' in e['1268']['rationale']
    assert e['1268']['translation_provenance']['translation_origin']=='assistant_source_corrected_rendering'
    assert all(x in e['1268']['text'] for x in ('er-Ruvâtü’s-sikāt','İkinci Arapça şahidin','İçtihadı','bunda ne var','Mîzân'))
    assert all(x in e['2769']['text'] for x in ('Vekî‘','Ahmed','Bilmiyorum','İbrâhim sikadır')) and 'sika olup olmadığını' not in e['2769']['text']
    assert 'Maîn' in e['1657']['rationale'] and 'Ahmed' in e['1657']['rationale']
    assert all(x in e['20']['rationale'] for x in ('Süleymân','Muhammed'))
    assert 'güçlük çıkarırdı' in e['2463']['text'] and 'Şüyûhu Abdillâh' in e['281']['text'] and 'ed-Duafâ' in e['420']['text'] and 'es-Sikât' in e['431']['text']
    assert all(x in e['62']['text'] for x in ('imam','ihtilâf','haksız','Zührî','sâlih','müstakim'))
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[4,8,6]
    names={n['alem_id']:n for n in read('critic-name-reviews-tr-v11.json')['critics']};assert set(names)=={'20','1657'} and all(n['status']=='problem_detected' for n in names.values())
    assert 'Süleymân' in names['20']['text'] and names['20']['expected_source']['rawy_id'] is None
    assert names['1657']['expected_source']['rawy_id']=='17862' and 'makbul' in names['1657']['rationale'] and 'tabaka3' in names['1657']['rationale']

def test_thirty_full_source_pairs_roundtrip_real_api_with_open_problems_and_stable_ids(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:11]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v23.json');ob=read('opinions-ibrahim-sad-tr-v1.json');nb=read('critic-name-reviews-tr-v11.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=10)
    assert _load_files(store,settings,['opinions-ibrahim-sad-tr-v1.json'])==dict(narrators=1,opinion_claims=18,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(11,56,56,56)
    reader=SourceReader(settings);p=fb['people'][0];raw=reader.narrator_records([823])['823'];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/823').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/823/opinions?limit=100').json();assert page['total']==len(page['items'])==18
    live={opinion_key(r):r for row in reader.critic_opinions(823,100)['items'] if (r:=opinion_record(823,row))};names={n['alem_id']:n for n in nb['critics']}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if e['status']=='problem_detected':assert row['localization']['complete'] is False
        if record['alem_id'] in names:
            n=names[record['alem_id']];assert reader.critic_records([n['alem_id']])[n['alem_id']]==n['expected_source'];pairs.append((row['localization']['fields']['critic'][0],n,n['expected_source']))
    assert len(pairs)==30 and profile['localization']['complete'] is False and 'critic_opinions' in profile['localization']['pending_fields']
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
    for b in (fb,ob,nb):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-ibrahim-sad-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}

def test_whole_field_registry_keeps_prior_pilot_successors_and_all_ten_new_fields(environment):
    new=read('narrator-field-reviews-tr-v23.json')
    settings,store,_=environment;load_localization_pilot(store,settings);datasets=[read(n) for n in read("field-review-batches.json")["files"][:23]]; result={"batches":len(datasets),**_load_datasets(store,settings,datasets)}
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(23,101,926,948)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/823').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1 and claims[0]['text']==e['text'] and claims[0]['status']=='source_compared'
    adem=api.get('/api/narrator/2').json()
    with store.connection() as c:
        for field,parent in {'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}.items():
            claims=adem['localization']['fields'][field];assert len(claims)==1
            row=c.execute('SELECT supersedes_id FROM localization_claims WHERE id=%s',(claims[0]['id'],)).fetchone();assert str(row['supersedes_id'])==parent
