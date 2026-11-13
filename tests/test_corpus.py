from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.config import Settings


def fixture_sources(tmp_path):
    from hadis_web.source import open_readonly
    root=tmp_path/'corpus';folder=root/'references/turkish/fawazahmed0';folder.mkdir(parents=True)
    db=root/'source.db'
    with sqlite3.connect(db) as c:
        c.executescript('CREATE TABLE books(book_id TEXT,name TEXT,author TEXT);'
                        'CREATE TABLE hadith_text(bhid TEXT,book_id TEXT,hadith_num INTEGER,raw_text TEXT);')
        c.executemany('INSERT INTO books VALUES(?,?,?)',[('158','صحيح مسلم','مسلم بن الحجاج'),('184','سنن أبي داود','أبو داود السجستاني')])
        c.executemany('INSERT INTO hadith_text VALUES(?,?,?,?)',[
          ('158_1','158',1,'$1 2 /94 حدّثنا L1 /94 '+'إنما الأعمال بالنيات '*9),
          ('158_2','158',2,'$2 3 حدثنا '+'إنماالأعمال بالنيات '*9),
          ('184_1','184',1,'$1 2 حدثنا '+'إنما الأعمال بالنيات '*9)])
    collections=[]
    for book in ('muslim','abudawud'):
        ar={'hadiths':[{'hadithnumber':7,'arabicnumber':2,'text':'حدثنا '+'إنما الأعمال بالنيات '*9},
                       {'hadithnumber':8,'arabicnumber':1,'text':'متن آخر لا يطابق المصدر '*9},
                       {'hadithnumber':9,'arabicnumber':5,'text':'نص من دون ترجمة '*10}]}
        tr={'hadiths':[{'hadithnumber':7,'text':'Mevcut kaynak çevirisi.'},
                       {'hadithnumber':8,'text':'Farklı Arapça metnin çevirisi.'},{'hadithnumber':9,'text':''}]}
        entry={'book':book,'edition_author_field':'Unknown','edition_source_field':''}
        for prefix,data in [('ara',ar),('tur',tr)]:
            path=folder/f'{prefix}-{book}.json';path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            entry[prefix]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        collections.append(entry)
    (folder/'coverage.json').write_text(json.dumps({'revision':'fixture-pinned','collections':collections}),encoding='utf-8')
    verify=root/'references/datasets/jawami3_alkalem';verify.mkdir(parents=True)
    (verify/'verification.json').write_text(json.dumps({'database_sha256':hashlib.sha256(db.read_bytes()).hexdigest()}),encoding='utf-8')
    return replace(Settings.load(),project_root=root,source_db=db)


def test_collection_comparison_uses_whole_arabic_and_never_number_only(tmp_path):
    from hadis_web.corpus import prepare_corpus
    settings=fixture_sources(tmp_path)
    data=prepare_corpus(settings,collections=['muslim','abudawud'])
    assert data['summary']['candidate_pairs']==3
    assert data['summary']['target_texts']==3
    links=data['links']
    assert {r['gk_bhid'] for r in links if r['collection']=='muslim'}=={'158_1','158_2'}
    assert {r['gk_bhid'] for r in links if r['collection']=='abudawud'}=={'184_1'}
    assert {r['source_key'] for r in links}=={'7'}
    boundary=next(r for r in links if r['gk_bhid']=='158_2')
    assert boundary['comparison']['arabic_comparison']=='equal_concatenated_letters_but_word_boundaries_differ'
    assert all(not row['translator_verified'] and row['status']=='candidate_requires_review' for row in links)
    assert all(row['comparison']['gk_raw_sha256'] for row in links)


def test_source_validation_happens_before_any_pg_write(environment,tmp_path):
    from hadis_web.corpus import load_corpus
    _,store,_=environment
    settings=fixture_sources(tmp_path)
    path=settings.project_root/'references/turkish/fawazahmed0/tur-muslim.json'
    path.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='checksum'):
        load_corpus(store,settings,collections=['muslim'])
    assert store.counts()['text_versions']==0


def test_import_is_idempotent_and_keeps_evidence_approval_and_source_versions_separate(environment,tmp_path):
    from hadis_web.corpus import load_corpus
    _,store,_=environment
    settings=fixture_sources(tmp_path)
    first=load_corpus(store,settings,collections=['muslim','abudawud'])
    assert first['candidate_pairs']==3
    before=store.counts()
    second=load_corpus(store,settings,collections=['muslim','abudawud'])
    assert store.counts()==before and second['candidate_pairs']==3
    assert before['alignment_revisions']==3 and before['review_events']==0
    with store.connection() as c:
        target=c.execute("SELECT tv.id FROM text_versions tv JOIN text_units u ON u.id=tv.unit_id WHERE u.namespace='gk45:ar' AND u.source_key='158_1'").fetchone()['id']
    result=store.translations('158_1',target)
    assert result['total']==1 and result['items'][0]['source_key']=='7'
    assert result['items'][0]['review']['status']=='needs_review'
    assert result['items'][0]['review']['expert_reviewed'] is False
    assert result['items'][0]['evidence']['v2']['gk_raw_sha256']


def test_book_identity_drift_stops_instead_of_assuming_a_number(tmp_path):
    from hadis_web.corpus import prepare_corpus
    settings=fixture_sources(tmp_path)
    with sqlite3.connect(settings.source_db) as c:
        c.execute("UPDATE books SET name='كتاب آخر' WHERE book_id='158'")
    # Refresh only fixture integrity to isolate the semantic book guard.
    path=settings.project_root/'references/datasets/jawami3_alkalem/verification.json'
    path.write_text(json.dumps({'database_sha256':hashlib.sha256(settings.source_db.read_bytes()).hexdigest()}))
    with pytest.raises(ValueError,match='Book identity'):
        prepare_corpus(settings,collections=['muslim'])
