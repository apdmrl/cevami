import hashlib
import json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import load_field_review_batches
from hadis_web.localization import NARRATOR_FIELDS,load_localization_pilot,opinion_record,opinion_key,record_digest
from hadis_web.opinions import load_opinion_batches
from hadis_web.opinion_reviews import load_opinion_reviews
from hadis_web.source import SourceReader

FOLDER=Path(__file__).parents[1]/'hadis_web/data'


def read(name): return json.loads((FOLDER/name).read_text(encoding='utf-8'))


def test_deferred_fields_preserve_both_name_readings_and_all_genealogy_steps():
    data=read('narrator-field-reviews-tr-v13.json')
    people={p['id']:p for p in data['people']};assert set(people)=={3232,3672}
    fields={(p['id'],e['field']):e for p in people.values() for e in p['fields']};assert len(fields)==18
    assert '[وهيب]' in fields[3232,'name']['text'] and '[أهيب]' in fields[3232,'badeel']['text']
    assert fields[3232,'konya']['text']=='Ebû İshak.' and 'babanın' in fields[3232,'konya']['rationale']
    assert 'künyesinden oğul' in fields[3232,'karaba']['rationale']
    assert fields[3672,'name']['text'].count('Hazrec')==2
    assert fields[3672,'konya']['text']=='Ebü’l-Abbâs; Ebû Yahyâ.'
    assert fields[3672,'konya']['translation_provenance']['turkish_availability']=='partial_support'
    support=[e['translation_provenance']['turkish_availability'] for e in fields.values()]
    assert (support.count('source_support_found'),support.count('partial_support'),support.count('not_found_in_checked_sources'))==(5,9,4)
    assert all(e['status']=='source_compared' for e in fields.values())
    artifact=data['review_artifacts'][0]
    path=FOLDER.parents[2]/artifact['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256']


def test_arrow_and_badr_share_are_distinct_in_the_complete_thirteen_opinion_texts():
    data=read('opinions-deferred-companions-tr-v1.json')
    entries={(p['id'],e['expected_source']['alem_id']):e for p in data['narrators'] for e in p['opinions']}
    assert len(entries)==13
    arrow=entries[3232,'1011'];share=entries[3331,'1125']
    assert 'رمى بسهم' in arrow['expected_source']['opinion'] and 'ok atan' in arrow['text']
    assert 'ضرب له' in share['expected_source']['opinion'] and 'ganimet payını ayırdı' in share['text']
    assert 'ok' not in share['text'] and 'katıldı' not in share['text']
    assert 'Sahâbî çocuğu olan bir sahâbî' in entries[3672,'1268']['text']
    support=[e['translation_provenance']['turkish_availability'] for e in entries.values()]
    assert (support.count('partial_support'),support.count('not_found_in_checked_sources'))==(11,2)
    assert entries[3672,'1268']['translation_provenance']['turkish_availability']=='partial_support'
    assert all(e['status']=='source_compared' and e['expected_source']['source_occurrences']==2 for e in entries.values())


def test_deferred_people_and_opinions_match_full_arabic_source_and_real_api(environment,monkeypatch):
    from hadis_web import field_reviews,opinions
    original_fields=field_reviews._read_batch;original_opinions=opinions.read_batch
    monkeypatch.setattr(field_reviews,'_read_batch',lambda filename:{**original_fields(filename),'files':original_fields(filename)['files'][:13]} if filename=='field-review-batches.json' else original_fields(filename))
    monkeypatch.setattr(opinions,'read_batch',lambda filename:{**original_opinions(filename),'files':original_opinions(filename)['files'][:7]} if filename=='opinion-batches.json' else original_opinions(filename))
    settings,store,_=environment;load_localization_pilot(store,settings)
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(13,88,788,799)
    assert load_opinion_batches(store,settings,include_critic_names=False)==dict(narrators=34,opinion_claims=316,critic_claims=0,batches=7)
    load_opinion_reviews(store,settings)
    source=SourceReader(settings);api=TestClient(create_app(settings),base_url='http://127.0.0.1')
    for p in read('narrator-field-reviews-tr-v13.json')['people']:
        raw=source.narrator_records([p['id']])[str(p['id'])]
        assert p['expected_source']==raw and p['expected_record_sha256']==record_digest(raw)
        assert {e['field'] for e in p['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
        profile=api.get(f'/api/narrator/{p["id"]}').json()
        for e in p['fields']:
            claim=profile['localization']['fields'][e['field']][0]
            assert profile[e['field']]==e['expected_arabic']==raw[e['field']]
            assert claim['text']==e['text'] and claim['status']==e['status']
            assert claim['actor_kind']=='assistant_source_review' and claim['expert_reviewed'] is False
    for p in read('opinions-deferred-companions-tr-v1.json')['narrators']:
        rows=source.critic_opinions(p['id'],100)['items']
        live={opinion_key(r):r for row in rows if (r:=opinion_record(p['id'],row))}
        page=api.get(f'/api/narrator/{p["id"]}/opinions?limit=100').json()
        assert page['total']==len(page['items'])==p['expected_opinion_count']
        for e in p['opinions']:
            assert e['expected_source']==live[e['key']] and e['expected_record_sha256']==record_digest(live[e['key']])
            row=next(r for r in page['items'] if str(r['alem_id'])==e['expected_source']['alem_id'])
            claim=row['localization']['fields']['opinion'][0]
            assert row['opinion']==e['expected_source']['opinion'] and claim['text']==e['text']
            assert claim['status']=='source_compared' and claim['expert_reviewed'] is False
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    assert load_field_review_batches(store,settings)==result
    load_opinion_batches(store,settings,include_critic_names=False);load_opinion_reviews(store,settings)
    with store.connection() as c:assert {str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}==before
