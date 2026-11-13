import json
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import DATA_FOLDER,load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS,record_digest
from hadis_web.source import SourceReader


def test_fifth_batch_keeps_person_identity_date_variants_and_disputed_vela(environment,monkeypatch):
    settings,store,_=environment
    import hadis_web.field_reviews as reviews
    original=reviews._read_batch
    def first_five(filename):
        if filename=='field-review-batches.json':
            return {'revision':'historical-v5','files':[f'narrator-field-reviews-tr-v{i}.json' for i in range(1,6)]}
        return original(filename)
    monkeypatch.setattr(reviews,'_read_batch',first_five)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(5,29,256,259)
    with store.connection() as c:
        before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    assert load_field_review_batches(store,settings)==result
    with store.connection() as c:
        assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v5.json').read_text(encoding='utf-8'))
    assert {p['id'] for p in data['people']}=={6861,6879,4820,6460,8271,5421,8160,4493}
    assert sum(len(p['fields']) for p in data['people'])==73
    records=SourceReader(settings).narrator_records([p['id'] for p in data['people']])
    api=TestClient(create_app(settings),base_url='http://127.0.0.1')
    for p in data['people']:
        raw=records[str(p['id'])]
        assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f"/api/narrator/{p['id']}").json()
        assert profile['localization']['complete'] is False
        for entry in p['fields']:
            field=entry['field'];claims=profile['localization']['fields'][field]
            assert profile[field]==raw[field] and len(claims)==1
            assert claims[0]['status']==entry['status'] and claims[0]['expert_reviewed'] is False
    yahya=api.get('/api/narrator/8271').json()
    vela=yahya['localization']['fields']['mawaaly'][0]
    assert yahya['mawaaly']=='مولى بني تميم' and vela['status']=='problem_detected'
    assert 'reddet' in vela['rationale'] and 'mawaaly' in yahya['localization']['pending_fields']
    assert yahya['localization']['fields']['wasf'][0]['text']=='Şaşı (kaynak nitelemesi).'
    ubeydullah=api.get('/api/narrator/5421').json()
    assert ubeydullah['death_year']=='143'
    assert '147' in ubeydullah['localization']['fields']['shohra'][0]['rationale']
    veki=api.get('/api/narrator/8160').json()
    assert veki['death_year']=='196' and '197' in veki['localization']['fields']['baladwafa'][0]['rationale']
    kilabe=api.get('/api/narrator/4820').json()
    assert kilabe['konya']=='أبو قلابة ، أبو كلابة'
    assert 'ك' in kilabe['localization']['fields']['konya'][0]['text']
    assert 'Âmir' in kilabe['localization']['fields']['badeel'][0]['text']
    for other in (30059,28764,26737,5422):
        namesake=api.get(f'/api/narrator/{other}').json()
        assert not namesake['localization']['fields'].get('shohra')
    assert api.get('/api/narrator/720').json()['localization']['fields']['lakab'][0]['translation_origin']=='assistant_source_corrected_rendering'
