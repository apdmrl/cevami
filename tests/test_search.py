from dataclasses import replace
import hashlib
from fastapi.testclient import TestClient
from hadis_web.app import create_app
from hadis_web.config import Settings
from hadis_web.search import SearchIndex, write_index
from scripts.build_search import build
import json
import sqlite3
from hadis_web.corpus import COLLECTIONS


def records():
    return [dict(bhid=bhid, book_id=bhid.split('_')[0], book_name='Buhârî',
                 hadith_num=int(bhid.split('_')[1]), language=lang, text=text,
                 edition=lang+'-fixture', source_key=str(i), revision='pinned',
                 source_url='https://example.org/source', target_raw_sha256='abc')
            for i, (bhid, lang, text) in enumerate([
                ('146_1', 'tr', 'Ameller niyetlere göre karşılık bulur.'),
                ('146_1', 'tr', 'Ameller için niyetlere bakılır.'),
                ('146_1', 'en', 'Actions are judged by intentions.'),
                ('146_2', 'tr', 'İnsanların karşılık bulması.'),
                ('158_1', 'tr', 'Ameller niyetlere göre değerlendirilir.')])]


def configured(tmp_path):
    settings = replace(Settings.load(), search_db=tmp_path/'search.sqlite')
    write_index(settings.search_db, records(), {'purpose': 'test'})
    return settings


def test_search_actual_words_prefix_turkish_folding_dedup_and_paging(tmp_path):
    index = SearchIndex(configured(tmp_path))
    found = index.search('niyet', language='tr', limit=1)
    assert found['total'] == 2
    assert len(found['items']) == 1
    second = index.search('niyet', language='tr', limit=1, offset=1)
    assert second['items'][0]['bhid'] != found['items'][0]['bhid']
    assert index.search('karsilik', language='tr')['total'] == 2
    assert index.search('intentions', language='en')['items'][0]['bhid'] == '146_1'
    assert index.search('niyet', language='en')['total'] == 0
    assert index.search('niyet', book_id='158')['items'][0]['bhid'] == '158_1'
    assert index.search('" OR 1=1 --')['items'] == []
    assert index.search('')['items'] == []


def test_missing_index_is_explained_and_no_translation_is_fabricated(tmp_path):
    settings = replace(Settings.load(), search_db=tmp_path/'missing.sqlite')
    data = SearchIndex(settings).search('niyet', language='tr')
    assert data['available'] is False and data['items'] == []
    assert data['message']
    assert SearchIndex(settings).translations('146_1', 'en', 'abc')['items'] == []


def test_translations_require_current_arabic_and_keep_all_sources(tmp_path):
    index = SearchIndex(configured(tmp_path))
    data = index.translations('146_1', 'tr', 'abc')
    assert len(data['items']) == 2
    assert data['items'][0]['edition'] == 'tr-fixture'
    assert data['items'][0]['source_url'] == 'https://example.org/source'
    assert index.translations('146_1', 'tr', 'changed')['items'] == []


def test_routes_and_multilingual_api(tmp_path):
    client = TestClient(create_app(configured(tmp_path)),base_url='http://127.0.0.1')
    assert client.get('/').status_code == 200
    assert 'home.js' in client.get('/').text
    assert client.get('/research').status_code == 200
    assert 'data-page="hadith"' in client.get('/hadith/146_1').text
    old = client.get('/?hadith=146_1', follow_redirects=False)
    assert old.status_code in (302, 307) and old.headers['location'] == '/hadith/146_1'
    assert client.get('/hadith/146_999999999').status_code == 404
    assert client.get('/hadith/not-an-id').status_code == 422
    assert client.get('/api/search', params={'q':'intentions','language':'en'}).json()['total'] == 1
    assert client.get('/api/search', params={'q':'146_1'}).json()['items'][0]['bhid'] == '146_1'
    assert client.get('/api/search', params={'q':'niyet','language':'invalid'}).status_code == 422
    assert client.get('/api/hadith/146_1/search-translations?language=ar').status_code == 422


def test_arabic_suggestions_match_the_last_unfinished_word(tmp_path):
    client = TestClient(create_app(configured(tmp_path)),base_url='http://127.0.0.1')
    data = client.get('/api/search',params={'q':'إنما الأعما','language':'ar','book_id':'146'}).json()
    assert '146_1' in [item['bhid'] for item in data['items']]


