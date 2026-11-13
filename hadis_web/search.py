"""Read-only published translation search; no review or alignment DB writes."""
import json
from contextlib import closing
import os
import re
import sqlite3
import tempfile
import unicodedata
from .source import open_readonly
from .presentation import present_result, book_title_tr


def search_text(text):
    text = unicodedata.normalize('NFKD', text.casefold()).replace('ı', 'i')
    return ''.join(c for c in text if not unicodedata.category(c).startswith('M'))


def write_index(path, records, metadata):
    """Publish a complete replacement atomically, never editing source corpora."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, pending = tempfile.mkstemp(prefix='search-', suffix='.sqlite', dir=path.parent)
    os.close(handle)
    try:
        with closing(sqlite3.connect(pending)) as conn, conn:
            conn.execute('CREATE TABLE metadata (value TEXT NOT NULL)')
            conn.execute('INSERT INTO metadata VALUES (?)', (json.dumps(metadata, ensure_ascii=False),))
            conn.execute('''CREATE TABLE documents (
                id INTEGER PRIMARY KEY, bhid TEXT, book_id TEXT, book_name TEXT,
                hadith_num INTEGER, language TEXT, text TEXT, edition TEXT,
                source_key TEXT, revision TEXT, source_url TEXT, target_raw_sha256 TEXT)''')
            conn.execute('CREATE INDEX document_target ON documents(bhid, language)')
            conn.execute('CREATE VIRTUAL TABLE search_fts USING fts5(words)')
            keys = ('bhid','book_id','book_name','hadith_num','language','text','edition',
                    'source_key','revision','source_url','target_raw_sha256')
            for record in records:
                row = conn.execute('INSERT INTO documents ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',
                                   [record[key] for key in keys])
                conn.execute('INSERT INTO search_fts(rowid,words) VALUES (?,?)',
                             (row.lastrowid, search_text(record['text'])))
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


class SearchIndex:
    def __init__(self, settings, *, query_timeout=None):
        self.path = settings.search_db
        self.query_timeout=query_timeout

    def search(self, q, language='auto', book_id=None, limit=30, offset=0):
        result = {'available': self.path.exists(), 'items': [], 'total': 0, 'books': [],
                  'limit': limit, 'offset': offset, 'language': language}
        if not result['available']:
            result['message'] = 'Çeviri arama dizini şu anda kullanılamıyor. Arapça metinlerde arama yapabilirsiniz.'
            return result
        words = re.findall(r'[^\W_]+', search_text(q), flags=re.UNICODE)
        if not words:
            return result
        expression = ' AND '.join('"'+w+'"*' for w in words)
        where, params = 'search_fts MATCH ?', [expression]
        if language != 'auto':
            where += ' AND d.language=?'
            params.append(language)
        # Materialize FTS ranks before deduplicating multiple witnesses/languages.
        cte = '''WITH matches AS MATERIALIZED (
            SELECT d.*, search_fts.rank AS score FROM search_fts
            JOIN documents d ON d.id=search_fts.rowid WHERE '''+where+'''),
            unique_matches AS (SELECT *, row_number() OVER (
                PARTITION BY bhid ORDER BY score, id) AS position FROM matches) '''
        with open_readonly(self.path,query_timeout=self.query_timeout) as conn:
            facets = conn.execute(cte+'''SELECT book_id, max(book_name) AS name, count(*) AS count
                FROM unique_matches WHERE position=1 GROUP BY book_id ORDER BY count DESC, CAST(book_id AS INTEGER)''',params).fetchall()
            result['books'] = [{**dict(r),'name_tr':book_title_tr(r['book_id'])} for r in facets]
            scope = 'position=1' + (' AND book_id=?' if book_id else '')
            scoped_params = params + ([book_id] if book_id else [])
            result['total'] = conn.execute(cte+'SELECT count(*) FROM unique_matches WHERE '+scope, scoped_params).fetchone()[0]
            rows = conn.execute(cte+'''SELECT bhid, book_id, book_name, hadith_num,
                text AS search_text, language, edition, source_key, source_url
                FROM unique_matches WHERE '''+scope+' ORDER BY score, bhid LIMIT ? OFFSET ?',
                scoped_params+[limit,offset]).fetchall()
        result['items'] = [present_result(row,q) for row in rows]
        return result

    def translations(self, bhid, language, target_raw_sha256):
        result = {'available': self.path.exists(), 'items': [], 'language': language,
                  'relation': 'full_arabic_token_equality', 'meaning_reviewed': False}
        if not result['available']:
            return result
        with open_readonly(self.path,query_timeout=self.query_timeout) as conn:
            rows = conn.execute('''SELECT text, edition, source_key, source_url, revision
                FROM documents WHERE bhid=? AND language=? AND target_raw_sha256=? ORDER BY id''',
                (bhid,language,target_raw_sha256)).fetchall()
        result['items'] = [dict(row) for row in rows]
        return result
