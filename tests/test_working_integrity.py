from copy import deepcopy
from types import SimpleNamespace

from hadis_web.localization import record_digest,claim_identity
from hadis_web.source import arabic_content
from hadis_web.working import stable_id,text_identity
from hadis_web.working_integrity import text_issues,chain_issues,claim_issues,component_issues,history_issues,public_error,foreign_key_issues,REQUIRED_FOREIGN_KEYS


def text():
    snapshot=str(stable_id('snapshot','fixture','v1','a'*64))
    raw='النص';display=arabic_content(raw)['text']
    unit,identity,checksum=text_identity(snapshot,'gk45:ar','146_1',raw,display)
    return dict(id=str(identity),unit_id=str(unit),snapshot_id=snapshot,namespace='gk45:ar',source_key='146_1',language='ar',
                raw_text=raw,display_text=display,raw_sha256=checksum,derivation_version='reader-v1')


def test_self_consistent_text_still_needs_actual_source_witness():
    row=text();witness=SimpleNamespace(text=lambda _:('النص','النص'))
    assert text_issues(row,witness)==[]
    wrong={**row,'raw_text':'نص آخر','display_text':'نص آخر'}
    unit,identity,checksum=text_identity(row['snapshot_id'],row['namespace'],row['source_key'],wrong['raw_text'],wrong['display_text'])
    wrong.update(unit_id=str(unit),id=str(identity),raw_sha256=checksum)
    assert 'text_source_content' in text_issues(wrong,witness)


def test_text_hash_and_identity_are_separate_checks():
    row=text();row['raw_sha256']='b'*64;row['id']='bad'
    codes=text_issues(row,SimpleNamespace(text=lambda _:('النص','النص')))
    assert {'text_raw_hash','text_identity'}<=set(codes)


def chain():
    target=text();snapshot=target['snapshot_id']
    person={'id':'person','snapshot_id':snapshot,'source_id':9}
    source={'sanad_id':7,'bhid':'146_1','rawy_ids':'9,30001,9','grade':0}
    row={'id':'chain','snapshot_id':snapshot,'source_sanad_id':7,'hadith_version_id':target['id'],
         'rawy_ids_raw':source['rawy_ids'],'source_data':source}
    members=[{'position':i,'source_value':value,'kind':'structural_marker' if value=='30001' else 'narrator',
              'narrator_record_id':None if value=='30001' else 'person'} for i,value in enumerate(source['rawy_ids'].split(','))]
    return row,members,{'person':person},target,source


def test_chain_retains_repeated_person_positions_and_marker_kinds():
    row,members,people,target,source=chain()
    assert chain_issues(row,members,people,target,source,{9})==[]
    members[1]['kind']='narrator';members[2]['position']=1
    assert {'chain_member_position','chain_member_kind'}<=set(chain_issues(row,members,people,target,source,{9}))


def test_chain_cannot_bind_another_hadith_or_person():
    row,members,people,target,source=chain()
    target['source_key']='146_2';people['person']['source_id']=10
    assert {'chain_target_binding','chain_person_binding'}<=set(chain_issues(row,members,people,target,source,{9}))
    row['rawy_ids_raw']='9'
    assert 'chain_source_record' in chain_issues(row,members,people,target,source,{9})


def claim():
    record={'id':9,'name':'اسم'}
    row={'id':'claim','snapshot_id':'snapshot','entity_type':'narrator','entity_key':'9','source_record':record,
        'source_record_sha256':record_digest(record),'field':'name','language':'tr','translated_text':'Ad',
        'rendering_kind':'transliteration','status':'needs_review','actor_kind':'assistant_source_review',
        'sources':[{'url':'https://example.org/source','title':'Fixture','locator':'s.1','accessed_on':'2026-11-12'}],
        'rationale':'Fixture source','supersedes_id':None}
    row['id']=str(claim_identity(snapshot=row['snapshot_id'],entity_type=row['entity_type'],entity_key=row['entity_key'],
        source_record=row['source_record'],field=row['field'],language=row['language'],text=row['translated_text'],
        rendering_kind=row['rendering_kind'],status=row['status'],actor_kind=row['actor_kind'],sources=row['sources'],
        rationale=row['rationale'],supersedes_id=row['supersedes_id']))
    return row


