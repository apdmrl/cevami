import hashlib
import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.localization import NARRATOR_FIELDS,opinion_record,opinion_key,record_digest
from hadis_web.source import SourceReader

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))


def test_four_ravis_preserve_partial_kunyas_and_vela_without_added_genealogy():
    data=read('narrator-field-reviews-tr-v14.json')
    people={p['id']:p for p in data['people']};assert set(people)=={3801,3194,1040,4506}
    fields={(p['id'],e['field']):e for p in people.values() for e in p['fields']};assert len(fields)==39
    assert 'Ebû Ubeydullah' in fields[3194,'konya']['text']
    assert 'Münzir' not in fields[3194,'konya']['text'] and 'Umeyr' not in fields[3194,'konya']['text']
    mother=fields[3194,'karaba'];assert 'Ümmü Sâlim' in mother['text'] and 'ümmüveled' in mother['text']
    assert 'Kisrâ' not in mother['text'] and 'Fars' not in mother['text']
    assert 'kölesi' not in fields[4506,'mawaaly']['text']
    assert 'Keysân' in fields[4506,'badeel']['text'] and fields[4506,'badeel']['translation_provenance']['turkish_availability']=='partial_support'
    assert 'bağımsız' in fields[4506,'wasf']['rationale']
    support=[e['translation_provenance']['turkish_availability'] for e in fields.values()]
    assert (support.count('source_support_found'),support.count('partial_support'),support.count('not_found_in_checked_sources'))==(26,11,2)
    assert all(e['status']=='source_compared' for e in fields.values())


def test_critical_opinion_scopes_exceptions_and_source_reading_are_preserved():
    data=read('opinions-high-frequency-tr-v1.json')
    entries={(p['id'],e['expected_source']['alem_id']):e for p in data['narrators'] for e in p['opinions']};assert len(entries)==40
    assert {key for key,e in entries.items() if e['status']=='problem_detected'}=={(3801,'466'),(1040,'1722')}
    quran=entries[4506,'1268']
    assert 'الفرآن' in quran['expected_source']['opinion']
    assert 'Kur’an' in quran['text'] and quran['translation_provenance']['translation_origin']=='assistant_source_corrected_rendering'
    assert 'qurra' in quran['source_support'] and 'الفرآن' in quran['rationale'] and 'القرآن' in quran['rationale']
    comparative=entries[3801,'700']['text']
    assert 'ittifak' in comparative and 'Buhârî' not in comparative and 'Müslim' not in comparative
    hady=entries[1040,'1011']['text']
    assert 'Buhârî' in hady and 'Müslim' not in hady and 'başka' in hady and 'i‘tibâr' in hady
    reports=entries[1040,'2821']['text']
    assert 'iki fels eder' in reports and 'iki fels etmez' not in reports
    assert all(word in reports for word in ('Muâviye','Üsâme','İbn Muhriz'))
    support=[e['translation_provenance']['turkish_availability'] for e in entries.values()]
    assert (support.count('source_support_found'),support.count('partial_support'),support.count('not_found_in_checked_sources'))==(1,34,5)


def test_missing_critic_names_keep_seyf_identity_open_and_existing_466_untouched():
    data=read('critic-name-reviews-tr-v3.json');entries={e['alem_id']:e for e in data['critics']}
    assert set(entries)=={'700','1722'} and all('supersedes_id' not in e for e in entries.values())
    assert entries['700']['text']=='Ebû Ya‘lâ el-Halîlî' and entries['700']['status']=='source_compared'
    seyf=entries['1722'];assert seyf['expected_source']['rawy_id']=='3738' and seyf['status']=='problem_detected'
    assert 'Sevrî' in seyf['rationale'] and '37' in seyf['rationale']
    assert seyf['text'].startswith('Seyf b. Muhammed b. Ahmed')


def test_new_roots_only_bind_every_arabic_row_and_roundtrip_through_real_api(environment,monkeypatch):
    from hadis_web import critic_name_reviews
    original_names=critic_name_reviews._read
    monkeypatch.setattr(critic_name_reviews,'_read',lambda filename:{**original_names(filename),'files':original_names(filename)['files'][:3]} if filename=='critic-name-review-batches.json' else original_names(filename))
    settings,store,_=environment
    field_data=read('narrator-field-reviews-tr-v14.json');opinion_data=read('opinions-high-frequency-tr-v1.json')
    assert 'narrator-field-reviews-tr-v14.json' in read('field-review-batches.json')['files']
    assert 'opinions-high-frequency-tr-v1.json' in read('opinion-batches.json')['files']
    result=_load_datasets(store,settings,[field_data]);assert result==dict(people=4,claims=39)
    assert _load_files(store,settings,['opinions-high-frequency-tr-v1.json'])==dict(narrators=4,opinion_claims=40,critic_claims=0,batches=1)
    load_critic_names(store,settings);names=load_critic_name_reviews(store,settings)
    assert (names['batches'],names['critics'],names['claims'],names['claim_versions'])==(3,35,35,35)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');source=SourceReader(settings)
    for p in field_data['people']:
        raw=source.narrator_records([p['id']])[str(p['id'])]
        assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f'/api/narrator/{p["id"]}').json()
        for e in p['fields']:
            claim=profile['localization']['fields'][e['field']][0]
            assert profile[e['field']]==e['expected_arabic'] and claim['text']==e['text']
            assert claim['status']==e['status'] and claim['expert_reviewed'] is False
    for p in opinion_data['narrators']:
        raw_rows=source.critic_opinions(p['id'],100)['items']
        live={opinion_key(r):r for row in raw_rows if (r:=opinion_record(p['id'],row))}
        page=api.get(f'/api/narrator/{p["id"]}/opinions?limit=100').json()
        assert page['total']==len(page['items'])==p['expected_opinion_count']
        for e in p['opinions']:
            assert live[e['key']]==e['expected_source'] and record_digest(live[e['key']])==e['expected_record_sha256']
            row=next(r for r in page['items'] if str(r['alem_id'])==e['expected_source']['alem_id'])
            cl=row['localization']['fields']['opinion'][0]
            assert row['opinion']==e['expected_source']['opinion'] and cl['text']==e['text']
            assert cl['status']==e['status'] and cl['expert_reviewed'] is False
            assert cl['translation_origin']==e['translation_provenance']['translation_origin']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[field_data]);_load_files(store,settings,['opinions-high-frequency-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
