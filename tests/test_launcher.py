import subprocess
from unittest.mock import Mock

import pytest
from hadis_web import launcher
from hadis_web.health import installation_id

SERVER_COMMAND=launcher.start_server


@pytest.fixture
def root(tmp_path,monkeypatch):
    root=tmp_path/'Türkçe yol ve boşluk'/'app'
    python=root/'.venv/Scripts/python.exe'
    python.parent.mkdir(parents=True);python.touch()
    monkeypatch.setattr(launcher,'port_in_use',lambda port:False)
    monkeypatch.setattr(launcher,'ensure_docker',Mock())
    monkeypatch.setattr(launcher,'start_server',Mock(return_value=None))
    monkeypatch.setattr(launcher,'open_page',Mock())
    return root


def report(root,ready=True):
    return {'app':'cevami-reader','installation_id':installation_id(root.parent),'ready':ready,'checks':{'working':'ready'}}


def test_ready_reader_reused_without_docker_or_new_process(root,monkeypatch):
    monkeypatch.setattr(launcher,'port_in_use',lambda port:True)
    monkeypatch.setattr(launcher,'read_health',lambda port:report(root))
    assert launcher.launch(root,8765,True)=='http://127.0.0.1:8765/'
    launcher.ensure_docker.assert_not_called();launcher.start_server.assert_not_called()
    launcher.open_page.assert_called_once()


@pytest.mark.parametrize('foreign',[None,{}, {'app':'other-service'}, {'app':'cevami-reader','installation_id':'other-copy','ready':True}])
def test_foreign_listener_is_untouched(root,monkeypatch,foreign):
    monkeypatch.setattr(launcher,'port_in_use',lambda port:True)
    monkeypatch.setattr(launcher,'read_health',lambda port:foreign)
    with pytest.raises(launcher.LaunchError,match='port'):
        launcher.launch(root,8765,False)
    launcher.ensure_docker.assert_not_called();launcher.start_server.assert_not_called()


def test_new_reader_waits_until_ready_and_no_browser_mode(root,monkeypatch):
    monkeypatch.setattr(launcher,'wait_for_health',lambda port,identity,process=None:report(root))
    launcher.launch(root,8767,False)
    launcher.ensure_docker.assert_called_once();launcher.start_server.assert_called_once_with(root,8767)
    launcher.open_page.assert_not_called()


def test_existing_unready_reader_rechecks_after_docker_without_duplicate(root,monkeypatch):
    monkeypatch.setattr(launcher,'port_in_use',lambda port:True)
    monkeypatch.setattr(launcher,'read_health',lambda port:report(root,False))
    monkeypatch.setattr(launcher,'wait_for_health',lambda port,identity,process=None:report(root))
    launcher.launch(root,8765,False)
    launcher.ensure_docker.assert_called_once();launcher.start_server.assert_not_called()


def test_missing_python_fails_without_mutation(root):
    (root/'.venv/Scripts/python.exe').unlink()
    with pytest.raises(launcher.LaunchError,match='Python'):launcher.launch(root,8765,False)
    launcher.ensure_docker.assert_not_called()


def test_process_calls_are_bounded_and_secrets_are_not_propagated(monkeypatch):
    monkeypatch.setattr(launcher.subprocess,'run',Mock(side_effect=subprocess.TimeoutExpired(['docker'],3,output='private-sentinel')))
    with pytest.raises(launcher.LaunchError) as failure:launcher.run_command(['docker','info'],3)
    assert 'private-sentinel' not in str(failure.value)
    assert launcher.subprocess.run.call_args.kwargs['timeout']==3


def test_lock_blocks_second_launcher_and_releases_after_exit(root):
    path=root/'.local/launch.lock'
    with launcher.launch_lock(path):
        with pytest.raises(launcher.LaunchError,match='hazırlanıyor'):
            with launcher.launch_lock(path):pass
    with launcher.launch_lock(path):pass


def test_server_command_handles_spaces_without_shell(root,monkeypatch):
    process=Mock();monkeypatch.setattr(launcher.subprocess,'Popen',process)
    SERVER_COMMAND(root,8767)
    args,kw=process.call_args
    assert args[0][0]==str(root/'.venv/Scripts/python.exe')
    assert args[0][1:4]==['-m','uvicorn','hadis_web.app:create_app']
    assert '--no-access-log' in args[0]
    assert kw['cwd']==str(root)
    assert not kw.get('shell',False)


def test_missing_container_never_created(monkeypatch):
    calls=[]
    def run(args,timeout=5):
        calls.append(args)
        return subprocess.CompletedProcess(args,1 if 'inspect' in args else 0,'','')
    monkeypatch.setattr(launcher,'run_command',run)
    monkeypatch.setattr(launcher,'docker_command',lambda:'docker')
    with pytest.raises(launcher.LaunchError,match='konteyner'):launcher.ensure_docker()
    assert not any('create' in c or 'run' in c or 'pull' in c for c in calls)


