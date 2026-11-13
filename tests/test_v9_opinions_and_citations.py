"""Actual source bindings, attribution boundaries and immutable citation revisions."""
import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.opinions import load_opinion_batches,load_critic_names
from hadis_web.opinion_reviews import load_opinion_reviews
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.field_reviews import load_field_review_batches
from hadis_web.localization import load_localization_pilot,record_digest
from hadis_web.source import SourceReader

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(f):return json.loads((FOLDER/f).read_text(encoding='utf8'))

def test_new_data_preserves_ambiguous_names_and_every_exception_before_import():
    data=read('opinions-v9-ravis-tr-v1.json')
    entries={(p['id'],e['expected_source']['alem_id']):e for p in data['narrators'] for e in p['opinions']}
    assert len(entries)==123 and len(data['narrators'])==13
    issues={(4798,'1627'),(5543,'1385'),(5543,'936'),(6123,'340'),(8055,'2772')}
    assert {k for k,e in entries.items() if e['status']=='problem_detected'}==issues
    assert 'Ubeydullah b. Abdullah' in entries[5594,'1047']['text']
    assert 'الحسين' in entries[8055,'2772']['expected_source']['opinion'] and 'Hüseyin' in entries[8055,'2772']['text']
    assert 'Hasan' in entries[8055,'2772']['rationale']
    for word in ('Tebük','Yemen','Allahım','Hasan','Hüseyin','Ömer','Hanefiyye','Osman'):
        assert word in entries[5722,'1290']['text']
    for word in ('Yalancıdır','Belki','hadise','sikadır','rivayet'):
        assert word in entries[8055,'2289']['text']
    assert 'bilinmemektedir' in entries[6123,'1125']['text']
    assert 'hayran' not in entries[8055,'1418']['text'].casefold()
    assert 'tâbiîden' in entries[1239,'2671']['text']
    assert 'ikinci halife' not in entries[4945,'1011']['text']
    assert entries[4798,'1125']['translation_provenance']['turkish_availability']=='source_support_found'
    for e in entries.values():
        assert record_digest(e['expected_source'])==e['expected_record_sha256']
        assert e['translation_provenance']['translation_origin']=='assistant_reviewed_translation'
    names={e['alem_id']:e for e in read('critic-name-reviews-tr-v2.json')['critics']}
    assert len(names)==20 and names['1627']['status']=='problem_detected'
    assert 'Hallâd' in names['1627']['text']
    assert names['2289']['text']=='Mâlik b. Enes' and names['2557']['text']=='Muhammed b. Ömer'
    assert names['2289']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    assert 'Vâkıdî' not in names['2557']['text']

