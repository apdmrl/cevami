import json
import hashlib
from dataclasses import replace
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.localization import LocalizationStore
import hadis_web.field_reviews as reviews

PARENTS={(720,'lakab'):'9bb64b45-7768-57cb-a3a7-fdd4d54ce3cd',
         (746,'baladwafa'):'313c74b2-a70c-53d3-a287-ff492bd2213c',
         (746,'wasf_rotba'):'f5c9004d-67b5-56a5-9137-67a9ad4b3f13'}


def correction_registry(tmp_path,monkeypatch):
    original=reviews.DATA_FOLDER
    names=[f'narrator-field-reviews-tr-v{i}.json' for i in (1,2,3)]
    for name in names:(tmp_path/name).write_bytes((original/name).read_bytes())
    old=json.loads((original/names[-1]).read_text(encoding='utf-8'))
    new={**old,'revision':'test-corrections','people':[]}
    for person in old['people']:
        entries=[]
        for entry in person['fields']:
            parent=PARENTS.get((person['id'],entry['field']))
            if not parent:continue
            entries.append({**entry,'supersedes_id':parent,
                'text':'Karşılaştırılmış yeni Türkçe aktarım.' if entry['field']!='baladwafa' else entry['text'],
                'status':'source_compared' if entry['field']!='baladwafa' else 'problem_detected',
                'rationale':'Test: önceki iddia korunarak kaynak karşılaştırmasıyla düzeltildi.'})
        if entries:new['people'].append({**person,'fields':entries})
    (tmp_path/'corrections.json').write_text(json.dumps(new),encoding='utf-8')
    (tmp_path/'field-review-batches.json').write_text(json.dumps({'revision':'test-history','files':names+['corrections.json']}),encoding='utf-8')
    monkeypatch.setattr(reviews,'DATA_FOLDER',tmp_path)
    return new


def row_ids(store):
    with store.connection() as c:return {str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}


def test_corrections_preserve_history_and_reimport_without_conflicts(environment,tmp_path,monkeypatch):
    settings,store,_=environment
    correction_registry(tmp_path,monkeypatch)
    result=reviews.load_field_review_batches(store,settings)
    assert result=={'revision':'test-history','batches':4,'people':21,'claims':183,'claim_versions':186}
    before=row_ids(store)
    assert len(before)==186 and set(PARENTS.values())<=before
    assert reviews.load_field_review_batches(store,settings)==result and row_ids(store)==before
    api=TestClient(create_app(settings),base_url='http://127.0.0.1')
    enes=api.get('/api/narrator/720').json()
    assert enes['lakab']=='ذو الأدنين'
    assert len(enes['localization']['fields']['lakab'])==1
    assert enes['localization']['fields']['lakab'][0]['status']=='source_compared'
    assert 'lakab' not in enes['localization']['pending_fields']
    eyyub=api.get('/api/narrator/746').json()['localization']
    assert 'wasf_rotba' not in eyyub['pending_fields'] and 'baladwafa' in eyyub['pending_fields']
    assert eyyub['complete'] is False


@pytest.mark.parametrize('invalid',['missing_parent','cross_field','old_parent','forward_file'])
def test_invalid_correction_lineage_is_rejected_before_any_write(environment,tmp_path,monkeypatch,invalid):
    settings,store,_=environment
    data=correction_registry(tmp_path,monkeypatch)
    entry=data['people'][0]['fields'][0]
    if invalid=='missing_parent':entry['supersedes_id']='00000000-0000-0000-0000-000000000001'
    elif invalid=='cross_field':entry['supersedes_id']=PARENTS[(746,'wasf_rotba')]
    elif invalid=='old_parent':data['people'][0]['fields'].append({**entry,'text':'Aynı eski ebeveynden ikinci dal.'})
    else:
        registry=json.loads((tmp_path/'field-review-batches.json').read_text(encoding='utf-8'))
        registry['files'].insert(0,registry['files'].pop())
        (tmp_path/'field-review-batches.json').write_text(json.dumps(registry),encoding='utf-8')
    (tmp_path/'corrections.json').write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError):reviews.load_field_review_batches(store,settings)
    assert row_ids(store)==set()


