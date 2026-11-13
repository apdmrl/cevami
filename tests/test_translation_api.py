from dataclasses import replace
import json
import uuid
import psycopg
from psycopg import sql
from fastapi.testclient import TestClient
from hadis_web.app import create_app
from hadis_web.config import Settings
from hadis_web.working import WorkingStore
from hadis_web.source import SourceReader


def test_translation_candidates_keep_their_source_key_and_review_state():
    settings = Settings.load()
    schema = 'test_' + uuid.uuid4().hex
    store = WorkingStore(settings.postgres_dsn, schema)
    store.migrate()
    try:
        checksum = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text())['database_sha256']
        snapshot = store.add_snapshot('gk45', '4.5', checksum, 'jawami.db')
        current = SourceReader(settings).hadith('146_5')['arabic']
        target = store.add_text(snapshot, 'gk45:ar', '146_5', 'ar', current['raw_text'], current['text'], {})
        bridge = store.add_text(snapshot, 'fixture:ar', '6', 'ar', 'الأصل', 'الأصل', {})
        translation = store.add_text(snapshot, 'fixture:tr', '6', 'tr', 'Örnek çeviri', 'Örnek çeviri', {})
        store.add_alignment(target, bridge, translation, {'method': 'fixture'})
        client = TestClient(create_app(replace(settings, postgres_schema=schema)),base_url='http://127.0.0.1')
        response = client.get('/api/hadith/146_5/translations')
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 1
        assert data['items'][0]['source_key'] == '6'
        assert data['items'][0]['review']['status'] == 'needs_review'
        assert data['items'][0]['review']['expert_reviewed'] is False
        assert client.get('/api/hadith/146_4412/translations').json()['items'] == []

        # Same source key, but changed text or source artifact: neither old
        # association may be inherited by the currently displayed Arabic.
        old_snapshot = store.add_snapshot('gk45', '4.5', 'a' * 64, 'jawami-old.db')
        old_target = store.add_text(old_snapshot, 'gk45:ar', '146_5', 'ar', current['raw_text'], current['text'], {})
        changed_target = store.add_text(snapshot, 'gk45:ar', '146_5', 'ar', 'نص مختلف', 'نص مختلف', {})
        store.add_alignment(old_target, bridge, translation, {'method': 'older-artifact'})
        store.add_alignment(changed_target, bridge, translation, {'method': 'changed-text'})
        assert client.get('/api/hadith/146_5/translations').json()['total'] == 1
    finally:
        with psycopg.connect(settings.postgres_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
