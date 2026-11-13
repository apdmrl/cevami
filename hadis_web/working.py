from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import re
import uuid
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

NAMESPACE = uuid.UUID('97978197-44d4-4143-97d6-231a82a3b705')
REQUIRED_DIMENSIONS = ('arabic_relation', 'translation_meaning', 'translation_completeness', 'notes_separation')


def stable_id(*parts):
    return uuid.uuid5(NAMESPACE, json.dumps(parts, ensure_ascii=False, separators=(',', ':')))


def text_identity(snapshot, namespace, key, raw, display):
    unit = stable_id('unit', namespace, str(key))
    raw_hash = hashlib.sha256(raw.encode()).hexdigest()
    identity = stable_id('text', str(snapshot), str(unit), raw_hash, hashlib.sha256(display.encode()).hexdigest(), 'reader-v1')
    return unit, identity, raw_hash


class WorkingStore:
    def __init__(self, dsn, schema='hadis', *, read_only=False):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('Invalid PostgreSQL schema name')
        self.dsn = dsn
        self.schema = schema
        self.read_only=read_only

    @contextmanager
    def connection(self):
        options={'connect_timeout':3,'options':'-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'} if self.read_only else {}
        with psycopg.connect(self.dsn, row_factory=dict_row,**options) as conn:
            conn.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(self.schema)))
            yield conn

    def migrate(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
            conn.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(self.schema)))
            for path in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
                conn.execute(path.read_text(encoding='utf-8'))

    def add_snapshot(self, provider, revision, checksum, artifact_name):
        identity = stable_id('snapshot', provider, revision, checksum)
        with self.connection() as conn:
            conn.execute('INSERT INTO source_snapshots(id,provider,revision,artifact_sha256,artifact_name) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                         (identity, provider, revision, checksum, artifact_name))
        return identity

    def add_text(self, snapshot, namespace, key, language, raw, display, locator):
        unit, identity, checksum = text_identity(snapshot, namespace, key, raw, display)
        with self.connection() as conn:
            conn.execute('INSERT INTO text_units VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (unit, namespace, str(key)))
            conn.execute('INSERT INTO text_versions(id,unit_id,snapshot_id,language,raw_text,display_text,raw_sha256,locator) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                         (identity, unit, snapshot, language, raw, display, checksum, Jsonb(locator)))
        return identity

    def add_alignment(self, target, bridge, translation, evidence, scope='unclassified'):
        fingerprint = hashlib.sha256(json.dumps([str(target), str(bridge), str(translation), scope]).encode()).hexdigest()
        case = stable_id('case', fingerprint)
        revision = stable_id('alignment', str(case), 1)
        with self.connection() as conn:
            exists = conn.execute('SELECT id FROM alignment_revisions WHERE id=%s', (revision,)).fetchone()
            if not exists:
                conn.execute('INSERT INTO alignment_cases VALUES(%s,%s) ON CONFLICT DO NOTHING', (case, fingerprint))
                conn.execute('INSERT INTO alignment_revisions(id,case_id,revision,scope) VALUES(%s,%s,1,%s)', (revision, case, scope))
                for role, identity in [('target_arabic', target), ('bridge_arabic', bridge), ('translation', translation)]:
                    conn.execute('INSERT INTO alignment_members VALUES(%s,%s,%s,0)', (revision, identity, role))
                conn.execute('UPDATE alignment_revisions SET sealed=true WHERE id=%s', (revision,))
                conn.execute('INSERT INTO comparison_evidence VALUES(%s,%s,%s,%s)',
                             (stable_id('evidence', str(revision), 'initial'), revision, evidence.get('method', 'source-comparison'), Jsonb(evidence)))
        return revision

    def record_review(self, revision, actor, actor_kind, dimension, outcome, rationale, source_refs, supersedes_id=None):
        if actor_kind == 'automated_check' and outcome in ('pass', 'not_applicable'):
            raise ValueError('Automated comparisons cannot approve source/translation dimensions')
        identity = uuid.uuid4()
        with self.connection() as conn:
            conn.execute('INSERT INTO review_events(id,revision_id,actor,actor_kind,dimension,outcome,rationale,source_refs,supersedes_id) '
                         'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (identity, revision, actor, actor_kind, dimension, outcome, rationale, Jsonb(source_refs), supersedes_id))
        return identity

    def assessment(self, revision):
        with self.connection() as conn:
            record = conn.execute('SELECT scope FROM alignment_revisions WHERE id=%s', (revision,)).fetchone()
            if record is None:
                raise ValueError('Unknown alignment revision')
            rows = conn.execute('SELECT e.* FROM review_events e WHERE e.revision_id=%s '
                                'AND NOT EXISTS(SELECT 1 FROM review_events newer WHERE newer.supersedes_id=e.id)', (revision,)).fetchall()
        dimensions = {d: 'pending' for d in (*REQUIRED_DIMENSIONS, 'bibliography')}
        for dimension in dimensions:
            active = [r['outcome'] for r in rows if r['dimension'] == dimension and r['actor_kind'] != 'automated_check']
            if 'fail' in active:
                dimensions[dimension] = 'fail'
            elif active and all(v == 'pass' for v in active):
                dimensions[dimension] = 'pass'
            elif active and all(v == 'not_applicable' for v in active):
                dimensions[dimension] = 'not_applicable'
        if 'fail' in dimensions.values():
            status = 'problem_detected'
        elif record['scope'] != 'unclassified' and all(dimensions[d] == 'pass' for d in REQUIRED_DIMENSIONS):
            status = 'source_compared'
        else:
            status = 'needs_review'
        experts = {r['dimension'] for r in rows if r['actor_kind'] == 'expert_review' and r['outcome'] == 'pass'}
        return {'status': status, 'expert_reviewed': status == 'source_compared' and all(d in experts for d in REQUIRED_DIMENSIONS),
                'bibliography': dimensions['bibliography'], 'dimensions': dimensions, 'scope': record['scope'],
                'events': [{'id': str(r['id']), 'actor_kind': r['actor_kind'], 'dimension': r['dimension'],
                            'outcome': r['outcome'], 'rationale': r['rationale'], 'sources': r['source_refs']}
                           for r in sorted(rows, key=lambda r: (r['dimension'], str(r['id'])))]}

    def counts(self):
        tables = ('source_snapshots', 'text_units', 'text_versions', 'alignment_revisions', 'review_events', 'sanad_records', 'sanad_members', 'narrator_records')
        with self.connection() as conn:
            return {name: conn.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}').format(sql.Identifier(name))).fetchone()['n'] for name in tables}

    def translations(self, bhid, target_version_id):
        with self.connection() as conn:
            rows = conn.execute("SELECT r.id AS alignment_revision_id, r.scope, tr.raw_text, tr.display_text, u.source_key, "
                                "u.namespace, s.provider, s.revision, e.evidence FROM text_units target "
                                "JOIN text_versions tv ON tv.unit_id=target.id "
                                "JOIN alignment_members am ON am.text_version_id=tv.id AND am.role='target_arabic' "
                                "JOIN alignment_revisions r ON r.id=am.revision_id "
                                "JOIN alignment_members tm ON tm.revision_id=r.id AND tm.role='translation' "
                                "JOIN text_versions tr ON tr.id=tm.text_version_id JOIN text_units u ON u.id=tr.unit_id "
                                "JOIN source_snapshots s ON s.id=tr.snapshot_id "
                                "LEFT JOIN comparison_evidence e ON e.revision_id=r.id "
                                "WHERE target.namespace='gk45:ar' AND target.source_key=%s AND tv.id=%s "
                                "AND r.sealed=true ORDER BY u.source_key", (bhid, target_version_id)).fetchall()
        items = []
        for row in rows:
            result = dict(row)
            result['alignment_revision_id'] = str(result['alignment_revision_id'])
            result['review'] = self.assessment(row['alignment_revision_id'])
            items.append(result)
        return {'available': True, 'items': items, 'total': len(items), 'target_version_id': str(target_version_id)}
