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
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v25.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-ebu-nuaym-tr-v1.json')['narrators'][0]['opinions']}

def test_fourteen_fields_preserve_father_nickname_long_genealogy_affiliations_and_raw_dates():
    f=fields();assert len(f)==14 and {k for k,v in f.items() if v['status']=='problem_detected'}=={'lakab'}
    assert all(x in f['name']['text'] for x in ('Amr','Hammâd','Züheyr','Dirhem'))
    assert all(x in f['nasab']['text'] for x in ('Kureşî','Teymî','Talhî','Kûfî'))
    assert 'babası Amr' in f['lakab']['text'] and 'Dükeyn' in f['lakab']['text']
    assert 'şehlâ' in f['wasf']['text'] and 'kör' not in f['wasf']['text']
    assert 'Şîa' in f['mazhab']['text'] and 'günümüz' in f['mazhab']['rationale']
    assert all(x in f['mawaaly']['text'] for x in ('Talha b. Ubeydullah','ailesinin','mevlâsı'))
    assert 'Ahmed b. Heysem' in f['karaba']['text'] and 'dedesi' in f['karaba']['text']
    raw=read('narrator-field-reviews-tr-v25.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'])==('','218',None)
    support=[v['translation_provenance']['turkish_availability'] for v in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[8,5,1]

def test_twenty_three_opinions_keep_all_clauses_six_questions_and_unresolved_relative_clause():
    e=opinions();assert len(e)==23 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'239','2507','2769','431','466','769'}
    assert all(x in e['1011']['text'] for x in ('Takrîb','Hedyü’s-sârî','Abdurrahman b. Mehdî','Teşeyyu‘','Nüzhetü’l-elbâb'))
    assert all(x in e['239']['text'] for x in ('Keşfü’n-nikāb','Ebû Bekir b. Kâmil','köpe','dadısı'))
    assert 'babası' in e['239']['rationale'] and 'Muhammed' in e['2507']['rationale']
    assert 'Yahyâ' in e['2769']['rationale'] and e['2769']['expected_source']['alem_id']=='2769'
    assert all(x in e['431']['text'] for x in ('es-Sikât','ولم يدرك من روى عنه','kesinleştirilemedi'))
    assert 'hocalarına yetişmedi' not in e['431']['text'] and 'özne' in e['431']['rationale'].lower()
    assert 'tedlîs yapardı' in e['769']['text'] and all(x in e['769']['rationale'] for x in ('1130','587','Ebû Cenâb','Şemmûmî'))
    assert all(x in e['2513']['text'] for x in ('Eğer','sika','hüccettir'))
    assert all(x in e['2821']['text'] for x in ('Ebû Nuaym','Affân','İbn Muhriz'))
    assert all(x.casefold() in e['751']['text'].casefold() for x in ('Başka','sadûk','sika','hüccet','Vekî‘'))
    assert 'ittifak' in e['2854']['text']
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[0,12,11]
    names={n['alem_id']:n for n in read('critic-name-reviews-tr-v12.json')['critics']};assert set(names)=={'1279','2067'} and all(n['status']=='source_compared' for n in names.values())
    assert names['1279']['expected_source']['name']=='السخاوي' and names['1279']['text']=='Sehâvî'
    assert names['2067']['expected_source']['rawy_id']=='5551'

def test_thirty_nine_full_source_pairs_real_api_provenance_open_questions_and_stable_repeat_ids(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:12]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v25.json');ob=read('opinions-ebu-nuaym-tr-v1.json');nb=read('critic-name-reviews-tr-v12.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=14)
    assert _load_files(store,settings,['opinions-ebu-nuaym-tr-v1.json'])==dict(narrators=1,opinion_claims=23,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(12,58,58,58)
    reader=SourceReader(settings);raw=reader.narrator_records([1548])['1548'];p=fb['people'][0];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/1548').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/1548/opinions?limit=100').json();assert page['total']==len(page['items'])==23
    live={opinion_key(r):r for row in reader.critic_opinions(1548,100)['items'] if (r:=opinion_record(1548,row))};names={n['alem_id']:n for n in nb['critics']}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if e['status']=='problem_detected':assert row['localization']['complete'] is False
        if record['alem_id'] in names:
            n=names[record['alem_id']];assert reader.critic_records([n['alem_id']])[n['alem_id']]==n['expected_source'];pairs.append((row['localization']['fields']['critic'][0],n,n['expected_source']))
    assert len(pairs)==39 and profile['localization']['complete'] is False and {'lakab','critic_opinions'}<=set(profile['localization']['pending_fields'])
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT source_record,source_record_sha256,supersedes_id FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record) and bound['supersedes_id'] is None
    for b in (fb,ob,nb):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-ebu-nuaym-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}

def test_full_field_registry_retains_prior_explicit_parents_and_all_fourteen_new_heads(environment):
    new=read('narrator-field-reviews-tr-v25.json');settings,store,_=environment;load_localization_pilot(store,settings);datasets=[read(n) for n in read("field-review-batches.json")["files"][:25]]; result={"batches":len(datasets),**_load_datasets(store,settings,datasets)}
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(25,103,947,969)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/1548').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1 and claims[0]['text']==e['text'] and claims[0]['status']==e['status']
    adem=api.get('/api/narrator/2').json()
    with store.connection() as c:
        for field,parent in {'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}.items():
            claims=adem['localization']['fields'][field];assert len(claims)==1
            row=c.execute('SELECT supersedes_id FROM localization_claims WHERE id=%s',(claims[0]['id'],)).fetchone();assert str(row['supersedes_id'])==parent
