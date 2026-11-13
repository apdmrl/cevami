import json
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.localization import LocalizationStore
from hadis_web.opinions import load_opinion_pilot,DATA_FOLDER as ORIGINAL_DATA


def ids(store):
    with store.connection() as c:return {str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}


def registry(settings,store,tmp_path,monkeypatch):
    import hadis_web.opinion_reviews as reviews
    load_opinion_pilot(store,settings)
    old=json.loads((ORIGINAL_DATA/'critic-opinions-tr-v1.json').read_text(encoding='utf-8'))
    with store.connection() as c:
        parents={r['entity_key']:str(r['id']) for r in c.execute("SELECT id,entity_key FROM localization_claims WHERE field='opinion'")}
    selected=[e for e in old['narrators'][0]['opinions'] if e['expected_source']['alem_id'] in ('431','924')]
    for e in selected:
        e.update(field='opinion',supersedes_id=parents[e['key']],status='source_compared',review_scope='arabic_opinion_translation')
        e['translation_provenance']['translation_origin']='assistant_reviewed_translation'
        e['rationale']='Test: Arapça görüşün dil aktarımı karşılaştırıldı; atfın tarihsel teyidi veya uzman onayı değildir.'
    data={**old,'language':'tr','revision':'test-opinion-review','narrators':[{'id':4698,'expected_opinion_count':12,'opinions':selected}]}
    (tmp_path/'reviews.json').write_text(json.dumps(data),encoding='utf-8')
    (tmp_path/'opinion-review-batches.json').write_text(json.dumps({'revision':'test-reviews','files':['reviews.json']}),encoding='utf-8')
    monkeypatch.setattr(reviews,'DATA_FOLDER',tmp_path)
    return reviews,data


def save(tmp_path,data):
    (tmp_path/'reviews.json').write_text(json.dumps(data),encoding='utf-8')


def test_opinion_review_preserves_history_attribution_counts_and_reimport(environment,tmp_path,monkeypatch):
    from hadis_web.opinion_reviews import load_opinion_reviews
    settings,store,_=environment;_,data=registry(settings,store,tmp_path,monkeypatch)
    before=ids(store);result=load_opinion_reviews(store,settings)
    assert result=={'revision':'test-reviews','batches':1,'people':1,'claims':2,'claim_versions':2}
    assert len(ids(store))==14 and before<=ids(store)
    assert load_opinion_reviews(store,settings)==result and len(ids(store))==14
    # Original import remains idempotent after the newer review exists.
    assert load_opinion_pilot(store,settings)['claims']==12 and len(ids(store))==14
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');rows=api.get('/api/narrator/4698/opinions?limit=100').json()['items']
    assert len(rows)==12 and all(r['source_occurrences']==2 for r in rows)
    by_id={str(r['alem_id']):r for r in rows}
    for critic,number in [('431','yirmi yıl'),('924','on dokuz yıl')]:
        cl=by_id[critic]['localization']['fields']['opinion'][0]
        assert number in cl['text'] and cl['status']=='source_compared'
        assert cl['translation_origin']=='assistant_reviewed_translation' and cl['expert_reviewed'] is False
        assert len(by_id[critic]['localization']['fields']['opinion'])==1
    assert by_id['924']['critic'].startswith('عبد الرحمن')
    assert 'critic_opinions' in api.get('/api/narrator/4698').json()['localization']['pending_fields']


@pytest.mark.parametrize('defect',['source','missing_parent','other_parent','status','summary','source_reference'])
def test_invalid_last_opinion_review_adds_no_claims(environment,tmp_path,monkeypatch,defect):
    settings,store,_=environment;reviews,data=registry(settings,store,tmp_path,monkeypatch)
    entry=data['narrators'][0]['opinions'][-1]
    if defect=='source':entry['expected_source']['opinion']+='x'
    elif defect=='missing_parent':entry['supersedes_id']='00000000-0000-0000-0000-000000000001'
    elif defect=='other_parent':entry['supersedes_id']=data['narrators'][0]['opinions'][0]['supersedes_id']
    elif defect=='status':entry['status']='needs_review'
    elif defect=='summary':entry['rendering_kind']='source_summary'
    else:data['sources']['tdv']['url']='javascript:alert(1)'
    save(tmp_path,data);before=ids(store)
    with pytest.raises(ValueError):reviews.load_opinion_reviews(store,settings)
    assert ids(store)==before


def test_external_opinion_correction_branch_is_rejected_before_any_new_write(environment,tmp_path,monkeypatch):
    settings,store,snapshot=environment;reviews,data=registry(settings,store,tmp_path,monkeypatch)
    entry=data['narrators'][0]['opinions'][-1]
    original=entry['expected_source'];local=LocalizationStore(store)
    local.add_claim(snapshot=snapshot,entity_type='critic_opinion',entity_key=entry['key'],source_record=original,
        field='opinion',language='tr',text='Dış incelemede farklı bir düzeltme.',rendering_kind='translation',
        status='needs_review',actor_kind='assistant_source_review',sources=[{'url':'gk45:test','title':'Test','locator':'test','accessed_on':'2026-11-01'}],
        rationale='Test dalı.',supersedes_id=entry['supersedes_id'])
    before=ids(store)
    with pytest.raises(ValueError,match='branch'):reviews.load_opinion_reviews(store,settings)
    assert ids(store)==before