def test_claim_raw_source_and_hash_are_verified_without_approving_pending_text():
    row=claim();assert claim_issues(row,row['source_record'])==[]
    assert 'claim_source_record' in claim_issues(row,{'id':10,'name':'اسم'})
    row['source_record_sha256']='f'*64
    assert 'claim_raw_hash' in claim_issues(row,row['source_record'])


def test_claim_cannot_create_automatic_approval_or_lose_source_references():
    row=claim();row.update(actor_kind='automated_check',status='source_compared',sources=[])
    assert {'claim_automatic_approval','claim_references'}<=set(claim_issues(row,row['source_record']))


def test_history_detects_foreign_parent_forks_and_cycles():
    rows=[{'id':'a','key':'one','supersedes_id':'b'},{'id':'b','key':'one','supersedes_id':'a'},
          {'id':'c','key':'other','supersedes_id':'a'},{'id':'d','key':'one','supersedes_id':'missing'}]
    codes={code for code,_ in history_issues(rows,('key',))}
    assert {'history_cycle','history_fork','history_foreign_parent','history_parent_missing'}<=codes


def component():
    target=text();display=target['display_text']
    meta={target['id']:{**target,'display_sha256':record_digest({'unused':'x'}),'display_length':len(display)}}
    from hashlib import sha256
    meta[target['id']]['display_sha256']=sha256(display.encode()).hexdigest()
    binding={'text_version_id':target['id'],'raw_sha256':target['raw_sha256'],
             'display_sha256':meta[target['id']]['display_sha256'],'start_codepoint':0,'end_codepoint':len(display)}
    payload={'target_version_id':target['id'],'target_raw_sha256':target['raw_sha256'],
             'target_display_sha256':binding['display_sha256'],'bhid':'146_1','language':'tr','segmentation_version':'fixture',
             'source_sanads':[],'components':[{'kind':'matn','ordinal':0,'source_bindings':[binding],'source_sanad_ids':[],
                'reviews':[{'actor_kind':'assistant_source_review','outcome':'pending'}]}]}
    row={'id':str(stable_id('hadith-component-set-v1',record_digest(payload))),'payload':payload,'payload_sha256':record_digest(payload),
         'target_version_id':target['id'],'language':'tr','segmentation_version':'fixture','supersedes_id':None}
    return row,meta


def test_component_pending_status_is_not_corruption_but_source_range_is_checked():
    row,meta=component();assert component_issues(row,meta,[])==[]
    row['payload']['components'][0]['source_bindings'][0]['end_codepoint']=10000
    row['payload_sha256']=record_digest(row['payload']);row['id']=str(stable_id('hadith-component-set-v1',row['payload_sha256']))
    assert 'component_source_range' in component_issues(row,meta,[])


def test_component_cannot_self_hash_another_source_sened_or_target():
    row,meta=component();row['payload']['source_sanads']=[{'sanad_id':7}]
    row['payload']['target_raw_sha256']='f'*64
    row['payload_sha256']=record_digest(row['payload']);row['id']=str(stable_id('hadith-component-set-v1',row['payload_sha256']))
    assert {'component_source_sanads','component_target_binding'}<=set(component_issues(row,meta,[]))


def test_report_errors_do_not_echo_connection_secrets():
    error=ValueError('postgresql://user:SECRET@private/db')
    assert public_error(error)=={'type':'ValueError'}


def test_foreign_key_inventory_cannot_be_masked_by_an_unrelated_constraint():
    rows=[{'table_name':table,'column_name':column,'referenced_table':parent,'referenced_column':'id',
           'referenced_schema':'hadis','convalidated':True,'key_columns':1} for table,column,parent in REQUIRED_FOREIGN_KEYS]
    assert foreign_key_issues(rows,'hadis')==[]
    rows[0]['column_name']='unrelated';rows[1]['referenced_schema']='other'
    assert 'foreign_key_inventory_missing' in foreign_key_issues(rows,'hadis')


