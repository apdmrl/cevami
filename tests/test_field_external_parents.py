import json
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.localization import LocalizationStore,load_localization_pilot,record_digest
from hadis_web.source import SourceReader
import hadis_web.field_reviews as reviews


def ids(store):
    with store.connection() as c:return {str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}


def setup(store,settings,tmp_path,monkeypatch):
    load_localization_pilot(store,settings)
    original=json.loads(reviews.DATA_FILE.read_text(encoding='utf-8'))
    original['people']=original['people'][:1]
    original['people'][0]['fields']=original['people'][0]['fields'][:1]
    raw=SourceReader(settings).narrator_records([4698])['4698']
    with store.connection() as c:
        parents={r['field']:r for r in c.execute("SELECT * FROM localization_claims c WHERE entity_type='narrator' "
            "AND entity_key='4698' AND language='tr' AND NOT EXISTS(SELECT 1 FROM localization_claims n WHERE n.supersedes_id=c.id)")}
    entries=[]
    for field in ('name','wasf_rotba'):
        entries.append({'field':field,'expected_arabic':raw[field],'text':parents[field]['translated_text'],
            'supersedes_id':str(parents[field]['id']),'rendering_kind':parents[field]['rendering_kind'],
            'review_scope':'arabic_field_translation','person_fact_support':'not_independently_confirmed',
            'status':'source_compared','source_support':{},
            'translation_provenance':{'translation_origin':'assistant_reviewed_translation','turkish_availability':'not_found_in_checked_sources'},
            'rationale':'Test: Arapça alanın dil aktarımı; tarihsel teyit veya uzman onayı değildir.'})
    data={'revision':'test-external-parent','language':'tr','reviewed_on':'2026-11-01',
        'source_artifact_sha256':original['source_artifact_sha256'],'sources':{},
        'people':[{'id':4698,'expected_record_sha256':record_digest(raw),'expected_source':raw,'fields':entries}]}
    (tmp_path/'first.json').write_text(json.dumps(original),encoding='utf-8')
    (tmp_path/'last.json').write_text(json.dumps(data),encoding='utf-8')
    (tmp_path/'field-review-batches.json').write_text(json.dumps({'revision':'test-registry','files':['first.json','last.json']}),encoding='utf-8')
    monkeypatch.setattr(reviews,'DATA_FOLDER',tmp_path)
    return data,parents


def save(tmp_path,data):
    (tmp_path/'last.json').write_text(json.dumps(data),encoding='utf-8')


def test_existing_pilot_parents_preserve_history_active_leaf_and_reimport(environment,tmp_path,monkeypatch):
    settings,store,_=environment;data,parents=setup(store,settings,tmp_path,monkeypatch);before=ids(store)
    result=reviews.load_field_review_batches(store,settings)
    assert result=={'revision':'test-registry','batches':2,'people':2,'claims':3}
    after=ids(store);assert before<=after and len(after)-len(before)==3
    assert reviews.load_field_review_batches(store,settings)==result and ids(store)==after
    load_localization_pilot(store,settings);assert ids(store)==after
    profile=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/4698').json()
    for entry in data['people'][0]['fields']:
        cl=profile['localization']['fields'][entry['field']]
        assert len(cl)==1 and cl[0]['status']=='source_compared'
        assert cl[0]['id']!=str(parents[entry['field']]['id']) and cl[0]['expert_reviewed'] is False
        assert cl[0]['translation_origin']=='assistant_reviewed_translation'
        assert profile[entry['field']]==entry['expected_arabic']
    assert profile['localization']['complete'] is False


