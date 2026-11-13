import json,hashlib
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import DATA_FOLDER,load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS,load_localization_pilot,record_digest
from hadis_web.source import SourceReader


def test_ebu_yaman_death_place_and_name_keep_published_turkish_support():
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v9.json').read_text(encoding='utf-8'))
    person=next(p for p in data['people'] if p['id']==1382)
    for field in ('badeel','baladwafa'):
        entry=next(e for e in person['fields'] if e['field']==field)
        assert entry['translation_provenance']['turkish_availability']=='source_support_found'
        assert entry['source_support']['person1382']['support_scope']=='supports_full_field'
        assert 'doğrulanmadı' not in entry['rationale']
    assert '228' in data['sources']['person1382']['locator']


def test_ninth_batch_compares_all_fields_preserves_generation_and_name_issues(environment,monkeypatch):
    from hadis_web import field_reviews
    original=field_reviews._read_batch
    monkeypatch.setattr(field_reviews,'_read_batch',lambda filename:{**original(filename),'files':original(filename)['files'][:9]} if filename=='field-review-batches.json' else original(filename))
    settings,store,_=environment;load_localization_pilot(store,settings)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(9,74,656,659)
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v9.json').read_text(encoding='utf-8'))
    assert {p['id'] for p in data['people']}=={1239,1382,4049,4798,4903,4945,5079,5543,5594,5722,6123,8055,8101}
    assert sum(len(p['fields']) for p in data['people'])==125
    records=SourceReader(settings).narrator_records([p['id'] for p in data['people']]);api=TestClient(create_app(settings),base_url='http://127.0.0.1');claims={}
    problems={(1239,'mawaaly'),(4798,'mawaaly'),(4798,'karaba'),(5079,'name'),(5079,'karaba'),(8055,'karaba')}
    for p in data['people']:
        raw=records[str(p['id'])];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f"/api/narrator/{p['id']}").json()
        for e in p['fields']:
            cl=profile['localization']['fields'][e['field']];assert len(cl)==1
            assert profile[e['field']]==e['expected_arabic']==raw[e['field']]
            assert cl[0]['text']==e['text'] and cl[0]['status']==e['status'] and not cl[0]['expert_reviewed']
            assert (e['status']=='problem_detected')==((p['id'],e['field']) in problems)
            assert (e['field'] in profile['localization']['pending_fields'])==((p['id'],e['field']) in problems)
            assert cl[0]['translation_origin']=='assistant_reviewed_translation'
            claims[p['id'],e['field']]=cl[0]
    assert 'babas' in claims[1239,'mawaaly']['rationale']
    assert 'nesil' in claims[4798,'karaba']['rationale'].casefold()
    assert 'Gāfil' in claims[5079,'name']['rationale'] and 'Gāfil' not in claims[5079,'name']['text']
    assert '[أن يحيى]' in claims[8055,'karaba']['text']
    assert 'Şemmâs' in claims[5543,'lakab']['text'] and 'meslek' in claims[5543,'lakab']['rationale']
    assert claims[8101,'name']['turkish_availability']=='partial_support'
    with store.connection() as c:
        before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')};assert len(before)==817
    assert load_field_review_batches(store,settings)==result
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    assert hashlib.sha256((DATA_FOLDER/'narrator-field-reviews-tr-v8.json').read_bytes()).hexdigest()=='ab30c2e9abf4c6c7cb0bf563d28312e6c981bfa6645a32803f740e9d46c2d52c'