def test_all_new_opinions_and_names_bind_to_actual_arabic_api_idempotently(environment,monkeypatch):
    from hadis_web import opinions,critic_name_reviews
    original_names=critic_name_reviews._read
    monkeypatch.setattr(critic_name_reviews,'_read',lambda filename:{**original_names(filename),'files':original_names(filename)['files'][:2]} if filename=='critic-name-review-batches.json' else original_names(filename))
    original_read=opinions.read_batch
    monkeypatch.setattr(opinions,'read_batch',lambda filename:{**original_read(filename),'files':original_read(filename)['files'][:5]} if filename=='opinion-batches.json' else original_read(filename))
    settings,store,_=environment
    assert load_opinion_batches(store,settings,include_critic_names=False)==dict(narrators=20,opinion_claims=253,critic_claims=0,batches=5)
    load_opinion_reviews(store,settings);load_critic_names(store,settings)
    result=load_critic_name_reviews(store,settings)
    assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(2,33,33,33)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');source=SourceReader(settings);checked_names=set()
    names={e['alem_id']:e for e in read('critic-name-reviews-tr-v2.json')['critics']}
    for p in read('opinions-v9-ravis-tr-v1.json')['narrators']:
        page=api.get(f"/api/narrator/{p['id']}/opinions?limit=100").json()
        assert page['total']==len(page['items'])==p['expected_opinion_count']
        expected={e['expected_source']['alem_id']:e for e in p['opinions']}
        for row in page['items']:
            e=expected[str(row['alem_id'])];raw=e['expected_source'];cl=row['localization']['fields']['opinion']
            assert len(cl)==1;cl=cl[0]
            assert row['opinion']==raw['opinion'] and row['critic']==raw['critic'] and row['source_occurrences']==raw['source_occurrences']
            assert cl['text']==e['text'] and cl['status']==e['status'] and not cl['expert_reviewed']
            with store.connection() as con:
                bound=con.execute('SELECT source_record,source_record_sha256 FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
            assert bound['source_record']==raw and bound['source_record_sha256']==e['expected_record_sha256']
            assert ('opinion' in row['localization']['pending_fields'])==(e['status']=='problem_detected')
            if str(row['alem_id']) in names:
                n=names[str(row['alem_id'])];nc=row['localization']['fields']['critic'];assert len(nc)==1;nc=nc[0]
                assert nc['text']==n['text'] and nc['status']==n['status'] and not nc['expert_reviewed']
                assert nc['source_binding']['entity_type']=='critic' and nc['source_binding']['source_record_sha256']==n['expected_record_sha256']
                checked_names.add(str(row['alem_id']))
    assert checked_names==set(names)
    with store.connection() as con:
        before={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')}
        assert len(before)==461
        assert con.execute("SELECT count(*) n FROM localization_claims x WHERE entity_type='critic' AND NOT EXISTS(SELECT 1 FROM localization_claims y WHERE y.supersedes_id=x.id)").fetchone()['n']==95
    load_opinion_batches(store,settings,include_critic_names=False);load_opinion_reviews(store,settings);load_critic_names(store,settings);assert load_critic_name_reviews(store,settings)==result
    with store.connection() as con:assert before=={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')}

def test_citation_children_preserve_all_arabic_text_and_status_with_single_leaf(environment,monkeypatch):
    from hadis_web import field_reviews
    original_read=field_reviews._read_batch
    monkeypatch.setattr(field_reviews,'_read_batch',lambda filename:{**original_read(filename),'files':original_read(filename)['files'][:10]} if filename=='field-review-batches.json' else original_read(filename))
    settings,store,_=environment;load_localization_pilot(store,settings)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(10,74,656,667)
    data=read('narrator-field-reviews-tr-v10.json');p=data['people'][0];assert p['id']==4049 and len(p['fields'])==8
    old=next(p for p in read('narrator-field-reviews-tr-v9.json')['people'] if p['id']==4049)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/4049').json()
    for e in p['fields']:
        previous=next(v for v in old['fields'] if v['field']==e['field'])
        assert e['text']==previous['text'] and e['status']==previous['status'] and e['expected_arabic']==previous['expected_arabic']
        cl=profile['localization']['fields'][e['field']];assert len(cl)==1;cl=cl[0]
        assert cl['text']==e['text'] and not cl['expert_reviewed']
        ref=next(s for s in cl['sources'] if s['url']=='https://islamansiklopedisi.org.tr/aise')
        assert '201–205' in ref['locator'] and '113Ümmü' not in ref['locator']
        with store.connection() as con:
            parent=con.execute('SELECT * FROM localization_claims WHERE id=%s',(e['supersedes_id'],)).fetchone()
            child=con.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert parent and parent['translated_text']==child['translated_text'] and parent['status']==child['status']
        assert str(child['supersedes_id'])==e['supersedes_id']
    with store.connection() as con:
        before={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')};assert len(before)==825
    assert load_field_review_batches(store,settings)==result
    with store.connection() as con:assert before=={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')}
    assert hashlib.sha256((FOLDER/'narrator-field-reviews-tr-v9.json').read_bytes()).hexdigest()=='c95ff86d131842438e30b99573ca8cf3ed2fdb0cedc9482e589ec409b8aaa1c1'