def test_book_facets_count_unique_records_and_survive_a_zero_result_filter(tmp_path):
    index=SearchIndex(configured(tmp_path))
    data=index.search('niyet',language='tr',book_id='146')
    assert data['total'] == 1
    assert [(r['book_id'],r['count']) for r in data['books']] == [('146',1),('158',1)]
    assert data['books'][0]['name_tr'].startswith('Buhârî')
    empty=index.search('niyet',language='tr',book_id='184')
    assert empty['total'] == 0 and len(empty['books']) == 2
    assert [r['book_id'] for r in index.search('intentions',language='en')['books']] == ['146']


def test_arabic_and_direct_identity_facets_use_the_same_scope_contract(tmp_path):
    client=TestClient(create_app(configured(tmp_path)),base_url='http://127.0.0.1')
    data=client.get('/api/search',params={'q':'إنما الأعمال','language':'ar','book_id':'999999'}).json()
    assert data['total'] == 0
    assert '146' in [r['book_id'] for r in data['books']]
    exact=client.get('/api/search',params={'q':'146_1','book_id':'158'}).json()
    assert exact['total'] == 0
    assert exact['books'][0]['book_id'] == '146' and exact['books'][0]['count'] == 1


def test_unicode_identity_and_scope_find_the_same_source_without_changing_keys(tmp_path):
    client=TestClient(create_app(configured(tmp_path)),base_url='http://127.0.0.1')
    for identity in ('١٤٦_١','۱۴۶_۱','1٤۶_1',' ١٤٦_١ '):
        data=client.get('/api/search',params={'q':identity,'book_id':'١٤٦','language':'ar'}).json()
        assert data['total']==1
        assert data['items'][0]['bhid']=='146_1'
        assert data['books'][0]['book_id']=='146'
    data=client.get('/api/search',params={'q':'١٤٦_١','book_id':'١٥٨'}).json()
    assert data['total']==0 and data['books'][0]['book_id']=='146'


def test_builder_requires_complete_arabic_tokens_not_numbers_or_joined_letters(tmp_path):
    project = tmp_path/'project'
    tr = project/'references/turkish/fawazahmed0'
    en = project/'references/search/fawazahmed0-20261104'
    verification = project/'references/datasets/jawami3_alkalem'
    for folder in [tr,en,verification]: folder.mkdir(parents=True)
    source_db = tmp_path/'source.sqlite'
    book_id,name,author = COLLECTIONS['bukhari']
    arabic = ' '.join(['صادق']*25)
    with sqlite3.connect(source_db) as conn:
        conn.execute('CREATE TABLE books(book_id TEXT,name TEXT,author TEXT)')
        conn.execute('INSERT INTO books VALUES(?,?,?)',(book_id,name,author))
        conn.execute('CREATE TABLE hadith_text(bhid TEXT,book_id TEXT,hadith_num INTEGER,raw_text TEXT)')
        conn.executemany('INSERT INTO hadith_text VALUES(?,?,?,?)',[
            ('146_1',book_id,1,'$1 1 '+arabic),
            ('146_2',book_id,2,'$2 2 '+arabic.replace('صادق','صا دق',1)),
            ('146_999',book_id,999,'$3 3 '+'مختلف '*25)])
    def write(path, value):
        data = json.dumps(value,ensure_ascii=False).encode()
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    ar_sha = write(tr/'ara-bukhari.json',{'hadiths':[{'hadithnumber':999,'text':arabic}]})
    tr_sha = write(tr/'tur-bukhari.json',{'hadiths':[{'hadithnumber':999,'text':'Yayımlanmış örnek niyet metni.'}]})
    en_sha = write(en/'eng-bukhari.json',{'hadiths':[{'hadithnumber':999,'text':'Published intentions text.'}]})
    write(tr/'coverage.json',{'revision':'pin','collections':[{'book':'bukhari','ara':{'sha256':ar_sha},'tur':{'sha256':tr_sha}}]})
    write(en/'manifest.json',{'revision':'pin','sources':[{'edition':'eng-bukhari','sha256':en_sha}]})
    write(verification/'verification.json',{'database_sha256':hashlib.sha256(source_db.read_bytes()).hexdigest()})
    settings = replace(Settings.load(),project_root=project,source_db=source_db,search_db=tmp_path/'search.sqlite')
    build(settings)
    found = SearchIndex(settings).search('intentions',language='en')
    assert [r['bhid'] for r in found['items']] == ['146_1']
    assert found['items'][0]['source_key'] == '999'
    # Changed source bytes must never silently regenerate the same associations.
    (en/'eng-bukhari.json').write_text('{}')
    import pytest
    with pytest.raises(ValueError,match='checksum mismatch'): build(settings)
