from copy import deepcopy
from dataclasses import replace
import hashlib
import html
import json
import re
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
import pytest
from fastapi.testclient import TestClient

from hadis_web.app import create_app
from hadis_web.config import Settings
from hadis_web.source import SourceReader
from hadis_web.working import WorkingStore
from hadis_web.hadith_reviews import load_hadith_reviews

DATA = Path(__file__).resolve().parents[1]/'hadis_web/data/hadith-source-reviews-tr-v1.json'


@pytest.fixture
def reviewed_store():
    settings=Settings.load()
    schema='test_'+uuid.uuid4().hex
    store=WorkingStore(settings.postgres_dsn,schema)
    store.migrate()
    data=json.loads(DATA.read_text(encoding='utf-8'))
    reader=SourceReader(settings)
    external={}
    try:
        for case in data['cases']:
            versions={}
            for m in case['members']:
                snapshot=store.add_snapshot(m['provider'],m['source_revision'],m['artifact_sha256'],m['artifact_name'])
                if m['role']=='target_arabic':
                    arabic=reader.hadith(case['bhid'])['arabic']
                    raw,display=arabic['raw_text'],arabic['text']
                else:
                    if m['artifact_name'] not in external:
                        external[m['artifact_name']]=json.loads((settings.project_root/'references/turkish/fawazahmed0'/m['artifact_name']).read_text(encoding='utf-8'))
                    ordinal=int(m['locator']['json_pointer'].split('/')[-1])
                    raw=external[m['artifact_name']]['hadiths'][ordinal]['text']
                    display=html.unescape(re.sub('<[^>]+>','',raw))
                identity=store.add_text(snapshot,m['namespace'],m['source_key'],m['language'],raw,display,m['locator'])
                assert str(identity)==m['id']
                versions[m['role']]=identity
            identity=store.add_alignment(versions['target_arabic'],versions['bridge_arabic'],versions['translation'],{'method':'fixture'})
            assert str(identity)==case['alignment']['id']
        yield store,replace(settings,postgres_schema=schema),data
    finally:
        with psycopg.connect(settings.postgres_dsn,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def event_ids(store):
    with store.connection() as c:
        return {str(r['id']) for r in c.execute('SELECT id FROM review_events')}


def test_bound_reviews_are_atomic_idempotent_and_not_full_translation_approval(reviewed_store):
    store,settings,data=reviewed_store
    before=store.counts()
    result=load_hadith_reviews(store,settings,data=data)
    assert result['events']==15 and result['cases']==3
    ids=event_ids(store)
    assert len(ids)==15
    assert load_hadith_reviews(store,settings,data=data)==result
    assert event_ids(store)==ids
    after=store.counts()
    assert after=={**before,'review_events':15}
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    for case,status in zip(data['cases'],('problem_detected','problem_detected','needs_review')):
        assessment=store.assessment(case['alignment']['id'])
        assert assessment['status']==status
        assert assessment['scope']=='unclassified'
        assert assessment['expert_reviewed'] is False
        assert assessment['bibliography']=='pending'
        assert assessment['dimensions']['translation_completeness']=='pending'
        events=assessment['events']
        assert len(events)==5 and all(e['actor_kind']=='assistant_source_review' for e in events)
        assert all(e['rationale'] and len(e['sources'])==3 and 'actor' not in e for e in events)
        actual=client.get(f'/api/hadith/{case["bhid"]}/translations').json()['items'][0]
        assert actual['review']==assessment
        if case['bhid']=='146_5': assert actual['source_key']=='6'


@pytest.mark.parametrize('fault', ['raw_hash','display_hash','locator','snapshot','url','date','parent','expert'])
def test_late_binding_or_metadata_error_writes_no_events(reviewed_store,fault):
    store,settings,data=reviewed_store
    bad=deepcopy(data)
    case=bad['cases'][-1]
    member=case['members'][-1]
    if fault=='raw_hash': member['raw_sha256']='f'*64
    elif fault=='display_hash': member['display_sha256']='f'*64
    elif fault=='locator': member['locator']['key']='changed'
    elif fault=='snapshot': member['artifact_name']='invented.json'
    elif fault=='url': case['reviews'][-1]['sources'][-1]['url']='javascript:alert(1)'
    elif fault=='date': case['reviews'][-1]['sources'][-1]['accessed_on']='2026-02-30'
    elif fault=='parent': case['reviews'][-1]['supersedes_id']=str(uuid.uuid4())
    elif fault=='expert': bad['actor_kind']='expert_review'
    with pytest.raises(ValueError): load_hadith_reviews(store,settings,data=bad)
    assert event_ids(store)==set()


def test_competing_root_is_rejected_without_partial_writes(reviewed_store):
    store,settings,data=reviewed_store
    last=data['cases'][-1]
    old=store.record_review(last['alignment']['id'],data['actor'],'assistant_source_review','bibliography','pending','Earlier independent root',['legacy source'])
    with pytest.raises(ValueError): load_hadith_reviews(store,settings,data=data)
    assert event_ids(store)=={str(old)}


def test_assessment_exposes_only_active_events_and_keeps_legacy_sources(reviewed_store):
    store,settings,data=reviewed_store
    revision=data['cases'][0]['alignment']['id']
    old=store.record_review(revision,'private actor identity','assistant_source_review','translation_meaning','pending','Old rationale',['old source'])
    new=store.record_review(revision,'private actor identity','assistant_source_review','translation_meaning','pass','Current rationale',['legacy source'],old)
    assessment=store.assessment(revision)
    assert assessment['events']==[{'id':str(new),'actor_kind':'assistant_source_review','dimension':'translation_meaning','outcome':'pass','rationale':'Current rationale','sources':['legacy source']}]
    assert assessment['status']=='needs_review' and assessment['expert_reviewed'] is False
