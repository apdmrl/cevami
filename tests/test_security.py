"""HTTP/security contracts use disposable SQLite, never live working schemas."""
from dataclasses import replace
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from hadis_web.app import create_app
from hadis_web.config import Settings
from hadis_web.search import SearchIndex, write_index
from hadis_web.source import SourceReader, open_readonly
from hadis_web.working import WorkingStore


@pytest.fixture
def installation(tmp_path):
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as db:
        db.executescript('''
            CREATE TABLE books(book_id TEXT PRIMARY KEY,name TEXT,author TEXT,priority INTEGER,
                publisher TEXT,edition TEXT,year_pub TEXT,editor TEXT);
            INSERT INTO books VALUES('146','كتاب','O''Neil',1,'','','','');
            CREATE TABLE hadith_text(bhid TEXT PRIMARY KEY,book_id TEXT,hadith_num INTEGER,raw_text TEXT,clean_text TEXT);
            INSERT INTO hadith_text VALUES('146_1','146',1,'أصل محفوظ','أصل محفوظ');
            CREATE TABLE hadith(bhid TEXT PRIMARY KEY,ehala TEXT,hokm INTEGER);
            INSERT INTO hadith VALUES('146_1','1',0);
            CREATE TABLE sanad(sanad_id INTEGER,bhid TEXT,rawy_ids TEXT,cluster_id INTEGER,hokm INTEGER);
            CREATE TABLE narrators(id INTEGER PRIMARY KEY,name TEXT,shohra TEXT,wasf_rotba TEXT);
            INSERT INTO narrators VALUES(1,'راو','راو','ثقة');
            CREATE TABLE critics(alem_id TEXT,name TEXT);
            CREATE TABLE critic_opinions(rawy_id TEXT,alem_id TEXT,opinion TEXT);
            CREATE VIRTUAL TABLE hadith_fts USING fts5(bhid UNINDEXED,book_id UNINDEXED,text);
            INSERT INTO hadith_fts VALUES('146_1','146','أصل محفوظ');
        ''')
    manifest=tmp_path/'references/datasets/jawami3_alkalem/verification.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({'database_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}),encoding='utf-8')
    settings=replace(Settings(),source_db=source,search_db=tmp_path/'search.sqlite',project_root=tmp_path,
                     books_archive=tmp_path/'absent.zip',postgres_dsn=None)
    records=[dict(bhid='146_1',book_id='146',book_name='كتاب',hadith_num=1,language='tr',
                  text='Niyet ve merhamet.',edition='fixture',source_key='1',revision='fixture',
                  source_url='https://example.test/source',target_raw_sha256='fixture')]
    write_index(settings.search_db,records,{'purpose':'disposable security test'})
    return settings


@pytest.fixture
def client(installation):
    return TestClient(create_app(installation),base_url='http://127.0.0.1:8765',raise_server_exceptions=False)


@pytest.mark.parametrize('host',['attacker.invalid','127.0.0.1.attacker.invalid','localhost.attacker.invalid',
                                      'localhost@attacker.invalid','testserver','[::1].attacker.invalid'])
def test_local_reader_rejects_foreign_or_ambiguous_host(client,host):
    assert client.get('/api/books?limit=1',headers={'host':host}).status_code==400


@pytest.mark.parametrize('url',['http://127.0.0.1:8765','http://localhost:8765','http://[::1]:8765'])
def test_loopback_readers_and_launcher_without_browser_headers_still_work(installation,url):
    response=TestClient(create_app(installation),base_url=url).get('/api/books?limit=1')
    assert response.status_code==200
    assert response.json()['total']==1


@pytest.mark.parametrize('origin',['https://attacker.invalid','http://127.0.0.1:9999','null',
                                        'http://127.0.0.1:8765.attacker.invalid','http://user@127.0.0.1:8765'])
def test_foreign_origin_cannot_read_local_api(client,origin):
    assert client.get('/api/books',headers={'origin':origin}).status_code==403


@pytest.mark.parametrize('site',['cross-site','same-site'])
def test_cross_origin_api_fetch_is_denied_even_without_origin(client,site):
    assert client.get('/api/books',headers={'sec-fetch-site':site}).status_code==403


def test_same_origin_fetch_and_external_navigation_to_home_are_allowed(client):
    assert client.get('/api/books',headers={'origin':'http://127.0.0.1:8765','sec-fetch-site':'same-origin'}).status_code==200
    assert client.get('/',headers={'sec-fetch-site':'cross-site','sec-fetch-mode':'navigate'}).status_code==200


def test_duplicate_security_headers_do_not_bypass_checks(client):
    assert client.get('/api/books',headers=[('host','127.0.0.1:8765'),('host','attacker.invalid')]).status_code==400
    assert client.get('/api/books',headers=[('origin','http://127.0.0.1:8765'),('origin','https://attacker.invalid')]).status_code==403


