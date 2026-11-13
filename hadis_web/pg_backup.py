"""Consistent schema dump and restore only to an invocation-owned disposable DB."""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo

from .backup import BackupError
from .launcher import docker_command,DOCKER_PIPE,CONTAINER,hidden_process,ensure_docker


class DatabaseBackup:
    def __init__(self,settings):
        self.settings=settings
        try:self.connection=conninfo_to_dict(settings.postgres_dsn or '')
        except psycopg.Error:raise BackupError('Çalışma veritabanı bağlantı ayarı okunamadı.') from None
        if (self.connection.get('host') not in ('127.0.0.1','localhost','::1')
            or not self.connection.get('dbname') or not self.connection.get('user')):
            raise BackupError('Yedekleme yalnız doğrulanmış yerel çalışma veritabanını destekliyor.')
        if not re.fullmatch('[a-z][a-z0-9_]{0,62}',settings.postgres_schema):
            raise BackupError('Çalışma şeması geçersiz.')
        self.owned=set()

    def command(self,arguments,output=None,input_file=None,timeout=300):
        args=[docker_command(),'--host',DOCKER_PIPE,'exec','-i',CONTAINER]+arguments
        environment={k:v for k,v in os.environ.items() if not k.upper().startswith('PG')
                     and k.upper() not in ('HADIS_DATABASE_URL','DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
        writer=reader=None
        try:
            if output:writer=Path(output).open('xb')
            if input_file:reader=Path(input_file).open('rb')
            result=subprocess.run(args,stdin=reader or subprocess.DEVNULL,stdout=writer or subprocess.PIPE,
                                  stderr=subprocess.PIPE,timeout=timeout,check=False,env=environment,**hidden_process())
            if result.returncode:raise BackupError('PostgreSQL yedek komutu tamamlanamadı; yerel veri servisini ve yetkileri kontrol edin.')
            return result.stdout
        except (subprocess.TimeoutExpired,OSError):
            raise BackupError('PostgreSQL yedek işlemi süresinde tamamlanamadı veya dosyaya erişilemedi.') from None
        finally:
            if writer:writer.close()
            if reader:reader.close()

    def pg_arguments(self,program,database):
        return [program,'--host=/var/run/postgresql','--port=5432',
                '--username='+self.connection['user'],'--dbname='+database]

    def validate_target(self,conn):
        ensure_docker()
        # Only request port mapping, never container environment/password fields.
        args=[docker_command(),'--host',DOCKER_PIPE,'inspect','--format','{{json .NetworkSettings.Ports}}',CONTAINER]
        environment={k:v for k,v in os.environ.items() if not k.upper().startswith('PG') and k.upper() not in
                     ('HADIS_DATABASE_URL','DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
        try:
            result=subprocess.run(args,capture_output=True,timeout=10,check=False,env=environment,**hidden_process())
            ports=json.loads(result.stdout) if result.returncode==0 else {}
            expected=str(self.connection.get('port','5432'))
            if not any(str(row.get('HostPort'))==expected and row.get('HostIp') in ('127.0.0.1','::1')
                       for row in ports.get('5432/tcp',[]) or []):
                raise BackupError('Yapılandırılmış veritabanı bu yerel konteynerle eşleşmiyor.')
            actual=str(conn.execute('SELECT system_identifier::text FROM pg_control_system()').fetchone()[0])
            reported=self.command(self.pg_arguments('psql',self.connection['dbname'])+
                                  ['-X','-A','-t','-c','SELECT system_identifier::text FROM pg_control_system()'],timeout=10).decode().strip()
            if not actual.isdecimal() or reported!=actual:raise BackupError('Veritabanı motor kimliği eşleşmiyor; yedek durduruldu.')
        except (subprocess.TimeoutExpired,OSError,ValueError,psycopg.Error):
            raise BackupError('Yerel veritabanı hedefi doğrulanamadı; ayarları ve doğrulama yetkilerini kontrol edin.') from None

    def table_counts(self,conn,schema):
        rows=conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",(schema,)).fetchall()
        if not rows:raise BackupError('Çalışma şemasında yedeklenecek tablo bulunamadı.')
        return {row[0]:conn.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(row[0]))).fetchone()[0] for row in rows}

    def dump(self,target):
        try:
            with psycopg.connect(self.settings.postgres_dsn,connect_timeout=3) as conn:
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                conn.execute("SET LOCAL statement_timeout='30s'")
                conn.execute("SET LOCAL lock_timeout='3s'")
                self.validate_target(conn)
                snapshot=conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
                counts=self.table_counts(conn,self.settings.postgres_schema)
                arguments=self.pg_arguments('pg_dump',self.connection['dbname'])
                arguments+=['--format=custom','--no-owner','--no-privileges','--schema='+self.settings.postgres_schema,
                            '--snapshot='+snapshot,'--lock-wait-timeout=5s']
                self.command(arguments,output=target,timeout=300)
                with Path(target).open('rb') as stream:
                    if stream.read(5)!=b'PGDMP':raise BackupError('PostgreSQL yedek biçimi doğrulanamadı.')
                return {'schema':self.settings.postgres_schema,'tables':counts,
                        'postgres_version':conn.info.server_version,'format':'pg-custom'}
        except psycopg.Error:
            raise BackupError('Çalışma veritabanının tutarlı yedeği alınamadı; bağlantı ve okuma yetkilerini kontrol edin.') from None

    def drop_owned_database(self,name):
        if (name not in self.owned or not re.fullmatch('cevami_restorecheck_[0-9a-f]{32}',name)
            or name==self.connection['dbname']):
            raise BackupError('Yalnız bu işlemin oluşturduğu test veritabanı temizlenebilir.')
        try:
            with psycopg.connect(self.settings.postgres_dsn,connect_timeout=3,autocommit=True,
                                 options='-c statement_timeout=30000 -c lock_timeout=3000') as conn:
                conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            self.owned.remove(name)
        except psycopg.Error:
            raise BackupError(f'Yalnız doğrulama için oluşturulan {name} temizlenemedi; yedek tamamlandı sayılmadı.') from None

    def verify_restore(self,dump,metadata):
        name='cevami_restorecheck_'+uuid.uuid4().hex
        try:
            with psycopg.connect(self.settings.postgres_dsn,connect_timeout=3,autocommit=True,
                                 options='-c statement_timeout=30000 -c lock_timeout=3000') as admin:
                self.validate_target(admin)
                admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
            self.owned.add(name)
            try:
                self.command(self.pg_arguments('pg_restore',name)+['--exit-on-error','--no-owner','--no-privileges'],
                             input_file=dump,timeout=300)
                restored=make_conninfo(self.settings.postgres_dsn,dbname=name)
                with psycopg.connect(restored,connect_timeout=3,options='-c default_transaction_read_only=on -c statement_timeout=30000') as conn:
                    counts=self.table_counts(conn,metadata['schema'])
                    if counts!=metadata['tables']:raise BackupError('Geri yüklenen tablo kapsamı veya satır sayıları eşleşmiyor.')
                return counts
            finally:self.drop_owned_database(name)
        except psycopg.Error:
            raise BackupError('Ayrı veritabanına geri yükleme doğrulanamadı; mevcut çalışma veritabanı değiştirilmedi.') from None
