import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,record_digest

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def data():return json.loads((FOLDER/'narrator-field-reviews-tr-v16.json').read_text(encoding='utf-8'))


def test_yunus_kunyas_alternative_names_and_kinship_remain_literal():
    batch=data();people={p['id']:p for p in batch['people']};assert set(people)=={8621,8297}
    fields={e['field']:e for e in people[8621]['fields']};assert len(fields)==11
    assert fields['konya']['text']=='Ebû Yezîd; Ebû Bekir.'
    assert 'Mişkân' in fields['name']['text'] and 'Muhârik' in fields['badeel']['text']
    assert 'Ebû Ali b. Yezîd’in kardeşi' in fields['karaba']['text']
    assert 'Anbese b. Hâlid b. Yezîd’in amcası' in fields['karaba']['text']
    assert 'kölesi' not in fields['mawaaly']['text']
    assert fields['karaba']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'


def test_yahya_father_grandfather_and_source_evaluation_scope_are_distinct():
    batch=data();p=next(p for p in batch['people'] if p['id']==8297);fields={e['field']:e for e in p['fields']};assert len(fields)==10
    assert fields['name']['text']=='Yahyâ b. Abdullah b. Bükeyr.' and fields['badeel']['text']=='İbn Bükeyr.'
    assert 'dede' in fields['badeel']['rationale'] and 'Yahyâ b. Yahyâ' in fields['name']['rationale']
    assert 'İbn Hibbân' in fields['wasf_rotba']['rationale'] and 'Nesâî' in fields['wasf_rotba']['rationale']
    assert fields['konya']['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
    assert fields['wasf_rotba']['source_support']['hanek']['support_scope']=='identity_only'
    support=[e['translation_provenance']['turkish_availability'] for p in batch['people'] for e in p['fields']]
    assert (support.count('source_support_found'),support.count('partial_support'),support.count('not_found_in_checked_sources'))==(5,5,11)
    assert all(e['status']=='source_compared' for p in batch['people'] for e in p['fields'])


def test_all_twenty_one_full_source_fields_roundtrip_real_api_with_opinions_pending(environment):
    settings,store,_=environment;reader=SourceReader(settings);batch=data()
    assert _load_datasets(store,settings,[batch])==dict(people=2,claims=21)
    registry=json.loads((FOLDER/'field-review-batches.json').read_text(encoding='utf-8'));assert 'narrator-field-reviews-tr-v16.json' in registry['files']
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');records=reader.narrator_records([8621,8297])
    for p in batch['people']:
        raw=records[str(p['id'])];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f'/api/narrator/{p["id"]}').json();assert profile['localization']['complete'] is False and 'critic_opinions' in profile['localization']['pending_fields']
        for e in p['fields']:
            cl=profile['localization']['fields'][e['field']][0]
            assert profile[e['field']]==e['expected_arabic'] and cl['text']==e['text'] and cl['status']=='source_compared'
            assert cl['expert_reviewed'] is False and cl['actor_kind']=='assistant_source_review'
            assert cl['translation_origin']=='assistant_reviewed_translation' and cl['turkish_availability']==e['translation_provenance']['turkish_availability']
            with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
            assert bound['source_record']==raw and bound['source_record_sha256']==p['expected_record_sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')};assert len(before)==21
    _load_datasets(store,settings,[batch])
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
