import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,opinion_record,opinion_key,record_digest

FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))


def test_nisba_and_source_support_do_not_replace_tinnis_with_tunis():
    data=read('narrator-field-reviews-tr-v15.json');p=data['people'][0];assert p['id']==5175 and len(p['fields'])==9
    fields={e['field']:e for e in p['fields']}
    for field in ('badeel','lakab'):
        assert 'Tinnîsî' in fields[field]['text'] and 'Tunusî' not in fields[field]['text']
        assert 'Tunusî' in fields[field]['rationale'] and 'durmus' in fields[field]['source_support']
    assert fields['baladekama']['translation_provenance']['turkish_availability']=='partial_support'
    assert 'köken' in fields['baladekama']['rationale']
    assert fields['lakab']['source_support']['uluman']['support_scope']=='identity_only'
    assert fields['lakab']['source_support']['durmus']['support_scope']=='supports_full_field'
    assert fields['konya']['source_support']['durmus']['support_scope']=='identity_only'
    support=[e['translation_provenance']['turkish_availability'] for e in fields.values()]
    assert (support.count('source_support_found'),support.count('partial_support'))==(7,2)


def test_complete_opinions_preserve_comparison_and_fathers_recording_agent():
    data=read('opinions-abdullah-yusuf-tr-v1.json');p=data['narrators'][0];assert p['id']==5175 and len(p['opinions'])==15
    entries={e['expected_source']['alem_id']:e for e in p['opinions']}
    assert 'Ka‘nebî' in entries['767']['text'] and 'üstündür' in entries['767']['text']
    assert '217' in entries['924']['text'] and 'babam' in entries['924']['text']
    assert 'Buhârî' not in entries['924']['text'] and 'Buhârî' in entries['924']['rationale']
    assert 'ittifak' in entries['700']['text'] and 'Müslim' not in entries['700']['text']
    assert 'Tinnîs' in entries['431']['text'] and 'Tunus' not in entries['431']['text']
    support=[e['translation_provenance']['turkish_availability'] for e in entries.values()]
    assert (support.count('source_support_found'),support.count('partial_support'),support.count('not_found_in_checked_sources'))==(1,9,5)
    names=read('critic-name-reviews-tr-v4.json')['critics'];assert {e['alem_id'] for e in names}=={'418','49','493','666'}
    assert all(e['status']=='source_compared' and 'supersedes_id' not in e for e in names)


def test_new_roots_source_bindings_and_complete_real_api_are_idempotent(environment,monkeypatch):
    from hadis_web import critic_name_reviews
    original=critic_name_reviews._read
    monkeypatch.setattr(critic_name_reviews,'_read',lambda name:{**original(name),'files':original(name)['files'][:4]} if name=='critic-name-review-batches.json' else original(name))
    settings,store,_=environment;source=SourceReader(settings)
    data=read('narrator-field-reviews-tr-v15.json');p=data['people'][0]
    raw=source.narrator_records([5175])['5175'];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
    assert 'narrator-field-reviews-tr-v15.json' in read('field-review-batches.json')['files']
    assert 'opinions-abdullah-yusuf-tr-v1.json' in read('opinion-batches.json')['files']
    assert _load_datasets(store,settings,[data])==dict(people=1,claims=9)
    assert _load_files(store,settings,['opinions-abdullah-yusuf-tr-v1.json'])==dict(narrators=1,opinion_claims=15,critic_claims=0,batches=1)
    load_critic_names(store,settings);names=load_critic_name_reviews(store,settings);assert (names['batches'],names['critics'],names['claims'],names['claim_versions'])==(4,39,39,39)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/5175').json()
    for e in p['fields']:
        cl=profile['localization']['fields'][e['field']][0]
        assert profile[e['field']]==e['expected_arabic'] and cl['text']==e['text'] and cl['status']==e['status'] and cl['expert_reviewed'] is False
    live={opinion_key(r):r for row in source.critic_opinions(5175,100)['items'] if (r:=opinion_record(5175,row))}
    page=api.get('/api/narrator/5175/opinions?limit=100').json();assert page['total']==len(page['items'])==15
    expected_names={e['alem_id']:e for e in read('critic-name-reviews-tr-v4.json')['critics']};checked=set()
    for e in read('opinions-abdullah-yusuf-tr-v1.json')['narrators'][0]['opinions']:
        assert live[e['key']]==e['expected_source'] and record_digest(live[e['key']])==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==e['expected_source']['alem_id']);assert row['opinion']==e['expected_source']['opinion']
        cl=row['localization']['fields']['opinion'][0];assert cl['text']==e['text'] and cl['status']=='source_compared' and cl['expert_reviewed'] is False
        if str(row['alem_id']) in expected_names:
            name=expected_names[str(row['alem_id'])];cl=row['localization']['fields']['critic'][0]
            assert cl['text']==name['text'] and cl['status']=='source_compared' and cl['expert_reviewed'] is False
            with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
            assert bound['source_record']==name['expected_source'] and bound['source_record_sha256']==name['expected_record_sha256'];checked.add(str(row['alem_id']))
    assert checked==set(expected_names)
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[data]);_load_files(store,settings,['opinions-abdullah-yusuf-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
