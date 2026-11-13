import json
from contextlib import closing
from pathlib import Path
import sqlite3
import zipfile

import pytest
from hadis_web import backup

REQUIRED=('app/requirements.lock','app/start.ps1','app/hadis_web/app.py','app/hadis_web/config.py',
          'app/hadis_web/source.py','Cevami.cmd','references/datasets/jawami3_alkalem/jawami.db',
          'references/datasets/jawami3_alkalem/verification.json','GK4.5/GK4.5/Data/Books.zip',
          'research/turkish-sources/translation-research.sqlite','app/.local/search.sqlite')


@pytest.fixture
def project(tmp_path):
    root=tmp_path/'project'
    (root/'app/.local').mkdir(parents=True)
    (root/'app/hadis_web').mkdir()
    (root/'app/hadis_web/app.py').write_text('source code',encoding='utf-8')
    (root/'app/.local/settings.json').write_text('{"postgres_dsn":"private-secret-sentinel"}')
    (root/'app/.local/old.log').write_text('private-secret-sentinel')
    (root/'app/.venv').mkdir();(root/'app/.venv/runtime').write_text('runtime')
    (root/'app/.git').mkdir();(root/'app/.git/index').write_bytes(b'working stage')
    (root/'references').mkdir();(root/'references/source.txt').write_text('original العربية',encoding='utf-8')
    (root/'README.md').write_text('readme',encoding='utf-8')
    for relative in REQUIRED:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            if path.suffix=='.sqlite':
                with closing(sqlite3.connect(path)) as c:c.execute('CREATE TABLE fixture(id INTEGER)')
            else:path.write_text('recovery input fixture',encoding='utf-8')
    return root


def fixture_package(project,tmp_path):
    packet=tmp_path/'backup.zip'
    files=backup.collect_files(project)
    dump=tmp_path/'working.dump';dump.write_bytes(b'PGDMP fixture')
    manifest=backup.write_package(packet,project,files,dump,{'schema':'hadis','tables':{'text_versions':3}},
                                  {'postgres_schema':'hadis'})
    return packet,manifest


def test_package_retains_work_and_originals_without_credentials_or_runtime(project,tmp_path):
    packet,manifest=fixture_package(project,tmp_path)
    with zipfile.ZipFile(packet) as z:
        assert 'project/app/.git/index' in z.namelist()
        assert 'project/references/source.txt' in z.namelist()
        assert 'project/app/.local/settings.json' not in z.namelist()
        assert not any('.venv' in name for name in z.namelist())
        assert b'private-secret-sentinel' not in b''.join(z.read(name) for name in z.namelist())
    assert backup.verify_package(packet)['database']['tables']=={'text_versions':3}
    restored=tmp_path/'new restore'
    backup.extract_verified(packet,restored)
    assert (restored/'project/app/.git/index').read_bytes()==b'working stage'
    assert (restored/'project/references/source.txt').read_text(encoding='utf-8')=='original العربية'


def test_changed_source_rejected_before_success(project,tmp_path):
    files=backup.collect_files(project)
    (project/'README.md').write_text('new contents',encoding='utf-8')
    dump=tmp_path/'working.dump';dump.write_bytes(b'PGDMP fixture')
    with pytest.raises(backup.BackupError,match='değiş'):
        backup.write_package(tmp_path/'bad.zip',project,files,dump,{'schema':'hadis','tables':{}},{})


@pytest.mark.parametrize('name',['../outside','/absolute','C:/absolute','folder\\evil','file:stream','project/CON','project/Bad.'])
def test_unsafe_archive_path_is_rejected(name):
    with pytest.raises(backup.BackupError):backup.safe_member(name)


def test_case_collisions_and_extra_entries_rejected(project,tmp_path):
    packet,_=fixture_package(project,tmp_path)
    with zipfile.ZipFile(packet,'a') as z:z.writestr('project/readme.md','collision')
    with pytest.raises(backup.BackupError):backup.verify_package(packet)


def test_modified_content_is_rejected_even_if_zip_crc_valid(project,tmp_path):
    packet,_=fixture_package(project,tmp_path)
    corrupted=tmp_path/'corrupted.zip'
    with zipfile.ZipFile(packet) as original,zipfile.ZipFile(corrupted,'w') as out:
        for name in original.namelist():
            out.writestr(name,b'changed' if name=='project/README.md' else original.read(name))
    with pytest.raises(backup.BackupError,match='doğrulan'):
        backup.verify_package(corrupted)


def test_existing_restore_destination_is_never_overwritten(project,tmp_path):
    packet,_=fixture_package(project,tmp_path)
    target=tmp_path/'existing';target.mkdir();(target/'keep').write_text('keep')
    with pytest.raises(backup.BackupError):backup.extract_verified(packet,target)
    assert (target/'keep').read_text()=='keep'


def test_sqlite_snapshot_retains_committed_records_without_changing_source(tmp_path):
    source=tmp_path/'research.sqlite'
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE work(text TEXT)');c.execute("INSERT INTO work VALUES ('source')")
    before=source.read_bytes()
    snapshot=tmp_path/'snapshot.sqlite'
    backup.snapshot_sqlite(source,snapshot)
    with sqlite3.connect(snapshot) as c:assert c.execute('SELECT text FROM work').fetchone()[0]=='source'
    assert source.read_bytes()==before


def test_owned_workspace_cleanup_refuses_wrong_owner_and_outside_path(tmp_path):
    workspace,token=backup.make_workspace(tmp_path)
    (workspace/'keep').write_text('test')
    with pytest.raises(backup.BackupError):backup.cleanup_workspace(workspace,tmp_path,'wrong-token')
    assert workspace.exists()
    with pytest.raises(backup.BackupError):backup.cleanup_workspace(workspace,tmp_path/'different',token)
    backup.cleanup_workspace(workspace,tmp_path,token)
    assert not workspace.exists()


