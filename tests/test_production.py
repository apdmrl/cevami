"""Production origin/secrets contracts without servers or real corpus data."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

from hadis_web.app import create_app
from hadis_web.config import Settings
from test_security import installation


def production(installation,origin='https://hadis.example.org'):
    return replace(installation,environment='production',public_origin=origin,
                   postgres_dsn='postgresql://fixture:fixture@database/fixture')


@pytest.mark.parametrize('origin',[None,'http://hadis.example.org','https://user:pass@hadis.example.org',
    'https://hadis.example.org/path','https://hadis.example.org/?query=x',
    'https://hadis.example.org/#fragment','https://hadis.example.org:99999',
    'https://127.0.0.1','https://localhost','https://bad..example.org','https://bad-.example.org'])
def test_production_rejects_missing_or_ambiguous_public_origin(installation,origin):
    with pytest.raises(ValueError):create_app(production(installation,origin))


def test_production_requires_database_configuration(installation):
    with pytest.raises(ValueError):create_app(replace(production(installation),postgres_dsn=None))


def test_https_host_and_origin_work_behind_internal_http_proxy(installation):
    client=TestClient(create_app(production(installation)),base_url='http://hadis.example.org')
    response=client.get('/api/books',headers={'origin':'https://hadis.example.org',
                                            'x-forwarded-host':'attacker.invalid','x-forwarded-proto':'http'})
    assert response.status_code==200
    assert response.json()['total']==1
    assert response.headers['strict-transport-security']=='max-age=31536000'
    assert "script-src 'self'" in response.headers['content-security-policy']


@pytest.mark.parametrize('host',['localhost','127.0.0.1','hadis.example.org.attacker.invalid',
                                       'hadis.example.org:8080'])
def test_production_rejects_alternate_hosts_and_ports(installation,host):
    client=TestClient(create_app(production(installation)),base_url='https://hadis.example.org')
    response=client.get('/api/books',headers={'host':host})
    assert response.status_code==400
    assert 'strict-transport-security' in response.headers


@pytest.mark.parametrize('origin',['http://hadis.example.org','https://attacker.invalid','null'])
def test_production_denies_foreign_or_insecure_browser_origin(installation,origin):
    client=TestClient(create_app(production(installation)),base_url='https://hadis.example.org')
    assert client.get('/api/books',headers={'origin':origin}).status_code==403


def test_hsts_is_absent_in_local_mode(installation):
    response=TestClient(create_app(installation),base_url='http://127.0.0.1').get('/api/books')
    assert response.status_code==200
    assert 'strict-transport-security' not in response.headers


def test_secrets_are_read_from_file_and_data_paths_can_be_mounted(monkeypatch,tmp_path):
    import hadis_web.config as config
    monkeypatch.setattr(config,'APP_ROOT',tmp_path/'app')
    password=tmp_path/'password';password.write_text("a secure ' quoted password\n",encoding='utf-8')
    for key,value in {'HADIS_ENV':'production','HADIS_PUBLIC_ORIGIN':'https://hadis.example.org',
                      'HADIS_DATA_ROOT':str(tmp_path/'data'),'HADIS_DB_PASSWORD_FILE':str(password),
                      'HADIS_DB_HOST':'database','HADIS_DB_USER':'cevami_web','HADIS_DB_NAME':'cevami'}.items():
        monkeypatch.setenv(key,value)
    monkeypatch.delenv('HADIS_DATABASE_URL',raising=False)
    settings=Settings.load()
    connection=conninfo_to_dict(settings.postgres_dsn)
    assert connection['password']=="a secure ' quoted password"
    assert connection['host']=='database' and connection['user']=='cevami_web'
    assert settings.source_db==tmp_path/'data/references/datasets/jawami3_alkalem/jawami.db'
    assert settings.search_db==tmp_path/'data/search/search.sqlite'
    assert settings.project_root==tmp_path/'data'
    assert 'quoted password' not in repr(settings)


def test_missing_secret_is_a_safe_startup_error(monkeypatch,tmp_path):
    import hadis_web.config as config
    monkeypatch.setattr(config,'APP_ROOT',tmp_path/'app')
    monkeypatch.setenv('HADIS_ENV','production')
    monkeypatch.setenv('HADIS_PUBLIC_ORIGIN','https://hadis.example.org')
    monkeypatch.setenv('HADIS_DATA_ROOT',str(tmp_path/'data'))
    monkeypatch.setenv('HADIS_DB_PASSWORD_FILE',str(tmp_path/'secret-does-not-exist'))
    monkeypatch.delenv('HADIS_DATABASE_URL',raising=False)
    with pytest.raises(ValueError) as error:Settings.load()
    assert 'secret-does-not-exist' not in str(error.value)


@pytest.mark.parametrize('missing',['file','data'])
def test_production_environment_requires_explicit_data_mount_and_file_secret(monkeypatch,tmp_path,missing):
    import hadis_web.config as config
    monkeypatch.setattr(config,'APP_ROOT',tmp_path/'app')
    secret=tmp_path/'password';secret.write_text('fixture-secret-value-'*4,encoding='utf-8')
    monkeypatch.setenv('HADIS_ENV','production')
    monkeypatch.setenv('HADIS_PUBLIC_ORIGIN','https://hadis.example.org')
    monkeypatch.delenv('HADIS_DATABASE_URL',raising=False)
    monkeypatch.setenv('HADIS_DB_PASSWORD_FILE',str(secret))
    monkeypatch.setenv('HADIS_DATA_ROOT',str(tmp_path/'data'))
    if missing=='file':
        monkeypatch.delenv('HADIS_DB_PASSWORD_FILE')
        monkeypatch.setenv('HADIS_DATABASE_URL','postgresql://fixture:fixture@database/fixture')
    else:monkeypatch.delenv('HADIS_DATA_ROOT')
    with pytest.raises(ValueError):Settings.load()


def test_production_error_response_also_keeps_hsts(installation):
    app=create_app(production(installation))
    @app.get('/fixture-error')
    def error():raise RuntimeError('PRIVATE')
    response=TestClient(app,base_url='https://hadis.example.org',raise_server_exceptions=False).get('/fixture-error')
    assert response.status_code==500
    assert response.headers['strict-transport-security']=='max-age=31536000'
    assert 'PRIVATE' not in response.text


def test_production_checks_pinned_source_before_accepting_requests(installation):
    installation.source_db.write_bytes(b'changed source fixture')
    with pytest.raises(ValueError):create_app(production(installation))
