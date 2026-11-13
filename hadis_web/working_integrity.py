"""Technical checks against a read-only repeatable working-data snapshot."""
from collections import Counter,defaultdict
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import re

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .field_reviews import _validate_references
from .localization import record_digest,opinion_key,claim_identity
from .relation_integrity import (alignment_issues,bound_members,coverage_issues,hadeethenc_pair_issues,
                                 review_issues,review_registry)
from .source import STRUCTURAL_IDS,open_readonly
from .source_witnesses import SourceWitnesses,WitnessError
from .working import stable_id,text_identity


TABLES=('source_snapshots','text_units','text_versions','text_segments','alignment_cases','alignment_revisions',
        'alignment_members','comparison_evidence','review_events','narrator_records','sanad_records','sanad_members',
        'localization_claims','hadith_component_sets')
REQUIRED_FOREIGN_KEYS=(('text_versions','unit_id','text_units'),('text_versions','snapshot_id','source_snapshots'),
    ('text_segments','text_version_id','text_versions'),('alignment_revisions','case_id','alignment_cases'),
    ('alignment_members','revision_id','alignment_revisions'),('alignment_members','text_version_id','text_versions'),
    ('comparison_evidence','revision_id','alignment_revisions'),('review_events','revision_id','alignment_revisions'),
    ('review_events','supersedes_id','review_events'),('narrator_records','snapshot_id','source_snapshots'),
    ('sanad_records','snapshot_id','source_snapshots'),('sanad_records','hadith_version_id','text_versions'),
    ('sanad_members','sanad_id','sanad_records'),('sanad_members','narrator_record_id','narrator_records'),
    ('localization_claims','snapshot_id','source_snapshots'),('localization_claims','supersedes_id','localization_claims'),
    ('hadith_component_sets','target_version_id','text_versions'),('hadith_component_sets','supersedes_id','hadith_component_sets'))


def foreign_key_issues(rows,schema):
    actual={(r['table_name'],r['column_name'],r['referenced_table']) for r in rows
            if r['referenced_schema']==schema and r['referenced_column']=='id' and r['key_columns']==1}
    codes=[]
    if not set(REQUIRED_FOREIGN_KEYS)<=actual:codes.append('foreign_key_inventory_missing')
    if any(not row['convalidated'] for row in rows):codes.append('foreign_key_not_validated')
    return codes


def public_error(error):
    result={'type':type(error).__name__}
    code=getattr(error,'sqlstate',None)
    if isinstance(code,str) and re.fullmatch('[A-Z0-9]{5}',code):result['sqlstate']=code
    return result


def text_issues(row,witness):
    codes=[]
    unit,identity,checksum=text_identity(row['snapshot_id'],row['namespace'],row['source_key'],row['raw_text'],row['display_text'])
    if row['raw_sha256']!=checksum:codes.append('text_raw_hash')
    if str(row['unit_id'])!=str(unit) or str(row['id'])!=str(identity) or row['derivation_version']!='reader-v1':codes.append('text_identity')
    raw,display=witness.text(row)
    if row['raw_text']!=raw or row['display_text']!=display:codes.append('text_source_content')
    return codes


def chain_issues(row,members,people,target,source,source_people):
    codes=[]
    if source is None:return ['chain_source_missing']
    if row['source_data']!=source or row['rawy_ids_raw']!=(source['rawy_ids'] or ''):codes.append('chain_source_record')
    if not target or target['namespace']!='gk45:ar' or target['source_key']!=source['bhid'] or str(target['snapshot_id'])!=str(row['snapshot_id']):
        codes.append('chain_target_binding')
    tokens=(source['rawy_ids'] or '').split(',')
    ordered=sorted(members,key=lambda m:m['position'])
    if len(ordered)!=len(tokens):codes.append('chain_member_count')
    for position,member in enumerate(ordered):
        if member['position']!=position or position>=len(tokens) or member['source_value']!=tokens[position]:
            codes.append('chain_member_position');continue
        value=tokens[position]
        try:identity=int(value) if value.isdigit() else None
        except ValueError:identity=None
        kind='structural_marker' if identity in STRUCTURAL_IDS else 'narrator' if identity in source_people else 'unresolved'
        if member['kind']!=kind:codes.append('chain_member_kind')
        person=people.get(str(member['narrator_record_id']))
        if (kind=='narrator' and person is None) or (member['narrator_record_id'] is not None and
            (person is None or person['source_id']!=identity or str(person['snapshot_id'])!=str(row['snapshot_id']))):
            codes.append('chain_person_binding')
    return list(dict.fromkeys(codes))


