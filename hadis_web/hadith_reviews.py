"""Atomic, source-bound assistant reviews of existing sealed hadith candidates."""
import datetime
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb
from .field_reviews import _validate_references
from .importer import verify_artifact
from .source import SourceReader
from .working import REQUIRED_DIMENSIONS, stable_id

DATA_FILE=Path(__file__).parent/'data/hadith-source-reviews-tr-v1.json'
DIMENSIONS=(*REQUIRED_DIMENSIONS,'bibliography')


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _bound_rows(conn,revision):
    alignment=conn.execute('SELECT id,case_id,revision,scope,sealed,relation_type FROM alignment_revisions WHERE id=%s',(revision,)).fetchone()
    if alignment is None: raise ValueError('Missing reviewed alignment')
    alignment={k:str(v) if k in ('id','case_id') else v for k,v in alignment.items()}
    rows=conn.execute('SELECT m.role,m.ordinal,v.*,u.namespace,u.source_key,s.provider,s.revision AS source_revision,s.artifact_sha256,s.artifact_name '
        'FROM alignment_members m JOIN text_versions v ON v.id=m.text_version_id JOIN text_units u ON u.id=v.unit_id '
        'JOIN source_snapshots s ON s.id=v.snapshot_id WHERE m.revision_id=%s ORDER BY m.role,m.ordinal',(revision,)).fetchall()
    members=[]
    for row in rows:
        if sha(row['raw_text'])!=row['raw_sha256']: raise ValueError('Stored raw text digest differs')
        member={k:str(row[k]) if k in ('id','unit_id','snapshot_id') else row[k] for k in
            ('role','ordinal','id','unit_id','snapshot_id','language','raw_sha256','derivation_version','locator','namespace','source_key','provider','source_revision','artifact_sha256','artifact_name')}
        members.append(member|{'display_sha256':sha(row['display_text'])})
    return alignment,members,rows


def _validate_sources(refs,case,reviewed_on):
    if not isinstance(refs,list) or not refs or any(not isinstance(r,dict) for r in refs):
        raise ValueError('Missing hadith review references')
    _validate_references(refs)
    for ref in refs:
        parts=urlsplit(ref['url'])
        if parts.scheme in ('http','https') and (not parts.netloc or parts.username or parts.password):
            raise ValueError('Invalid hadith review URL')
        if ref['accessed_on']!=reviewed_on: raise ValueError('Hadith review source date differs')
    for member in case['members']:
        url=f'gk45:hadith:{case["bhid"]}' if member['role']=='target_arabic' else f'https://github.com/fawazahmed0/hadith-api/tree/{member["source_revision"]}'
        matches=[r for r in refs if r['url']==url and member['raw_sha256'] in r['locator']]
        if member['role']!='target_arabic':
            matches=[r for r in matches if member['artifact_name']+member['locator']['json_pointer'] in r['locator'] and member['artifact_sha256'] in r['locator']]
        if not matches: raise ValueError('Review references do not identify the pinned source member')