def test_closed_engine_and_stopped_container_use_only_existing_installation(monkeypatch):
    calls=[];engine_attempts=iter([1,0])
    def run(args,timeout=5):
        calls.append(args)
        if 'info' in args:return subprocess.CompletedProcess(args,next(engine_attempts),'','')
        return subprocess.CompletedProcess(args,0,'false' if 'inspect' in args else '','')
    monkeypatch.setattr(launcher,'run_command',run)
    monkeypatch.setattr(launcher,'docker_command',lambda:'docker')
    desktop=Mock();monkeypatch.setattr(launcher,'start_desktop',desktop)
    launcher.ensure_docker()
    desktop.assert_called_once()
    assert any(c[-2:]==['start',launcher.CONTAINER] for c in calls)
    assert any('pg_isready' in c for c in calls)
    assert not any('create' in c or 'pull' in c or 'rm' in c for c in calls)


def test_engine_deadline_and_own_timer_do_not_wait_forever(monkeypatch):
    moments=iter([0,0,2])
    monkeypatch.setattr(launcher.time,'monotonic',lambda:next(moments))
    monkeypatch.setattr(launcher.time,'sleep',lambda duration:None)
    with pytest.raises(launcher.LaunchError,match='deadline'):
        launcher.wait_until(lambda:False,1,'deadline')


def test_health_deadline_explains_missing_resource_without_source_paths(monkeypatch):
    moments=iter([0,0,30])
    monkeypatch.setattr(launcher.time,'monotonic',lambda:next(moments))
    monkeypatch.setattr(launcher.time,'sleep',lambda duration:None)
    monkeypatch.setattr(launcher,'read_health',lambda port:{'app':'cevami-reader','installation_id':'same',
                         'ready':False,'checks':{'source':'missing','archive':'ready','working':'ready','search':'ready'}})
    with pytest.raises(launcher.LaunchError,match='Arapça kaynak'):
        launcher.wait_for_health(8765,'same')


def test_status_mode_never_starts_services_or_browser(root,monkeypatch):
    monkeypatch.setattr(launcher,'APP_ROOT',root)
    monkeypatch.setattr(launcher,'read_health',lambda port:report(root))
    assert launcher.main(['--status','--port','8765'])==0
    launcher.ensure_docker.assert_not_called();launcher.start_server.assert_not_called();launcher.open_page.assert_not_called()


def test_unresponsive_endpoint_does_not_leak_transport_exception(monkeypatch):
    connection=Mock();connection.request.side_effect=TimeoutError('private-sentinel')
    monkeypatch.setattr(launcher,'HTTPConnection',Mock(return_value=connection))
    assert launcher.read_health(8765) is None


def test_docker_calls_ignore_remote_context_and_host(monkeypatch):
    monkeypatch.setenv('DOCKER_HOST','tcp://remote.invalid:2375')
    monkeypatch.setenv('DOCKER_CONTEXT','remote-selection')
    execute=Mock(return_value=subprocess.CompletedProcess([],0,'',''))
    monkeypatch.setattr(launcher.subprocess,'run',execute)
    launcher.run_command(['docker','info'])
    assert 'DOCKER_HOST' not in execute.call_args.kwargs['env']
    assert 'DOCKER_CONTEXT' not in execute.call_args.kwargs['env']
    calls=[]
    def run(args,timeout=5):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,'true','')
    monkeypatch.setattr(launcher,'run_command',run)
    monkeypatch.setattr(launcher,'docker_command',lambda:'docker')
    launcher.ensure_docker()
    assert all(c[1:3]==['--host','npipe:////./pipe/dockerDesktopLinuxEngine'] for c in calls)


def test_failed_new_server_is_cleaned_but_existing_reader_is_not(root,monkeypatch):
    owned=Mock();launcher.start_server.return_value=owned
    cleanup=Mock();monkeypatch.setattr(launcher,'stop_owned_server',cleanup,raising=False)
    monkeypatch.setattr(launcher,'wait_for_health',Mock(side_effect=launcher.LaunchError('startup failed')))
    with pytest.raises(launcher.LaunchError):launcher.launch(root,8767,False)
    cleanup.assert_called_once_with(owned)
    cleanup.reset_mock()
    monkeypatch.setattr(launcher,'port_in_use',lambda port:True)
    monkeypatch.setattr(launcher,'read_health',lambda port:report(root,False))
    with pytest.raises(launcher.LaunchError):launcher.launch(root,8767,False)
    cleanup.assert_not_called()


def test_early_child_exit_is_reported_without_waiting_for_deadline(monkeypatch):
    owned=Mock();owned.poll.return_value=1
    with pytest.raises(launcher.LaunchError,match='Sunucu başlatılamadı'):
        launcher.wait_for_health(8767,'identity',owned)


def test_launcher_bootstrap_does_not_import_database_dependency():
    import sys
    result=subprocess.run([sys.executable,'-c',"import sys;sys.modules['psycopg']=None;import hadis_web.launcher"],
                          capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_health_does_not_follow_redirect_to_reader():
    from http.server import BaseHTTPRequestHandler,HTTPServer
    import threading
    paths=[]
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            if self.path=='/api/health':
                self.send_response(302);self.send_header('Location','/other-reader');self.end_headers()
            else:
                self.send_response(200);self.end_headers();self.wfile.write(b'{"app":"cevami-reader","ready":true}')
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Redirect)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert launcher.read_health(server.server_port) is None
        assert paths==['/api/health']
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def test_non_http_listener_is_safely_reported_unavailable():
    import socketserver
    import threading
    class Raw(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(4096);self.request.sendall(b'not HTTP\r\n\r\n')
    server=socketserver.TCPServer(('127.0.0.1',0),Raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:assert launcher.read_health(server.server_address[1]) is None
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
