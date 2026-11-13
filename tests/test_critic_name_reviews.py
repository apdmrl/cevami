import json
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.source import SourceReader
from hadis_web.localization import LocalizationStore,record_digest
from hadis_web.opinions import load_critic_names


def ids(store):
    with store.connection() as c:return {str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}


def setup(settings,store,tmp_path,monkeypatch,load=True):
    import hadis_web.critic_name_reviews as reviews
    if load:load_critic_names(store,settings)
    records=SourceReader(settings).critic_records(['1847','340','2671'])
    with store.connection() as c:
        parent=c.execute("SELECT id FROM localization_claims WHERE entity_type='critic' AND entity_key='2671'").fetchone()
    entries=[]
    for key in ('1847','340','2671'):
        raw=records[key]
        e={'alem_id':key,'field':'name','expected_source':raw,'expected_record_sha256':record_digest(raw),
           'text':{'1847':'Abdurrahman b. Yûsuf b. Saîd b. Hırâş','340':'Ahmed b. Batta b. İshak b. Velîd','2671':'Tahrîru Takrîbü’t-Tehzîb müellifleri'}[key],
           'rendering_kind':'name_form','status':'source_compared','review_scope':'arabic_critic_name',
           'source_support':{},'translation_provenance':{'translation_origin':'assistant_reviewed_translation','turkish_availability':'not_found_in_checked_sources'},
           'rationale':'Kaynakta yazılı adın dil aktarımıdır; yeni tarihsel kişi eşleştirmesi veya uzman onayı değildir.'}
        if key=='2671':e['supersedes_id']=str(parent['id']) if parent else '00000000-0000-0000-0000-000000000001'
        entries.append(e)
    from hadis_web.opinions import read_batch
    data={'revision':'test-names','reviewed_on':'2026-11-01','language':'tr','source_artifact_sha256':read_batch('critic-names-tr-v1.json')['source_artifact_sha256'],'sources':{},'critics':entries}
    monkeypatch.setattr(reviews,'DATA_FOLDER',tmp_path)
    (tmp_path/'critic-name-review-batches.json').write_text(json.dumps({'revision':'test','files':['last.json']}),encoding='utf-8')
    save(tmp_path,data)
    return reviews,data


def save(folder,data):
    (folder/'last.json').write_text(json.dumps(data),encoding='utf-8')


def test_roots_and_external_parent_preserve_critic_identity_and_history(environment,tmp_path,monkeypatch):
    settings,store,_=environment;reviews,data=setup(settings,store,tmp_path,monkeypatch);before=ids(store)
    result=reviews.load_critic_name_reviews(store,settings)
    assert result=={'revision':'test','batches':1,'critics':3,'claims':3,'claim_versions':3}
    after=ids(store);assert before<=after and len(after)-len(before)==3
    assert reviews.load_critic_name_reviews(store,settings)==result and ids(store)==after
    load_critic_names(store,settings);assert ids(store)==after
    rows=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/6796/opinions?limit=100').json()['items']
    row=next(r for r in rows if str(r['alem_id'])=='1847')
    cl=row['localization']['fields']['critic'][0]
    assert row['critic']==data['critics'][0]['expected_source']['name']
    assert cl['text']==data['critics'][0]['text'] and cl['status']=='source_compared' and not cl['expert_reviewed']
    assert cl['source_binding']['entity_type']=='critic' and cl['translation_origin']=='assistant_reviewed_translation'
    assert 'opinion' in row['localization']['pending_fields']


