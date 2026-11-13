from dataclasses import replace
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.source import SourceReader
from hadis_web.app import create_app


def test_controlled_terms_use_whole_field_and_never_override_person_specific_translation(environment):
    from hadis_web.controlled_terms import load_controlled_terms, apply_controlled_terms
    from hadis_web.localization import LocalizationStore, empty_localization, narrator_record
    settings,store,snapshot=environment
    assert load_controlled_terms(store)['terms']==12
    assert load_controlled_terms(store)['terms']==12
    record=narrator_record(SourceReader(settings).narrator(4698))
    records={'4698':{**record,'wasf_rotba':'ثقة','baladekama':'المدينة'}}
    initial={key:empty_localization(value) for key,value in records.items()}
    result=apply_controlled_terms(store,snapshot,records,initial,'tr')['4698']
    assert result['fields']['wasf_rotba'][0]['text']=='Sika (güvenilir).'
    assert result['fields']['baladekama'][0]['text']=='Medine.'
    claim=result['fields']['wasf_rotba'][0]
    assert claim['status']=='needs_review' and claim['actor_kind']=='automated_check'
    assert claim['translation_origin']=='controlled_vocabulary' and claim['expert_reviewed'] is False
    assert claim['source_binding']['source_record_sha256']
    assert 'wasf_rotba' in result['pending_fields'] and not result['complete']
    changed={'4698':{**records['4698'],'wasf_rotba':'ثقة حافظ','baladekama':'المدينة، بغداد'}}
    new=apply_controlled_terms(store,snapshot,changed,{key:empty_localization(value) for key,value in changed.items()},'tr')['4698']
    assert not new['fields']
    special={'4698':{**initial['4698'],'fields':{'wasf_rotba':[{'text':'Kişiye özel aktarım'}]}}}
    assert apply_controlled_terms(store,snapshot,records,special,'tr')['4698']['fields']['wasf_rotba']==special['4698']['fields']['wasf_rotba']
    revised={'4698':{**records['4698'],'death_year':'değişmiş kaynak'}}
    shifted=apply_controlled_terms(store,snapshot,revised,{key:empty_localization(value) for key,value in revised.items()},'tr')['4698']
    assert shifted['fields']['wasf_rotba'][0]['id']!=claim['id']
    assert not apply_controlled_terms(store,snapshot,records,initial,'en')['4698']['fields']
    compound={'4698':{**record,'wasf_rotba':'صدوق حسن الحديث'}}
    safe=apply_controlled_terms(store,snapshot,compound,{key:empty_localization(value) for key,value in compound.items()},'tr')['4698']['fields']['wasf_rotba'][0]
    assert 'hadisi hasen olarak nitelenmiş' not in safe['text']
    assert 'ravi nitelemeleri' in safe['text']
    assert any(ref['url']=='https://islamansiklopedisi.org.tr/mukaribul-hadis' for ref in safe['sources'])
    assert safe['status']=='needs_review'


def test_api_shows_automatic_term_origin_without_new_grade_or_false_completion(environment):
    from hadis_web.controlled_terms import load_controlled_terms
    settings,store,_=environment
    load_controlled_terms(store)
    # Humaydî's source rank is compound, so no partial substring rendering.
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    data=client.get('/api/narrator/4698').json()
    original=SourceReader(settings).narrator(4698)
    assert data['wasf_rotba']==original['wasf_rotba']
    assert not data['localization']['complete']
    from hadis_web.source import open_readonly
    with open_readonly(settings.source_db) as c:
        identity=c.execute("SELECT id FROM narrators WHERE wasf_rotba='ثقة' LIMIT 1").fetchone()[0]
    rendered=client.get(f'/api/narrator/{identity}').json()
    assert rendered['wasf_rotba']=='ثقة'
    assert rendered['localization']['fields']['wasf_rotba'][0]['translation_origin']=='controlled_vocabulary'
    fallback=TestClient(create_app(replace(settings,postgres_dsn=None)),base_url='http://127.0.0.1').get('/api/narrator/4698').json()
    assert fallback['localization']['available'] is False
    assert fallback['wasf_rotba']==data['wasf_rotba']


def test_queue_and_scope_identify_glossary_renderings_as_automatic_review_work(environment,tmp_path):
    from hadis_web.controlled_terms import load_controlled_terms, controlled_term_coverage
    from hadis_web.translation_queue import write_narrator_queue
    import json
    settings,store,_=environment
    load_controlled_terms(store)
    coverage=controlled_term_coverage(store,settings)
    assert coverage['potential_matching_cells']>=50000
    assert coverage['terms_available']==12 and coverage['person_specific_reviews_completed']==0
    output=tmp_path/'queue.jsonl'
    report=write_narrator_queue(store,settings,output)
    assert report['stages']['controlled_term_review']>0
    task=next(row for line in output.read_text(encoding='utf-8').splitlines() if (row:=json.loads(line))['stage']=='controlled_term_review')
    assert task['derived_from_claim_ids']
