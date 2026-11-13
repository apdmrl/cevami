"""Verified local backup files. Existing projects and backups are never overwritten."""
import argparse
from contextlib import closing,contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import uuid
import zipfile

CHUNK=1024*1024
RUNTIME={'.venv','__pycache__','.pytest_cache','.superpowers','node_modules'}
SOURCE='references/datasets/jawami3_alkalem/jawami.db'
REQUIRED_INPUTS={'app/requirements.lock','app/start.ps1','app/hadis_web/app.py','app/hadis_web/config.py',
                 'app/hadis_web/source.py','Cevami.cmd',SOURCE,
                 'references/datasets/jawami3_alkalem/verification.json','GK4.5/GK4.5/Data/Books.zip',
                 'research/turkish-sources/translation-research.sqlite','app/.local/search.sqlite'}


class BackupError(Exception):
    pass


@contextmanager
def backup_lock(root):
    from .launcher import launch_lock,LaunchError
    guard=launch_lock(root/'app/.local/backup.lock')
    try:
        guard.__enter__()
    except LaunchError:
        raise BackupError('Başka bir yedekleme veya kontrol çalışıyor; bitmesini bekleyin.') from None
    try:yield
    finally:guard.__exit__(None,None,None)


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(CHUNK),b''):digest.update(data)
    return digest.hexdigest()


def excluded(relative):
    parts=relative.parts
    if any(part.casefold() in RUNTIME for part in parts):return True
    if len(parts)>2 and parts[0:2]==('app','.local'):
        return parts[2:]!=('search.sqlite',)
    name=parts[-1].casefold()
    return (name.startswith('.env') or name.endswith(('-wal','-shm','.pyc','.log','.key','.pem')))


def linked(path):
    if path.is_symlink():return True
    try:return bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)
    except FileNotFoundError:return False


def walk_sources(root):
    def scan_error(error):raise BackupError('Bir proje klasörü okunamadı; yedek eksik sayılacağı için durduruldu.')
    for folder,dirs,names in os.walk(root,followlinks=False,onerror=scan_error):
        current=Path(folder);kept=[]
        for name in sorted(dirs):
            path=current/name
            if excluded(path.relative_to(root)):continue
            if linked(path):raise BackupError('Bağlantılı klasör bulundu; proje dışına taşan kaynaklar yedeklenmedi.')
            kept.append(name)
        dirs[:]=kept
        yield current,dirs,names


def collect_directories(root):
    root=Path(root).resolve()
    return sorted('project/'+path.relative_to(root).as_posix() for path,dirs,names in walk_sources(root) if path!=root)


def require_recovery_inputs(paths):
    if not {'project/'+path for path in REQUIRED_INPUTS}.issubset(set(paths)):
        raise BackupError('Geri yükleme için gerekli kurulum/kaynak dosyaları eksik; yedek doğrulanmadı.')


def collect_files(root):
    root=Path(root).resolve()
    records=[]
    for current,dirs,names in walk_sources(root):
        for name in sorted(names):
            path=current/name;relative=path.relative_to(root)
            if excluded(relative):continue
            if relative.parts[:2]==('app','.git') and name.endswith('.lock'):
                raise BackupError('Git işlemi sürüyor veya kilit dosyası var; bitmesini bekleyip yeniden deneyin.')
            if linked(path) or not path.is_file():raise BackupError('Bağlantılı veya özel kaynak dosyası desteklenmiyor.')
            info=path.stat()
            records.append({'relative':relative.as_posix(),'size':info.st_size,'mtime':info.st_mtime_ns})
    return sorted(records,key=lambda record:record['relative'])


