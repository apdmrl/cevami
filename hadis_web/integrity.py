"""Read-only structural audit. This never certifies a translation's meaning."""
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from .source import open_readonly, STRUCTURAL_IDS
from .search import search_text


def audit(settings):
    counts, findings = {}, {}
    source_sha,expected_sha = None,None
    def add(code, severity, example=None, count=1):
        item = findings.setdefault(code,{'code':code,'severity':severity,'count':0,'examples':[]})
        item['count'] += count
        if example is not None and len(item['examples']) < 12:
            item['examples'].append(example)
    def result():
        items = list(findings.values())
        ok = not any(f['severity']=='error' for f in items)
        return {'ok':ok, 'status':'technical_error' if not ok else 'technical_checks_passed',
                'checked_at_utc':datetime.now(timezone.utc).isoformat(),
                'meaning_reviewed':False,'expert_approval':False,
                'fingerprints':{'source_sha256':source_sha,'expected_source_sha256':expected_sha},
                'scope':['source_snapshot','book_text_links','recorded_chain_identifiers','search_target_binding','fts_content'],
                'counts':counts,'findings':items}

    manifest = json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    expected_sha = manifest['database_sha256']
    with settings.source_db.open('rb') as stream:
        source_sha = hashlib.file_digest(stream,'sha256').hexdigest()
    if source_sha != manifest['database_sha256']:
        add('source_snapshot_mismatch','error')
    with open_readonly(settings.source_db) as source:
        for table in ('books','hadith_text','narrators','sanad'):
            counts['source_'+table] = source.execute('SELECT count(*) FROM '+table).fetchone()[0]
        dangling = source.execute('''SELECT count(*) FROM hadith_text t LEFT JOIN books b ON b.book_id=t.book_id
                                    WHERE b.book_id IS NULL''').fetchone()[0]
        if dangling: add('text_without_book','source_warning',count=dangling)
        dangling = source.execute('''SELECT count(*) FROM sanad s LEFT JOIN hadith_text t ON t.bhid=s.bhid
                                    WHERE t.bhid IS NULL''').fetchone()[0]
        if dangling: add('chain_without_text','source_warning',count=dangling)
        people = {int(row[0]) for row in source.execute('SELECT id FROM narrators')}
        counts.update(chain_members=0,structural_marker_references=0,person_references=0)
        for chain in source.execute('SELECT sanad_id,rawy_ids FROM sanad'):
            for value in (chain['rawy_ids'] or '').split(','):
                counts['chain_members'] += 1
                if not value.strip().isascii() or not value.strip().isdigit():
                    add('invalid_chain_token','source_warning',{'sanad_id':chain['sanad_id'],'value':value})
                    continue
                identity = int(value)
                if identity in STRUCTURAL_IDS:
                    counts['structural_marker_references'] += 1
                elif identity in people:
                    counts['person_references'] += 1
                else:
                    add('unknown_person_reference','source_warning',{'sanad_id':chain['sanad_id'],'source_id':identity})

        if not settings.search_db.exists():
            add('search_index_unavailable','error')
            return result()
        try:
            with open_readonly(settings.search_db) as index:
                metadata = json.loads(index.execute('SELECT value FROM metadata').fetchone()[0])
                if metadata.get('source_sha256') != source_sha:
                    add('index_snapshot_mismatch','error')
                documents = index.execute('SELECT * FROM documents ORDER BY id').fetchall()
                counts['search_documents_checked'] = len(documents)
                counts['search_targets_checked'] = len({row['bhid'] for row in documents})
                for query,code in [
                    ('SELECT count(*) FROM documents d LEFT JOIN search_fts f ON f.rowid=d.id WHERE f.rowid IS NULL','missing_fts_document'),
                    ('SELECT count(*) FROM search_fts f LEFT JOIN documents d ON d.id=f.rowid WHERE d.id IS NULL','orphan_fts_document')]:
                    count = index.execute(query).fetchone()[0]
                    if count: add(code,'error',count=count)
                for row in index.execute('SELECT d.id,d.text,f.words FROM documents d JOIN search_fts f ON f.rowid=d.id'):
                    if row['words'] != search_text(row['text']):
                        add('fts_content_mismatch','error',{'document_id':row['id']})
                # Bind each witness to the actual current source record, never just its number.
                ids = sorted({row['bhid'] for row in documents})
                targets = {}
                for start in range(0,len(ids),500):
                    chunk = ids[start:start+500]
                    for row in source.execute('SELECT bhid,book_id,hadith_num,raw_text FROM hadith_text WHERE bhid IN ('+
                                              ','.join('?' for _ in chunk)+')',chunk):
                        targets[row['bhid']] = (row['book_id'],row['hadith_num'],hashlib.sha256(row['raw_text'].encode()).hexdigest())
                for row in documents:
                    target = targets.get(row['bhid'])
                    ref = {'document_id':row['id'],'bhid':row['bhid']}
                    if not target:
                        add('search_target_missing','error',ref)
                        continue
                    if row['book_id'] != target[0]: add('target_book_mismatch','error',ref)
                    if row['hadith_num'] != target[1]: add('target_number_mismatch','error',ref)
                    if row['target_raw_sha256'] != target[2]: add('target_raw_hash_mismatch','error',ref)
                    if row['revision'] != metadata.get('revision'): add('source_revision_mismatch','error',ref)
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            add('search_index_unreadable','error',{'type':type(exc).__name__})
    return result()
