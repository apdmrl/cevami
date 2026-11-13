from pathlib import Path
from functools import lru_cache
import hashlib
import html
import json
import re
from psycopg.types.json import Jsonb
from .source import open_readonly, arabic_content, STRUCTURAL_IDS
from .working import stable_id, text_identity


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


@lru_cache(maxsize=8)
def _digest_at_signature(path, signature):
    # The signature is part of the cache key. A changed file is hashed again.
    return digest(Path(path))


def verify_artifact(path, expected):
    path=Path(path).resolve()
    def signature():
        stat=path.stat()
        return stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino
    before=signature()
    actual=_digest_at_signature(str(path),before)
    if signature()!=before or actual!=expected:
        raise ValueError('Source artifact checksum differs or file changed; import stopped')
    return actual


def batch(conn, query, rows):
    if rows:
        with conn.cursor() as cursor:
            cursor.executemany(query, rows)


def load_pilot(store, settings):
    root = settings.project_root
    verification = json.loads((root / 'references/datasets/jawami3_alkalem/verification.json').read_text())
    coverage = json.loads((root / 'references/turkish/fawazahmed0/coverage.json').read_text())
    external = root / 'references/turkish/fawazahmed0'
    bukhari = next(c for c in coverage['collections'] if c['book'] == 'bukhari')
    if digest(settings.source_db) != verification['database_sha256']:
        raise ValueError('Reference database checksum differs; import stopped')
    for language, prefix in [('ar', 'ara'), ('tr', 'tur')]:
        if digest(external / f'{prefix}-bukhari.json') != bukhari[prefix]['sha256']:
            raise ValueError('Translation source checksum differs; import stopped')
    snapshots = {
        'gk45:ar': store.add_snapshot('gk45', '4.5', verification['database_sha256'], 'jawami.db'),
        'fawaz:ara-bukhari': store.add_snapshot('fawazahmed0', coverage['revision'], bukhari['ara']['sha256'], 'ara-bukhari.json'),
        'fawaz:tur-bukhari': store.add_snapshot('fawazahmed0', coverage['revision'], bukhari['tur']['sha256'], 'tur-bukhari.json'),
    }
    units, versions, version_ids = [], [], {}

    def collect(namespace, key, language, raw, display, locator):
        snapshot = snapshots[namespace]
        unit, identity, checksum = text_identity(snapshot, namespace, key, raw, display)
        units.append((unit, namespace, str(key)))
        versions.append((identity, unit, snapshot, language, raw, display, checksum, Jsonb(locator)))
        version_ids[(namespace, str(key))] = identity

    with open_readonly(settings.source_db) as source:
        for row in source.execute("SELECT * FROM hadith_text WHERE book_id='146' ORDER BY hadith_num"):
            collect('gk45:ar', row['bhid'], 'ar', row['raw_text'], arabic_content(row['raw_text'])['text'],
                    {'table': 'hadith_text', 'key': row['bhid'], 'book_id': '146'})
        chains = [dict(row) for row in source.execute("SELECT s.* FROM sanad s JOIN hadith_text t ON t.bhid=s.bhid WHERE t.book_id='146'")]
        narrator_ids = {int(n) for row in chains for n in row['rawy_ids'].split(',') if n.isdigit()}
        narrators = [dict(r) for r in source.execute('SELECT * FROM narrators WHERE id IN (' + ','.join('?' for _ in narrator_ids) + ')', list(narrator_ids))]
    for language, prefix in [('ar', 'ara'), ('tr', 'tur')]:
        data = json.loads((external / f'{prefix}-bukhari.json').read_text(encoding='utf-8'))
        for ordinal, row in enumerate(data['hadiths']):
            text = row.get('text', '')
            display = html.unescape(re.sub(r'<[^>]+>', '', text))
            collect(f'fawaz:{prefix}-bukhari', str(row['hadithnumber']), language, text, display,
                    {'json_pointer': f'/hadiths/{ordinal}', 'hadithnumber': row['hadithnumber'],
                     'arabicnumber': row.get('arabicnumber'), 'reference': row.get('reference'),
                     'bibliography_status': 'unverified'})
    evidence = { (r['gk_bhid'], r['source_key']): r for r in
                (json.loads(s) for s in (root / 'research/bukhari-review/candidate-comparisons.jsonl').read_text(encoding='utf-8').splitlines()) }
    links = [json.loads(s) for s in (root / 'research/turkish-sources/bukhari-candidate-links.jsonl').read_text(encoding='utf-8').splitlines()]
    with store.connection() as conn:
        batch(conn, 'INSERT INTO text_units VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', units)
        batch(conn, 'INSERT INTO text_versions(id,unit_id,snapshot_id,language,raw_text,display_text,raw_sha256,locator) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', versions)
        existing = {str(row['id']) for row in conn.execute('SELECT id FROM alignment_revisions')}
        cases, revisions, members, results, to_seal = [], [], [], [], []
        for link in links:
            target = version_ids[('gk45:ar', link['gk_bhid'])]
            bridge = version_ids[('fawaz:ara-bukhari', link['source_key'])]
            translation = version_ids[('fawaz:tur-bukhari', link['source_key'])]
            fingerprint = hashlib.sha256(json.dumps([str(target), str(bridge), str(translation), 'unclassified']).encode()).hexdigest()
            case = stable_id('case', fingerprint)
            revision = stable_id('alignment', str(case), 1)
            if str(revision) in existing:
                continue
            cases.append((case, fingerprint))
            revisions.append((revision, case, 'unclassified'))
            members.extend((revision, identity, role, 0) for role, identity in
                           [('target_arabic', target), ('bridge_arabic', bridge), ('translation', translation)])
            result = {'v1': link, 'v2': evidence[(link['gk_bhid'], link['source_key'])]}
            results.append((stable_id('evidence', str(revision), 'initial'), revision, 'research-v1-and-v2', Jsonb(result)))
            to_seal.append((revision,))
        batch(conn, 'INSERT INTO alignment_cases VALUES(%s,%s) ON CONFLICT DO NOTHING', cases)
        batch(conn, 'INSERT INTO alignment_revisions(id,case_id,revision,scope) VALUES(%s,%s,1,%s)', revisions)
        batch(conn, 'INSERT INTO alignment_members VALUES(%s,%s,%s,%s)', members)
        batch(conn, 'UPDATE alignment_revisions SET sealed=true WHERE id=%s', to_seal)
        batch(conn, 'INSERT INTO comparison_evidence VALUES(%s,%s,%s,%s)', results)
        snapshot = snapshots['gk45:ar']
        narrator_map = {row['id']: stable_id('narrator', str(snapshot), row['id']) for row in narrators}
        batch(conn, 'INSERT INTO narrator_records VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',
              [(narrator_map[row['id']], snapshot, row['id'], Jsonb(row)) for row in narrators])
        sanad_rows, sanad_members = [], []
        for row in chains:
            identity = stable_id('sanad', str(snapshot), row['sanad_id'])
            sanad_rows.append((identity, snapshot, row['sanad_id'], version_ids[('gk45:ar', row['bhid'])], row['rawy_ids'], Jsonb(row)))
            for position, value in enumerate(row['rawy_ids'].split(',')):
                source_id = int(value) if value.isdigit() else None
                kind = 'structural_marker' if source_id in STRUCTURAL_IDS else 'narrator' if source_id in narrator_map else 'unresolved'
                sanad_members.append((identity, position, value, narrator_map.get(source_id), kind))
        batch(conn, 'INSERT INTO sanad_records VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', sanad_rows)
        batch(conn, 'INSERT INTO sanad_members VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', sanad_members)
    return store.counts()
