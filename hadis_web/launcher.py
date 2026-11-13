"""Start the installed local reader without creating or importing any data."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from http.client import HTTPConnection, HTTPException
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import webbrowser

from .config import APP_ROOT
from .local_identity import installation_id

CONTAINER='hadis-reader-20261031'
DOCKER_PIPE='npipe:////./pipe/dockerDesktopLinuxEngine'
CHECK_NAMES={'source':'Arapça kaynak','archive':'Kitap arşivi','search':'Arama dizini','working':'Çalışma veritabanı'}


class LaunchError(Exception):
    pass


def hidden_process():
    if os.name!='nt':
        return {}
    info=subprocess.STARTUPINFO()
    info.dwFlags|=subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow=0
    return {'creationflags':subprocess.CREATE_NO_WINDOW,'startupinfo':info}


def run_command(args,timeout=5):
    environment={key:value for key,value in os.environ.items()
                 if key.upper() not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}
    try:
        return subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',
                              timeout=timeout,check=False,env=environment,**hidden_process())
    except (subprocess.TimeoutExpired,OSError):
        raise LaunchError('Yerel servis komutu tamamlanamadı. Docker Desktop durumunu kontrol edip yeniden deneyin.') from None


@contextmanager
def launch_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        if not path.stat().st_size:
            handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise LaunchError('Uygulama başka bir açılışta hazırlanıyor. Biraz sonra yeniden deneyin.') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name=='nt':
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def docker_command():
    found=shutil.which('docker')
    if found:
        return found
    candidates=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DockerDesktop/resources/bin/docker.exe',
                Path(os.environ.get('ProgramFiles',''))/'Docker/Docker/resources/bin/docker.exe']
    for path in candidates:
        if path.is_file():return str(path)
    raise LaunchError('Docker bulunamadı. Kurulu Docker Desktop yolunu kontrol edin; otomatik kurulum yapılmadı.')


def start_desktop():
    candidates=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DockerDesktop/Docker Desktop.exe',
                Path(os.environ.get('ProgramFiles',''))/'Docker/Docker/Docker Desktop.exe']
    for path in candidates:
        if path.is_file():
            subprocess.Popen([str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,**hidden_process())
            return
    raise LaunchError('Docker motoru kapalı. Docker Desktop’ı açıp yeniden deneyin.')


def wait_until(action,seconds,message):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if action():return
        time.sleep(.5)
    raise LaunchError(message)


def ensure_docker():
    docker=docker_command()
    prefix=[docker,'--host',DOCKER_PIPE]
    def engine_ready():
        try:return run_command(prefix+['info','--format','{{.ServerVersion}}'],3).returncode==0
        except LaunchError:return False
    if not engine_ready():
        print('Veri servisi hazırlanıyor; Docker Desktop açılıyor…',flush=True)
        start_desktop()
        wait_until(engine_ready,90,'Docker hazır olmadı. Docker Desktop içindeki hata durumunu kontrol edip yeniden deneyin.')
    container=run_command(prefix+['inspect','--format','{{.State.Running}}',CONTAINER])
    if container.returncode:
        raise LaunchError('Mevcut veri konteyneri bulunamadı. Kurulum/yedek geri yükleme adımlarını kontrol edin; yeni veritabanı oluşturulmadı.')
    if container.stdout.strip()!='true':
        if run_command(prefix+['start',CONTAINER],15).returncode:
            raise LaunchError('Veri konteyneri başlatılamadı. Docker Desktop durumunu kontrol edin.')
    wait_until(lambda:run_command(prefix+['exec',CONTAINER,'pg_isready','-q'],3).returncode==0,
               30,'Veritabanı hazır olmadı. Docker Desktop içindeki mevcut konteyner durumunu kontrol edin.')


def port_in_use(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1):return True
    except OSError:return False


def read_health(port):
    connection=HTTPConnection('127.0.0.1',port,timeout=4)
    try:
        connection.request('GET','/api/health',headers={'Accept':'application/json'})
        response=connection.getresponse()
        if response.status!=200:return None
        result=json.loads(response.read(16385))
        return result if isinstance(result,dict) else None
    except (OSError,ValueError,HTTPException):return None
    finally:connection.close()


def matches(report,identity):
    return isinstance(report,dict) and report.get('app')=='cevami-reader' and report.get('installation_id')==identity


def not_ready_message(report):
    checks=report.get('checks',{}) if isinstance(report,dict) else {}
    if not isinstance(checks,dict):checks={}
    labels=[label for key,label in CHECK_NAMES.items() if checks.get(key)!='ready']
    return ('Uygulama tam hazır değil: '+', '.join(labels)+'. Kurulumdaki kaynak dosyalarını ve mevcut veritabanı bağlantısını kontrol edin. Otomatik veri aktarımı yapılmadı.')


def wait_for_health(port,identity,process=None):
    end=time.monotonic()+25
    report=None
    while time.monotonic()<end:
        if process is not None and process.poll() is not None:
            raise LaunchError('Sunucu başlatılamadı. .local/logs altındaki başlangıç günlüğünü ve Python bağımlılıklarını kontrol edin.')
        report=read_health(port)
        if report is not None and not matches(report,identity):
            raise LaunchError('Bu port başka bir uygulamaya veya kuruluma ait. Mevcut süreç değiştirilmedi.')
        if matches(report,identity) and report.get('ready') is True:return report
        time.sleep(.5)
    raise LaunchError(not_ready_message(report) if report else 'Sunucu hazır olmadı. .local/logs altındaki başlangıç günlüğünü kontrol edin.')


def stop_owned_server(process):
    # Called only with the Popen object created by THIS launch, never a port PID.
    if process.poll() is not None:return
    if os.name=='nt':
        taskkill=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/taskkill.exe'
        result=run_command([str(taskkill),'/PID',str(process.pid),'/T','/F'],5)
        if result.returncode and process.poll() is None:
            raise LaunchError('Bu açılışın sunucu süreci kapanmadı. Başlangıç günlüğünü kontrol edin.')
    else:
        process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        raise LaunchError('Bu açılışın sunucu süreci kapanmadı. Başlangıç günlüğünü kontrol edin.') from None


def start_server(app_root,port):
    logs=app_root/'.local/logs'
    logs.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    with (logs/f'reader-{port}-{stamp}.log').open('ab') as log:
        return subprocess.Popen([str(app_root/'.venv/Scripts/python.exe'),'-m','uvicorn','hadis_web.app:create_app',
                                 '--factory','--host','127.0.0.1','--port',str(port),'--no-access-log'],
                                cwd=str(app_root),stdin=subprocess.DEVNULL,stdout=log,stderr=log,**hidden_process())


def open_page(url):
    if not webbrowser.open(url,new=2):
        print('Tarayıcı otomatik açılamadı. Bu adresi açabilirsiniz: '+url,flush=True)


def launch(app_root=APP_ROOT,port=8765,open_browser=True):
    app_root=Path(app_root).resolve()
    if not (app_root/'.venv/Scripts/python.exe').is_file():
        raise LaunchError('Python ortamı bulunamadı. app/README.md kurulum adımlarını kontrol edin.')
    identity=installation_id(app_root.parent)
    url=f'http://127.0.0.1:{port}/'
    with launch_lock(app_root/'.local/launch.lock'):
        running=port_in_use(port)
        report=read_health(port) if running else None
        if running and not matches(report,identity):
            raise LaunchError('Bu port başka bir uygulamaya veya eski bir okuyucu sürümüne ait. Mevcut süreç durdurulmadı; uygulama adresini kontrol edin.')
        if not running or report.get('ready') is not True:
            print('Uygulama ve veri bağlantısı kontrol ediliyor…',flush=True)
            ensure_docker()
            owned=None
            try:
                if not running:owned=start_server(app_root,port)
                wait_for_health(port,identity,owned)
            except BaseException:
                if owned is not None:stop_owned_server(owned)
                raise
        print('Cevâmi hazır: '+url,flush=True)
        if open_browser:open_page(url)
    return url


def main(argv=None):
    parser=argparse.ArgumentParser(description='Cevâmi yerel uygulama açılışı')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--status',action='store_true',help='Servis başlatmadan hazır olma durumunu kontrol et')
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error('Port 1–65535 arasında olmalıdır.')
    try:
        if args.status:
            report=read_health(args.port)
            if not matches(report,installation_id(APP_ROOT.parent)):
                raise LaunchError('Bu kurulumun uygulaması açık değil. Cevami.cmd ile başlatabilirsiniz.')
            if report.get('ready') is not True:raise LaunchError(not_ready_message(report))
            print('Cevâmi ve veri bağlantıları hazır.',flush=True)
        else:launch(APP_ROOT,args.port,not args.no_browser)
        return 0
    except LaunchError as error:
        print('Açılış tamamlanamadı: '+str(error),file=sys.stderr,flush=True)
        return 1
    except KeyboardInterrupt:
        print('Açılış iptal edildi.',file=sys.stderr,flush=True)
        return 130
    except (OSError,ValueError):
        print('Açılış tamamlanamadı. Kurulum klasörünü ve günlük yazma izinlerini kontrol edin.',file=sys.stderr,flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
