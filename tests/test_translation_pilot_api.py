from copy import deepcopy
from dataclasses import replace

from fastapi.testclient import TestClient

from hadis_web.app import create_app
from hadis_web.config import Settings
from hadis_web.source import SourceReader
from test_hadith_source_reviews import reviewed_store
from test_hadith_components import batch, component_case


def test_components_api_reports_scope_origin_and_sources(reviewed_store):
    from hadis_web.hadith_components import load_component_batch
    store, settings, data = reviewed_store
    case = component_case(store, settings, data)
    case['components'][1]['bibliography']['status'] = 'unverified'
    load_component_batch(store, settings, data=batch(case))
    client = TestClient(create_app(settings),base_url='http://127.0.0.1')
    response = client.get('/api/hadith/146_1/components?language=tr')
    assert response.status_code == 200
    report = response.json()
    assert report['hadith_core_complete'] is False
    assert [i['kind'] for i in report['items']] == ['isnad', 'matn']
    assert all(i['origin'] == 'assistant_translation' and i['expert_reviewed'] is False for i in report['items'])
    assert all(i['source_bindings'] and i['reviews'][0]['sources'] for i in report['items'])
    assert client.get('/api/hadith/999999_999999/components').status_code == 404
    assert client.get('/api/hadith/146_1/components?language=ar').status_code == 422


def test_unavailable_components_do_not_break_arabic_reader():
    client = TestClient(create_app(replace(Settings.load(), postgres_dsn=None)),base_url='http://127.0.0.1')
    assert client.get('/api/hadith/146_1').status_code == 200
    response = client.get('/api/hadith/146_1/components')
    assert response.status_code == 200
    assert response.json()['available'] is False
    assert response.json()['items'] == []
    assert response.json()['hadith_core_complete'] is False


def test_changed_arabic_source_is_reported_without_serving_stale_components(reviewed_store, monkeypatch):
    from hadis_web.hadith_components import load_component_batch
    store, settings, data = reviewed_store
    load_component_batch(store, settings, data=batch(component_case(store, settings, data)))
    original = SourceReader.hadith
    def changed(self, bhid):
        value = deepcopy(original(self, bhid))
        if value is not None:
            value['arabic']['raw_text'] += ' changed-source-fixture'
        return value
    monkeypatch.setattr(SourceReader, 'hadith', changed)
    response = TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/hadith/146_1/components')
    assert response.status_code == 200
    assert response.json()['items'] == []
    assert response.json()['hadith_core_complete'] is False
    assert 'source_binding_invalid' in response.json()['blockers']
