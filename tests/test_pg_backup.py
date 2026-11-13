import subprocess
from unittest.mock import Mock
import pytest
from hadis_web import pg_backup
from hadis_web.config import Settings


def test_remote_database_connection_is_rejected_before_docker():
    settings=Settings(postgres_dsn='postgresql://test:private-secret@remote.invalid:55432/work')
    with pytest.raises(pg_backup.BackupError,match='yerel'):pg_backup.DatabaseBackup(settings)


def test_live_database_cannot_be_deleted_or_reused_for_restore():
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test@127.0.0.1:55432/live'))
    with pytest.raises(pg_backup.BackupError):database.drop_owned_database('live')
    with pytest.raises(pg_backup.BackupError):database.drop_owned_database('cevami_restorecheck_'+'a'*32)


def test_binary_dump_command_is_bounded_and_contains_no_password(monkeypatch,tmp_path):
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test:private-secret@127.0.0.1:55432/live'))
    monkeypatch.setattr(pg_backup,'docker_command',lambda:'docker')
    execute=Mock(return_value=subprocess.CompletedProcess([],0,b'',b''))
    monkeypatch.setattr(pg_backup.subprocess,'run',execute)
    database.command(['pg_dump','--format=custom'],output=tmp_path/'dump',timeout=10)
    args,kw=execute.call_args
    assert args[0][1:3]==['--host','npipe:////./pipe/dockerDesktopLinuxEngine']
    assert kw['timeout']==10
    assert 'private-secret' not in str(args)+str(kw.get('env',{}))


def test_subprocess_errors_are_sanitized(monkeypatch,tmp_path):
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test:private-secret@127.0.0.1:55432/live'))
    monkeypatch.setattr(pg_backup,'docker_command',lambda:'docker')
    monkeypatch.setattr(pg_backup.subprocess,'run',Mock(side_effect=subprocess.TimeoutExpired(['docker'],10,output=b'private-secret')))
    with pytest.raises(pg_backup.BackupError) as failure:database.command(['pg_dump'],output=tmp_path/'dump',timeout=10)
    assert 'private-secret' not in str(failure.value)


def test_engine_mismatch_rejected_before_dump(monkeypatch):
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test@127.0.0.1:55432/live'))
    monkeypatch.setattr(pg_backup,'ensure_docker',Mock())
    monkeypatch.setattr(pg_backup,'docker_command',lambda:'docker')
    monkeypatch.setattr(pg_backup.subprocess,'run',Mock(return_value=subprocess.CompletedProcess([],0,
                       b'{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"55432"}]}',b'')))
    monkeypatch.setattr(database,'command',lambda *a,**k:b'222\n')
    conn=Mock();conn.execute.return_value.fetchone.return_value=('111',)
    with pytest.raises(pg_backup.BackupError,match='kimliği'):database.validate_target(conn)


def test_dump_and_counts_share_read_only_exported_snapshot(monkeypatch,tmp_path):
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test@127.0.0.1:55432/live'))
    conn=Mock();conn.info.server_version=180000
    conn.execute.return_value.fetchone.return_value=('snapshot-id',)
    connection=Mock();connection.__enter__=Mock(return_value=conn);connection.__exit__=Mock(return_value=False)
    monkeypatch.setattr(pg_backup.psycopg,'connect',lambda *a,**k:connection)
    monkeypatch.setattr(database,'validate_target',lambda c:None)
    monkeypatch.setattr(database,'table_counts',lambda c,s:{'text_versions':17})
    commands=[]
    def dump(args,output,timeout):
        commands.append(args);output.write_bytes(b'PGDMP fixture')
    monkeypatch.setattr(database,'command',dump)
    metadata=database.dump(tmp_path/'working.dump')
    assert metadata['tables']=={'text_versions':17}
    assert '--snapshot=snapshot-id' in commands[0]
    assert conn.execute.call_args_list[0].args[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'


def test_existing_name_collision_is_never_adopted_or_dropped(monkeypatch,tmp_path):
    import psycopg
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test@127.0.0.1:55432/live'))
    admin=Mock();admin.execute.side_effect=psycopg.errors.DuplicateDatabase('fixture')
    connection=Mock();connection.__enter__=Mock(return_value=admin);connection.__exit__=Mock(return_value=False)
    monkeypatch.setattr(pg_backup.psycopg,'connect',lambda *a,**k:connection)
    monkeypatch.setattr(database,'validate_target',lambda c:None)
    drop=Mock();monkeypatch.setattr(database,'drop_owned_database',drop)
    with pytest.raises(pg_backup.BackupError):database.verify_restore(tmp_path/'dump',{'schema':'hadis','tables':{}})
    drop.assert_not_called();assert not database.owned


def test_admin_cleanup_has_query_and_lock_deadlines_and_names_leftover(monkeypatch):
    import psycopg
    name='cevami_restorecheck_'+'a'*32
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test@127.0.0.1:55432/live'))
    database.owned.add(name)
    admin=Mock();admin.execute.side_effect=psycopg.errors.LockNotAvailable('fixture')
    connection=Mock();connection.__enter__=Mock(return_value=admin);connection.__exit__=Mock(return_value=False)
    connect=Mock(return_value=connection);monkeypatch.setattr(pg_backup.psycopg,'connect',connect)
    with pytest.raises(pg_backup.BackupError) as error:database.drop_owned_database(name)
    assert name in str(error.value)
    assert 'statement_timeout=' in connect.call_args.kwargs['options']
    assert 'lock_timeout=' in connect.call_args.kwargs['options']


def test_database_url_is_not_in_docker_environment(monkeypatch,tmp_path):
    monkeypatch.setenv('HADIS_DATABASE_URL','private-secret-from-env')
    database=pg_backup.DatabaseBackup(Settings(postgres_dsn='postgresql://test@127.0.0.1:55432/live'))
    monkeypatch.setattr(pg_backup,'docker_command',lambda:'docker')
    execute=Mock(return_value=subprocess.CompletedProcess([],0,b'',b''))
    monkeypatch.setattr(pg_backup.subprocess,'run',execute)
    database.command(['pg_dump'],output=tmp_path/'dump')
    forwarded='HADIS_DATABASE_URL' in execute.call_args.kwargs['env']
    assert not forwarded
