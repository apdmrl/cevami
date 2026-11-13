from dataclasses import replace
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app


def test_all_first_chain_opinion_texts_import_idempotently_without_false_completion(environment,monkeypatch):
    from hadis_web import opinions
    original=opinions.read_batch
    monkeypatch.setattr(opinions,'read_batch',lambda filename: {**original(filename),'files':original(filename)['files'][:4]} if filename=='opinion-batches.json' else original(filename))
    from hadis_web.opinions import load_opinion_batches
    settings,store,_=environment
    first=load_opinion_batches(store,settings,include_critic_names=False)
    assert first['narrators']==7 and first['opinion_claims']==130 and first['critic_claims']==0
    assert load_opinion_batches(store,settings,include_critic_names=False)==first
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    total=0
    for person in (6817,4698,3443,8272,6796,5719,5913):
        data=client.get(f'/api/narrator/{person}/opinions?limit=100').json()
        assert len(data['items'])==data['total']
        for item in data['items']:
            assert len(item['localization']['fields']['opinion'])==1
            assert 'critic' in item['localization']['pending_fields']
            assert not item['localization']['complete']
        total+=data['total']
    assert total==130


def test_batch_prevalidation_rejects_missing_or_duplicate_entries_before_writes(environment,tmp_path,monkeypatch):
    from hadis_web import opinions
    settings,store,_=environment
    original=Path(opinions.DATA_FOLDER)
    seed=json.loads((original/'critic-opinions-tr-v1.json').read_text(encoding='utf-8'))
    seed['narrators'][0]['opinions']=seed['narrators'][0]['opinions'][:-1]
    (tmp_path/'bad.json').write_text(json.dumps(seed,ensure_ascii=False),encoding='utf-8')
    (tmp_path/'opinion-batches.json').write_text(json.dumps({'files':['bad.json']}))
    monkeypatch.setattr(opinions,'DATA_FOLDER',tmp_path)
    with pytest.raises(ValueError,match='coverage'):
        opinions.load_opinion_batches(store,settings,include_critic_names=False)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0


def test_name_form_dictionary_is_exact_identity_bound_and_not_a_full_name_translation(environment,tmp_path,monkeypatch):
    from hadis_web import opinions
    settings,store,_=environment
    original=Path(opinions.DATA_FOLDER)
    seed=json.loads((original/'critic-opinions-tr-v1.json').read_text(encoding='utf-8'))
    (tmp_path/'pilot.json').write_text(json.dumps(seed,ensure_ascii=False),encoding='utf-8')
    row=next(e['expected_source'] for e in seed['narrators'][0]['opinions'] if str(e['expected_source']['alem_id'])=='751')
    names={'revision':'test-names','reviewed_on':'2026-10-31','source_artifact_sha256':seed['source_artifact_sha256'],
        'sources':{'tr':{'url':'https://islamansiklopedisi.org.tr/ahmed-b-hanbel','title':'TDV Ahmed b. Hanbel','locator':'Ad başlığı','accessed_on':'2026-10-31'}},
        'critics':[{'alem_id':'751','expected_arabic_name':row['critic'],'text':'Ahmed b. Hanbel','rendering_kind':'name_form',
        'status':'source_compared','source_support':{'tr':{'support_scope':'supports_full_field'}},
        'translation_provenance':{'translation_origin':'source_supported_rendering','turkish_availability':'source_support_found'},
        'rationale':'Kaynakta kimliği karşılaştırılan kısa Türkçe ad biçimi; bütün soy zincirinin çevirisi değildir.'}]}
    (tmp_path/'names.json').write_text(json.dumps(names,ensure_ascii=False),encoding='utf-8')
    (tmp_path/'opinion-batches.json').write_text(json.dumps({'files':['pilot.json'],'critic_names':'names.json'}))
    monkeypatch.setattr(opinions,'DATA_FOLDER',tmp_path)
    result=opinions.load_opinion_batches(store,settings)
    assert result['critic_claims']==1
    data=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/4698').json()
    item=next(row for row in data['opinions'] if str(row['alem_id'])=='751')
    assert item['localization']['fields']['critic'][0]['text']=='Ahmed b. Hanbel'
    assert 'critic' not in item['localization']['pending_fields']
    assert item['critic']==row['critic']
    names['critics'][0]['expected_arabic_name']='غير مطابق'
    (tmp_path/'names.json').write_text(json.dumps(names,ensure_ascii=False),encoding='utf-8')
    with pytest.raises(ValueError,match='critic identity'):
        opinions.load_opinion_batches(store,settings)
