import json
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import DATA_FOLDER,load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS,record_digest
from hadis_web.source import SourceReader


def test_sixth_batch_keeps_qualifications_disputes_and_arabic_only_evidence_explicit(environment,monkeypatch):
    settings,store,_=environment
    import hadis_web.field_reviews as reviews
    original=reviews._read_batch
    def first_six(filename):
        if filename=='field-review-batches.json':
            return {'revision':'historical-v6','files':[f'narrator-field-reviews-tr-v{i}.json' for i in range(1,7)]}
        return original(filename)
    monkeypatch.setattr(reviews,'_read_batch',first_six)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(6,46,423,426)
    assert load_field_review_batches(store,settings)==result
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v6.json').read_text(encoding='utf-8'))
    assert len(data['people'])==17 and sum(len(p['fields']) for p in data['people'])==167
    records=SourceReader(settings).narrator_records([p['id'] for p in data['people']])
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');states=[]
    for p in data['people']:
        raw=records[str(p['id'])]
        assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f"/api/narrator/{p['id']}").json()
        assert profile['death_year']==raw['death_year'] and profile['localization']['complete'] is False
        for e in p['fields']:
            cl=profile['localization']['fields'][e['field']][0]
            assert profile[e['field']]==e['expected_arabic']
            assert cl['status']==e['status'] and cl['expert_reviewed'] is False
            states.append(cl['status'])
    assert states.count('problem_detected')==4
    for identity,field in [(6508,'mazhab'),(2122,'mazhab'),(6641,'mawaaly'),(7561,'san3a')]:
        p=api.get(f'/api/narrator/{identity}').json()
        assert p['localization']['fields'][field][0]['status']=='problem_detected'
        assert field in p['localization']['pending_fields']
    huseym=api.get('/api/narrator/8062').json()['localization']['fields']['wasf_rotba'][0]
    assert 'çok tedlîs' in huseym['text'] and 'gizli irsâl' in huseym['text']
    muaz=api.get('/api/narrator/7561').json()['localization']['fields']['san3a'][0]
    assert muaz['turkish_availability']=='partial_support' and 'Bağdat' in muaz['rationale']
    assert not any(ref.get('support_scope')=='supports_full_field' for ref in muaz['sources'])
    ibnuleyye=api.get('/api/narrator/1003').json()['localization']['fields']['karaba'][0]
    assert 'kelâmcı' in ibnuleyye['text'] and 'Dımaşk kadısı' in ibnuleyye['text']
    assert api.get('/api/narrator/5680').json()['death_year']=='39'
    for namesake in (12339,53743,9466,21946,15535,46199,29010):
        assert not api.get(f'/api/narrator/{namesake}').json()['localization']['fields'].get('shohra')
