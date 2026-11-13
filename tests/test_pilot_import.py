import json
import uuid
from pathlib import Path
import psycopg
from psycopg import sql

from hadis_web.config import Settings
from hadis_web.working import WorkingStore
from hadis_web.importer import load_pilot


def test_real_pilot_import_preserves_sanads_and_does_not_duplicate():
    settings = Settings.load()
    schema = 'test_' + uuid.uuid4().hex
    store = WorkingStore(settings.postgres_dsn, schema)
    store.migrate()
    try:
        first = load_pilot(store, settings)
        assert first['text_versions'] == 22209
        assert first['alignment_revisions'] == 4605
        assert first['sanad_records'] == 8795
        assert first['review_events'] == 0
        with store.connection() as c:
            chain = c.execute('SELECT sm.position,sm.source_value,sm.kind FROM sanad_members sm '
                              'JOIN sanad_records s ON s.id=sm.sanad_id WHERE s.source_sanad_id=74259 ORDER BY sm.position').fetchall()
        assert [r['source_value'] for r in chain] == ['6817','30001','4864','6641','5688','7272','5594','4049']
        assert chain[1]['kind'] == 'structural_marker'
        with store.connection() as c:
            versions = {r['source_key']: r['id'] for r in c.execute("SELECT tv.id,u.source_key FROM text_versions tv JOIN text_units u ON u.id=tv.unit_id WHERE u.namespace='gk45:ar' AND u.source_key IN ('146_5','146_1')")}
        assert store.translations('146_5', versions['146_5'])['items'][0]['source_key'] == '6'
        assert store.translations('146_1', versions['146_1'])['items'][0]['review']['status'] == 'needs_review'
        second = load_pilot(store, settings)
        assert second == first
    finally:
        with psycopg.connect(settings.postgres_dsn, autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
