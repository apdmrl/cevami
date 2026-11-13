from collections import Counter
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.opinions import load_opinion_batches
from hadis_web.opinion_reviews import load_opinion_reviews


def test_all_first_chain_drafts_have_immutable_reviews_and_four_unresolved_issues(environment,monkeypatch):
    from hadis_web import opinions
    original=opinions.read_batch
    monkeypatch.setattr(opinions,'read_batch',lambda filename:{**original(filename),'files':original(filename)['files'][:4]} if filename=='opinion-batches.json' else original(filename))
    settings,store,_=environment
    load_opinion_batches(store,settings,include_critic_names=False)
    with store.connection() as c:
        roots={str(r['id']):r for r in c.execute('SELECT * FROM localization_claims')}
    assert len(roots)==130
    result=load_opinion_reviews(store,settings)
    assert result=={'revision':'opinion-language-review-batches-v2','batches':2,'people':7,'claims':110,'claim_versions':110}
    with store.connection() as c:
        rows=c.execute('SELECT * FROM localization_claims').fetchall()
    assert len(rows)==240 and all(str(r['id']) in {str(v['id']) for v in rows} for r in roots.values())
    assert load_opinion_reviews(store,settings)==result
    assert load_opinion_batches(store,settings,include_critic_names=False)['opinion_claims']==130
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');found={};counts=Counter()
    expected_counts={4698:12,3443:28,6817:41,8272:21,6796:15,5719:6,5913:7}
    issues={(3443,'1051'),(3443,'2821'),(8272,'1555'),(5913,'936')}
    for pid,total in expected_counts.items():
        page=api.get(f'/api/narrator/{pid}/opinions?limit=100').json()
        assert len(page['items'])==total
        for row in page['items']:
            claims=row['localization']['fields']['opinion'];assert len(claims)==1
            cl=claims[0];key=(pid,str(row['alem_id']));found[key]=(row,cl);counts[cl['status']]+=1
            assert not cl['expert_reviewed'] and row['source_occurrences']==2
            assert (cl['status']=='problem_detected')==(key in issues)
            assert ('opinion' in row['localization']['pending_fields'])==(key in issues)
    assert counts=={'source_compared':126,'problem_detected':4}
    assert found[(3443,'1051')][1]['text'].endswith('…')
    assert 'أحال' not in found[(3443,'1051')][0]['opinion']
    assert 'قمطة' in found[(3443,'2821')][1]['text']
    assert 'Kımta' not in found[(3443,'2821')][1]['text']
    assert 'yirmi derece' in found[(6817,'839')][1]['text'] and 'bin lanet' in found[(6817,'839')][1]['text']
    assert 'salât ve selâm' in found[(5913,'1385')][1]['text'] and 'salât ve selâm' in found[(5913,'239')][1]['text']
    assert 'Mecdüddin' in found[(5913,'936')][1]['rationale'] and 'İzzeddin' in found[(5913,'936')][1]['rationale']
    assert '“Hasenü’l-hadîs”' in found[(6796,'2136')][1]['text'] and 'oğlu zayıf' in found[(6796,'2136')][1]['text']
    assert 'Sahîhü’l-hadîs' in found[(6796,'1125')][1]['text']
    # Older compared roots keep the same IDs, not new blanket status versions.
    for identity,root in roots.items():
        if root['status']=='source_compared':
            row,claim=found[(int(root['source_record']['narrator_id']),root['source_record']['alem_id'])]
            assert claim['id']==identity
    with store.connection() as c:assert c.execute('SELECT count(*) n FROM localization_claims').fetchone()['n']==240
