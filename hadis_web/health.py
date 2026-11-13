"""Small read-only readiness probes; not a content or integrity certification."""
import sqlite3
import zipfile

import psycopg
from psycopg import sql
from .local_identity import installation_id
from .source import open_readonly


def sqlite_state(path, tables):
    if not path.is_file():
        return 'missing'
    try:
        with open_readonly(path) as c:
            for table in tables:
                if c.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() is None:
                    return 'unavailable'
        return 'ready'
    except (sqlite3.Error,OSError):
        return 'unavailable'


def archive_state(path):
    if not path.is_file():
        return 'missing'
    try:
        with zipfile.ZipFile(path) as archive:
            return 'ready' if archive.infolist() else 'unavailable'
    except (OSError,zipfile.BadZipFile):
        return 'unavailable'


def working_state(settings):
    if not settings.postgres_dsn:
        return 'unconfigured'
    try:
        with psycopg.connect(settings.postgres_dsn,connect_timeout=2,
                            options='-c default_transaction_read_only=on -c statement_timeout=1500') as c:
            for table in ('source_snapshots','text_versions','review_events','narrator_records','sanad_records','sanad_members'):
                found=c.execute('SELECT to_regclass(%s)',(f'{settings.postgres_schema}.{table}',)).fetchone()[0]
                if found is None:
                    return 'unavailable'
            row=c.execute(sql.SQL('SELECT 1 FROM {}.text_versions LIMIT 1').format(sql.Identifier(settings.postgres_schema))).fetchone()
            return 'ready' if row else 'unavailable'
    except (psycopg.Error,ValueError):
        return 'unavailable'


def health_report(settings):
    checks={
        'source':sqlite_state(settings.source_db,('books','hadith_text','sanad')),
        'archive':archive_state(settings.books_archive),
        'search':sqlite_state(settings.search_db,('documents','metadata','search_fts')),
        'working':working_state(settings),
    }
    return {'app':'cevami-reader','installation_id':installation_id(settings.project_root),
            'ready':all(state=='ready' for state in checks.values()),'checks':checks}
