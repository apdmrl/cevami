"""Additive response presentation without importing or modifying working data."""
from copy import deepcopy
from dataclasses import replace

from fastapi.testclient import TestClient
from hadis_web.config import Settings
from hadis_web.app import create_app
import pytest


@pytest.mark.parametrize('namespace,expected',[('fawaz:tur-fixture','Özgün çeviri.'),
    ('fixture:tr','Özgün çeviri. İzah için buraya tıklayın'),('fawaz:eng-fixture','Özgün çeviri. İzah için buraya tıklayın')])
def test_translation_response_keeps_original_source_and_review_while_adding_reading_view(monkeypatch,namespace,expected):
    source='Özgün çeviri. İzah için buraya tıklayın'
    original={'available':True,'total':1,'items':[{'display_text':source,'raw_text':source,
        'provider':'fawazahmed0','namespace':namespace,'source_key':'9',
        'review':{'status':'needs_review','expert_reviewed':False}}]}
    before=deepcopy(original)
    class Store:
        def __init__(self,*args,**kwargs):pass
        def translations(self,bhid,version):
            assert bhid=='146_1'
            return original
    monkeypatch.setattr('hadis_web.app.WorkingStore',Store)
    settings=replace(Settings.load(),postgres_dsn='fixture-not-a-connection')
    response=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/hadith/146_1/translations')
    assert response.status_code==200
    row=response.json()['items'][0]
    assert row['display_text']==row['raw_text']==source
    assert row['review']==before['items'][0]['review']
    assert row['presentation']=={'text':expected,'navigation_note':'İzah için buraya tıklayın' if expected!=source else ''}
    assert original==before
