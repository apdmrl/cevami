from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import html
import re
import sqlite3
import unicodedata
import zipfile
from time import monotonic
from .terminology import SOURCE_NAME, GRADE_LABELS, MARKER_TURKISH, MARKER_SOURCES, source_judgement
from .presentation import present_result, book_title_tr

STRUCTURAL_IDS = {30000, 30001, 30002}


@contextmanager
def open_readonly(path: Path, *, query_timeout=None):
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA trusted_schema=OFF')
    conn.execute('PRAGMA query_only=ON')
    if query_timeout is not None:
        deadline=monotonic()+query_timeout
        conn.set_progress_handler(lambda: int(monotonic()>=deadline),1000)
    try:
        yield conn
    finally:
        conn.close()


def plain_markup(text: str) -> str:
    text = re.sub(r'/\d+|L\d+', '', text)
    text = re.sub(r'@\s*([^@]*)\s*@', r' [\1] ', text)
    return re.sub(r'\s+', ' ', text.replace('*', '')).strip()


def arabic_content(raw: str):
    body = re.sub(r'^\$\d+\s+\d+\s*', '', raw)
    pattern = re.compile(r'/(94|26|93)\s+(.*?)\s+L(\d+)\s*/\1(?=\s|$)', re.S)
    runs = []
    position = 0
    for match in pattern.finditer(body):
        gap = plain_markup(body[position:match.start()])
        if gap:
            runs.append({'kind': 'text', 'text': gap + ' '})
        runs.append({'kind': 'narrator', 'text': plain_markup(match.group(2)) + ' ',
                     'narrator_id': int(match.group(3))})
        position = match.end()
    rest = plain_markup(body[position:])
    if rest:
        runs.append({'kind': 'text', 'text': rest})
    return {'text': plain_markup(body), 'raw_text': raw, 'runs': runs,
            'inline_narrator_ids': [int(n) for n in re.findall(r'L(\d+)', raw)]}


def read_strings(data: bytes):
    position = 0
    while position < len(data):
        size = 0
        for shift in range(0, 35, 7):
            if position >= len(data):
                raise ValueError('Truncated string prefix')
            value = data[position]
            position += 1
            size |= (value & 127) << shift
            if value < 128:
                break
        else:
            raise ValueError('Invalid string prefix')
        end = position + size
        if end > len(data):
            raise ValueError('Truncated string')
        yield data[position:end].decode('utf-8')
        position = end


