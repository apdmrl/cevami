"""Disposable PostgreSQL fixture: provisioning must commit all or nothing."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from test_deployment_config import deployment


def test_restore_role_failure_rolls_back_and_success_is_readonly(tmp_path,deployment):
    owner='cevami-fixture-'+uuid.uuid4().hex
    root=Path(__file__).resolve().parents[1]
    script=Path(os.environ.get('CEVAMI_TEST_RESTORE_SCRIPT',root/'deploy/restore.sh')).resolve()
    tmp_path.chmod(0o755)
    for name in ('pg_admin_password','web_db_password'):
        path=tmp_path/name;path.write_bytes((('fixture-'+name+'-')*5).encode()+b'\n');path.chmod(0o444)
    (tmp_path/'postgres').mkdir()
    image=deployment['services']['database']['image']
    args=['docker','run','-d','--name',owner,'--label','io.cevami.fixture='+owner,'--network','none',
        '--user','999:999','--cap-drop','ALL','-e','POSTGRES_DB=fixture',
        '-e','POSTGRES_USER=cevami_owner','-e','POSTGRES_PASSWORD_FILE=/run/secrets/pg_admin_password']
    for name in ('pg_admin_password','web_db_password'):
        args+=['--mount',f'type=bind,source={tmp_path/name},target=/run/secrets/{name},readonly']
    args+=['--mount',f'type=bind,source={tmp_path},target=/workspace/data,readonly',
           '--mount',f'type=bind,source={script},target=/opt/restore.sh,readonly',image]
    container=subprocess.run(args,capture_output=True,text=True,check=True,timeout=60).stdout.strip()
    def execute(command,*,check=True,binary=False):
        return subprocess.run(['docker','exec',container,*command],capture_output=True,text=not binary,
                              check=check,timeout=90)
    def sql(query,database='fixture'):
        return execute(['psql','-X','-A','-t','-U','cevami_owner','-d',database,'-c',query]).stdout.strip()
    def restore(database):
        return subprocess.run(['docker','exec','-e','PGHOST=127.0.0.1','-e','PGUSER=cevami_owner',
            '-e','PGDATABASE='+database,container,'sh','/opt/restore.sh'],capture_output=True,text=True,timeout=90)
    try:
        for _ in range(100):
            if execute(['pg_isready','-h','127.0.0.1','-U','cevami_owner','-d','fixture'],check=False).returncode==0:break
            time.sleep(.2)
        else:raise AssertionError('Disposable PostgreSQL did not become ready')
        sql('CREATE SCHEMA hadis; CREATE TABLE hadis.text_versions(id integer); INSERT INTO hadis.text_versions VALUES(1)')
        dump=execute(['pg_dump','-U','cevami_owner','-d','fixture','--schema=hadis','--format=custom',
                      '--no-owner','--no-privileges'],binary=True).stdout
        (tmp_path/'postgres/working.dump').write_bytes(dump)
        (tmp_path/'postgres/working.dump').chmod(0o444)
        sql('DROP SCHEMA hadis CASCADE')
        # The grant targets database cevami, intentionally absent: fail after
        # schema/data restore and reader-role creation, then prove full rollback.
        for _ in range(2):
            failed=restore('fixture')
            assert failed.returncode!=0
            assert 'Existing schema' not in failed.stderr
            assert 'database "cevami" does not exist' in failed.stderr
            assert sql("SELECT count(*) FROM pg_namespace WHERE nspname='hadis'")=='0'
            assert sql("SELECT count(*) FROM pg_roles WHERE rolname='cevami_web'")=='0'
        sql('CREATE DATABASE cevami OWNER cevami_owner',database='postgres')
        completed=restore('cevami')
        assert completed.returncode==0,completed.stderr
        assert sql('SELECT count(*) FROM hadis.text_versions',database='cevami')=='1'
        assert sql("SELECT has_table_privilege('cevami_web','hadis.text_versions','INSERT')",database='cevami')=='f'
        assert restore('cevami').returncode!=0
        assert sql('SELECT count(*) FROM hadis.text_versions',database='cevami')=='1'
    finally:
        info=json.loads(subprocess.run(['docker','inspect',container],capture_output=True,text=True,check=True).stdout)[0]
        assert info['Config']['Labels'].get('io.cevami.fixture')==owner
        subprocess.run(['docker','rm','--force','--volumes',container],capture_output=True,check=True,timeout=60)
