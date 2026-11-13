import pytest
import json
import hashlib
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.config import Settings
from hadis_web.source import SourceReader
from hadis_web.app import create_app


def test_assistant_field_review_is_person_bound_idempotent_and_replaces_only_automatic_rendering(environment):
    from hadis_web.field_reviews import load_field_reviews
    from hadis_web.controlled_terms import load_controlled_terms
    settings,store,_=environment
    load_controlled_terms(store)
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    before=client.get('/api/narrator/118').json()
    assert before['localization']['fields']['wasf_rotba'][0]['actor_kind']=='automated_check'
    first=load_field_reviews(store,settings)
    assert first['people']==4 and first['claims']==12
    assert load_field_reviews(store,settings)==first
    from hadis_web.controlled_terms import controlled_term_coverage
    assert controlled_term_coverage(store,settings)['assistant_reviewed_field_cells']==8
    after=client.get('/api/narrator/118').json()
    claim=after['localization']['fields']['wasf_rotba'][0]
    assert claim['actor_kind']=='assistant_source_review' and claim['status']=='source_compared'
    assert claim['translation_origin']=='assistant_reviewed_translation'
    assert claim['expert_reviewed'] is False
    assert after['wasf_rotba']==before['wasf_rotba']=='ثقة'
    assert 'wasf_rotba' not in after['localization']['pending_fields']
    assert after['localization']['complete'] is False
    assert any(ref.get('review_scope')=='arabic_field_translation' for ref in claim['sources'])
    other=client.get('/api/narrator/4574').json()['localization']['fields']['wasf_rotba'][0]
    assert other['actor_kind']=='automated_check' and other['status']=='needs_review'
    compound=client.get('/api/narrator/130').json()['localization']['fields']['wasf_rotba'][0]
    assert 'ravi nitelemeleri' in compound['text'] and 'hadisi hasen olarak' not in compound['text']


def test_all_person_bindings_are_checked_before_any_field_review_write(environment,monkeypatch):
    from hadis_web.field_reviews import load_field_reviews
    settings,store,_=environment
    original=SourceReader.narrator_records
    def changed(self,ids):
        records=original(self,ids)
        if '133' in records: records['133']['death_year']='changed'
        return records
    monkeypatch.setattr(SourceReader,'narrator_records',changed)
    with pytest.raises(ValueError,match='record changed'):
        load_field_reviews(store,settings)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0


def review_registry(tmp_path,monkeypatch):
    import hadis_web.field_reviews as reviews
    data=json.loads(reviews.DATA_FILE.read_text(encoding='utf-8'))
    for name,people in [('first.json',data['people'][:2]),('second.json',data['people'][2:])]:
        (tmp_path/name).write_text(json.dumps({**data,'people':people}),encoding='utf-8')
    (tmp_path/'field-review-batches.json').write_text(json.dumps({'revision':'test-review-registry',
        'files':['first.json','second.json']}),encoding='utf-8')
    monkeypatch.setattr(reviews,'DATA_FOLDER',tmp_path)
    return reviews


def test_multiple_review_batches_preserve_claim_ids_and_are_idempotent(environment,tmp_path,monkeypatch):
    settings,store,_=environment
    from hadis_web.field_reviews import load_field_reviews
    load_field_reviews(store,settings)
    with store.connection() as c:
        old_ids={r['id'] for r in c.execute('SELECT id FROM localization_claims')}
    reviews=review_registry(tmp_path,monkeypatch)
    result=reviews.load_field_review_batches(store,settings)
    assert result=={'revision':'test-review-registry','batches':2,'people':4,'claims':12}
    assert reviews.load_field_review_batches(store,settings)==result
    with store.connection() as c:
        assert {r['id'] for r in c.execute('SELECT id FROM localization_claims')}==old_ids


def test_last_batch_record_drift_is_rejected_before_any_batch_writes(environment,tmp_path,monkeypatch):
    settings,store,_=environment
    reviews=review_registry(tmp_path,monkeypatch)
    path=tmp_path/'second.json'; data=json.loads(path.read_text(encoding='utf-8'))
    data['people'][-1]['expected_record_sha256']='0'*64
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='record changed'):
        reviews.load_field_review_batches(store,settings)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0


