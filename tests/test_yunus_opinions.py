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
def entries():return {e['expected_source']['alem_id']:e for e in read('opinions-yunus-yazid-tr-v1.json')['narrators'][0]['opinions']}

def test_hammam_subject_and_multiple_critical_reports_keep_full_scope():
    e=entries();assert len(e)==21 and {k for k,v in e.items() if v['status']=='problem_detected'}=={'2507','466','769'}
    assert 'Hemmâm kitabından Katâde’den' in e['2136']['text']
    assert 'همام همام' in e['2136']['rationale'] and 'İbn Muharriz' in e['2136']['rationale']
    assert all(x.lower() in e['1011']['text'].lower() for x in ('Tehzîb','Hedyü’s-sârî','ezberinden','kitabından','hafızasında'))
    assert all(x in e['751']['text'] for x in ('bilmezdi','çok hata','münker','Sikadır'))
    assert e['2671']['text'].endswith('Bundan ne çıkar?') and 'Şüyûhu Abdillâh b. Vehb' in e['281']['text']
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[3,7,11]

def test_namesakes_are_not_silently_merged_and_linked_full_records_are_pinned():
    e=entries();names={x['alem_id']:x for x in read('critic-name-reviews-tr-v6.json')['critics']}
    assert set(names)=={'1121','1935','2545','2769','281','769'}
    assert {k for k,v in names.items() if v['status']=='problem_detected'}=={'2545','769'}
    assert '2507' in e['2507']['rationale'] and '1935' in e['2507']['rationale']
    assert e['2507']['expected_source']['critic']=='محمد بن عبد الله بن المبارك'
    assert names['1935']['expected_source']['name']=='عبد الله بن المبارك بن واضح'
    assert names['769']['expected_source']['rawy_id']=='9885'
    assert 'الشمومي' in names['769']['rationale'] and '441' in names['2545']['rationale']
    artifact=next(a for a in read('opinions-yunus-yazid-tr-v1.json')['review_artifacts'] if a['path'].endswith('yunus-related-records.json'))
    p=FOLDER.parents[2]/artifact['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==artifact['sha256']
    evidence=json.loads(p.read_text(encoding='utf-8'));reader=SourceReader(__import__('hadis_web.config',fromlist=['Settings']).Settings.load())
    assert evidence['records']==reader.narrator_records([9885,61450])

def test_all_twenty_seven_source_bound_pairs_roundtrip_idempotently(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:6]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;reader=SourceReader(settings)
    assert _load_files(store,settings,['opinions-yunus-yazid-tr-v1.json'])==dict(narrators=1,opinion_claims=21,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings)
    assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(6,46,46,46)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');page=api.get('/api/narrator/8621/opinions?limit=100').json();assert page['total']==len(page['items'])==21
    live={opinion_key(r):r for row in reader.critic_opinions(8621,100)['items'] if (r:=opinion_record(8621,row))}
    names={e['alem_id']:e for e in read('critic-name-reviews-tr-v6.json')['critics']};checked=set()
    for entry in entries().values():
        raw=entry['expected_source'];assert live[entry['key']]==raw and record_digest(raw)==entry['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==raw['alem_id']);assert row['opinion']==raw['opinion'] and row['critic']==raw['critic'] and row['source_occurrences']==2
        cl=row['localization']['fields']['opinion'][0];assert cl['text']==entry['text'] and cl['status']==entry['status'] and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in entry['translation_provenance'].items())
        for claim,expected,record in [(cl,entry,raw)]+([(row['localization']['fields']['critic'][0],names[raw['alem_id']],names[raw['alem_id']]['expected_source'])] if raw['alem_id'] in names else []):
            assert claim['text']==expected['text'] and claim['status']==expected['status'] and claim['actor_kind']=='assistant_source_review' and claim['expert_reviewed'] is False
            with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(claim['id'],)).fetchone()
            assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
        if raw['alem_id'] in names:checked.add(raw['alem_id'])
    assert checked==set(names) and api.get('/api/narrator/8621').json()['localization']['complete'] is False
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_files(store,settings,['opinions-yunus-yazid-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
