import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS,load_localization_pilot,record_digest
from hadis_web.source import SourceReader

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def test_eleven_companions_keep_genealogy_variants_and_unresolved_word():
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v11.json').read_text(encoding='utf8'))
    people={p['id']:p for p in data['people']};assert len(people)==11
    fields={(p['id'],e['field']):e for p in people.values() for e in p['fields']};assert len(fields)==104
    issues={(2069,'karaba'),(2650,'karaba'),(3260,'karaba'),(4018,'nasab'),(4697,'wasf'),(5021,'name'),(5021,'karaba')}
    assert {k for k,e in fields.items() if e['status']=='problem_detected'}==issues
    assert 'Ukbe' in fields[2069,'karaba']['text'] and 'Aneme' in fields[2069,'karaba']['rationale']
    assert 'Saîd' in fields[2650,'karaba']['text'] and 'Sa‘d' in fields[2650,'karaba']['rationale']
    assert 'Temîmî' in fields[4018,'nasab']['text'] and 'Teymî' in fields[4018,'nasab']['rationale']
    assert '[أكلس]' in fields[4697,'wasf']['text'] and 'sakalı yoktur' in fields[4697,'wasf']['text'].lower()
    assert 'renk' in fields[4697,'wasf']['rationale'] and 'beyaz' not in fields[4697,'wasf']['text']
    assert 'erkek kardeşinin oğlu' in fields[3142,'karaba']['text']
    assert 'Şam bölgesi' in fields[3142,'baladwafa']['text']
    assert 'Bîrîn' in fields[1733,'baladwafa']['text']
    assert 'Hâris' in fields[4840,'badeel']['text']
    assert 'amcası' in fields[5021,'karaba']['rationale'] and 'oğlu' in fields[5021,'karaba']['rationale']

def test_eleven_more_people_are_fully_source_bound_idempotent_and_not_falsely_complete(environment,monkeypatch):
    from hadis_web import field_reviews
    original_read=field_reviews._read_batch
    monkeypatch.setattr(field_reviews,'_read_batch',lambda filename:{**original_read(filename),'files':original_read(filename)['files'][:11]} if filename=='field-review-batches.json' else original_read(filename))
    settings,store,_=environment;load_localization_pilot(store,settings)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(11,85,760,771)
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v11.json').read_text(encoding='utf8'))
    source=SourceReader(settings);records=source.narrator_records([p['id'] for p in data['people']]);api=TestClient(create_app(settings),base_url='http://127.0.0.1');checked=0
    for p in data['people']:
        raw=records[str(p['id'])];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f"/api/narrator/{p['id']}").json()
        assert not profile['localization']['complete'] and 'critic_opinions' in profile['localization']['pending_fields']
        for e in p['fields']:
            cl=profile['localization']['fields'][e['field']];assert len(cl)==1;cl=cl[0]
            assert profile[e['field']]==e['expected_arabic']==raw[e['field']]
            assert cl['text']==e['text'] and cl['status']==e['status'] and not cl['expert_reviewed']
            assert cl['translation_origin']=='assistant_reviewed_translation' and cl['turkish_availability']==e['translation_provenance']['turkish_availability']
            assert (e['field'] in profile['localization']['pending_fields'])==(e['status']=='problem_detected')
            checked+=1
    assert checked==104
    with store.connection() as con:
        before={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')};assert len(before)==929
    assert load_field_review_batches(store,settings)==result
    with store.connection() as con:assert before=={str(r['id']) for r in con.execute('SELECT id FROM localization_claims')}

def test_unresolved_genealogy_keeps_source_consonant_and_explicit_unresolved_state():
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v11.json').read_text(encoding='utf8'))
    fields={(p['id'],e['field']):e for p in data['people'] for e in p['fields']}
    name=fields[5021,'name']
    assert 'حماهر' in name['expected_arabic']
    assert '[حماهر]' in name['text'] and 'Cemâhir' not in name['text']
    assert name['status']=='problem_detected'

def test_unresolved_family_links_and_word_do_not_assert_they_are_clear():
    data=json.loads((FOLDER/'narrator-field-reviews-tr-v11.json').read_text(encoding='utf8'))
    fields={(p['id'],e['field']):e for p in data['people'] for e in p['fields']}
    for key in ((3260,'karaba'),(4697,'wasf'),(5021,'karaba')):
        assert 'henüz çözülemedi' in fields[key]['text']
        assert fields[key]['status']=='problem_detected'
