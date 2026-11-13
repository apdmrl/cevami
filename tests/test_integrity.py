from dataclasses import replace
import hashlib
import json
import sqlite3
from hadis_web.config import Settings
from hadis_web.search import write_index
from hadis_web.integrity import audit


def fixture(tmp_path):
    source=tmp_path/'source.sqlite'
    with sqlite3.connect(source) as c:
        c.executescript('''CREATE TABLE books(book_id TEXT);
            CREATE TABLE hadith_text(bhid TEXT,book_id TEXT,hadith_num INTEGER,raw_text TEXT);
            CREATE TABLE narrators(id INTEGER);
            CREATE TABLE sanad(sanad_id INTEGER,bhid TEXT,rawy_ids TEXT);''')
        c.execute('INSERT INTO books VALUES (?)',('146',))
        c.execute('INSERT INTO hadith_text VALUES (?,?,?,?)',('146_1','146',1,'أصل ثابت'))
        c.executemany('INSERT INTO narrators VALUES (?)',[(1,),(2,),(30001,)])
        c.execute('INSERT INTO sanad VALUES (?,?,?)',(1,'146_1','1,30001,2'))
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    folder=tmp_path/'references/datasets/jawami3_alkalem'
    folder.mkdir(parents=True)
    (folder/'verification.json').write_text(json.dumps({'database_sha256':sha}))
    settings=replace(Settings.load(),source_db=source,project_root=tmp_path,search_db=tmp_path/'search.sqlite')
    row=dict(bhid='146_1',book_id='146',book_name='مصدر',hadith_num=1,language='tr',text='Kaynak niyet metni.',
        edition='tur-test',source_key='9',revision='pin',source_url='https://example.org/source',
        target_raw_sha256=hashlib.sha256('أصل ثابت'.encode()).hexdigest())
    write_index(settings.search_db,[row],{'source_sha256':sha,'revision':'pin'})
    return settings


def test_audit_counts_real_ordered_references_without_approving_meaning(tmp_path):
    settings=fixture(tmp_path)
    report=audit(settings)
    assert report['ok'] is True
    assert report['meaning_reviewed'] is False
    assert report['counts']['chain_members'] == 3
    assert report['counts']['structural_marker_references'] == 1
    assert report['counts']['person_references'] == 2
    assert report['counts']['search_documents_checked'] == 1
    assert report['findings'] == []
    assert report['fingerprints']['source_sha256']==hashlib.sha256(settings.source_db.read_bytes()).hexdigest()
    assert report['fingerprints']['expected_source_sha256']==report['fingerprints']['source_sha256']


def test_audit_detects_changed_target_hash_number_book_and_fts(tmp_path):
    settings=fixture(tmp_path)
    with sqlite3.connect(settings.search_db) as c:
        c.execute("UPDATE documents SET target_raw_sha256='changed',book_id='158',hadith_num=10")
        c.execute('DELETE FROM search_fts WHERE rowid=1')
        c.execute("INSERT INTO search_fts(rowid,words) VALUES (99,'orphan')")
    report=audit(settings)
    codes={f['code'] for f in report['findings']}
    assert {'target_raw_hash_mismatch','target_book_mismatch','target_number_mismatch','missing_fts_document','orphan_fts_document'} <= codes
    assert report['ok'] is False


def test_source_gaps_are_reported_and_source_bytes_are_not_changed(tmp_path):
    settings=fixture(tmp_path)
    with sqlite3.connect(settings.source_db) as c:
        c.execute("INSERT INTO sanad VALUES (2,'missing','999,30002,broken')")
    original=settings.source_db.read_bytes()
    report=audit(settings)
    codes={f['code'] for f in report['findings']}
    assert {'source_snapshot_mismatch','chain_without_text','unknown_person_reference','invalid_chain_token'} <= codes
    assert report['counts']['structural_marker_references'] == 2
    assert settings.source_db.read_bytes() == original


def test_audit_reports_unavailable_index_and_changed_fts_content(tmp_path):
    settings=fixture(tmp_path)
    with sqlite3.connect(settings.search_db) as c:
        c.execute("UPDATE search_fts SET words='unrelated' WHERE rowid=1")
    assert any(f['code']=='fts_content_mismatch' for f in audit(settings)['findings'])
    missing=replace(settings,search_db=tmp_path/'missing.sqlite')
    report=audit(missing)
    assert any(f['code']=='search_index_unavailable' for f in report['findings'])
