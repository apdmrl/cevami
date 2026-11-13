import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,record_digest,opinion_record,opinion_key
FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v20.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-musnedi-tr-v1.json')['narrators'][0]['opinions']}

def test_vela_and_ancestry_ambiguity_is_not_turned_into_certain_blood_or_slavery():
    f=fields();assert len(f)==11 and {k for k,e in f.items() if e['status']=='problem_detected'}=={'mawaaly','karaba'}
    assert 'Muhammed b. İsmâîl' in f['mawaaly']['text'] and 'mevlâsı' in f['mawaaly']['text']
    assert all(x in f['karaba']['text'] for x in ('Yemân','Ahnes','atalarından'))
    assert 'kan bağı' in f['karaba']['rationale'] and 'köle' in f['mawaaly']['rationale']
    assert f['baladekama']['text']=='Vâsıt; Buhara; Bağdat; Rey.' and f['baladekama']['person_fact_support']=='not_independently_confirmed'
    assert f['baladwafa']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    s=[e['translation_provenance']['turkish_availability'] for e in f.values()]
    assert [s.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[3,5,3]

def test_second_geographical_reading_and_long_son_father_report_preserve_all_clauses():
    e=opinions();assert len(e)==9 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'527'}
    assert 'بلاد السند' in e['527']['expected_source']['opinion'] and 'بما وراء النهر' in e['527']['rationale']
    assert 'İkinci Arapça şahidin' in e['527']['text'] and 'Mâverâünnehir' in e['527']['text']
    assert e['527']['translation_provenance']['translation_origin']=='assistant_source_corrected_rendering'
    assert all(x in e['924']['text'] for x in ('el-Cerh ve’t-ta‘dîl','Babam','Rey','222','İbn Uyeyne','Hişâm b. Yûsuf','Ubeydullah b. Sevr','Hafs b. Gıyâs','Abdurrahman b. Mehdî','Haremî b. Umâre','Vehb b. Cerîr','Züheyr b. Harb','Ebû Dâvûd','Ebû Zür‘a'))
    assert 'et-Târîhu’l-kebîr' in e['1125']['text'] and 'el-Kâşif' in e['1268']['text'] and 'es-Sikât' in e['431']['text']
    s=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [s.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[1,6,2]
    name=read('critic-name-reviews-tr-v8.json')['critics'][0]
    assert name['alem_id']=='677' and name['text']=='İbn Mâkûlâ' and name['expected_source']['rawy_id']=='61970'
    assert '487' in name['rationale'] and '475' in name['rationale']

def test_twenty_one_full_source_pairs_roundtrip_real_api_and_repeat(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:8]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v20.json');ob=read('opinions-musnedi-tr-v1.json');names=read('critic-name-reviews-tr-v8.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=11)
    assert _load_files(store,settings,['opinions-musnedi-tr-v1.json'])==dict(narrators=1,opinion_claims=9,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(8,51,51,51)
    reader=SourceReader(settings);raw=reader.narrator_records([5060])['5060'];p=fb['people'][0];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/5060').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/5060/opinions?limit=100').json();assert page['total']==len(page['items'])==9
    live={opinion_key(r):r for row in reader.critic_opinions(5060,100)['items'] if (r:=opinion_record(5060,row))}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('opinion','critic','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        if record['alem_id']=='677':
            name=names['critics'][0];assert reader.critic_records(['677'])['677']==name['expected_source'];pairs.append((row['localization']['fields']['critic'][0],name,name['expected_source']))
    assert len(pairs)==21
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale']
        assert cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False and all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
    for b in (fb,ob,names):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    assert profile['localization']['complete'] is False
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-musnedi-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
