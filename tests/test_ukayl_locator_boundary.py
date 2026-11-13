import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))

def test_uncertain_physical_page_becomes_precise_section_without_rewriting_translations():
    old=read('narrator-field-reviews-tr-v17.json');new=read('narrator-field-reviews-tr-v18.json')
    assert len(new['people'])==1 and new['people'][0]['id']==5688
    parent=next(p for p in old['people'] if p['id']==5688);child=new['people'][0]
    assert parent['expected_source']==child['expected_source'] and parent['expected_record_sha256']==child['expected_record_sha256']
    before={e['field']:e for e in parent['fields']};assert len(child['fields'])==len(before)==9
    for e in child['fields']:
        previous=before[e['field']]
        assert e['supersedes_id'] and all(e[k]==previous[k] for k in ('expected_arabic','text','status','translation_provenance','person_fact_support','rendering_kind'))
        assert 'kesinliği geri çekildi' in e['rationale']
    locator=new['sources']['kandirali']['locator']
    assert 'Hadis33' in locator and '3. Ukayl b. Hâlid el-Eylî' in locator
    assert 'Basılı sayfa numarası doğrulanmadı' in locator and '98–99' not in locator and '97–98' not in locator
    assert 'basılı99' not in str(child['fields'])
    assert hashlib.sha256((FOLDER/'narrator-field-reviews-tr-v17.json').read_bytes()).hexdigest()=='37dc9d567a7354bd03b2d1754a7d6b9d1b86a1def499078d8e65efe7b00cb14e'

def test_nine_citation_children_replace_only_ukayl_heads_and_preserve_all_history(environment):
    settings,store,_=environment;old=read('narrator-field-reviews-tr-v17.json');new=read('narrator-field-reviews-tr-v18.json')
    assert _load_datasets(store,settings,[old,new])==dict(people=2,claims=19,claim_versions=28)
    registry=read('field-review-batches.json');assert registry['files'][17]=='narrator-field-reviews-tr-v18.json'
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/5688').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1;cl=claims[0]
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['expert_reviewed'] is False
        assert profile[e['field']]==e['expected_arabic'] and cl['actor_kind']=='assistant_source_review'
        assert any('Basılı sayfa numarası doğrulanmadı' in r.get('locator','') for r in cl['sources'])
        with store.connection() as c:
            parent=c.execute('SELECT * FROM localization_claims WHERE id=%s',(e['supersedes_id'],)).fetchone()
            child=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert str(child['supersedes_id'])==e['supersedes_id'] and parent['translated_text']==child['translated_text']==e['text']
        assert parent['source_record']==child['source_record']==new['people'][0]['expected_source']
    musa=api.get('/api/narrator/7721').json();assert sum(len(v) for v in musa['localization']['fields'].values())==10
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')};assert len(before)==28
    _load_datasets(store,settings,[old,new])
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
