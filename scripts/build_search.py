"""Rebuild only the sidecar search index from checksum-pinned source files.

Run from app/: .venv/Scripts/python.exe -m scripts.build_search
"""
from collections import defaultdict, Counter
import hashlib
import json
from hadis_web.config import Settings
from hadis_web.corpus import COLLECTIONS, arabic_tokens, plain_for_comparison
from hadis_web.source import open_readonly
from hadis_web.search import write_index


def checked_json(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'Source checksum mismatch: {path.name}')
    return json.loads(data)


def build(settings):
    tr_folder = settings.project_root/'references/turkish/fawazahmed0'
    en_folder = settings.project_root/'references/search/fawazahmed0-20261104'
    tr_manifest = json.loads((tr_folder/'coverage.json').read_text())
    en_manifest = json.loads((en_folder/'manifest.json').read_text())
    assert tr_manifest['revision'] == en_manifest['revision']
    revision = tr_manifest['revision']
    source_manifest = json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    with settings.source_db.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == source_manifest['database_sha256']
    documents, counts = [], Counter()
    with open_readonly(settings.source_db) as conn:
        for pin in tr_manifest['collections']:
            key = pin['book']
            if key not in COLLECTIONS:
                continue
            book_id, name, author = COLLECTIONS[key]
            book = conn.execute('SELECT name,author FROM books WHERE book_id=?',(book_id,)).fetchone()
            assert (book['name'],book['author']) == (name,author)
            # Preserve token boundaries. No fuzzy or coincident-number GK match.
            targets = defaultdict(list)
            for row in conn.execute('SELECT bhid,hadith_num,raw_text FROM hadith_text WHERE book_id=?',(book_id,)):
                tokens = tuple(arabic_tokens(plain_for_comparison(row['raw_text']), fold=True))
                if len(''.join(tokens)) >= 80:
                    targets[tokens].append(dict(row))
            ar = checked_json(tr_folder/f'ara-{key}.json', pin['ara']['sha256'])['hadiths']
            en_pin = next(r for r in en_manifest['sources'] if r['edition']=='eng-'+key)
            languages = [('tr','tur',tr_folder,pin['tur']['sha256']), ('en','eng',en_folder,en_pin['sha256'])]
            for language,prefix,folder,checksum in languages:
                edition = prefix+'-'+key
                rows = checked_json(folder/(edition+'.json'),checksum)['hadiths']
                translations = {str(row['hadithnumber']):row for row in rows}
                assert len(translations) == len(rows)
                for arabic in ar:
                    source_key = str(arabic['hadithnumber'])
                    translated = translations.get(source_key)
                    if not translated or not translated.get('text','').strip():
                        continue
                    tokens = tuple(arabic_tokens(arabic.get('text',''),fold=True))
                    for target in targets.get(tokens,[]):
                        documents.append(dict(bhid=target['bhid'],book_id=book_id,book_name=name,
                            hadith_num=target['hadith_num'],language=language,text=translated['text'],
                            edition=edition,source_key=source_key,revision=revision,
                            source_url=f'https://github.com/fawazahmed0/hadith-api/blob/{revision}/editions/{edition}.json',
                            target_raw_sha256=hashlib.sha256(target['raw_text'].encode()).hexdigest()))
                        counts[language] += 1
    metadata = {'revision':revision,'source_sha256':source_manifest['database_sha256'],
                'relation':'full_arabic_token_equality_after_orthographic_folding',
                'meaning_reviewed':False,'counts':dict(counts),
                'targets':len({r['bhid'] for r in documents}),
                'sources':[tr_manifest,en_manifest]}
    write_index(settings.search_db,documents,metadata)
    print(json.dumps({k:v for k,v in metadata.items() if k!='sources'}))


if __name__ == '__main__':
    build(Settings.load())
