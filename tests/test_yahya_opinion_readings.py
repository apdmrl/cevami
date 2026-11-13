import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import opinion_record,opinion_key,record_digest

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))


def test_two_witness_readings_remain_problems_with_raw_unchanged_and_no_invented_attribution():
    d=read('opinions-yahya-bukayr-tr-v1.json');entries={e['expected_source']['alem_id']:e for e in d['narrators'][0]['opinions']};assert len(entries)==15
    assert {k for k,e in entries.items() if e['status']=='problem_detected'}=={'1125','1264'}
    assert 'أنقيه' in entries['1125']['expected_source']['opinion'] and 'أتقيه' in entries['1125']['rationale']
    assert 'tarih konusunda' not in entries['1125']['text']
    assert 'في التاريخ' in entries['1125']['text'] and 'kapsamı kesinleştirilmedi' in entries['1125']['text'] and 'ihtiyat' in entries['1125']['text']
    assert 'لا بأس' in entries['1264']['expected_source']['opinion'] and 'sakınca yoktur' in entries['1264']['text']
    assert 'GK’nin atfı' in entries['1264']['text'] and 'Ebû Abdullah b. Bükeyr el-Bağdâdî' in entries['1264']['text'] and 'Suâlât' in entries['1264']['text']
    for key in ('1125','1264'):
        assert entries[key]['translation_provenance']['translation_origin']=='assistant_source_corrected_rendering'
        assert 'sarhi' in entries[key]['source_support'] and 'Asıl' in entries[key]['rationale']
    assert all(x in entries['2821']['text'] for x in ('İbn Muhriz','Ebû Müshir','Osman b. Talût','nasıl','Leys'))
    assert 'Sâcî' not in entries['1627']['text'] and '1627' in entries['1627']['rationale']
    assert 'ihticâc' in entries['429']['text'] and 'yazılır' in entries['429']['text']
    support=[e['translation_provenance']['turkish_availability'] for e in entries.values()]
    assert (support.count('partial_support'),support.count('not_found_in_checked_sources'))==(10,5)
    path=FOLDER.parents[2]/d['review_artifacts'][0]['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==d['review_artifacts'][0]['sha256']
    names=read('critic-name-reviews-tr-v5.json')['critics'];assert len(names)==1 and names[0]['alem_id']=='1796' and names[0]['text']=='İbn Kāni‘'


def test_full_source_opinions_and_critic_bind_real_api_idempotently(environment,monkeypatch):
    from hadis_web import critic_name_reviews
    original=critic_name_reviews._read
    monkeypatch.setattr(critic_name_reviews,'_read',lambda name:{**original(name),'files':original(name)['files'][:5]} if name=='critic-name-review-batches.json' else original(name))
    settings,store,_=environment
    assert _load_files(store,settings,['opinions-yahya-bukayr-tr-v1.json'])==dict(narrators=1,opinion_claims=15,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings)
    assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(5,40,40,40)
    assert 'opinions-yahya-bukayr-tr-v1.json' in read('opinion-batches.json')['files']
    reader=SourceReader(settings);live={opinion_key(r):r for row in reader.critic_opinions(8297,100)['items'] if (r:=opinion_record(8297,row))}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');page=api.get('/api/narrator/8297/opinions?limit=100').json();assert page['total']==len(page['items'])==15
    for e in read('opinions-yahya-bukayr-tr-v1.json')['narrators'][0]['opinions']:
        raw=e['expected_source'];assert live[e['key']]==raw and record_digest(raw)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==raw['alem_id']);cl=row['localization']['fields']['opinion'][0]
        assert row['opinion']==raw['opinion'] and cl['text']==e['text'] and cl['status']==e['status'] and cl['expert_reviewed'] is False
        assert cl['translation_origin']==e['translation_provenance']['translation_origin']
        if raw['alem_id']=='1627':assert row['localization']['fields']['critic'][0]['status']=='problem_detected'
        if raw['alem_id']=='1796':assert row['localization']['fields']['critic'][0]['text']=='İbn Kāni‘'
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_files(store,settings,['opinions-yahya-bukayr-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