def safe_member(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or name.startswith('/'):
        raise BackupError('Arşivde güvenli olmayan dosya yolu var.')
    parts=name.split('/')
    reserved={'CON','PRN','AUX','NUL'}|{f'{p}{n}' for p in ('COM','LPT') for n in range(1,10)}
    if any(p in ('','.', '..') or p[-1:] in (' ','.') or p.split('.')[0].upper() in reserved
           or any(ord(c)<32 or c in '<>"|?*' for c in p) for p in parts):
        raise BackupError('Arşivde güvenli olmayan dosya yolu var.')
    return PurePosixPath(name)


def snapshot_sqlite(source,target):
    if target.exists():raise BackupError('SQLite test hedefi zaten var.')
    target.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    def progress(status,remaining,total):
        if time.monotonic()-started>60:raise BackupError('SQLite anlık görüntüsü uzun sürdü; yazan aracı kapatıp yeniden deneyin.')
    try:
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as origin:
            origin.execute('PRAGMA query_only=ON')
            with closing(sqlite3.connect(target)) as copy:
                origin.backup(copy,pages=256,progress=progress,sleep=.05)
                if copy.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise BackupError('SQLite kopyası doğrulanamadı.')
    except sqlite3.Error:
        raise BackupError('Araştırma SQLite anlık görüntüsü alınamadı; kaynak değiştirilmedi.') from None


def check_space(directory,needed):
    if shutil.disk_usage(directory).free<needed+64*1024**2:
        raise BackupError('Yedek ve doğrulama için yeterli boş disk alanı yok.')


def make_workspace(parent):
    parent=Path(parent).resolve();parent.mkdir(parents=True,exist_ok=True)
    path=Path(tempfile.mkdtemp(prefix='.cevami-work-',dir=parent)).resolve()
    token=uuid.uuid4().hex
    (path/'.owner').write_text(token,encoding='ascii')
    return path,token


def cleanup_workspace(path,parent,token):
    path=Path(path);parent=Path(parent).resolve()
    if (linked(path) or path.resolve().parent!=parent or not path.name.startswith('.cevami-work-')
        or not re.fullmatch('[0-9a-f]{32}',token) or (path/'.owner').read_text(encoding='ascii')!=token):
        raise BackupError('Geçici alanın sahipliği doğrulanamadı; silme yapılmadı.')
    shutil.rmtree(path.resolve())


def write_package(packet,root,files,dump,database,settings_template,source_hash=None,progress=None):
    root=Path(root).resolve()
    require_recovery_inputs('project/'+record['relative'] for record in files)
    directories=collect_directories(root)
    manifest={'format':'cevami-backup-v1','id':uuid.uuid4().hex,
              'created_utc':datetime.now(timezone.utc).isoformat(),'database':database,'files':[],
              'excludes':['runtime/cache/logs','WAL/SHM sidecars','actual settings/credentials'],
              'source_sha256':source_hash,'directories':directories}
    original=collect_files(root)
    if original!=files:raise BackupError('Proje dosyaları değişti; yedeği yeniden başlatın.')
    try:
        with zipfile.ZipFile(packet,'x',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
            for directory in directories:
                safe_member(directory)
                archive.writestr(directory+'/',b'')
            def add(path,name):
                safe_member(name)
                digest=hashlib.sha256();size=0
                with Path(path).open('rb') as stream,archive.open(name,'w',force_zip64=True) as out:
                    for data in iter(lambda:stream.read(CHUNK),b''):
                        digest.update(data);size+=len(data);out.write(data)
                manifest['files'].append({'path':name,'size':size,'sha256':digest.hexdigest()})
                return digest.hexdigest()
            found_source=False
            for index,record in enumerate(files):
                relative=record['relative'];path=root/relative
                info=path.stat()
                if (info.st_size,info.st_mtime_ns)!=(record['size'],record['mtime']):
                    raise BackupError('Proje dosyası değişti; yedeği yeniden başlatın.')
                if relative.startswith('research/') and path.suffix.lower() in ('.sqlite','.sqlite3','.db'):
                    snapshot=packet.parent/'sqlite-snapshots'/f'{index}.sqlite'
                    snapshot_sqlite(path,snapshot);path=snapshot
                digest=add(path,'project/'+relative)
                if relative==SOURCE:
                    found_source=True
                    wal=root/(relative+'-wal')
                    if wal.exists() and wal.stat().st_size:raise BackupError('Özgün kaynağın WAL dosyası boş değil; yedek durduruldu.')
                    if source_hash and digest!=source_hash:raise BackupError('Özgün kaynak özeti doğrulanamadı.')
                if progress and (index%50==0 or index==len(files)-1):progress(index+1,len(files))
            if source_hash and not found_source:raise BackupError('Özgün kaynak dosyası bulunamadı.')
            add(dump,'database/working.dump')
            template=json.dumps(settings_template,ensure_ascii=False,indent=2).encode('utf-8')
            name='project/app/.local/settings.template.json';archive.writestr(name,template)
            manifest['files'].append({'path':name,'size':len(template),'sha256':hashlib.sha256(template).hexdigest()})
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
        if collect_files(root)!=files or collect_directories(root)!=directories:
            raise BackupError('Yedek sırasında proje değişti; paket yayımlanmadı.')
        return manifest
    except (OSError,zipfile.BadZipFile):
        raise BackupError('Yedek paketi yazılamadı; disk alanını ve izinleri kontrol edin.') from None


def verify_package(packet):
    try:
        with zipfile.ZipFile(packet) as archive:
            infos=archive.infolist();seen=set()
            for info in infos:
                name=info.filename[:-1] if info.is_dir() else info.filename
                safe_member(name)
                key=name.casefold()
                if key in seen or (info.is_dir() and info.file_size) or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:
                    raise BackupError('Arşivde çakışan veya desteklenmeyen giriş var.')
                seen.add(key)
            if archive.getinfo('manifest.json').file_size>8*1024**2:raise BackupError('Yedek manifesti çok büyük.')
            manifest=json.loads(archive.read('manifest.json'))
            if manifest.get('format')!='cevami-backup-v1':raise BackupError('Yedek biçimi desteklenmiyor.')
            files=manifest.get('files')
            if not isinstance(files,list):raise BackupError('Yedek manifesti geçersiz.')
            expected={'manifest.json'};normalized=set()
            for record in files:
                name=record['path'];safe_member(name)
                if name.casefold() in normalized:raise BackupError('Yedek manifestinde yinelenen dosya var.')
                normalized.add(name.casefold());expected.add(name)
                if type(record['size']) is not int or record['size']<0 or not re.fullmatch('[0-9a-f]{64}',record['sha256']):
                    raise BackupError('Yedek dosya bilgileri geçersiz.')
                if archive.getinfo(name).file_size!=record['size']:raise BackupError('Dosya boyutu doğrulanamadı.')
                digest=hashlib.sha256();size=0
                with archive.open(name) as stream:
                    for data in iter(lambda:stream.read(CHUNK),b''):digest.update(data);size+=len(data)
                if size!=record['size'] or digest.hexdigest()!=record['sha256']:raise BackupError('Dosya özeti doğrulanamadı.')
            require_recovery_inputs(expected)
            directories=manifest.get('directories')
            if not isinstance(directories,list):raise BackupError('Klasör sicili eksik.')
            for name in directories:
                safe_member(name)
                if not name.startswith('project/') or name.casefold() in normalized:
                    raise BackupError('Arşiv klasörleri çakışıyor.')
                normalized.add(name.casefold())
                expected.add(name+'/')
            if {info.filename for info in infos}!=expected or 'database/working.dump' not in expected:
                raise BackupError('Arşiv kapsamı manifestle eşleşmiyor.')
            if not re.fullmatch('[0-9a-f]{32}',manifest['id']):raise BackupError('Yedek kimliği geçersiz.')
            return manifest
    except (OSError,zipfile.BadZipFile,KeyError,ValueError,TypeError):
        raise BackupError('Yedek paketi doğrulanamadı; dosya eksik veya bozuk.') from None


def extract_verified(packet,target):
    manifest=verify_package(packet)
    target=Path(target)
    if target.exists() or linked(target):raise BackupError('Geri yükleme hedefi zaten var; üzerine yazılmaz.')
    check_space(target.parent,sum(record['size'] for record in manifest['files']))
    target.mkdir()
    resolved=target.resolve()
    with zipfile.ZipFile(packet) as archive:
        for name in manifest['directories']:
            path=target.joinpath(*safe_member(name).parts)
            if not path.resolve().is_relative_to(resolved):raise BackupError('Geri yükleme klasör yolu güvenli değil.')
            path.mkdir(parents=True,exist_ok=True)
        for record in manifest['files']:
            name=record['path'];path=target.joinpath(*safe_member(name).parts)
            if not path.resolve().is_relative_to(resolved):raise BackupError('Geri yükleme yolu güvenli değil.')
            path.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(name) as source,path.open('xb') as out:shutil.copyfileobj(source,out,CHUNK)
            if file_hash(path)!=record['sha256']:raise BackupError('Geri yüklenen dosya doğrulanamadı.')
    return manifest


def publish_new(staged,target):
    if target.exists():raise BackupError('Yedek hedefi zaten var; üzerine yazılmaz.')
    try:
        if os.name=='nt':os.rename(staged,target)
        else:os.link(staged,target);Path(staged).unlink()
    except OSError:raise BackupError('Yedek yayımlanamadı; mevcut dosya korunuyor.') from None


def copy_verified(packet,directory):
    packet=Path(packet);directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    target=directory/packet.name
    if target.exists():raise BackupError('İkinci yedek zaten var; üzerine yazılmaz.')
    check_space(directory,packet.stat().st_size)
    partial=directory/f'.{packet.name}.{uuid.uuid4().hex}.partial'
    created=False
    try:
        out=partial.open('xb');created=True
        with out,packet.open('rb') as source:shutil.copyfileobj(source,out,CHUNK)
        if file_hash(packet)!=file_hash(partial):raise BackupError('İkinci kopyanın özeti doğrulanamadı.')
        publish_new(partial,target)
        return target
    finally:
        if created and partial.exists() and partial.parent==directory and partial.name.endswith('.partial'):partial.unlink()


def trust_catalog(root):
    path=root/'app/.local/backup-trust.json'
    if not path.exists():return {}
    try:
        content=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(content,dict):raise ValueError()
        return content
    except (OSError,ValueError):raise BackupError('Bağımsız yedek özet sicili okunamadı.') from None


def retain_trust(root,receipt):
    catalog=trust_catalog(root)
    catalog[receipt['sha256']]={'archive':receipt['archive'],'created_utc':receipt['created_utc']}
    target=root/'app/.local/backup-trust.json';target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.parent/f'.backup-trust-{uuid.uuid4().hex}.partial'
    with partial.open('x',encoding='utf-8') as out:json.dump(catalog,out,ensure_ascii=False,indent=2)
    os.replace(partial,target)


def make_backup(settings,primary,mirror,progress=print):
    from .pg_backup import DatabaseBackup
    root=settings.project_root.resolve();primary=Path(primary).resolve();mirror=Path(mirror).resolve()
    if primary==mirror or primary.is_relative_to(root) or mirror.is_relative_to(root):
        raise BackupError('Yedek hedefleri ayrı ve proje klasörünün dışında olmalıdır.')
    if os.name=='nt' and primary.drive.casefold()==mirror.drive.casefold():
        raise BackupError('Yedek ve eş kopya farklı sürücülerde olmalıdır.')
    primary.mkdir(parents=True,exist_ok=True);mirror.mkdir(parents=True,exist_ok=True)
    files=collect_files(root);size=sum(record['size'] for record in files)
    check_space(primary,size*3+1024**3);check_space(mirror,size+1024**3)
    work,token=make_workspace(primary)
    try:
        progress('Çalışma veritabanının tutarlı kopyası alınıyor…')
        database=DatabaseBackup(settings)
        dump=work/'working.dump';metadata=database.dump(dump)
        expected=json.loads((root/'references/datasets/jawami3_alkalem/verification.json').read_text())['database_sha256']
        packet=work/f'cevami-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex}.zip'
        progress('Kod ve kaynak dosyaları paketleniyor…')
        write_package(packet,root,files,dump,metadata,{'postgres_schema':settings.postgres_schema,
                      'postgres_dsn':'<Yeni kurulumun bağlantı bilgisi buraya yazılacak>'},expected,
                      lambda count,total:progress(f'Dosya: {count}/{total}'))
        progress('Dosyalar yeni test alanına geri yüklenip doğrulanıyor…')
        restored=work/'restored';manifest=extract_verified(packet,restored)
        progress('Veritabanı ayrı doğrulama veritabanında geri yükleniyor…')
        database.verify_restore(restored/'database/working.dump',manifest['database'])
        digest=file_hash(packet);target=primary/packet.name
        publish_new(packet,target)
        progress('Doğrulanmış tam yedek ikinci diske kopyalanıyor…')
        try:copied=copy_verified(target,mirror)
        except (BackupError,OSError):
            raise BackupError(f'İlk doğrulanmış yedek korundu: {target}. İkinci kopya tamamlanamadı; hedefi kontrol edin.') from None
        receipt={'format':'cevami-backup-receipt-v1','archive':target.name,'sha256':digest,
                 'bytes':target.stat().st_size,'files':len(manifest['files']),'database':metadata,
                 'restore_tested':True,'copies':[str(target),str(copied)],'created_utc':datetime.now(timezone.utc).isoformat()}
        for location in (primary,mirror):
            with (location/(target.name+'.receipt.json')).open('x',encoding='utf-8') as out:json.dump(receipt,out,ensure_ascii=False,indent=2)
        retain_trust(root,receipt)
        return receipt
    finally:cleanup_workspace(work,primary,token)


def main(argv=None):
    from .config import Settings
    parser=argparse.ArgumentParser(description='Cevâmi doğrulanmış yerel yedek')
    parser.add_argument('--primary',type=Path)
    parser.add_argument('--mirror',type=Path)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--trusted-sha256',help='Yeni kurulumda bağımsız kayıtla karşılaştırılan güvenilir arşiv özeti')
    args=parser.parse_args(argv)
    try:
        settings=Settings.load()
        with backup_lock(settings.project_root):
            return run_cli(settings,args)
    except Exception as error:
        from .launcher import LaunchError
        if not isinstance(error,(BackupError,LaunchError,OSError,ValueError)):raise
        message=str(error) if isinstance(error,(BackupError,LaunchError)) else 'Dosya erişimi veya ayarlar kontrol edilemedi; README adımlarına bakın.'
        print('Yedekleme tamamlanamadı: '+message,file=sys.stderr,flush=True)
        return 1


def run_cli(settings,args):
    if args.verify:
        packet=args.verify.resolve()
        verify_package(packet)
        digest=file_hash(packet)
        supplied=getattr(args,'trusted_sha256',None)
        if supplied and (not re.fullmatch('[0-9a-fA-F]{64}',supplied) or supplied.casefold()!=digest):
            raise BackupError('Verilen bağımsız güvenilir özet bu arşivle eşleşmiyor.')
        if not supplied and digest not in trust_catalog(settings.project_root):
            print('Dosyalar doğrulandı; bu arşivin bağımsız güvenilir özeti bu kurulumda yok. Veritabanı komutları çalıştırılmadı.',flush=True)
            return 2
        from .pg_backup import DatabaseBackup
        work,token=make_workspace(packet.parent)
        try:
            manifest=extract_verified(packet,work/'restored')
            DatabaseBackup(settings).verify_restore(work/'restored/database/working.dump',manifest['database'])
            print('Yedek dosyaları ve ayrı veritabanına geri yükleme doğrulandı.',flush=True)
        finally:cleanup_workspace(work,packet.parent,token)
    else:
        receipt=make_backup(settings,args.primary or settings.project_root.parent/'HadisYedekleri',
                            args.mirror or Path.home()/'HadisYedekleri',lambda message:print(message,flush=True))
        for path in receipt['copies']:print('Doğrulanmış yedek: '+path,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
