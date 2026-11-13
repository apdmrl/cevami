import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.opinions import load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.localization import LocalizationStore
from hadis_web.source import SourceReader


def test_all_thirteen_name_records_have_immutable_history_and_explicit_support(environment,monkeypatch):
    from hadis_web import critic_name_reviews
    original_read=critic_name_reviews._read
    monkeypatch.setattr(critic_name_reviews,'_read',lambda filename:{**original_read(filename),'revision':'assistant-critic-name-reviews-20261101-v1','files':original_read(filename)['files'][:1]} if filename=='critic-name-review-batches.json' else original_read(filename))
    settings,store,snapshot=environment
    folder=Path(__file__).parents[1]/'hadis_web/data'
    original=folder/'critic-names-tr-v1.json'
    assert hashlib.sha256(original.read_bytes()).hexdigest()=='e6021dce85f841d054c62a53f1fe70c34241266dac5fb3d77c852f5a0a33cb24'
    load_critic_names(store,settings)
    result=load_critic_name_reviews(store,settings)
    assert result=={'revision':'assistant-critic-name-reviews-20261101-v1','batches':1,'critics':13,'claims':13,'claim_versions':13}
    data=json.loads((folder/'critic-name-reviews-tr-v1.json').read_text(encoding='utf-8'));entries=data['critics']
    assert len(entries)==13 and sum('supersedes_id' in e for e in entries)==3
    assert {e['alem_id'] for e in entries if e['status']=='problem_detected'}=={'2622'}
    records=SourceReader(settings).critic_records([e['alem_id'] for e in entries])
    localized=LocalizationStore(store).for_records(snapshot,'critic',records,'tr')
    for e in entries:
        key=e['alem_id'];assert e['expected_source']==records[key]
        cl=localized[key]['fields']['name'];assert len(cl)==1
        assert cl[0]['text']==e['text'] and cl[0]['status']==e['status'] and not cl[0]['expert_reviewed']
        assert cl[0]['translation_origin']=='assistant_reviewed_translation'
        assert cl[0]['turkish_availability']==e['translation_provenance']['turkish_availability']
        assert localized[key]['complete']==(e['status']=='source_compared')
    with store.connection() as c:
        before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
        assert len(before)==78
        active=c.execute("SELECT count(*) n FROM localization_claims x WHERE NOT EXISTS(SELECT 1 FROM localization_claims y WHERE y.supersedes_id=x.id)").fetchone()['n']
        assert active==75
    load_critic_names(store,settings);assert load_critic_name_reviews(store,settings)==result
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    rows=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/3443/opinions?limit=100').json()['items']
    amm=next(r for r in rows if str(r['alem_id'])=='2513')['localization']['fields']['critic'][0]
    assert amm['text']=='İbn Ammâr el-Mavsılî' and amm['status']=='source_compared'
    assert entries[9]['expected_source']['name']!=entries[9]['expected_source']['rawy_shohra']
