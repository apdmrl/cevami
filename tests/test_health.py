import json
import sqlite3
import zipfile
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from hadis_web.config import Settings
from hadis_web import health


@pytest.fixture
def installation(tmp_path, monkeypatch):
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as c:
        for table in ('books','hadith_text','sanad'):
            c.execute(f'CREATE TABLE {table}(id INTEGER)')
            c.execute(f'INSERT INTO {table} VALUES (1)')
    search=tmp_path/'search.sqlite'
    with sqlite3.connect(search) as c:
        for table in ('documents','metadata','search_fts'):
            c.execute(f'CREATE TABLE {table}(value TEXT)')
            c.execute(f'INSERT INTO {table} VALUES (?)',('source fixture',))
    archive=tmp_path/'Books.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('books/test','fixture')
    settings=Settings(project_root=tmp_path,source_db=source,search_db=search,books_archive=archive,postgres_dsn='postgresql://private-sentinel')
    monkeypatch.setattr(health,'working_state',lambda settings:'ready')
    return settings


def test_ready_is_read_only_and_does_not_expose_connection_or_paths(installation):
    paths=(installation.source_db,installation.search_db,installation.books_archive)
    before={p:p.read_bytes() for p in paths}
    report=health.health_report(installation)
    assert report['ready'] is True
    assert report['app']=='cevami-reader'
    assert report['installation_id']==health.installation_id(installation.project_root)
    assert 'private-sentinel' not in json.dumps(report)
    assert str(installation.project_root) not in json.dumps(report)
    assert before=={p:p.read_bytes() for p in paths}


@pytest.mark.parametrize('field,check',[('source_db','source'),('search_db','search'),('books_archive','archive')])
def test_missing_resource_is_not_created_or_reported_ready(installation,field,check):
    missing=installation.project_root/'missing-resource'
    report=health.health_report(replace(installation,**{field:missing}))
    assert not report['ready']
    assert report['checks'][check]!='ready'
    assert not missing.exists()


@pytest.mark.parametrize('field,check',[('source_db','source'),('search_db','search'),('books_archive','archive')])
def test_corrupt_resource_is_unavailable_without_raw_exception(installation,field,check):
    getattr(installation,field).write_bytes(b'broken fixture')
    report=health.health_report(installation)
    assert report['checks'][check]=='unavailable'
    assert not report['ready']
    assert 'broken fixture' not in json.dumps(report)


def test_failed_working_layer_prevents_full_readiness(installation,monkeypatch):
    monkeypatch.setattr(health,'working_state',lambda settings:'unavailable')
    assert not health.health_report(installation)['ready']
    assert health.installation_id(installation.project_root)!=health.installation_id(installation.project_root/'other')


def test_health_endpoint_uses_its_own_installation(installation):
    from hadis_web.app import create_app
    manifest=installation.project_root/'references/datasets/jawami3_alkalem/verification.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'database_sha256':'a'*64}))
    with TestClient(create_app(installation),base_url='http://127.0.0.1') as client:
        response=client.get('/api/health')
    assert response.status_code==200
    assert response.json()['installation_id']==health.installation_id(installation.project_root)


def test_working_errors_and_unconfigured_dsn_are_not_disclosed(monkeypatch):
    def failed(*a,**kw):raise health.psycopg.OperationalError('private-password-sentinel')
    monkeypatch.setattr(health.psycopg,'connect',failed)
    assert health.working_state(Settings(postgres_dsn=None))=='unconfigured'
    assert health.working_state(Settings(postgres_dsn='private-password-sentinel'))=='unavailable'


def test_closed_wal_source_probe_creates_no_sidecars(installation):
    with sqlite3.connect(installation.source_db) as c:c.execute('PRAGMA journal_mode=WAL')
    before={p.name:p.read_bytes() for p in installation.project_root.iterdir() if p.is_file()}
    assert health.sqlite_state(installation.source_db,('books','hadith_text','sanad'))=='ready'
    after={p.name:p.read_bytes() for p in installation.project_root.iterdir() if p.is_file()}
    assert after==before,'Readiness must not create or modify source WAL/SHM files'