@pytest.mark.parametrize('files',[[],['first.json','first.json'],['../outside.json'],['C:/outside.json']])
def test_invalid_review_registry_writes_nothing(environment,tmp_path,monkeypatch,files):
    settings,store,_=environment
    reviews=review_registry(tmp_path,monkeypatch)
    (tmp_path/'field-review-batches.json').write_text(json.dumps({'revision':'invalid','files':files}),encoding='utf-8')
    with pytest.raises(ValueError):
        reviews.load_field_review_batches(store,settings)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0


def test_same_person_field_in_two_batches_is_rejected(environment,tmp_path,monkeypatch):
    settings,store,_=environment
    reviews=review_registry(tmp_path,monkeypatch)
    first=json.loads((tmp_path/'first.json').read_text(encoding='utf-8'))
    second=json.loads((tmp_path/'second.json').read_text(encoding='utf-8'))
    second['people'].append(first['people'][0])
    (tmp_path/'second.json').write_text(json.dumps(second),encoding='utf-8')
    with pytest.raises(ValueError,match='uplicat'):
        reviews.load_field_review_batches(store,settings)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0


def test_review_problem_is_not_promoted_or_hidden_by_glossary(environment,tmp_path,monkeypatch):
    settings,store,_=environment
    from hadis_web.controlled_terms import load_controlled_terms
    load_controlled_terms(store)
    reviews=review_registry(tmp_path,monkeypatch)
    path=tmp_path/'first.json';data=json.loads(path.read_text(encoding='utf-8'))
    entry=next(e for e in data['people'][0]['fields'] if e['field']=='wasf_rotba')
    entry['status']='problem_detected'
    entry['text']='Kaynak ifadesi için inceleme sorunu kaydedildi.'
    path.write_text(json.dumps(data),encoding='utf-8')
    reviews.load_field_review_batches(store,settings)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/2').json()
    local=api['localization'];claim=local['fields']['wasf_rotba'][0]
    assert claim['status']=='problem_detected' and claim['actor_kind']=='assistant_source_review'
    assert claim['text']==entry['text'] and claim['expert_reviewed'] is False
    assert 'wasf_rotba' in local['pending_fields'] and local['complete'] is False


@pytest.mark.parametrize('status',['needs_review','approved','unexpected'])
def test_unreviewed_or_unknown_outcomes_rejected_before_writes(environment,tmp_path,monkeypatch,status):
    settings,store,_=environment
    reviews=review_registry(tmp_path,monkeypatch)
    path=tmp_path/'second.json';data=json.loads(path.read_text(encoding='utf-8'))
    data['people'][-1]['fields'][-1]['status']=status
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='scope or outcome'):
        reviews.load_field_review_batches(store,settings)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0


