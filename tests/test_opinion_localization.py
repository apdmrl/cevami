from dataclasses import replace
import json
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.source import SourceReader


def test_opinion_identity_is_person_and_text_bound_and_does_not_change_narrator_hash(environment):
    from hadis_web.localization import narrator_record, record_digest, opinion_record, opinion_key
    settings, _, _ = environment
    reader = SourceReader(settings)
    profile = reader.narrator(4698)
    record = opinion_record(4698, profile['opinions'][0])
    assert opinion_key(record) != opinion_key({**record, 'narrator_id': 6817})
    assert opinion_key(record) != opinion_key({**record, 'opinion': record['opinion'] + 'x'})
    assert record_digest(record) != record_digest({**record, 'source_occurrences': 99})
    assert narrator_record(profile) == reader.narrator_records([4698])['4698']
    assert len(profile['opinions']) == profile['opinions_total'] == 12


def test_opinion_pilot_is_idempotent_source_bound_and_honest_about_partial_support(environment):
    from hadis_web.opinions import load_opinion_pilot
    from hadis_web.localization import LocalizationStore, opinion_record, opinion_key
    settings, store, snapshot = environment
    assert load_opinion_pilot(store, settings)['claims'] == 12
    assert load_opinion_pilot(store, settings)['claims'] == 12
    with store.connection() as c:
        assert c.execute("SELECT count(*) AS n FROM localization_claims WHERE entity_type='critic_opinion'").fetchone()['n'] == 12
    rows = SourceReader(settings).critic_opinions(4698)['items']
    records = {opinion_key(opinion_record(4698, r)): opinion_record(4698, r) for r in rows}
    result = LocalizationStore(store).for_records(snapshot, 'critic_opinion', records, 'tr')
    by_critic = {str(r['alem_id']): result[opinion_key(opinion_record(4698, r))] for r in rows}
    assert by_critic['2463']['fields']['opinion'][0]['translation_origin'] == 'source_supported_rendering'
    assert by_critic['431']['fields']['opinion'][0]['translation_origin'] == 'assistant_translation'
    assert 'yirmi yıl' in by_critic['431']['fields']['opinion'][0]['text']
    assert 'on dokuz yıl' in by_critic['924']['fields']['opinion'][0]['text']
    assert all('critic' in value['pending_fields'] and not value['complete'] for value in result.values())
    assert all(not cl['expert_reviewed'] for value in result.values() for cl in value['fields']['opinion'])
    local = LocalizationStore(store)
    stale = {key:{**value,'opinion':value['opinion']+'x'} for key,value in records.items()}
    assert all(not value['fields'] for value in local.for_records(snapshot,'critic_opinion',stale,'tr').values())
    other = store.add_snapshot('gk45','other','b'*64,'other.db')
    assert all(not value['fields'] for value in local.for_records(other,'critic_opinion',records,'tr').values())


def test_opinion_import_prevalidates_all_records_before_writing(environment, monkeypatch):
    from hadis_web.opinions import load_opinion_pilot
    settings, store, _ = environment
    original = SourceReader.critic_opinions
    def changed(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        value['items'][-1]['opinion'] += 'x'
        return value
    monkeypatch.setattr(SourceReader,'critic_opinions',changed)
    with pytest.raises(ValueError, match='changed'):
        load_opinion_pilot(store, settings)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n'] == 0


def test_api_opinions_preserve_arabic_attribution_pagination_and_unavailable_fallback(environment):
    from hadis_web.opinions import load_opinion_pilot
    settings, store, _ = environment
    load_opinion_pilot(store, settings)
    client = TestClient(create_app(settings),base_url='http://127.0.0.1')
    profile = client.get('/api/narrator/4698').json()
    assert profile['opinions_total'] == 12
    assert 'critic_opinions' in profile['localization']['pending_fields']
    assert all(row['localization']['fields']['opinion'] for row in profile['opinions'])
    recorded = next(row for row in profile['opinions'] if str(row['alem_id']) == '924')
    assert recorded['critic'].startswith('عبد الرحمن')
    assert recorded['source_occurrences'] == 2
    page = client.get('/api/narrator/4698/opinions?limit=5&offset=5').json()
    assert page['total'] == 12 and len(page['items']) == 5 and page['offset'] == 5
    assert client.get('/api/narrator/99999999/opinions').status_code == 404
    assert client.get('/api/narrator/4698/opinions?limit=101').status_code == 422
    fallback = TestClient(create_app(replace(settings,postgres_dsn=None)),base_url='http://127.0.0.1').get('/api/narrator/4698').json()
    assert fallback['opinions'][0]['opinion'] == profile['opinions'][0]['opinion']
    assert fallback['opinions'][0]['localization']['available'] is False


def test_queue_does_not_call_translated_opinions_unsearched(environment, tmp_path):
    from hadis_web.opinions import load_opinion_pilot
    from hadis_web.translation_queue import write_narrator_queue
    settings, store, _ = environment
    load_opinion_pilot(store,settings)
    output=tmp_path/'queue.jsonl'
    write_narrator_queue(store,settings,output)
    row=next(row for line in output.read_text(encoding='utf-8').splitlines()
             if (row:=json.loads(line))['narrator_id']==4698 and row['field']=='critic_opinions')
    assert row['stage']=='translation_draft_review'
    assert row['opinion_progress']=={'distinct_opinions':12,'translated_opinions':12,
           'source_compared_texts':1,'complete_opinions':0}
    assert len(row['claim_ids'])==12
    from hadis_web.localization import LocalizationStore, opinion_record, opinion_key
    opinion=SourceReader(settings).critic_opinions(4698)['items'][0]
    record=opinion_record(4698,opinion)
    _,_,snapshot=environment
    LocalizationStore(store).add_claim(snapshot=snapshot,entity_type='critic_opinion',entity_key=opinion_key(record),
        source_record=record,field='opinion',language='tr',text='Farklı test aktarımı',rendering_kind='translation',
        status='needs_review',actor_kind='assistant_source_review',
        sources=[{'url':'gk45:critic_opinion:test','title':'Test kaynak kaydı','locator':'Yalnız geçici test şeması','accessed_on':'2026-10-31'}],
        rationale='Çelişen iki karşılıkta kuyruk sorunu gizlememeli.')
    write_narrator_queue(store,settings,output)
    row=next(row for line in output.read_text(encoding='utf-8').splitlines()
             if (row:=json.loads(line))['narrator_id']==4698 and row['field']=='critic_opinions')
    assert row['stage']=='conflicting_translation_review'


def test_more_than_thirty_source_opinions_remain_accessible_and_incomplete(environment):
    settings, _, _ = environment
    client=TestClient(create_app(replace(settings,postgres_dsn=None)),base_url='http://127.0.0.1')
    profile=client.get('/api/narrator/30276').json()
    assert len(profile['opinions'])==30 and profile['opinions_total']==44
    remaining=client.get('/api/narrator/30276/opinions?offset=30').json()
    assert remaining['total']==44 and len(remaining['items'])==14
    assert len({row['key'] for row in profile['opinions']+remaining['items']})==44
    assert profile['localization']['complete'] is False
