"""Create deployment secrets once; never print or silently rotate credentials."""
import argparse
from pathlib import Path
import secrets
import os


def prepare_secrets(directory):
    directory=Path(directory)
    paths=[directory/'pg_admin_password',directory/'web_db_password']
    if directory.is_symlink() or any(path.is_symlink() for path in paths):raise ValueError('Sır dizini veya dosyası bağlantı olamaz.')
    if any(path.exists() for path in paths):
        if not all(path.is_file() and 48<=path.stat().st_size<=256 for path in paths):
            raise ValueError('Eksik veya geçersiz mevcut sırlar var; dosyalara dokunulmadı.')
        if os.name!='nt':
            directory.chmod(0o700)
            for path in paths:path.chmod(0o444)
        return paths
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt':directory.chmod(0o700)
    for path in paths:
        with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(secrets.token_urlsafe(48)+'\n')
        # Compose file-backed secrets keep host modes: readable in a non-root
        # container, protected from other host users by the parent directory.
        if os.name!='nt':path.chmod(0o444)
    return paths


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',default='deploy/secrets')
    args=parser.parse_args();paths=prepare_secrets(args.directory)
    print('Sır dosyaları hazır; değerler yazdırılmadı: '+', '.join(path.name for path in paths))


if __name__=='__main__':main()
