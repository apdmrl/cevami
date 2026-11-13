import json
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import DATA_FOLDER,load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS,record_digest
from hadis_web.source import SourceReader


def test_seventh_batch_preserves_errors_stepfamily_name_variants_and_source_issues(environment,monkeypatch):
    import hadis_web.field_reviews as reviews
    original=reviews._read_batch
    monkeypatch.setattr(reviews,'_read_batch',lambda f: {'revision':'historical-v7',
        'files':[f'narrator-field-reviews-tr-v{i}.json' for i in range(1,8)]} if f=='field-review-batches.json' else original(f))
    settings,store,_=environment
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(7,54,501,504)
    assert load_field_review_batches(store,settings)==result
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v7.json').read_text(encoding='utf-8'))
    assert {p['id'] for p in data['people']}=={3585,8053,5653,8488,6904,927,5792,8350}
    assert sum(len(p['fields']) for p in data['people'])==78
    records=SourceReader(settings).narrator_records([p['id'] for p in data['people']]);api=TestClient(create_app(settings),base_url='http://127.0.0.1')
    for p in data['people']:
        raw=records[str(p['id'])]
        assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {f['field'] for f in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f"/api/narrator/{p['id']}").json()
        assert profile['localization']['complete'] is False and profile['death_year']==raw['death_year']
        for e in p['fields']:
            cl=profile['localization']['fields'][e['field']][0]
            assert profile[e['field']]==e['expected_arabic'] and cl['status']==e['status'] and cl['expert_reviewed'] is False
    tayalisi=api.get('/api/narrator/3585').json()
    assert 'bazı hadislerde hata' in tayalisi['localization']['fields']['wasf_rotba'][0]['text']
    assert tayalisi['death_year']=='203' and '204' in tayalisi['localization']['fields']['shohra'][0]['rationale']
    gunder=api.get('/api/narrator/6904').json()['localization']
    assert 'üvey oğlu' in gunder['fields']['karaba'][0]['text']
    assert 'Ebû Bekir' in gunder['fields']['konya'][0]['text']
    for person,field in [(927,'badeel'),(8488,'mawaaly')]:
        p=api.get(f'/api/narrator/{person}').json()['localization']
        assert p['fields'][field][0]['status']=='problem_detected' and field in p['pending_fields']
    ali=api.get('/api/narrator/5792').json()
    assert ali['baladwafa']=='سر من رأى' and 'Sâmerrâ' in ali['localization']['fields']['baladwafa'][0]['text']
    for other in (8054,53078,24469,36733):
        assert not api.get(f'/api/narrator/{other}').json()['localization']['fields'].get('shohra')