@pytest.mark.parametrize('defect',['missing','empty','null','other_person','language','entity','snapshot','record','field','url','date','text','provenance'])
def test_bad_last_entry_prevents_all_new_claims(environment,tmp_path,monkeypatch,defect):
    settings,store,snapshot=environment;reviews,data=setup(settings,store,tmp_path,monkeypatch)
    entry=data['critics'][-1];raw=entry['expected_source']
    if defect in ('missing','empty','null'):entry['supersedes_id']={'missing':'00000000-0000-0000-0000-000000000001','empty':'','null':None}[defect]
    elif defect=='other_person':
        with store.connection() as c:entry['supersedes_id']=str(c.execute("SELECT id FROM localization_claims WHERE entity_type='critic' AND entity_key='2513'").fetchone()['id'])
    elif defect in ('language','entity','snapshot','record'):
        args=dict(snapshot=snapshot,entity_type='critic',entity_key='2671',source_record=raw,field='name',language='tr',text='Test',rendering_kind='name_form',status='needs_review',actor_kind='assistant_source_review',sources=[{'url':'gk45:test','title':'Test','locator':'Test','accessed_on':'2026-11-01'}],rationale='Test.')
        if defect=='language':args['language']='de'
        elif defect=='entity':args.update(entity_type='narrator',source_record={**raw,'id':2671})
        elif defect=='snapshot':args['snapshot']=store.add_snapshot('test','other','b'*64,'test')
        else:args['source_record']={**raw,'death_date':'1'}
        entry['supersedes_id']=str(LocalizationStore(store).add_claim(**args))
    elif defect=='field':entry['field']='opinion'
    elif defect in ('url','date'):
        data['sources']['bad']={'url':'javascript:alert(1)' if defect=='url' else 'gk45:test','title':'Test','locator':'Test','accessed_on':'2026-02-30' if defect=='date' else '2026-11-01'}
        entry['source_support']['bad']={'support_scope':'not_found'}
    elif defect=='text':entry['text']=' '
    else:entry['translation_provenance']['translation_origin']='expert_translation'
    save(tmp_path,data);before=ids(store)
    with pytest.raises(ValueError):reviews.load_critic_name_reviews(store,settings)
    assert ids(store)==before


def test_missing_original_parent_prevents_earlier_new_roots(environment,tmp_path,monkeypatch):
    settings,store,_=environment;reviews,data=setup(settings,store,tmp_path,monkeypatch,load=False);before=ids(store)
    with pytest.raises(ValueError):reviews.load_critic_name_reviews(store,settings)
    assert ids(store)==before


def test_competing_root_or_external_child_does_not_branch(environment,tmp_path,monkeypatch):
    settings,store,snapshot=environment;reviews,data=setup(settings,store,tmp_path,monkeypatch)
    raw=data['critics'][0]['expected_source']
    LocalizationStore(store).add_claim(snapshot=snapshot,entity_type='critic',entity_key='1847',source_record=raw,field='name',language='tr',text='Other root',rendering_kind='name_form',status='needs_review',actor_kind='assistant_source_review',sources=[{'url':'gk45:test','title':'Test','locator':'Test','accessed_on':'2026-11-01'}],rationale='Test.')
    before=ids(store)
    with pytest.raises(ValueError):reviews.load_critic_name_reviews(store,settings)
    assert ids(store)==before


def test_existing_external_child_rejected(environment,tmp_path,monkeypatch):
    settings,store,_=environment;reviews,data=setup(settings,store,tmp_path,monkeypatch)
    reviews.load_critic_name_reviews(store,settings)
    before=ids(store);data['critics'][-1]['rationale']+=' Different branch.';save(tmp_path,data)
    with pytest.raises(ValueError):reviews.load_critic_name_reviews(store,settings)
    assert ids(store)==before


def test_forward_parent_is_rejected_even_when_already_in_database(environment,tmp_path,monkeypatch):
    settings,store,_=environment;reviews,data=setup(settings,store,tmp_path,monkeypatch)
    reviews.load_critic_name_reviews(store,settings);before=ids(store)
    with store.connection() as c:
        parent=c.execute("SELECT id FROM localization_claims x WHERE entity_type='critic' AND entity_key='2671' AND NOT EXISTS(SELECT 1 FROM localization_claims y WHERE y.supersedes_id=x.id)").fetchone()
    child=json.loads(json.dumps(data));child['critics']=child['critics'][-1:]
    child['critics'][0]['supersedes_id']=str(parent['id']);child['critics'][0]['text']+=' (topluluk etiketi)'
    (tmp_path/'child.json').write_text(json.dumps(child),encoding='utf-8')
    (tmp_path/'critic-name-review-batches.json').write_text(json.dumps({'revision':'test','files':['child.json','last.json']}),encoding='utf-8')
    with pytest.raises(ValueError,match='Forward'):reviews.load_critic_name_reviews(store,settings)
    assert ids(store)==before