def claim_issues(row,actual):
    codes=[]
    identity=claim_identity(snapshot=row['snapshot_id'],entity_type=row['entity_type'],entity_key=row['entity_key'],
        source_record=row['source_record'],field=row['field'],language=row['language'],text=row['translated_text'],
        rendering_kind=row['rendering_kind'],status=row['status'],actor_kind=row['actor_kind'],sources=row['sources'],
        rationale=row['rationale'],supersedes_id=row['supersedes_id'])
    if str(row['id'])!=str(identity):codes.append('claim_identity')
    if record_digest(row['source_record'])!=row['source_record_sha256']:codes.append('claim_raw_hash')
    if actual is not None and actual!=row['source_record']:codes.append('claim_source_record')
    if row['entity_type'] in ('narrator','critic'):
        key='id' if row['entity_type']=='narrator' else 'alem_id'
        if str(row['source_record'].get(key))!=row['entity_key']:codes.append('claim_entity_key')
    elif row['entity_type']=='critic_opinion':
        if opinion_key(row['source_record'])!=row['entity_key']:codes.append('claim_entity_key')
    elif row['entity_type']=='controlled_term':
        if row['source_record'].get('key')!=row['entity_key']:codes.append('claim_entity_key')
    else:codes.append('claim_entity_type')
    if row['actor_kind']=='automated_check' and row['status']=='source_compared':codes.append('claim_automatic_approval')
    try:
        if not isinstance(row['sources'],list) or not row['sources']:raise ValueError('Missing references')
        _validate_references(row['sources'])
    except (ValueError,TypeError,KeyError):codes.append('claim_references')
    if row['rendering_kind']=='source_summary' and not row['field'].endswith('_note'):codes.append('claim_summary_field')
    return codes


def history_issues(rows,keys):
    lookup={str(row['id']):row for row in rows};children=Counter();result=[];done=set()
    for row in rows:
        parent_id=row.get('supersedes_id')
        if parent_id is None:continue
        parent_id=str(parent_id);children[parent_id]+=1;parent=lookup.get(parent_id)
        if parent is None:result.append(('history_parent_missing',str(row['id'])))
        elif any(row[key]!=parent[key] for key in keys):result.append(('history_foreign_parent',str(row['id'])))
    for identity,count in children.items():
        if count>1:result.append(('history_fork',identity))
    for identity in lookup:
        path=set();cursor=identity
        while cursor in lookup and cursor not in done:
            if cursor in path:
                result.append(('history_cycle',cursor));break
            path.add(cursor);parent=lookup[cursor].get('supersedes_id')
            if parent is None:break
            cursor=str(parent)
        done.update(path)
    return result


