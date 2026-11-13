from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import re
from urllib.parse import urlsplit
from ipaddress import ip_address

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent


def normalize_public_origin(value):
    try:
        url=urlsplit(value or '')
        if (url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None
            or url.path not in ('','/') or url.query or url.fragment):raise ValueError()
        host=url.hostname.encode('idna').decode('ascii').lower()
        try:
            address=ip_address(host)
        except ValueError:
            if (host=='localhost' or len(host)>253 or
                any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.'))):raise ValueError()
        else:
            if address.is_loopback or address.is_unspecified:raise ValueError()
        port=url.port
        if port is not None and not 1<=port<=65535:raise ValueError()
        authority=('['+host+']') if ':' in host else host
        return 'https://'+authority+(':'+str(port) if port not in (None,443) else '')
    except (ValueError,UnicodeError):
        raise ValueError('Üretim için geçerli, yalnız HTTPS bir genel adres gereklidir.') from None


@dataclass(frozen=True)
class Settings:
    source_db: Path = PROJECT_ROOT / 'references/datasets/jawami3_alkalem/jawami.db'
    research_db: Path = PROJECT_ROOT / 'research/turkish-sources/translation-research.sqlite'
    search_db: Path = APP_ROOT / '.local/search.sqlite'
    books_archive: Path = PROJECT_ROOT / 'GK4.5/GK4.5/Data/Books.zip'
    project_root: Path = PROJECT_ROOT
    postgres_dsn: str | None = field(default=None, repr=False)
    postgres_schema: str = 'hadis'
    environment: str = 'local'
    public_origin: str | None = None

    def validate(self):
        if self.environment not in ('local','production'):raise ValueError('Çalışma ortamı geçersiz.')
        if self.environment=='production':
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
            normalize_public_origin(self.public_origin)
            if not self.postgres_dsn:raise ValueError('Üretim veritabanı bağlantısı yapılandırılmalıdır.')
            try:conninfo_to_dict(self.postgres_dsn)
            except psycopg.Error:raise ValueError('Üretim veritabanı bağlantısı geçersiz.') from None
        elif self.public_origin:
            raise ValueError('Genel adres yalnız üretim ortamında kullanılabilir.')

    @classmethod
    def load(cls):
        config_path = APP_ROOT / '.local/settings.json'
        local = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
        environment=os.environ.get('HADIS_ENV','local')
        if environment=='production' and (not os.environ.get('HADIS_DATA_ROOT') or not os.environ.get('HADIS_DB_PASSWORD_FILE')):
            raise ValueError('Üretimde açık veri dizini ve parola dosyası zorunludur.')
        dsn=os.environ.get('HADIS_DATABASE_URL') or (local.get('postgres_dsn') if environment=='local' else None)
        secret=os.environ.get('HADIS_DB_PASSWORD_FILE')
        if secret:
            from psycopg.conninfo import make_conninfo
            if os.environ.get('HADIS_DATABASE_URL'):raise ValueError('Tek bir veritabanı bağlantı kaynağı seçilmelidir.')
            try:
                with Path(secret).open(encoding='utf-8') as stream:password=stream.read(16385).rstrip('\r\n')
                if not password or len(password)>16384:raise ValueError()
            except (OSError,UnicodeError,ValueError):raise ValueError('Veritabanı parola dosyası okunamadı.') from None
            dsn=make_conninfo(host=os.environ.get('HADIS_DB_HOST','database'),port=os.environ.get('HADIS_DB_PORT','5432'),
                dbname=os.environ.get('HADIS_DB_NAME','cevami'),user=os.environ.get('HADIS_DB_USER','cevami_web'),password=password)
        paths={}
        if base:=os.environ.get('HADIS_DATA_ROOT'):
            base=Path(base).resolve()
            paths=dict(project_root=base,source_db=base/'references/datasets/jawami3_alkalem/jawami.db',
                research_db=base/'research/turkish-sources/translation-research.sqlite',search_db=base/'search/search.sqlite',
                books_archive=base/'GK4.5/GK4.5/Data/Books.zip')
        result=cls(**paths,postgres_dsn=dsn,postgres_schema=local.get('postgres_schema','hadis'),
            environment=environment,public_origin=os.environ.get('HADIS_PUBLIC_ORIGIN'))
        result.validate()
        return result
