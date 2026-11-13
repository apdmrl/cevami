from copy import deepcopy
import hashlib
import json

from hadis_web.working import stable_id


def alignment():
    roles=('target_arabic','bridge_arabic','translation')
    versions={}
    members=[]
    for i,role in enumerate(roles):
        identity=str(stable_id('fixture-version',role))
        versions[identity]=dict(id=identity,unit_id='u',snapshot_id='s',namespace='gk45:ar' if i==0 else 'fawaz:'+('ara-' if i==1 else 'tur-')+'bukhari',
            source_key='146_1' if i==0 else '1',language='tr' if i==2 else 'ar',raw_sha256=str(i)*64,
            provider='gk45' if i==0 else 'fawazahmed0',revision='4.5' if i==0 else 'pin',artifact_sha256='a'*64,
            artifact_name='jawami.db' if i==0 else ('ara-' if i==1 else 'tur-')+'bukhari.json',
            derivation_version='reader-v1',locator={'json_pointer':'/hadiths/0'},display_sha256='d'*64)
        members.append(dict(role=role,ordinal=0,text_version_id=identity))
    fingerprint=hashlib.sha256(json.dumps([m['text_version_id'] for m in members]+['unclassified']).encode()).hexdigest()
    case=dict(id=str(stable_id('case',fingerprint)),fingerprint=fingerprint)
    revision=dict(id=str(stable_id('alignment',case['id'],1)),case_id=case['id'],revision=1,scope='unclassified',sealed=True,relation_type='proposed')
    for m in members:m['revision_id']=revision['id']
    evidence=dict(id=str(stable_id('evidence',revision['id'],'initial')),revision_id=revision['id'],method='research-v1-and-v2',
        evidence={'v1':{'gk_bhid':'146_1','source_key':'1','edition':'tur-bukhari','source_revision':'pin','language':'tr'},
                  'v2':{'gk_raw_sha256':'0'*64,'source_arabic_sha256':'1'*64,'source_turkish_sha256':'2'*64}})
    return case,revision,members,evidence,versions


def test_real_nested_evidence_requires_all_three_hashes_and_correct_source_members():
    from hadis_web.relation_integrity import alignment_issues
    args=alignment();assert alignment_issues(*args)==[]
    wrong=deepcopy(args);wrong[3]['evidence']['v2']['source_turkish_sha256']='f'*64
    assert 'evidence_source_hash' in alignment_issues(*wrong)
    wrong=deepcopy(args);del wrong[3]['evidence']['v2']
    assert 'evidence_shape' in alignment_issues(*wrong)
    wrong=deepcopy(args);wrong[4][wrong[2][2]['text_version_id']]['source_key']='2'
    assert 'alignment_source_binding' in alignment_issues(*wrong)
    wrong=deepcopy(args);wrong[2][2]['ordinal']=1
    assert 'alignment_member_shape' in alignment_issues(*wrong)
    wrong=deepcopy(args);wrong[0]['fingerprint']='f'*64
    assert 'alignment_case_identity' in alignment_issues(*wrong)


def test_expected_inventory_rejects_empty_or_reduced_scope_but_allows_additions():
    from hadis_web.relation_integrity import coverage_issues
    baseline={'working_minimum':{'text_versions':10},'required_snapshot_ids':['s'],
        'search_minimum':{'documents':10,'targets':8,'languages':{'tr':4,'en':6}}}
    assert {'working_coverage_reduced','snapshot_coverage_reduced','search_coverage_reduced'}<=set(coverage_issues({},[],{},baseline))
    assert coverage_issues({'text_versions':11},['s','new'],{'documents':12,'targets':9,'languages':{'tr':5,'en':7}},baseline)==[]
    assert 'search_coverage_reduced' in coverage_issues({'text_versions':10},['s'],{'documents':10,'targets':8,'languages':{'tr':3,'en':7}},baseline)


def test_review_cannot_be_moved_to_another_sealed_revision_or_lose_its_source_bindings():
    from hadis_web.relation_integrity import review_issues,bound_members
    from hadis_web.localization import record_digest
    case,revision,members,evidence,versions=alignment()
    bound=bound_members(members,versions)
    refs=[]
    for member in bound:
        refs.append(dict(url='gk45:hadith:146_1' if member['role']=='target_arabic' else 'https://github.com/fawazahmed0/hadith-api/tree/pin',
            title='Source',locator=member['raw_sha256']+' '+member['artifact_name']+member['locator'].get('json_pointer','')+' '+member['artifact_sha256'],accessed_on='2026-11-12'))
    root={'bhid':'146_1','alignment':revision,'members':bound}
    decision=dict(dimension='translation_meaning',outcome='pending',rationale='Pending',sources=refs)
    batch=dict(actor='assistant-hadith-source-review',actor_kind='assistant_source_review',reviewed_on='2026-11-12')
    identity=str(stable_id('hadith-source-review','batch-digest',revision['id'],decision['dimension']))
    registry={identity:dict(case=root,review=decision,batch=batch)}
    event=dict(id=identity,revision_id=revision['id'],actor=batch['actor'],actor_kind=batch['actor_kind'],
        dimension=decision['dimension'],outcome='pending',rationale='Pending',source_refs=refs,supersedes_id=None)
    assert review_issues(event,revision,bound,registry)==[]
    wrong=deepcopy(revision);wrong['id']='other';event['revision_id']='other'
    assert 'review_batch_binding' in review_issues(event,wrong,bound,registry)
    event['revision_id']=revision['id'];event['source_refs']=refs[:1]
    assert 'review_source_binding' in review_issues(event,revision,bound,registry)


def test_hadeethenc_working_pair_requires_the_exact_archived_arabic_version():
    from hadis_web.relation_integrity import hadeethenc_pair_issues
    rows={'ar':dict(provider='hadeethenc',language='ar',source_key='1',locator={'ar_version':1}),
          'tr':dict(provider='hadeethenc',language='tr',source_key='1',locator={'ar_version':2})}
    assert hadeethenc_pair_issues(rows)==['hadeethenc_working_pair']
    rows['ar']['locator']['ar_version']=2
    assert hadeethenc_pair_issues(rows)==[]
