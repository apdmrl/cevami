from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.source import SourceReader


def test_verified_critic_identity_can_supply_name_forms_outside_the_original_seven_people(environment,tmp_path):
    from hadis_web.opinions import load_critic_names
    settings,store,_=environment
    result=load_critic_names(store,settings)
    assert result['critic_names']==65 and result['pending_critics']==10
    assert load_critic_names(store,settings)==result
    with store.connection() as c:
        assert c.execute("SELECT count(*) AS n FROM localization_claims WHERE entity_type='critic'").fetchone()['n']==65
    original=SourceReader(settings).critic_opinions(30276,limit=100)
    data=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/30276/opinions?limit=100').json()
    mapped=[row for row in data['items'] if row['localization']['fields'].get('critic')]
    assert mapped
    assert all(row['critic']==raw['critic'] and row['opinion']==raw['opinion'] for row,raw in zip(data['items'],original['items']))
    claim=mapped[0]['localization']['fields']['critic'][0]
    assert claim['rendering_kind']=='name_form'
    assert claim['source_binding']['entity_type']=='critic'
    assert claim['expert_reviewed'] is False
    assert all('opinion' in row['localization']['pending_fields'] and not row['localization']['complete'] for row in data['items'])
    from hadis_web.opinions import load_opinion_pilot
    from hadis_web.translation_queue import write_narrator_queue
    import json
    load_opinion_pilot(store,settings)
    output=tmp_path/'queue.jsonl'
    write_narrator_queue(store,settings,output)
    task=next(row for line in output.read_text(encoding='utf-8').splitlines()
              if (row:=json.loads(line))['narrator_id']==4698 and row['field']=='critic_opinions')
    assert task['opinion_progress']['complete_opinions']==1