def test_empty_components_or_empty_source_bindings_are_not_verified():
    row,meta=component();row['payload']['components']=[]
    assert 'component_identity' in component_issues(row,meta,[])
    row,meta=component();row['payload']['components'][0]['source_bindings']=[]
    assert 'component_source_range' in component_issues(row,meta,[])


def rehash_component(row):
    row['payload_sha256']=record_digest(row['payload'])
    row['id']=str(stable_id('hadith-component-set-v1',row['payload_sha256']))


def test_claim_identity_detects_changed_translation_status_or_parent():
    for field,value in [('translated_text','Changed'),('status','source_compared'),('supersedes_id','other')]:
        row=claim();row[field]=value
        assert 'claim_identity' in claim_issues(row,row['source_record'])


def test_component_must_bind_its_own_arabic_and_exact_published_slices():
    row,meta=component();other=deepcopy(next(iter(meta.values())))
    other.update(id='other',source_key='146_2');meta['other']=other
    row['payload']['components'][0]['source_bindings'][0]['text_version_id']='other'
    rehash_component(row)
    assert 'component_arabic_binding' in component_issues(row,meta,[])
    row,meta=component();translated=deepcopy(next(iter(meta.values())))
    translated.update(id='tr',language='tr',display_text='Published',display_length=9)
    from hashlib import sha256
    translated['display_sha256']=sha256(b'Published').hexdigest();meta['tr']=translated
    binding=deepcopy(row['payload']['components'][0]['source_bindings'][0])
    binding.update(text_version_id='tr',display_sha256=translated['display_sha256'],end_codepoint=9)
    comp=row['payload']['components'][0];comp.update(origin='published_translation',translation_text='Unrelated')
    comp['source_bindings'].append(binding);rehash_component(row)
    assert 'component_published_text' in component_issues(row,meta,[])
    comp['translation_text']='Published';rehash_component(row)
    assert component_issues(row,meta,[])==[]
    comp['kind']='notes';comp['source_bindings']=[binding];rehash_component(row)
    assert component_issues(row,meta,[])==[]


def test_component_payload_and_column_parent_cannot_disagree():
    row,meta=component();row['payload']['supersedes_id']='missing';rehash_component(row)
    assert 'component_parent_binding' in component_issues(row,meta,[])


def test_historical_reuse_requires_fixed_existing_component_and_matching_text():
    from hadis_web.working_integrity import reuse_issues
    source,meta=component();source['payload']['components'][0].update(translation_text='Same',bibliography={},origin='assistant_translation')
    rehash_component(source)
    target=deepcopy(source);target['payload']['segmentation_version']='fixture'
    comp=target['payload']['components'][0];comp.update(origin='reused_rendering',reuses_component_id='missing')
    rehash_component(target)
    assert 'component_reuse_missing' in reuse_issues([source,target],meta)
    comp['reuses_component_id']=str(stable_id('hadith-component-v1',source['id'],'matn',0));rehash_component(target)
    assert reuse_issues([source,target],meta)==[]
    comp['translation_text']='Changed';rehash_component(target)
    assert 'component_reuse_binding' in reuse_issues([source,target],meta)


def test_narrator_and_chain_ids_are_bound_to_original_import_identity():
    from hadis_web.working_integrity import record_identity_issues
    row={'id':'changed','snapshot_id':'s','source_id':9,'source_sanad_id':7}
    assert record_identity_issues(row,'narrator')==['narrator_identity']
    assert record_identity_issues(row,'sanad')==['chain_identity']
    row['id']=str(stable_id('narrator','s',9))
    assert record_identity_issues(row,'narrator')==[]


def test_readonly_connection_resolves_catalog_functions_before_audited_schema(monkeypatch):
    from hadis_web import working_integrity
    calls=[]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query):calls.append(query if isinstance(query,str) else query.as_string())
    monkeypatch.setattr(working_integrity.psycopg,'connect',lambda *args,**kwargs:Connection())
    settings=SimpleNamespace(postgres_dsn='not printed',postgres_schema='hadis')
    with working_integrity.readonly_connection(settings):pass
    path=calls[1].replace(' ','').replace('"','')
    assert 'search_pathTOpg_catalog,hadis' in path
