import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS, record_digest, load_localization_pilot
from hadis_web.source import SourceReader

FOLDER=Path(__file__).parents[1]/'hadis_web/data'


def test_said_does_not_infer_a_physical_fact_or_merge_death_with_burial():
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v12.json').read_text(encoding='utf-8'))
    assert len(data['people'])==1
    person=data['people'][0];assert person['id']==3331
    fields={e['field']:e for e in person['fields']};assert len(fields)==10
    assert fields['wasf']['expected_arabic']=='الأعور'
    assert fields['wasf']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    assert fields['wasf']['person_fact_support']=='not_independently_confirmed'
    assert 'bağımsız' in fields['wasf']['rationale'] and 'künye' in fields['wasf']['rationale']
    assert fields['baladwafa']['status']=='problem_detected'
    assert 'Akīk' in fields['baladwafa']['rationale'] and 'defin' in fields['baladwafa']['rationale']
    assert 'Medine' in fields['baladwafa']['text']
    assert 'Şam bölgesi' in fields['baladekama']['text']
    assert 'Esmâ' in fields['karaba']['text'] and 'Zeyd' in fields['karaba']['text']
    assert fields['karaba']['translation_provenance']['turkish_availability']=='partial_support'
    assert 'eksik liste' in fields['karaba']['rationale']
    assert sum(e['translation_provenance']['turkish_availability']=='source_support_found' for e in fields.values())==5
    assert sum(e['translation_provenance']['turkish_availability']=='partial_support' for e in fields.values())==4
    assert {e['field'] for e in fields.values() if e['status']=='problem_detected'}=={'baladwafa'}


def test_said_fields_keep_all_source_bindings_and_reimport_history(environment,monkeypatch):
    from hadis_web import field_reviews
    original_read=field_reviews._read_batch
    monkeypatch.setattr(field_reviews,'_read_batch',lambda filename:{**original_read(filename),'files':original_read(filename)['files'][:12]} if filename=='field-review-batches.json' else original_read(filename))
    settings,store,_=environment
    load_localization_pilot(store,settings)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(12,86,770,781)
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v12.json').read_text(encoding='utf-8'))
    person=data['people'][0];raw=SourceReader(settings).narrator_records([3331])['3331']
    assert person['expected_source']==raw and person['expected_record_sha256']==record_digest(raw)
    assert {e['field'] for e in person['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    profile=client.get('/api/narrator/3331').json()
    for expected in person['fields']:
        field=expected['field'];entry=profile['localization']['fields'][field][0]
        assert profile[field]==expected['expected_arabic']
        assert entry['text']==expected['text'] and entry['status']==expected['status']
        assert entry['expert_reviewed'] is False
        assert entry['actor_kind']=='assistant_source_review'
        assert entry['translation_origin']=='assistant_reviewed_translation'
        assert entry['rationale']==expected['rationale']
        assert entry['turkish_availability']==expected['translation_provenance']['turkish_availability']
    with store.connection() as c: before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    assert load_field_review_batches(store,settings)==result
    with store.connection() as c: assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}


def test_ebu_sevr_is_in_the_turkish_thesis_but_not_in_the_bound_gk_field():
    # Tatlı2008 printed p22/PDF index34 explicitly gives this alternative.
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v12.json').read_text(encoding='utf-8'))
    konya=next(e for e in data['people'][0]['fields'] if e['field']=='konya')
    assert konya['expected_arabic']=='أبو الأعور'
    assert 'Sevr' not in konya['text']
    assert 'GK alanında olmayan Ebû Sevr' in konya['rationale']
    assert 'kaynakta olmayan' not in konya['rationale']
    assert 'GK alanında olmayan Ebû Sevr' in konya['source_support']['thesis']['evidence_note']