def component_issues(row,versions,source_sanads):
    codes=[];payload=row['payload'];checksum=record_digest(payload)
    if checksum!=row['payload_sha256'] or str(row['id'])!=str(stable_id('hadith-component-set-v1',checksum)):codes.append('component_payload_hash')
    target=versions.get(str(row['target_version_id']))
    if (target is None or payload['target_version_id']!=str(row['target_version_id']) or payload['language']!=row['language']
        or payload['segmentation_version']!=row['segmentation_version'] or target['namespace']!='gk45:ar'
        or payload['bhid']!=target['source_key'] or payload['target_raw_sha256']!=target['raw_sha256']
        or payload['target_display_sha256']!=target['display_sha256']):codes.append('component_target_binding')
    if payload['source_sanads']!=source_sanads:codes.append('component_source_sanads')
    if payload.get('supersedes_id')!=(str(row['supersedes_id']) if row['supersedes_id'] is not None else None):
        codes.append('component_parent_binding')
    ids={s['sanad_id'] for s in source_sanads};seen=set()
    if not isinstance(payload['components'],list) or not payload['components']:return codes+['component_identity']
    for comp in payload['components']:
        key=(comp['kind'],comp['ordinal'])
        if key in seen or comp['kind'] not in ('matn','isnad','notes','unclassified') or type(comp['ordinal']) is not int or comp['ordinal']<0:
            codes.append('component_identity')
        seen.add(key)
        if not isinstance(comp['source_bindings'],list) or not comp['source_bindings']:codes.append('component_source_range')
        arabic=[];translated=[]
        for binding in comp['source_bindings']:
            source=versions.get(binding['text_version_id']);start,end=binding['start_codepoint'],binding['end_codepoint']
            if (source is None or type(start) is not int or type(end) is not int or not 0<=start<end<=source['display_length']
                or binding['raw_sha256']!=source['raw_sha256'] or binding['display_sha256']!=source['display_sha256']):
                codes.append('component_source_range')
                continue
            if binding['text_version_id']==str(row['target_version_id']):arabic.append(source['display_text'][start:end])
            elif source['language']==row['language']:translated.append(source['display_text'][start:end])
        if not arabic and not (comp['kind']=='notes' and translated):codes.append('component_arabic_binding')
        if comp.get('origin')=='published_translation' and (not translated or comp.get('translation_text')!=''.join(translated)):
            codes.append('component_published_text')
        if any(type(identity) is not int or identity not in ids for identity in comp.get('source_sanad_ids',[])):codes.append('component_sanad_binding')
        if any(r.get('actor_kind')=='automated_check' and r.get('outcome') in ('pass','not_applicable') for r in comp.get('reviews',[])):
            codes.append('component_automatic_approval')
    return list(dict.fromkeys(codes))


def record_identity_issues(row,kind):
    key='source_id' if kind=='narrator' else 'source_sanad_id'
    code='narrator_identity' if kind=='narrator' else 'chain_identity'
    return [code] if str(row['id'])!=str(stable_id(kind,str(row['snapshot_id']),row[key])) else []


def reuse_issues(rows,versions):
    components={};codes=[];edges={}
    for row in rows:
        for comp in row['payload']['components']:
            identity=str(stable_id('hadith-component-v1',str(row['id']),comp['kind'],comp['ordinal']))
            components[identity]=(row['payload'],comp)
    def arabic(case,comp):
        text=[]
        for binding in comp['source_bindings']:
            if binding['text_version_id']==case['target_version_id']:
                version=versions[binding['text_version_id']]
                if (binding['raw_sha256']!=version['raw_sha256'] or binding['display_sha256']!=version['display_sha256']
                        or not 0<=binding['start_codepoint']<binding['end_codepoint']<=version['display_length']):
                    raise ValueError('Invalid reuse source range')
                text.append(version['display_text'][binding['start_codepoint']:binding['end_codepoint']])
        return ''.join(text)
    for identity,(case,comp) in components.items():
        if comp.get('origin')!='reused_rendering':continue
        previous_id=comp.get('reuses_component_id');previous=components.get(previous_id)
        if previous is None:codes.append('component_reuse_missing');continue
        edges[identity]=previous_id;old_case,old_comp=previous
        if (case['segmentation_version']!=old_case['segmentation_version'] or case['language']!=old_case['language']
                or comp['kind']!=old_comp['kind'] or comp.get('translation_text')!=old_comp.get('translation_text')
                or comp.get('bibliography')!=old_comp.get('bibliography') or arabic(case,comp)!=arabic(old_case,old_comp)):
            codes.append('component_reuse_binding')
    for identity in edges:
        seen=set();cursor=identity
        while cursor in edges:
            if cursor in seen or len(seen)>40:codes.append('component_reuse_cycle');break
            seen.add(cursor);cursor=edges[cursor]
    return list(dict.fromkeys(codes))