@pytest.mark.parametrize('path',['/','/research','/hadith/146_1','/assets/app.js','/api/books','/missing','/api/books?limit=900'])
def test_security_policy_covers_documents_assets_api_and_error_responses(client,path):
    response=client.get(path)
    assert response.headers.get('x-content-type-options')=='nosniff'
    assert response.headers.get('x-frame-options')=='DENY'
    assert response.headers.get('referrer-policy')=='no-referrer'
    assert response.headers.get('cross-origin-resource-policy')=='same-origin'
    policy=response.headers.get('content-security-policy','')
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "base-uri 'none'" in policy
    assert "connect-src 'self'" in policy
    assert "'unsafe-eval'" not in policy
    assert 'access-control-allow-origin' not in response.headers


@pytest.mark.parametrize('path',['/api/narrator/999999999999999999999','/api/narrator/-1',
    '/api/narrator/999999999999999999999/opinions','/api/books?offset=999999999999999999999',
    '/api/books/146/hadiths?offset=999999999999999999999',
    '/api/hadith/146_1/sanads?offset=999999999999999999999',
    '/api/narrator/1/opinions?offset=999999999999999999999',
    '/api/search?q=niyet&offset=999999999999999999999'])
def test_numeric_overflow_is_rejected_instead_of_reaching_sqlite(client,path):
    assert client.get(path).status_code==422


def test_query_and_identifier_sizes_are_bounded_before_database_work(client):
    assert client.get('/api/search',params={'q':'x'*161}).status_code==422
    assert client.get('/api/search',params={'book_id':'1'*21}).status_code==422
    assert client.get('/api/search',params={'q':'x'*9000}).status_code==414


@pytest.mark.parametrize('payload',["' OR 1=1 --", "'; DROP TABLE books; --", '" UNION SELECT 1 --',
                                       '<img src=x onerror=alert(1)>','niyet" OR "mercy'])
def test_sql_and_fts_tokens_are_data_not_executable_syntax(client,installation,payload):
    assert client.get('/api/books',params={'q':payload}).json()['total']==0
    result=client.get('/api/search',params={'q':payload,'language':'tr'})
    assert result.status_code==200
    assert result.json()['total']==0
    assert client.get('/api/books',params={'q':"O'Neil"}).json()['total']==1
    assert client.get('/api/search',params={'q':'niyet','language':'tr'}).json()['total']==1
    assert SourceReader(installation).book("146' OR 1=1 --") is None
    assert SearchIndex(installation).translations("146_1' OR 1=1 --",'tr','fixture')['items']==[]


@pytest.mark.parametrize('path',['/assets/%2e%2e/app.py','/assets/%2e%2e/%2e%2e/.local/settings.json',
    '/assets/..%5capp.py','/.env','/.local/settings.json','/hadis_web/config.py',
    '/references/datasets/jawami3_alkalem/jawami.db'])
def test_private_files_cannot_be_downloaded_from_http(client,path):
    assert client.get(path).status_code in (400,404)


def test_readonly_source_and_index_connections_cannot_modify_even_fixture_data(installation):
    for path,table in [(installation.source_db,'books'),(installation.search_db,'documents')]:
        with open_readonly(path) as db:
            with pytest.raises(sqlite3.OperationalError):
                db.execute(f'DELETE FROM {table}')
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==1


@pytest.mark.parametrize('method',['POST','PUT','PATCH','DELETE'])
def test_reader_exposes_no_mutation_endpoint(client,method):
    assert client.request(method,'/api/books',json={'q':'replace'}).status_code==405


def test_sql_schema_cannot_be_supplied_as_sql_text():
    with pytest.raises(ValueError): WorkingStore('not-a-connection','hadis; DROP SCHEMA public')


def test_unexpected_errors_never_disclose_traceback_or_settings(installation):
    app=create_app(installation)
    @app.get('/fixture-failure')
    def fail(): raise RuntimeError('PRIVATE_DSN_AND_SQL_SHOULD_NOT_LEAK')
    response=TestClient(app,base_url='http://127.0.0.1',raise_server_exceptions=False).get('/fixture-failure')
    assert response.status_code==500
    assert 'PRIVATE_DSN' not in response.text
    assert 'Traceback' not in response.text
    assert response.headers.get('x-content-type-options')=='nosniff'


def test_expensive_sql_is_interrupted_without_changing_import_connections(installation):
    with open_readonly(installation.source_db,query_timeout=.005) as db:
        with pytest.raises(sqlite3.OperationalError,match='interrupted'):
            db.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000000) SELECT sum(x) FROM n').fetchone()
    with open_readonly(installation.source_db) as db:
        assert db.execute('SELECT count(*) FROM books').fetchone()[0]==1


def test_web_pg_connections_are_readonly_and_bounded_while_cli_remains_writable(monkeypatch):
    calls=[]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):pass
    def connect(*args,**kwargs):calls.append(kwargs);return Connection()
    monkeypatch.setattr('hadis_web.working.psycopg.connect',connect)
    with WorkingStore('fixture',read_only=True).connection():pass
    assert calls[0]['connect_timeout']<=5
    assert 'default_transaction_read_only=on' in calls[0]['options']
    assert 'statement_timeout=5000' in calls[0]['options']
    assert 'lock_timeout=1000' in calls[0]['options']
    with WorkingStore('fixture').connection():pass
    assert 'default_transaction_read_only=on' not in calls[1].get('options','')
