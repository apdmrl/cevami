import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,record_digest

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def data():return json.loads((FOLDER/'narrator-field-reviews-tr-v17.json').read_text(encoding='utf-8'))
def fields(batch,pid):return {e['field']:e for e in next(p for p in batch['people'] if p['id']==pid)['fields']}

def test_musa_nisba_is_not_a_guessed_occupation_and_sebt_has_partial_support():
    batch=data();f=fields(batch,7721);assert len(f)==10
    assert f['san3a']['text']=='Tebûzekî (nisbe).'
    assert 'kesin meslek' in f['san3a']['rationale']
    assert 'tavukçu' not in f['san3a']['text']
    assert f['wasf_rotba']['translation_provenance']['turkish_availability']=='partial_support'
    assert f['wasf_rotba']['source_support']['tebuzeki']['support_scope']=='supports_part_of_field'
    assert f['mawaaly']['text']=='Benî Minkar’ın mevlâsı (velâ bağıyla bağlı).'
    assert '226' not in str(f) and f['baladwafa']['text']=='Basra.'

def test_ukayl_exact_identity_and_bounded_turkish_support_preserve_open_details():
    batch=data();f=fields(batch,5688);assert len(f)==9
    assert f['name']['text']=='Ukayl b. Hâlid b. Ukayl.'
    assert f['konya']['text']=='Ebû Hâlid.' and f['baladwafa']['text']=='Mısır.'
    for key in ('lakab','baladwafa'):
        assert f[key]['translation_provenance']['turkish_availability']=='not_found_in_checked_sources'
        assert f[key]['source_support']['kandirali']['support_scope']=='identity_only'
    assert f['wasf_rotba']['translation_provenance']['turkish_availability']=='source_support_found'
    assert '98–99' in batch['sources']['kandirali']['locator']
    assert 'PDF sayfa indeksi doğrulanmadı' in batch['sources']['kandirali']['locator']
    assert 'karaba' not in f and 'baladekama' not in f
    kinds=[e['translation_provenance']['turkish_availability'] for p in batch['people'] for e in p['fields']]
    assert [kinds.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[16,1,2]

def test_nineteen_full_arabic_fields_roundtrip_with_opinions_still_pending(environment):
    settings,store,_=environment;batch=data();assert _load_datasets(store,settings,[batch])==dict(people=2,claims=19)
    registry=json.loads((FOLDER/'field-review-batches.json').read_text(encoding='utf-8'));assert registry['files'][16]=='narrator-field-reviews-tr-v17.json'
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');records=SourceReader(settings).narrator_records([7721,5688])
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
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')};assert len(before)==19
    _load_datasets(store,settings,[batch])
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