@contextmanager
def readonly_connection(settings):
    if not settings.postgres_dsn:raise ValueError('Working database unconfigured')
    if not re.fullmatch('[a-z][a-z0-9_]{0,62}',settings.postgres_schema):raise ValueError('Invalid audit schema')
    with psycopg.connect(settings.postgres_dsn,row_factory=dict_row,connect_timeout=3,
                        options='-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=3000') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        conn.execute(sql.SQL('SET LOCAL search_path TO pg_catalog,{}').format(sql.Identifier(settings.postgres_schema)))
        yield conn


def audit_working(settings,source_sha,progress=None):
    result={'scan_complete':False,'meaning_reviewed':False,'expert_approval':False,'counts':{},'findings':[],
            'coverage':{},'fingerprints':{},'connection':{}}
    findings={};counts=result['counts']
    def add(code,example=None,severity='error',count=1):
        item=findings.setdefault((code,severity),{'code':code,'severity':severity,'count':0,'examples':[]})
        item['count']+=count
        if example is not None and len(item['examples'])<12:item['examples'].append(example)
    def notify(stage):
        if progress:progress(stage)
    def checked(function,*args):
        try:return function(*args)
        except WitnessError as error:return ['witness_'+str(error)]
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):return ['invalid_record_shape']
    def rows(conn,table):
        return list(conn.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))))
    try:
        with readonly_connection(settings) as conn,SourceWitnesses(settings,source_sha) as sources:
            baseline_path=Path(__file__).parent/'data/source-audit-baseline-v1.json'
            baseline=sources._json(baseline_path)
            sources._verify(baseline_path,sha256(sources._contents[baseline_path]).hexdigest(),'audit:baseline-v1')
            result['baseline']=baseline['provenance']
            state=conn.execute("SELECT current_setting('transaction_read_only') AS readonly,current_setting('transaction_isolation') AS isolation,current_setting('statement_timeout') AS statement_timeout,current_setting('lock_timeout') AS lock_timeout").fetchone()
            result['connection']=state
            if state['readonly']!='on' or state['isolation']!='repeatable read':raise ValueError('Unsafe audit connection')
            for table in TABLES:
                counts[table]=conn.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(table))).fetchone()['n']
            snapshots={str(row['id']):row for row in rows(conn,'source_snapshots')}
            for identity,snapshot in snapshots.items():
                try:sources.snapshot(snapshot)
                except (WitnessError,OSError,ValueError,KeyError) as error:add('snapshot_artifact',{'id':identity,**public_error(error)})
            notify('registered_artifacts')
            counts['search_published_witnesses_checked']=0;counts['search_published_witnesses_anchored']=0
            with open_readonly(settings.search_db) as index:
                search_counts={'documents':index.execute('SELECT count(*) FROM documents').fetchone()[0],
                    'targets':index.execute('SELECT count(DISTINCT bhid) FROM documents').fetchone()[0],
                    'languages':dict(index.execute('SELECT language,count(*) FROM documents GROUP BY language'))}
                result['search_inventory']=search_counts
                for document in index.execute('SELECT * FROM documents ORDER BY id'):
                    counts['search_published_witnesses_checked']+=1
                    try:
                        sources.search_document(document);counts['search_published_witnesses_anchored']+=1
                    except (WitnessError,ValueError,KeyError,TypeError,OSError) as error:
                        add('search_published_witness',{'document_id':document['id'],**public_error(error)})
            notify('search_published_witnesses')
            for code in coverage_issues(counts,snapshots,search_counts,baseline):add(code)
            components=rows(conn,'hadith_component_sets')
            bound_ids={b['text_version_id'] for row in components for c in row['payload']['components'] for b in c['source_bindings']}
            versions={};counts['text_versions_checked']=0;counts['text_versions_source_anchored']=0
            with conn.cursor(name='integrity_text_versions',row_factory=dict_row) as cursor:
                cursor.execute('''SELECT v.*,u.namespace,u.source_key,s.provider,s.revision,s.artifact_sha256,s.artifact_name
                    FROM text_versions v LEFT JOIN text_units u ON u.id=v.unit_id LEFT JOIN source_snapshots s ON s.id=v.snapshot_id ORDER BY v.id''')
                for row in cursor:
                    codes=checked(text_issues,row,sources);counts['text_versions_checked']+=1
                    for code in codes:add(code,{'id':str(row['id']),'source_key':row['source_key']})
                    if not codes:counts['text_versions_source_anchored']+=1
                    versions[str(row['id'])]={key:row[key] for key in ('id','unit_id','namespace','source_key','language','snapshot_id',
                        'provider','revision','artifact_sha256','artifact_name','derivation_version','locator')}
                    versions[str(row['id'])].update(raw_sha256=sha256(row['raw_text'].encode()).hexdigest(),
                        display_sha256=sha256(row['display_text'].encode()).hexdigest(),display_length=len(row['display_text']))
                    if str(row['id']) in bound_ids:versions[str(row['id'])]['display_text']=row['display_text']
            for code in hadeethenc_pair_issues(versions):add(code)
            for unit in rows(conn,'text_units'):
                if str(unit['id'])!=str(stable_id('unit',unit['namespace'],unit['source_key'])):add('text_unit_identity',{'id':str(unit['id'])})
            for segment in rows(conn,'text_segments'):
                target=versions.get(str(segment['text_version_id']))
                if target is None or not 0<=segment['start_codepoint']<segment['end_codepoint']<=target['display_length']:add('segment_range',{'id':str(segment['id'])})
            notify('text_versions')
            people={str(row['id']):row for row in rows(conn,'narrator_records')}
            source_people={r['id'] for r in sources.source.execute('SELECT id FROM narrators')}
            gk_snapshot=str(stable_id('snapshot','gk45','4.5',source_sha))
            for identity,person in people.items():
                for code in record_identity_issues(person,'narrator'):add(code,{'id':identity})
                actual=sources.source.execute('SELECT * FROM narrators WHERE id=?',(person['source_id'],)).fetchone()
                if actual is None or dict(actual)!=person['data'] or str(person['snapshot_id'])!=gk_snapshot:
                    add('narrator_source_record',{'id':identity,'source_id':person['source_id']})
            members=defaultdict(list)
            chains=rows(conn,'sanad_records');chain_ids={str(row['id']) for row in chains}
            for member in rows(conn,'sanad_members'):
                members[str(member['sanad_id'])].append(member)
                if str(member['sanad_id']) not in chain_ids:add('orphan_sanad_member',{'sanad_id':str(member['sanad_id'])})
            for row in chains:
                for code in record_identity_issues(row,'sanad'):add(code,{'id':str(row['id'])})
                source=sources.source.execute('SELECT * FROM sanad WHERE sanad_id=?',(row['source_sanad_id'],)).fetchone()
                codes=checked(chain_issues,row,members[str(row['id'])],people,versions.get(str(row['hadith_version_id'])),dict(source) if source else None,source_people)
                if str(row['snapshot_id'])!=gk_snapshot:codes.append('chain_snapshot')
                for code in codes:add(code,{'source_sanad_id':row['source_sanad_id']})
            counts['sanad_records_checked']=len(chains);counts['sanad_members_checked']=sum(map(len,members.values()))
            notify('sanad_and_narrators')
            claims=rows(conn,'localization_claims');counts['claims_source_anchored']=0
            for row in claims:
                identity=str(row['id']);snapshot=snapshots.get(str(row['snapshot_id']))
                if snapshot is None:add('claim_snapshot_missing',{'id':identity});continue
                try:
                    actual=sources.claim(row,snapshot)
                    codes=checked(claim_issues,row,actual)
                    for code in codes:add(code,{'id':identity})
                    if actual is None:add('claim_source_unverified',{'id':identity},severity='source_warning')
                    elif not codes:counts['claims_source_anchored']+=1
                except (WitnessError,OSError,ValueError,KeyError,TypeError) as error:add('claim_source_binding',{'id':identity,**public_error(error)})
            for code,identity in history_issues(claims,('snapshot_id','entity_type','entity_key','source_record_sha256','field','language')):add(code,{'table':'localization_claims','id':identity})
            counts['localization_claims_checked']=len(claims)
            notify('localization_claims')
            cases={str(row['id']):row for row in rows(conn,'alignment_cases')}
            revisions={str(row['id']):row for row in rows(conn,'alignment_revisions')};roles=defaultdict(set);alignment_members=defaultdict(list)
            for row in rows(conn,'alignment_members'):
                revision=str(row['revision_id']);target=versions.get(str(row['text_version_id']))
                if revision not in revisions or target is None:add('alignment_member_reference',{'revision_id':revision});continue
                role=row['role'];roles[revision].add(role)
                alignment_members[revision].append(row)
                if role not in ('target_arabic','bridge_arabic','translation') or (target['language']=='ar')!=(role!='translation'):
                    add('alignment_language',{'revision_id':revision})
            evidence_rows=rows(conn,'comparison_evidence');evidence_by_revision=defaultdict(list)
            counts['comparison_evidence_checked']=len(evidence_rows);counts['comparison_evidence_anchored']=0
            for row in evidence_rows:
                revision=str(row['revision_id'])
                if revision not in revisions:add('evidence_revision_missing',{'id':str(row['id'])})
                evidence_by_revision[revision].append(row)
            for identity,row in revisions.items():
                if str(row['case_id']) not in cases:add('alignment_case_missing',{'id':identity})
                if row['sealed'] and roles[identity]!={'target_arabic','bridge_arabic','translation'}:add('alignment_roles',{'id':identity})
                for evidence in evidence_by_revision[identity] or [None]:
                    codes=checked(alignment_issues,cases.get(str(row['case_id'])),row,alignment_members[identity],evidence,versions)
                    for code in codes:add(code,{'revision_id':identity})
                    if evidence is not None:
                        if evidence['method']!='research-v1-and-v2':add('evidence_method_unverified',{'id':str(evidence['id'])},severity='source_warning')
                        elif not codes:counts['comparison_evidence_anchored']+=1
            initial_cases={str(r['case_id']) for r in revisions.values() if r['revision']==1}
            for identity in cases:
                if identity not in initial_cases:add('alignment_case_without_initial_revision',{'id':identity})
            registry_path=Path(__file__).parent/'data/hadith-source-reviews-tr-v1.json'
            registry=review_registry(sources._json(registry_path))
            sources._verify(registry_path,sha256(sources._contents[registry_path]).hexdigest(),'audit:hadith-review-batch-v1')
            reviews=rows(conn,'review_events')
            counts['review_events_checked']=len(reviews);counts['review_events_source_anchored']=0;counts['review_events_batch_anchored']=0
            for row in reviews:
                revision=revisions.get(str(row['revision_id']))
                alignment={k:str(revision[k]) if k in ('id','case_id') else revision[k] for k in
                    ('id','case_id','revision','scope','sealed','relation_type')} if revision is not None else None
                try:bound=bound_members(alignment_members[str(row['revision_id'])],versions)
                except KeyError:bound=[]
                codes=checked(review_issues,row,alignment,bound,registry)
                for code in codes:add(code,{'id':str(row['id'])},severity='source_warning' if code=='review_source_schema_unverified' else 'error')
                if not codes:
                    counts['review_events_source_anchored']+=1
                    if str(row['id']) in registry:counts['review_events_batch_anchored']+=1
            for identity in set(registry)-{str(r['id']) for r in reviews}:add('review_batch_root_missing',{'id':identity})
            for code,identity in history_issues(reviews,('revision_id','actor','dimension')):add(code,{'table':'review_events','id':identity})
            counts['component_sets_checked']=len(components);counts['component_bindings_checked']=0
            for row in components:
                payload=row['payload'];source_sanads=[dict(r) for r in sources.source.execute('SELECT * FROM sanad WHERE bhid=? ORDER BY sanad_id',(payload.get('bhid'),))]
                for code in checked(component_issues,row,versions,source_sanads):add(code,{'id':str(row['id'])})
                counts['component_bindings_checked']+=sum(len(c.get('source_bindings',[])) for c in payload.get('components',[]))
            for code,identity in history_issues(components,('target_version_id','language')):add(code,{'table':'hadith_component_sets','id':identity})
            for code in checked(reuse_issues,components,versions):add(code)
            notify('components_and_review_history')
            triggers=conn.execute('''SELECT c.relname AS table_name,t.tgname,t.tgenabled FROM pg_catalog.pg_trigger t
                JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=%s AND NOT t.tgisinternal''',(settings.postgres_schema,)).fetchall()
            for table in TABLES:
                guard='alignment_revision_guard' if table=='alignment_revisions' else 'immutable_guard'
                if not any(t['table_name']==table and t['tgname']==guard and t['tgenabled'] in ('O','A') for t in triggers):add('guard_inventory_missing',{'table':table})
            constraints=conn.execute('''SELECT c.conname,c.convalidated,child.relname AS table_name,a.attname AS column_name,
                parent.relname AS referenced_table,pa.attname AS referenced_column,pn.nspname AS referenced_schema,
                cardinality(c.conkey) AS key_columns FROM pg_catalog.pg_constraint c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace JOIN pg_catalog.pg_class child ON child.oid=c.conrelid
                JOIN pg_catalog.pg_class parent ON parent.oid=c.confrelid JOIN pg_catalog.pg_namespace pn ON pn.oid=parent.relnamespace
                JOIN pg_catalog.pg_attribute a ON a.attrelid=child.oid AND a.attnum=c.conkey[1]
                JOIN pg_catalog.pg_attribute pa ON pa.attrelid=parent.oid AND pa.attnum=c.confkey[1]
                WHERE n.nspname=%s AND c.contype='f' ''',(settings.postgres_schema,)).fetchall()
            counts['declared_foreign_keys']=len(constraints)
            for code in foreign_key_issues(constraints,settings.postgres_schema):add(code)
            sources.verify_unchanged()
            result['fingerprints']=sources.fingerprints;result['artifact_files']=sources.artifact_files
            for warning in sources.warnings:add(warning['code'],warning,severity='source_warning')
            result['coverage']={'registered_snapshots':len(snapshots),'verified_snapshots':sum(verified for _,verified in sources._snapshots.values()),
                                'unverified_snapshots':sum(not verified for _,verified in sources._snapshots.values()),
                                'failed_snapshots':len(snapshots)-len(sources._snapshots),
                                'semantics_bibliography_reuse_eligibility':'not_evaluated','guard_inventory':'presence_and_enabled_only'}
            result['scan_complete']=True
    except (psycopg.Error,OSError,ValueError,KeyError,TypeError) as error:
        add('working_scan_incomplete',public_error(error))
    result['findings']=list(findings.values())
    result['ok']=result['scan_complete'] and not any(f['severity']=='error' for f in result['findings'])
    return result