def test_new_review_data_preserves_variants_and_does_not_merge_namesakes(environment,monkeypatch):
    from hadis_web.field_reviews import load_field_review_batches,DATA_FILE,DATA_FOLDER
    from hadis_web.localization import NARRATOR_FIELDS,record_digest
    settings,store,_=environment
    assert hashlib.sha256(DATA_FILE.read_bytes()).hexdigest()=='fd95956fe8b4e799a9a999a56dccee2c85b2c309446414ae0989520b33561fbf'
    # Preserve the historical two-batch regression when further batches are added.
    import hadis_web.field_reviews as reviews
    original=reviews._read_batch
    def first_two(filename):
        if filename=='field-review-batches.json':
            return {'revision':'historical-v2','files':['narrator-field-reviews-tr-v1.json','narrator-field-reviews-tr-v2.json']}
        return original(filename)
    monkeypatch.setattr(reviews,'_read_batch',first_two)
    result=load_field_review_batches(store,settings)
    assert result['batches']==2 and result['people']==11 and result['claims']==79
    assert load_field_review_batches(store,settings)==result
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v2.json').read_text(encoding='utf-8'))
    records=SourceReader(settings).narrator_records([p['id'] for p in data['people']])
    for person in data['people']:
        raw=records[str(person['id'])]
        assert record_digest(raw)==person['expected_record_sha256']
        assert {e['field'] for e in person['fields']}=={f for f in NARRATOR_FIELDS if raw.get(f)}
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    nafi=client.get('/api/narrator/7863').json()
    assert nafi['death_year']=='116'
    alternative=nafi['localization']['fields']['badeel'][0]
    assert 'Nâfe' in alternative['text'] and alternative['expert_reviewed'] is False
    assert alternative['turkish_availability']=='partial_support'
    assert any(ref.get('person_fact_support')=='not_independently_confirmed' for ref in alternative['sources'])
    assert nafi['localization']['complete'] is False  # Critic opinions still await translation.
    ibn_omer=client.get('/api/narrator/4967').json()
    assert ibn_omer['localization']['fields']['shohra'][0]['status']=='source_compared'
    namesake=client.get('/api/narrator/4968').json()
    assert not namesake['localization']['fields'].get('shohra')
    said=client.get('/api/narrator/3299').json()
    assert said['death_year']=='92'
    assert any('94' in c['rationale'] for c in said['localization']['fields']['shohra'])


def test_third_batch_preserves_source_problems_and_qualifications(environment,monkeypatch):
    from hadis_web.field_reviews import load_field_review_batches,DATA_FOLDER
    from hadis_web.localization import NARRATOR_FIELDS,record_digest
    settings,store,_=environment
    import hadis_web.field_reviews as reviews
    original=reviews._read_batch
    def first_three(filename):
        if filename=='field-review-batches.json':
            return {'revision':'historical-v3','files':[f'narrator-field-reviews-tr-v{i}.json' for i in (1,2,3)]}
        return original(filename)
    monkeypatch.setattr(reviews,'_read_batch',first_three)
    assert hashlib.sha256((DATA_FOLDER/'narrator-field-reviews-tr-v2.json').read_bytes()).hexdigest()=='2488e353ec405f1e11f3d5ebb4b119e7737550e4a9264498d4ad71d0116958dc'
    result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'])==(3,21,183)
    assert load_field_review_batches(store,settings)==result
    data=json.loads((DATA_FOLDER/'narrator-field-reviews-tr-v3.json').read_text(encoding='utf-8'))
    raw=SourceReader(settings).narrator_records([p['id'] for p in data['people']])
    states=[]
    for person in data['people']:
        record=raw[str(person['id'])]
        assert record==person['expected_source'] and record_digest(record)==person['expected_record_sha256']
        assert {e['field'] for e in person['fields']}=={f for f in NARRATOR_FIELDS if record.get(f)}
        states.extend(e['status'] for e in person['fields'])
    assert states.count('source_compared')==101 and states.count('problem_detected')==3
    client=TestClient(create_app(settings),base_url='http://127.0.0.1')
    eyyub=client.get('/api/narrator/746').json()
    assert eyyub['wasf_rotba']=='ثقة ثبتت حجة'
    for field in ('wasf_rotba','baladwafa'):
        assert eyyub['localization']['fields'][field][0]['status']=='problem_detected'
        assert field in eyyub['localization']['pending_fields']
    enes=client.get('/api/narrator/720').json()
    assert enes['lakab']=='ذو الأدنين'
    assert enes['localization']['fields']['lakab'][0]['status']=='problem_detected'
    sevri=client.get('/api/narrator/3436').json()['localization']['fields']['wasf_rotba'][0]
    assert 'bazen tedlîs' in sevri['text'] and sevri['expert_reviewed'] is False
    katade=client.get('/api/narrator/6458').json()['localization']['fields']['wasf_rotba'][0]
    assert 'tedlîsle tanınan' in katade['text']
    sirin=client.get('/api/narrator/7016').json()['localization']['fields']['wasf_rotba'][0]
    assert 'uygun görmeyen' in sirin['text']
    mamer=client.get('/api/narrator/7633').json()
    assert mamer['death_year']=='154' and mamer['localization']['complete'] is False