def test_mirror_is_byte_identical_and_never_replaces_existing(project,tmp_path):
    packet,_=fixture_package(project,tmp_path)
    mirror=tmp_path/'mirror';mirror.mkdir()
    copied=backup.copy_verified(packet,mirror)
    assert backup.file_hash(packet)==backup.file_hash(copied)
    with pytest.raises(backup.BackupError):backup.copy_verified(packet,mirror)


def test_disk_space_failure_happens_before_copy(monkeypatch,tmp_path):
    monkeypatch.setattr(backup.shutil,'disk_usage',lambda path:type('Usage',(),{'free':10})())
    with pytest.raises(backup.BackupError,match='alan'):backup.check_space(tmp_path,100)


def test_pinned_requirements_are_kept(project,tmp_path):
    packet,_=fixture_package(project,tmp_path)
    with zipfile.ZipFile(packet) as z:assert 'project/app/requirements.lock' in z.namelist()


def test_empty_git_refs_and_staged_index_recover_unborn_repo(project,tmp_path):
    import subprocess
    (project/'app/.git/index').unlink()
    subprocess.run(['git','init','-q',str(project/'app')],check=True,capture_output=True)
    subprocess.run(['git','-C',str(project/'app'),'add','hadis_web/app.py'],check=True,capture_output=True)
    packet,_=fixture_package(project,tmp_path)
    with zipfile.ZipFile(packet) as archive:
        assert 'project/app/.git/refs/heads/' in archive.namelist()
    target=tmp_path/'restored';backup.extract_verified(packet,target)
    result=subprocess.run(['git','-C',str(target/'project/app'),'rev-parse','--is-inside-work-tree'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    staged=subprocess.run(['git','-C',str(target/'project/app'),'diff','--cached','--name-only'],capture_output=True,text=True,check=True)
    assert 'hadis_web/app.py' in staged.stdout


@pytest.mark.parametrize('relative',['GK4.5/GK4.5/Data/Books.zip','research/turkish-sources/translation-research.sqlite','app/.local/search.sqlite'])
def test_missing_recovery_input_is_not_silently_omitted(project,tmp_path,relative):
    (project/relative).unlink()
    with pytest.raises(backup.BackupError,match='gerekli|Gerekli'):fixture_package(project,tmp_path)


def test_scan_permission_error_is_fatal(project,monkeypatch):
    def failed_walk(*args,**kwargs):
        if kwargs.get('onerror'):kwargs['onerror'](PermissionError('fixture'))
        return iter(())
    monkeypatch.setattr(backup.os,'walk',failed_walk)
    with pytest.raises(backup.BackupError):backup.collect_files(project)


def test_reparse_point_detected_without_python312_junction_method(monkeypatch,tmp_path):
    path=type('Reparse',(),{'is_symlink':lambda self:False,'lstat':lambda self:type('Info',(),{'st_file_attributes':0x400})()})()
    assert backup.linked(path) is True


def test_preexisting_partial_is_never_removed(project,tmp_path,monkeypatch):
    packet,_=fixture_package(project,tmp_path)
    mirror=tmp_path/'mirror';mirror.mkdir()
    fixed='a'*32
    monkeypatch.setattr(backup.uuid,'uuid4',lambda:type('Uuid',(),{'hex':fixed})())
    partial=mirror/f'.{packet.name}.{fixed}.partial';partial.write_bytes(b'keep this existing file')
    with pytest.raises((backup.BackupError,OSError)):backup.copy_verified(packet,mirror)
    assert partial.read_bytes()==b'keep this existing file'


def test_unknown_archive_never_reaches_database_restore(project,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from hadis_web.config import Settings
    from hadis_web import pg_backup
    packet,_=fixture_package(project,tmp_path)
    database=Mock();monkeypatch.setattr(pg_backup,'DatabaseBackup',database)
    result=backup.run_cli(Settings(project_root=project),SimpleNamespace(verify=packet,primary=None,mirror=None))
    assert result==2
    database.assert_not_called()


def test_operation_error_is_not_translated_as_lock_contention(project):
    from hadis_web.launcher import LaunchError
    with pytest.raises(LaunchError,match='Docker missing'):
        with backup.backup_lock(project):raise LaunchError('Docker missing')


def test_retained_trusted_digest_allows_exact_archive_restore_check(project,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from hadis_web.config import Settings
    from hadis_web import pg_backup
    packet,manifest=fixture_package(project,tmp_path)
    digest=backup.file_hash(packet)
    backup.retain_trust(project,{'sha256':digest,'archive':packet.name,'created_utc':'fixture'})
    database=Mock();monkeypatch.setattr(pg_backup,'DatabaseBackup',database)
    result=backup.run_cli(Settings(project_root=project),SimpleNamespace(verify=packet,primary=None,mirror=None))
    assert result==0
    database.return_value.verify_restore.assert_called_once()


def test_manifest_cannot_omit_required_recovery_file(project,tmp_path):
    packet,manifest=fixture_package(project,tmp_path)
    name='project/GK4.5/GK4.5/Data/Books.zip'
    manifest['files']=[record for record in manifest['files'] if record['path']!=name]
    stripped=tmp_path/'stripped.zip'
    with zipfile.ZipFile(packet) as original,zipfile.ZipFile(stripped,'w') as out:
        for entry in original.namelist():
            if entry not in (name,'manifest.json'):out.writestr(entry,original.read(entry))
        out.writestr('manifest.json',json.dumps(manifest))
    with pytest.raises(backup.BackupError,match='gerekli'):backup.verify_package(stripped)