def load_hadith_reviews(working,settings,*,data=None):
    data=json.loads(DATA_FILE.read_text(encoding='utf-8')) if data is None else data
    if data.get('language')!='tr' or data.get('actor_kind')!='assistant_source_review' or data.get('actor')!='assistant-hadith-source-review':
        raise ValueError('Unexpected hadith review language or actor')
    if not isinstance(data.get('revision'),str) or not data['revision'].strip(): raise ValueError('Missing hadith review batch revision')
    date=data.get('reviewed_on','')
    if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date): raise ValueError('Invalid hadith review date')
    datetime.date.fromisoformat(date)
    cases=data.get('cases')
    if not isinstance(cases,list) or not cases: raise ValueError('Missing hadith review cases')
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text(encoding='utf-8'))
    folder=settings.project_root/'references/turkish/fawazahmed0'
    coverage=json.loads((folder/'coverage.json').read_text(encoding='utf-8'))
    bukhari=next(c for c in coverage['collections'] if c['book']=='bukhari')
    verify_artifact(settings.source_db,manifest['database_sha256'])
    external={}
    for prefix in ('ara','tur'):
        path=folder/f'{prefix}-bukhari.json'
        verify_artifact(path,bukhari[prefix]['sha256'])
        external[prefix]=json.loads(path.read_text(encoding='utf-8'))['hadiths']
    reader=SourceReader(settings)
    batch_digest=sha(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    prepared=[];seen=set()
    # All validation and inserts share a transaction. The lock also serializes
    # competing root imports against ordinary record_review INSERTs.
    with working.connection() as conn:
        conn.execute('LOCK TABLE review_events IN SHARE ROW EXCLUSIVE MODE')
        for case in cases:
            expected=case['alignment']
            revision=expected['id']
            if revision in seen: raise ValueError('Duplicate hadith review alignment')
            seen.add(revision)
            alignment,members,rows=_bound_rows(conn,revision)
            if alignment!=expected or not alignment['sealed'] or alignment['scope']!='unclassified':
                raise ValueError('Reviewed alignment binding changed')
            if members!=case['members'] or len(members)!=3 or {m['role'] for m in members}!={'target_arabic','bridge_arabic','translation'}:
                raise ValueError('Reviewed member binding changed')
            current=reader.hadith(case['bhid'])['arabic']
            for member,row in zip(members,rows):
                if member['ordinal']!=0 or member['derivation_version']!='reader-v1': raise ValueError('Unexpected reviewed member derivation')
                if member['role']=='target_arabic':
                    metadata=('gk45','4.5',manifest['database_sha256'],'jawami.db','gk45:ar',case['bhid'],'ar')
                    raw,display=current['raw_text'],current['text']
                    locator={'table':'hadith_text','key':case['bhid'],'book_id':'146'}
                else:
                    prefix='ara' if member['role']=='bridge_arabic' else 'tur'
                    metadata=('fawazahmed0',coverage['revision'],bukhari[prefix]['sha256'],f'{prefix}-bukhari.json',f'fawaz:{prefix}-bukhari',member['source_key'],'ar' if prefix=='ara' else 'tr')
                    pointer=member['locator'].get('json_pointer','')
                    if not re.fullmatch(r'/hadiths/\d+',pointer): raise ValueError('Invalid reviewed source pointer')
                    index=int(pointer.rsplit('/',1)[1])
                    if index>=len(external[prefix]): raise ValueError('Reviewed source pointer outside artifact')
                    source=external[prefix][index]
                    if str(source['hadithnumber'])!=member['source_key']: raise ValueError('Reviewed source key differs')
                    raw=source['text'];display=html.unescape(re.sub('<[^>]+>','',raw))
                    locator={'json_pointer':pointer,'hadithnumber':source['hadithnumber'],'arabicnumber':source.get('arabicnumber'),
                        'reference':source.get('reference'),'bibliography_status':'unverified'}
                actual=tuple(member[k] for k in ('provider','source_revision','artifact_sha256','artifact_name','namespace','source_key','language'))
                if metadata!=actual or raw!=row['raw_text'] or display!=row['display_text'] or locator!=member['locator']:
                    raise ValueError('Live source artifact and reviewed member differ')
            reviews=case['reviews']
            if len(reviews)!=5 or {r['dimension'] for r in reviews}!=set(DIMENSIONS): raise ValueError('Duplicate or missing hadith review dimension')
            for review in reviews:
                if 'supersedes_id' in review: raise ValueError('Root batch cannot introduce correction parents')
                if review.get('outcome') not in ('pending','pass','fail','not_applicable') or not isinstance(review.get('rationale'),str) or not review['rationale'].strip():
                    raise ValueError('Invalid hadith review decision')
                _validate_sources(review.get('sources'),case,date)
                identity=stable_id('hadith-source-review',batch_digest,revision,review['dimension'])
                existing=conn.execute('SELECT id FROM review_events WHERE revision_id=%s AND actor=%s AND dimension=%s',
                    (revision,data['actor'],review['dimension'])).fetchall()
                if existing and any(r['id']!=identity for r in existing): raise ValueError('Competing hadith review root; preserve existing history')
                prepared.append((identity,revision,data['actor'],data['actor_kind'],review['dimension'],review['outcome'],review['rationale'],Jsonb(review['sources'])))
        # A late failed source binding cannot leave earlier review decisions behind.
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO review_events(id,revision_id,actor,actor_kind,dimension,outcome,rationale,source_refs) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',prepared)
    return {'revision':data['revision'],'cases':len(cases),'events':len(prepared)}
