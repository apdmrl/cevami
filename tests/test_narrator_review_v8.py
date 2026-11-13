import json
import hashlib
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import DATA_FOLDER,load_field_review_batches
from hadis_web.localization import load_localization_pilot,record_digest
from hadis_web.source import SourceReader


def test_eighth_batch_preserves_pilot_parents_source_variants_and_source_limits(environment,monkeypatch):
    import hadis_web.field_reviews as reviews
    original=reviews._read_batch
    monkeypatch.setattr(reviews,'_read_batch',lambda f: {'revision':'historical-v8',
        'files':[f'narrator-field-reviews-tr-v{i}.json' for i in range(1,9)]} if f=='field-review-batches.json' else original(f))
    settings,store,_=environment;load_localization_pilot(store,settings)
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(8,61,531,534)
    assert load_field_review_batches(store,settings)==result
    load_localization_pilot(store,settings)
    with store.connection() as c:
        all_ids={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
        assert len(all_ids)==692 and before<=all_ids
        assert c.execute('SELECT count(*) n FROM localization_claims c WHERE NOT EXISTS(SELECT 1 FROM localization_claims n WHERE n.supersedes_id=c.id)').fetchone()['n']==577
    assert hashlib.sha256((DATA_FOLDER/'narrators-tr-v1.json').read_bytes()).hexdigest()=='775b400beec18a3563ec80bc5c27dddcde0fa577f854ac63b68be04bed2f8df4'
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v8.json').read_text(encoding='utf-8'))
    assert {p['id']:len(p['fields']) for p in data['people']}=={6817:4,4698:3,3443:5,8272:5,6796:4,5719:6,5913:3}
    raw=SourceReader(settings).narrator_records([p['id'] for p in data['people']]);api=TestClient(create_app(settings),base_url='http://127.0.0.1');found={}
    issues={(6817,'name'),(6817,'baladekama'),(8272,'badeel'),(6796,'name'),(6796,'karaba')}
    for p in data['people']:
        record=raw[str(p['id'])];assert record==p['expected_source'] and record_digest(record)==p['expected_record_sha256']
        profile=api.get(f"/api/narrator/{p['id']}").json()
        for entry in p['fields']:
            field=entry['field'];cl=profile['localization']['fields'][field]
            assert len(cl)==1 and cl[0]['text']==entry['text'] and cl[0]['status']==entry['status']
            assert profile[field]==entry['expected_arabic']==record[field] and not cl[0]['expert_reviewed']
            assert (cl[0]['status']=='problem_detected')==((p['id'],field) in issues)
            assert (field in profile['localization']['pending_fields'])==((p['id'],field) in issues)
            found[p['id'],field]=cl[0]
    assert 'dünyanın imamı' in found[6817,'wasf_rotba']['text']
    assert 'en önde geleni' in found[4698,'wasf_rotba']['text']
    assert 'Medînî' in found[8272,'nasab']['text']
    assert 'Mihsan' in found[5719,'name']['text'] and 'Muhsin' not in found[5719,'name']['text']
    assert found[3443,'mawaaly']['turkish_availability']=='candidate_inaccessible'
    assert found[6796,'karaba']['translation_origin']=='assistant_source_corrected_rendering'
    assert 'Siyer' in found[6796,'karaba']['rationale'] and '[b.]' in found[6796,'karaba']['text']
    for field in ('name','karaba'):
        assert found[5913,field]['turkish_availability']=='source_support_found'
        assert any('Musa K. Yılmaz' in ref['title'] for ref in found[5913,field]['sources'])
