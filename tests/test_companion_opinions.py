import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.opinions import load_opinion_batches,load_critic_names
from hadis_web.opinion_reviews import load_opinion_reviews
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.localization import record_digest

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def test_companion_opinions_keep_missing_sentences_and_context_limits():
    data=json.loads((FOLDER/'opinions-companions-tr-v1.json').read_text(encoding='utf8'))
    entries={(p['id'],e['expected_source']['alem_id']):e for p in data['narrators'] for e in p['opinions']}
    assert len(entries)==50 and len(data['narrators'])==11
    assert {k for k,e in entries.items() if e['status']=='problem_detected'}=={(4697,'1011'),(4697,'924'),(4980,'1290'),(4980,'431')}
    assert entries[4980,'1290']['expected_source']['opinion'].endswith('مات') and entries[4980,'1290']['text'].endswith('…')
    assert '63' not in entries[4980,'1290']['text'] and 'Hârre' in entries[4980,'1290']['rationale']
    assert '…' in entries[4980,'431']['text'] and 'on üç' in entries[4980,'431']['text']
    assert 'Medine' in entries[4697,'1011']['rationale'] and 'muhacirler' in entries[4697,'1011']['rationale']
    for word in ('Medineliler','Iraklılar','dışında','işittim'):
        assert word in entries[1733,'2821']['text']
    for word in ('dört','Ebû Mûsâ','Ebû Âmir','Ebû Bürde','Ebû Ruhm','Kays'):
        assert word in entries[5021,'431']['text']
    assert 'yirmi ay' in entries[4697,'1290']['text'] and 'Medine' in entries[4697,'1290']['text']
    assert 'eliyle korudu' in entries[4018,'1290']['text'] and 'defnet' not in entries[4018,'1290']['text']
    for e in entries.values():assert record_digest(e['expected_source'])==e['expected_record_sha256']

def test_fifty_new_opinions_and_original_claims_are_idempotent_and_arabic_bound(environment,monkeypatch):
    from hadis_web import opinions,critic_name_reviews
    original_names=critic_name_reviews._read
    monkeypatch.setattr(critic_name_reviews,'_read',lambda filename:{**original_names(filename),'files':original_names(filename)['files'][:2]} if filename=='critic-name-review-batches.json' else original_names(filename))
    original_read=opinions.read_batch
    monkeypatch.setattr(opinions,'read_batch',lambda filename:{**original_read(filename),'files':original_read(filename)['files'][:6]} if filename=='opinion-batches.json' else original_read(filename))
    settings,store,_=environment
    result=load_opinion_batches(store,settings,include_critic_names=False)
    assert result==dict(narrators=31,opinion_claims=303,critic_claims=0,batches=6)
    load_opinion_reviews(store,settings);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');data=json.loads((FOLDER/'opinions-companions-tr-v1.json').read_text(encoding='utf8'));checked=0
    for p in data['narrators']:
        page=api.get(f"/api/narrator/{p['id']}/opinions?limit=100").json();assert page['total']==len(page['items'])==p['expected_opinion_count']
        expected={e['expected_source']['alem_id']:e for e in p['opinions']}
        for row in page['items']:
            e=expected[str(row['alem_id'])];raw=e['expected_source'];cl=row['localization']['fields']['opinion'];assert len(cl)==1;cl=cl[0]
            assert row['opinion']==raw['opinion'] and row['critic']==raw['critic'] and row['source_occurrences']==raw['source_occurrences']
            assert cl['text']==e['text'] and cl['status']==e['status'] and not cl['expert_reviewed']
            assert ('opinion' in row['localization']['pending_fields'])==(e['status']=='problem_detected')
            assert len(row['localization']['fields']['critic'])==1
            with store.connection() as con:binding=con.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
            assert binding['source_record']==raw and binding['source_record_sha256']==e['expected_record_sha256'];checked+=1
    assert checked==50
    with store.connection() as con:
        before={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')};assert len(before)==511
    assert load_opinion_batches(store,settings,include_critic_names=False)==result
    load_opinion_reviews(store,settings);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as con:assert before=={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')}