def test_existing_external_branch_is_rejected_before_writes(environment,tmp_path,monkeypatch):
    settings,store,snapshot=environment
    data=correction_registry(tmp_path,monkeypatch)
    registry_path=tmp_path/'field-review-batches.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8'))
    registry_path.write_text(json.dumps({**registry,'files':registry['files'][:3]}),encoding='utf-8')
    reviews.load_field_review_batches(store,settings)
    person=next(p for p in data['people'] if p['id']==746)
    record=person['expected_source'];local=LocalizationStore(store)
    old=local.for_records(snapshot,'narrator',{'746':record},'tr')['746']['fields']['wasf_rotba'][0]
    local.add_claim(snapshot=snapshot,entity_type='narrator',entity_key='746',source_record=record,
        field='wasf_rotba',language='tr',text='Dış incelemede oluşturulmuş alternatif düzeltme.',rendering_kind='translation',
        status='needs_review',actor_kind='assistant_source_review',sources=old['sources'],rationale='Test dış dalı.',supersedes_id=old['id'])
    before=row_ids(store)
    registry_path.write_text(json.dumps(registry),encoding='utf-8')
    with pytest.raises(ValueError,match='branch'):reviews.load_field_review_batches(store,settings)
    assert row_ids(store)==before


@pytest.mark.parametrize('artifact_path',['references/evidence.bin','../outside.bin'])
def test_changed_or_escaping_review_artifact_rejected_before_writes(environment,tmp_path,monkeypatch,artifact_path):
    settings,store,_=environment
    data=correction_registry(tmp_path,monkeypatch)
    manifest=tmp_path/'references/datasets/jawami3_alkalem/verification.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_bytes())
    (tmp_path/'references/evidence.bin').write_bytes(b'changed')
    data['review_artifacts']=[{'path':artifact_path,'sha256':'0'*64}]
    (tmp_path/'corrections.json').write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='checksum|artifact path'):
        reviews.load_field_review_batches(store,replace(settings,project_root=tmp_path))
    assert row_ids(store)==set()


def test_real_source_corrections_keep_original_arabic_and_unresolved_history(environment,monkeypatch):
    settings,store,_=environment
    original=reviews._read_batch
    def first_four(filename):
        if filename=='field-review-batches.json':
            return {'revision':'historical-v4','files':[f'narrator-field-reviews-tr-v{i}.json' for i in (1,2,3,4)]}
        return original(filename)
    monkeypatch.setattr(reviews,'_read_batch',first_four)
    assert hashlib.sha256((reviews.DATA_FOLDER/'narrator-field-reviews-tr-v3.json').read_bytes()).hexdigest()=='98e02b9a7a8cae8cb3fd319fd073ae6d466518aa383d0287a425631006c22040'
    result=reviews.load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result.get('claim_versions'))==(4,21,183,186)
    assert reviews.load_field_review_batches(store,settings)==result
    api=TestClient(create_app(settings),base_url='http://127.0.0.1')
    enes=api.get('/api/narrator/720').json()
    nickname=enes['localization']['fields']['lakab'][0]
    assert enes['lakab']=='ذو الأدنين' and 'iki kulaklı' in nickname['text']
    assert nickname['translation_origin']=='assistant_source_corrected_rendering' and nickname['status']=='source_compared'
    assert nickname['expert_reviewed'] is False
    eyyub=api.get('/api/narrator/746').json()
    rank=eyyub['localization']['fields']['wasf_rotba'][0]
    death=eyyub['localization']['fields']['baladwafa'][0]
    assert eyyub['wasf_rotba']=='ثقة ثبتت حجة' and 'sebt' in rank['text']
    assert rank['translation_origin']=='assistant_source_corrected_rendering' and rank['status']=='source_compared'
    assert death['status']=='problem_detected' and '132' in death['rationale']
    assert 'baladwafa' in eyyub['localization']['pending_fields'] and eyyub['localization']['complete'] is False
    assert len(row_ids(store))==186
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims WHERE supersedes_id=ANY(%s::uuid[])',(list(PARENTS.values()),)).fetchone()['n']==3
        assert c.execute('SELECT count(*) AS n FROM localization_claims c WHERE NOT EXISTS (SELECT 1 FROM localization_claims n WHERE n.supersedes_id=c.id)').fetchone()['n']==183
