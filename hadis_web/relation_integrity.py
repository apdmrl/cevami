"""Pure checks for stored technical relationships; no assessment of meaning."""
from collections import Counter
from hashlib import sha256
import json

from .field_reviews import _validate_references
from .hadith_reviews import _validate_sources
from .working import stable_id


ROLES=('target_arabic','bridge_arabic','translation')


def coverage_issues(counts,snapshots,search,baseline):
    codes=[]
    if any(counts.get(key,0)<value for key,value in baseline['working_minimum'].items()):
        codes.append('working_coverage_reduced')
    if not set(baseline['required_snapshot_ids'])<=set(snapshots):codes.append('snapshot_coverage_reduced')
    expected=baseline['search_minimum']
    if (any(search.get(key,0)<expected[key] for key in ('documents','targets'))
            or any(search.get('languages',{}).get(key,0)<value for key,value in expected['languages'].items())):
        codes.append('search_coverage_reduced')
    return codes


def alignment_issues(case,revision,members,evidence,versions):
    codes=[]
    if len(members)!=3 or Counter((m['role'],m['ordinal']) for m in members)!=Counter((r,0) for r in ROLES):
        return ['alignment_member_shape']
    by_role={m['role']:versions.get(str(m['text_version_id'])) for m in members}
    if any(v is None for v in by_role.values()):return ['alignment_member_reference']
    if str(revision['id'])!=str(stable_id('alignment',str(revision['case_id']),revision['revision'])):
        codes.append('alignment_revision_identity')
    if revision['revision']==1:
        fingerprint=sha256(json.dumps([str(by_role[r]['id']) for r in ROLES]+[revision['scope']]).encode()).hexdigest()
        if (case['fingerprint']!=fingerprint or str(case['id'])!=str(stable_id('case',fingerprint))
                or str(revision['case_id'])!=str(case['id'])):codes.append('alignment_case_identity')
    if evidence is None:return codes+['alignment_evidence_missing']
    if evidence['method']!='research-v1-and-v2':return codes
    if (str(evidence['id'])!=str(stable_id('evidence',str(revision['id']),'initial'))
            or str(evidence['revision_id'])!=str(revision['id'])):codes.append('evidence_identity')
    payload=evidence['evidence'];v1=payload.get('v1');v2=payload.get('v2')
    if not isinstance(v1,dict) or not isinstance(v2,dict):return codes+['evidence_shape']
    target,bridge,translation=(by_role[r] for r in ROLES)
    if (target['namespace']!='gk45:ar' or target['language']!='ar' or target['provider']!='gk45'
            or bridge['provider']!='fawazahmed0' or translation['provider']!='fawazahmed0'
            or not translation['artifact_name'].startswith('tur-')
            or bridge['artifact_name']!='ara-'+translation['artifact_name'][4:]
            or bridge['namespace']!='fawaz:'+bridge['artifact_name'][:-5]
            or translation['namespace']!='fawaz:'+translation['artifact_name'][:-5]
            or bridge['source_key']!=translation['source_key'] or bridge['revision']!=translation['revision']
            or bridge['language']!='ar' or translation['language']!='tr'
            or v1.get('gk_bhid')!=target['source_key'] or v1.get('source_key')!=translation['source_key']
            or v1.get('edition')!=translation['artifact_name'][:-5] or v1.get('source_revision')!=translation['revision']
            or v1.get('language')!=translation['language']):codes.append('alignment_source_binding')
    for key,row in [('gk_raw_sha256',target),('source_arabic_sha256',bridge),('source_turkish_sha256',translation)]:
        if v2.get(key)!=row['raw_sha256']:codes.append('evidence_source_hash')
    for key,expected in [('gk_bhid',target['source_key']),('source_key',translation['source_key']),
                         ('source_edition',translation['artifact_name'][:-5])]:
        if key in v2 and v2[key]!=expected:codes.append('alignment_source_binding')
    if 'source_translation_sha256' in v1 and v1['source_translation_sha256']!=translation['raw_sha256']:
        codes.append('evidence_source_hash')
    return list(dict.fromkeys(codes))


def bound_members(members,versions):
    result=[]
    for member in sorted(members,key=lambda m:(m['role'],m['ordinal'])):
        row=versions[str(member['text_version_id'])]
        item={k:str(row[k]) if k in ('id','unit_id','snapshot_id') else row[k] for k in
              ('id','unit_id','snapshot_id','language','raw_sha256','derivation_version','locator','namespace','source_key',
               'provider','artifact_sha256','artifact_name','display_sha256')}
        item.update(role=member['role'],ordinal=member['ordinal'],source_revision=row['revision'])
        result.append(item)
    return result


def review_registry(data):
    checksum=sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {str(stable_id('hadith-source-review',checksum,case['alignment']['id'],review['dimension'])):
            {'case':case,'review':review,'batch':data} for case in data['cases'] for review in case['reviews']}


def review_issues(row,revision,members,registry):
    codes=[]
    if revision is None or not revision['sealed']:return ['review_revision']
    try:
        if not isinstance(row['source_refs'],list) or not row['source_refs']:raise ValueError('Missing source')
        _validate_references(row['source_refs'])
    except (ValueError,KeyError,TypeError):codes.append('review_references')
    if row['actor_kind']=='automated_check' and row['outcome'] in ('pass','not_applicable'):codes.append('review_automatic_approval')
    registered=registry.get(str(row['id']))
    if registered:
        case=registered['case'];decision=registered['review'];batch=registered['batch']
        if (case['alignment']!=revision or str(row['revision_id'])!=case['alignment']['id'] or case['members']!=members
                or row['supersedes_id'] is not None or row['actor']!=batch['actor'] or row['actor_kind']!=batch['actor_kind']
                or any(row[k]!=decision[k] for k in ('dimension','outcome','rationale')) or row['source_refs']!=decision['sources']):
            codes.append('review_batch_binding')
    elif row['actor']=='assistant-hadith-source-review' and row['supersedes_id'] is None:
        codes.append('review_batch_identity')
    target=next((m for m in members if m['role']=='target_arabic'),None)
    supported=(len(members)==3 and all(m['provider'] in ('gk45','fawazahmed0') for m in members) and target is not None)
    if supported:
        case={'bhid':target['source_key'],'members':members}
        dates={r.get('accessed_on') for r in row['source_refs'] if isinstance(r,dict)}
        try:
            if len(dates)!=1:raise ValueError('Mixed source dates')
            _validate_sources(row['source_refs'],case,next(iter(dates)))
        except (ValueError,KeyError,TypeError):codes.append('review_source_binding')
    else:codes.append('review_source_schema_unverified')
    return list(dict.fromkeys(codes))


def hadeethenc_pair_issues(versions):
    arabic={(v['source_key'],v['locator'].get('ar_version')) for v in versions.values()
            if v['provider']=='hadeethenc' and v['language']=='ar'}
    return ['hadeethenc_working_pair'] if any(
        (v['source_key'],v['locator'].get('ar_version')) not in arabic for v in versions.values()
        if v['provider']=='hadeethenc' and v['language']=='tr') else []
