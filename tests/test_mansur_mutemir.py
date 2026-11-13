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
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v26.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-mansur-mutemir-tr-v1.json')['narrators'][0]['opinions']}

def test_nine_fields_preserve_ten_part_name_variant_kinship_context_and_dates():
    f=fields();assert len(f)==9 and all(e['status']=='source_compared' for e in f.values())
    assert f['name']['text'].count(' b.')==9 and all(x in f['name']['text'] for x in ('Hureys','Mâlik','Rifâa','Hâris','Süleym'))
    assert f['badeel']['text'].count(' b.')==4 and 'Attâb' in f['badeel']['text']
    assert 'Utbe b. Ferkad' in f['karaba']['text'] and 'baba tarafından kuzeni' in f['karaba']['text'] and 'anne bir kardeşi' in f['karaba']['text']
    assert 'Muhammed b. Ali es-Sülemî' in f['karaba']['text'] and 'günümüz' in f['mazhab']['rationale']
    support=[v['translation_provenance']['turkish_availability'] for v in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[4,4,1]
    raw=read('narrator-field-reviews-tr-v26.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'],raw['e5telat'])==('','132',None,0)

def test_sixteen_opinions_keep_conditions_narrative_layers_and_all_book_clauses():
    e=opinions();assert len(e)==16 and all(v['status']=='source_compared' for v in e.values())
    assert all(x.casefold() in e['751']['text'].casefold() for x in ('İsmâil b. Ebû Hâlid','Meşâyih','indiğinde','ıztırab'))
    assert 'yaşlanınca' not in e['751']['text'] and all(x in e['751']['rationale'] for x in ('Zührî','Mâlik','yaşlılık'))
    assert all(x in e['1708']['rationale'] for x in ('Süfyân','anlatı','doğrudan'))
    assert 'Ali adlı' in e['1675']['rationale'] and 'itibarı yüksektir' in e['2463']['text'] and 'merfû' not in e['2463']['text']
    assert all(x.casefold() in e['429']['text'].casefold() for x in ('Sika','A‘meş','karıştırmaz','tedlîs yapmaz'))
    assert all(x in e['1892']['text'] for x in ('Müştebihü’n-nisbe','Sülemî'))
    assert 'Başka' in e['1843']['text'] and all(x in e['2804']['text'] for x in ('Mücâhid','Başka'))
    assert all(x.casefold() in e['431']['text'].casefold() for x in ('es-Sikât','âbid','teşeyyu‘'))
    assert all(x.casefold() in e['779']['text'].casefold() for x in ('sika','sebt','Kûfe'))
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[0,15,1]
    names={n['alem_id']:n for n in read('critic-name-reviews-tr-v13.json')['critics']};assert set(names)=={'44','1708'} and all(n['status']=='source_compared' for n in names.values())
    assert names['44']['expected_source']['rawy_id']=='890' and names['44']['expected_source']['death_date']=='225'
    assert names['1708']['expected_source']['rawy_id']=='3629' and names['1708']['expected_source']['death_date']=='148'

def test_twenty_seven_complete_source_pairs_api_and_stable_repeat_without_expert_certificate(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:13]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v26.json');ob=read('opinions-mansur-mutemir-tr-v1.json');nb=read('critic-name-reviews-tr-v13.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=9)
    assert _load_files(store,settings,['opinions-mansur-mutemir-tr-v1.json'])==dict(narrators=1,opinion_claims=16,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(13,60,60,60)
    reader=SourceReader(settings);raw=reader.narrator_records([7673])['7673'];p=fb['people'][0];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/7673').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/7673/opinions?limit=100').json();assert page['total']==len(page['items'])==16
    live={opinion_key(r):r for row in reader.critic_opinions(7673,100)['items'] if (r:=opinion_record(7673,row))};names={n['alem_id']:n for n in nb['critics']}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if record['alem_id'] in names:
            n=names[record['alem_id']];assert reader.critic_records([n['alem_id']])[n['alem_id']]==n['expected_source'];pairs.append((row['localization']['fields']['critic'][0],n,n['expected_source']))
    assert len(pairs)==27 and profile['localization']['complete'] is True
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT source_record,source_record_sha256,supersedes_id FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record) and bound['supersedes_id'] is None
    for b in (fb,ob,nb):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-mansur-mutemir-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}

def test_whole_registry_keeps_all_old_pilot_successors_and_nine_new_heads(environment):
    new=read('narrator-field-reviews-tr-v26.json');settings,store,_=environment;load_localization_pilot(store,settings);datasets=[read(n) for n in read("field-review-batches.json")["files"][:26]];result={"batches":len(datasets),**_load_datasets(store,settings,datasets)}
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(26,104,956,978)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/7673').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1 and claims[0]['text']==e['text']
    adem=api.get('/api/narrator/2').json()
    with store.connection() as c:
        for field,parent in {'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}.items():
            claims=adem['localization']['fields'][field];assert len(claims)==1
            row=c.execute('SELECT supersedes_id FROM localization_claims WHERE id=%s',(claims[0]['id'],)).fetchone();assert str(row['supersedes_id'])==parent