@pytest.mark.parametrize('difference',['language','snapshot','field'])
def test_opinion_parent_requires_same_language_snapshot_and_field(environment,tmp_path,monkeypatch,difference):
    settings,store,snapshot=environment;reviews,data=registry(settings,store,tmp_path,monkeypatch)
    entry=data['narrators'][0]['opinions'][-1]
    args=dict(snapshot=snapshot,entity_type='critic_opinion',entity_key=entry['key'],source_record=entry['expected_source'],
        field='opinion',language='tr',text='Farklı bağdaki taslak.',rendering_kind='translation',status='needs_review',
        actor_kind='assistant_source_review',sources=[{'url':'gk45:test','title':'Test','locator':'test','accessed_on':'2026-11-01'}],rationale='Test.')
    if difference=='language':args['language']='de'
    elif difference=='field':args['field']='critic'
    else:args['snapshot']=store.add_snapshot('gk45','other','a'*64,'other.db')
    entry['supersedes_id']=str(LocalizationStore(store).add_claim(**args));save(tmp_path,data);before=ids(store)
    with pytest.raises(ValueError,match='binding'):reviews.load_opinion_reviews(store,settings)
    assert ids(store)==before


def test_ordered_opinion_history_rejects_forward_parent_even_after_import(environment,tmp_path,monkeypatch):
    settings,store,_=environment;reviews,data=registry(settings,store,tmp_path,monkeypatch)
    reviews.load_opinion_reviews(store,settings)
    first=data['narrators'][0]['opinions'][0]
    with store.connection() as c:
        child=c.execute('SELECT id FROM localization_claims WHERE supersedes_id=%s',(first['supersedes_id'],)).fetchone()
    second=json.loads(json.dumps(data));second['revision']='test-second'
    second['narrators'][0]['opinions']=[second['narrators'][0]['opinions'][0]]
    entry=second['narrators'][0]['opinions'][0];entry['supersedes_id']=str(child['id']);entry['rationale']+=' İkinci dil incelemesi.'
    (tmp_path/'second.json').write_text(json.dumps(second),encoding='utf-8')
    index=tmp_path/'opinion-review-batches.json'
    index.write_text(json.dumps({'revision':'chain','files':['reviews.json','second.json']}),encoding='utf-8')
    assert reviews.load_opinion_reviews(store,settings)['claim_versions']==3
    assert len(ids(store))==15
    index.write_text(json.dumps({'revision':'reversed','files':['second.json','reviews.json']}),encoding='utf-8');before=ids(store)
    with pytest.raises(ValueError,match='Forward'):reviews.load_opinion_reviews(store,settings)
    assert ids(store)==before


def test_missing_registry_revision_fails_before_any_opinion_write(environment,tmp_path,monkeypatch):
    settings,store,_=environment;reviews,_=registry(settings,store,tmp_path,monkeypatch)
    (tmp_path/'opinion-review-batches.json').write_text(json.dumps({'files':['reviews.json']}),encoding='utf-8')
    before=ids(store)
    with pytest.raises(ValueError,match='revision'):reviews.load_opinion_reviews(store,settings)
    assert ids(store)==before


def test_real_humaydi_reviews_keep_twelve_active_opinions_and_older_full_support(environment,monkeypatch):
    import hadis_web.opinion_reviews as reviews
    original=reviews._read
    monkeypatch.setattr(reviews,'_read',lambda f: {'revision':'opinion-language-review-batches-v1',
        'files':['humaydi-opinion-reviews-tr-v1.json']} if f=='opinion-review-batches.json' else original(f))
    from hadis_web.opinion_reviews import load_opinion_reviews
    settings,store,_=environment;load_opinion_pilot(store,settings);before=ids(store)
    result=load_opinion_reviews(store,settings)
    assert result['claims']==11 and result['people']==1
    assert len(ids(store))==23 and before<=ids(store)
    assert load_opinion_reviews(store,settings)==result
    rows=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/4698/opinions?limit=100').json()['items']
    assert len(rows)==12
    assert all(len(r['localization']['fields']['opinion'])==1 for r in rows)
    assert all(r['localization']['fields']['opinion'][0]['status']=='source_compared' for r in rows)
    sad=next(r for r in rows if str(r['alem_id'])=='2463')['localization']['fields']['opinion'][0]
    assert sad['id'] in before and sad['translation_origin']=='source_supported_rendering'
    assert all(not r['localization']['fields']['opinion'][0]['expert_reviewed'] for r in rows)