class SourceReader:
    def __init__(self, settings, *, query_timeout=None):
        self.settings = settings
        self.query_timeout=query_timeout

    def connection(self):
        return open_readonly(self.settings.source_db,query_timeout=self.query_timeout)

    def books(self, q='', limit=100, offset=0):
        aliases = {'buhari': 'صحيح البخاري', 'buhârî': 'صحيح البخاري', 'muslim': 'صحيح مسلم', 'müslim': 'صحيح مسلم'}
        q = aliases.get(q.lower().strip(), q.strip())
        where = 'WHERE name LIKE ? OR author LIKE ?' if q else ''
        params = [f'%{q}%', f'%{q}%'] if q else []
        with self.connection() as c:
            total = c.execute('SELECT COUNT(*) FROM books ' + where, params).fetchone()[0]
            rows = c.execute('SELECT * FROM books ' + where +
                             ' ORDER BY CASE book_id WHEN \'146\' THEN 0 ELSE 1 END, priority, CAST(book_id AS INTEGER) LIMIT ? OFFSET ?',
                             params + [limit, offset]).fetchall()
        return {'total': total, 'items': [dict(r) for r in rows], 'limit': limit, 'offset': offset}

    def book(self, book_id):
        with self.connection() as c:
            row = c.execute('SELECT * FROM books WHERE book_id=?', (book_id,)).fetchone()
        return {**dict(row),'name_tr':book_title_tr(book_id)} if row else None

    def hadiths(self, book_id, limit=30, offset=0):
        with self.connection() as c:
            total = c.execute('SELECT COUNT(*) FROM hadith_text WHERE book_id=?', (book_id,)).fetchone()[0]
            rows = c.execute('SELECT bhid,hadith_num,substr(clean_text,1,240) AS snippet FROM hadith_text '
                             'WHERE book_id=? ORDER BY hadith_num LIMIT ? OFFSET ?', (book_id, limit, offset)).fetchall()
        return {'total': total, 'items': [dict(r) for r in rows], 'limit': limit, 'offset': offset}

    @lru_cache(maxsize=16)
    def page_references(self, book_id):
        if not self.settings.books_archive.exists():
            return {}
        wanted = f'books/e7ala/{book_id.zfill(4)}.tbx'
        with zipfile.ZipFile(self.settings.books_archive) as archive:
            name = next((n for n in archive.namelist() if n.lower() == wanted), None)
            if name is None:
                return {}
            return {fields[0]: fields[1:] for text in read_strings(archive.read(name))
                    if len(fields := text.split('\t')) >= 2}

    def hadith(self, bhid):
        with self.connection() as c:
            row = c.execute('SELECT * FROM hadith_text WHERE bhid=?', (bhid,)).fetchone()
            if row is None:
                return None
            row = dict(row)
            index = c.execute('SELECT * FROM hadith WHERE bhid=?', (bhid,)).fetchone()
            index = dict(index) if index else None
            previous = c.execute('SELECT bhid FROM hadith_text WHERE book_id=? AND hadith_num<? '
                                 'ORDER BY hadith_num DESC LIMIT 1', (row['book_id'], row['hadith_num'])).fetchone()
            following = c.execute('SELECT bhid FROM hadith_text WHERE book_id=? AND hadith_num>? '
                                  'ORDER BY hadith_num LIMIT 1', (row['book_id'], row['hadith_num'])).fetchone()
            count = c.execute('SELECT COUNT(*) FROM sanad WHERE bhid=?', (bhid,)).fetchone()[0]
        reference = self.page_references(row['book_id']).get(str(row['hadith_num']), [])
        display = re.match(r'^\$\d+\s+(\d+)', row['raw_text'])
        return {'bhid': bhid, 'primary_language': 'ar', 'internal_number': row['hadith_num'],
                'display_number': display.group(1) if display else None,
                'arabic': arabic_content(row['raw_text']), 'book': self.book(row['book_id']),
                'citation': {'source': SOURCE_NAME, 'hadith_reference_raw': index['ehala'] if index else None,
                             'page_reference_raw': reference[0] if reference else None,
                             'page_reference_fields': reference, 'index_record_present': index is not None},
                'source_judgement': source_judgement(index['hokm']) if index else None,
                'sanad_count': count, 'previous': previous[0] if previous else None,
                'next': following[0] if following else None}

    def sanads(self, bhid, limit=20, offset=0):
        with self.connection() as c:
            exists = c.execute('SELECT 1 FROM hadith_text WHERE bhid=?', (bhid,)).fetchone()
            if not exists:
                return None
            total = c.execute('SELECT COUNT(*) FROM sanad WHERE bhid=?', (bhid,)).fetchone()[0]
            rows = c.execute('SELECT * FROM sanad WHERE bhid=? ORDER BY sanad_id LIMIT ? OFFSET ?', (bhid, limit, offset)).fetchall()
            ids = {int(v) for r in rows for v in r['rawy_ids'].split(',') if v.strip().isdigit()}
            people = {}
            if ids:
                people = {r['id']: dict(r) for r in c.execute('SELECT * FROM narrators WHERE id IN (' + ','.join('?' for _ in ids) + ')', list(ids))}
            items = []
            for record in rows:
                members = []
                for position, raw_id in enumerate(record['rawy_ids'].split(',')):
                    identity = int(raw_id) if raw_id.strip().isdigit() else None
                    person = people.get(identity)
                    members.append({'position': position, 'source_id': identity, 'source_value': raw_id,
                                    'kind': 'structural_marker' if identity in STRUCTURAL_IDS else 'narrator' if person else 'unresolved',
                                    'label': (person['name'] if identity in STRUCTURAL_IDS else person['shohra'] or person['name']) if person else raw_id,
                                    'name': person['name'] if person else None,
                                    'label_tr': MARKER_TURKISH.get(identity),
                                    'translation_source': MARKER_SOURCES.get(identity),
                                    'source_rank': person['wasf_rotba'] if person else None})
                items.append({'sanad_id': record['sanad_id'], 'bhid': bhid, 'members': members,
                              'rawy_ids_raw': record['rawy_ids'], 'cluster_id': record['cluster_id'],
                              'source_judgement': source_judgement(record['hokm'])})
        return {'total': total, 'items': items, 'limit': limit, 'offset': offset, 'source': SOURCE_NAME,
                'order': 'as_recorded_compiler_to_companion'}

    def narrator_records(self, identities):
        identities=list(identities)
        if not identities:
            return {}
        with self.connection() as c:
            return {str(r['id']):dict(r) for r in c.execute('SELECT * FROM narrators WHERE id IN ('+
                ','.join('?' for _ in identities)+')',identities)}

    def critic_records(self, identities):
        identities=list(identities)
        if not identities: return {}
        with self.connection() as c:
            return {str(row['alem_id']):dict(row) for row in c.execute('SELECT * FROM critics WHERE alem_id IN ('+
                ','.join('?' for _ in identities)+')',identities)}

    def narrator(self, narrator_id):
        with self.connection() as c:
            person = c.execute('SELECT * FROM narrators WHERE id=?', (narrator_id,)).fetchone()
            if person is None:
                return None
        opinions = self.critic_opinions(narrator_id)
        return {**dict(person), 'source': SOURCE_NAME, 'kind': 'structural_marker' if narrator_id in STRUCTURAL_IDS else 'narrator',
                'opinions': opinions['items'], 'opinions_total':opinions['total'], 'opinions_limit':opinions['limit']}

    def critic_opinions(self, narrator_id, limit=30, offset=0):
        query = ('SELECT o.alem_id, cr.name AS critic, o.opinion, COUNT(*) AS source_occurrences '
                 'FROM critic_opinions o LEFT JOIN critics cr ON cr.alem_id=o.alem_id '
                 'WHERE o.rawy_id=? GROUP BY o.alem_id,cr.name,o.opinion')
        with self.connection() as c:
            if c.execute('SELECT 1 FROM narrators WHERE id=?',(narrator_id,)).fetchone() is None:
                return None
            total = c.execute('SELECT COUNT(*) FROM ('+query+')',(str(narrator_id),)).fetchone()[0]
            rows = c.execute(query+' ORDER BY o.alem_id,cr.name,o.opinion LIMIT ? OFFSET ?',
                             (str(narrator_id),limit,offset)).fetchall()
        return {'items':[dict(row) for row in rows], 'total':total, 'limit':limit, 'offset':offset}

    def search(self, q, book_id=None, limit=30, offset=0):
        normalized = ''.join(ch for ch in unicodedata.normalize('NFKC', q) if not unicodedata.category(ch).startswith('M'))
        words = re.findall(r'[\u0621-\u064a]+', normalized)
        if not words:
            return {'total': 0, 'items': [], 'books': [], 'limit': limit, 'offset': offset}
        expression = ' AND '.join('"' + word + '"' + ('*' if index == len(words)-1 else '')
                                  for index, word in enumerate(words))
        where = 'hadith_fts MATCH ?'
        params = [expression]
        if book_id:
            where += ' AND f.book_id=?'
            params.append(book_id)
        with self.connection() as c:
            facets = c.execute('''SELECT f.book_id,b.name,count(*) AS count FROM hadith_fts f
                JOIN books b ON b.book_id=f.book_id WHERE hadith_fts MATCH ?
                GROUP BY f.book_id ORDER BY count DESC, CAST(f.book_id AS INTEGER)''',(expression,)).fetchall()
            total = c.execute('SELECT COUNT(*) FROM hadith_fts f WHERE ' + where, params).fetchone()[0]
            rows = c.execute('SELECT f.bhid,f.book_id, t.hadith_num, t.clean_text AS search_text, b.name AS book_name '
                             'FROM hadith_fts f JOIN hadith_text t ON t.bhid=f.bhid JOIN books b ON b.book_id=f.book_id '
                             'WHERE ' + where + ' ORDER BY rank LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
        return {'total': total, 'items': [present_result(r,q) for r in rows],
                'books':[{**dict(r),'name_tr':book_title_tr(r['book_id'])} for r in facets], 'limit': limit, 'offset': offset}
