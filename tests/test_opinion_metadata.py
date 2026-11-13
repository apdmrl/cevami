import json
import pytest
import psycopg
from test_localization import environment
from hadis_web import opinions


@pytest.mark.parametrize('defect',['url','date','text','rationale','kind','language','status','parent'])
def test_late_root_opinion_metadata_failure_writes_no_earlier_claims(environment,tmp_path,monkeypatch,defect):
    settings,store,_=environment
    data=opinions.read_batch('critic-opinions-tr-v1.json')
    entry=data['narrators'][-1]['opinions'][-1]
    if defect in ('url','date'):
        data['sources']['bad']={'url':'javascript:alert(1)' if defect=='url' else 'gk45:test','title':'Test','locator':'Test','accessed_on':'2026-02-30' if defect=='date' else '2026-11-01'}
        entry['source_support']['bad']={'support_scope':'not_found'}
    elif defect=='language':data['language']='de'
    elif defect=='kind':entry['rendering_kind']='name_form'
    elif defect=='status':entry['status']='expert_approved'
    elif defect=='parent':entry['supersedes_id']='00000000-0000-0000-0000-000000000001'
    else:entry[defect]=' '
    (tmp_path/'pilot.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    (tmp_path/'opinion-batches.json').write_text(json.dumps({'files':['pilot.json']}),encoding='utf-8')
    monkeypatch.setattr(opinions,'DATA_FOLDER',tmp_path)
    with pytest.raises((ValueError,psycopg.Error)) as failure:opinions.load_opinion_batches(store,settings,include_critic_names=False)
    with store.connection() as c:assert c.execute('SELECT count(*) n FROM localization_claims').fetchone()['n']==0
    assert isinstance(failure.value,ValueError)