@pytest.mark.parametrize('defect',['missing','empty_parent','null_parent','other_field','other_person','language','snapshot','record','url','date','kind','empty_text'])
def test_invalid_external_parent_or_late_metadata_adds_no_claims(environment,tmp_path,monkeypatch,defect):
    settings,store,snapshot=environment;data,parents=setup(store,settings,tmp_path,monkeypatch)
    entry=data['people'][0]['fields'][-1]
    if defect=='missing':entry['supersedes_id']='00000000-0000-0000-0000-000000000001'
    elif defect=='empty_parent':entry['supersedes_id']=''
    elif defect=='null_parent':entry['supersedes_id']=None
    elif defect=='other_field':entry['supersedes_id']=str(parents['name']['id'])
    elif defect=='other_person':
        with store.connection() as c:
            entry['supersedes_id']=str(c.execute("SELECT id FROM localization_claims WHERE entity_key='6817' AND field='name' LIMIT 1").fetchone()['id'])
    elif defect in ('language','snapshot','record'):
        raw=data['people'][0]['expected_source']
        args=dict(snapshot=snapshot,entity_type='narrator',entity_key='4698',source_record=raw,
            field=entry['field'],language='de' if defect=='language' else 'tr',text='Test başka bağ.',
            rendering_kind='translation',status='needs_review',actor_kind='assistant_source_review',
            sources=[{'url':'gk45:test','title':'Test','locator':'test','accessed_on':'2026-11-01'}],rationale='Test.')
        if defect=='snapshot':args['snapshot']=store.add_snapshot('gk45','other','a'*64,'other.db')
        elif defect=='record':args['source_record']={**raw,'age':'test'}
        entry['supersedes_id']=str(LocalizationStore(store).add_claim(**args))
    elif defect in ('url','date'):
        data['sources']['invalid']={'url':'javascript:alert(1)' if defect=='url' else 'gk45:test',
            'title':'Test','locator':'test','accessed_on':'2026-02-30' if defect=='date' else '2026-11-01'}
        entry['source_support']['invalid']={'support_scope':'not_found'}
    elif defect=='kind':entry['rendering_kind']='source_summary'
    else:entry['text']=' '
    save(tmp_path,data);before=ids(store)
    with pytest.raises(ValueError):reviews.load_field_review_batches(store,settings)
    assert ids(store)==before


def test_external_correction_branch_is_rejected_before_other_new_fields(environment,tmp_path,monkeypatch):
    settings,store,snapshot=environment;data,_=setup(store,settings,tmp_path,monkeypatch)
    entry=data['people'][0]['fields'][-1]
    LocalizationStore(store).add_claim(snapshot=snapshot,entity_type='narrator',entity_key='4698',
        source_record=data['people'][0]['expected_source'],field=entry['field'],language='tr',
        text='Başka incelemedeki düzeltme.',rendering_kind='translation',status='needs_review',actor_kind='assistant_source_review',
        sources=[{'url':'gk45:test','title':'Test','locator':'test','accessed_on':'2026-11-01'}],
        rationale='Test dış dalı.',supersedes_id=entry['supersedes_id'])
    before=ids(store)
    with pytest.raises(ValueError,match='branch'):reviews.load_field_review_batches(store,settings)
    assert ids(store)==before


def test_forward_registry_parent_rejected_even_if_all_claims_exist(environment,tmp_path,monkeypatch):
    settings,store,_=environment;data,_=setup(store,settings,tmp_path,monkeypatch)
    reviews.load_field_review_batches(store,settings)
    entry=data['people'][0]['fields'][0]
    with store.connection() as c:
        child=str(c.execute('SELECT id FROM localization_claims WHERE supersedes_id=%s',(entry['supersedes_id'],)).fetchone()['id'])
    second=json.loads(json.dumps(data));second['people'][0]['fields']=second['people'][0]['fields'][:1]
    second['people'][0]['fields'][0].update(supersedes_id=child,rationale='İkinci test incelemesi.')
    (tmp_path/'second.json').write_text(json.dumps(second),encoding='utf-8')
    reg=tmp_path/'field-review-batches.json'
    reg.write_text(json.dumps({'revision':'chain','files':['first.json','last.json','second.json']}),encoding='utf-8')
    assert reviews.load_field_review_batches(store,settings)['claim_versions']==4
    before=ids(store)
    reg.write_text(json.dumps({'revision':'reverse','files':['second.json','first.json','last.json']}),encoding='utf-8')
    with pytest.raises(ValueError,match='Forward'):reviews.load_field_review_batches(store,settings)
    assert ids(store)==before


def test_missing_registry_revision_prevents_all_writes(environment,tmp_path,monkeypatch):
    settings,store,_=environment;setup(store,settings,tmp_path,monkeypatch)
    (tmp_path/'field-review-batches.json').write_text(json.dumps({'files':['first.json','last.json']}),encoding='utf-8')
    before=ids(store)
    with pytest.raises(ValueError,match='revision'):reviews.load_field_review_batches(store,settings)
    assert ids(store)==before
