from typing import Annotated
import json
import hashlib
import re
import sqlite3
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import psycopg
from .config import Settings
from .source import SourceReader
from .working import WorkingStore, stable_id, text_identity
from .localization import LocalizationStore, narrator_record, empty_localization, opinion_record, opinion_key, merge_critic_name
from .controlled_terms import apply_controlled_terms
from .hadith_components import component_report
from .search import SearchIndex
from .presentation import canonical_digits,present_result,source_presentation
from .health import health_report
from .importer import verify_artifact
from .security import LocalReaderSecurity, SECURITY_HEADERS
from pathlib import Path as FilePath


HadithId = Annotated[str, Path(pattern=r'^\d+_\d+$', max_length=50)]
BookId = Annotated[str, Path(pattern=r'^\d+$', max_length=20)]
Language = Annotated[str, Query(pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$', max_length=35)]
NarratorId = Annotated[int, Path(ge=1,le=2**63-1)]
Offset = Annotated[int, Query(ge=0,le=2**63-1)]


def create_app(settings=None):
    settings = settings or Settings.load()
    settings.validate()
    source = SourceReader(settings,query_timeout=5)
    search_index = SearchIndex(settings,query_timeout=5)
    manifest = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text())
    if settings.environment=='production':verify_artifact(settings.source_db,manifest['database_sha256'])
    source_snapshot = stable_id('snapshot', 'gk45', '4.5', manifest['database_sha256'])
    app = FastAPI(title='Cevâmi — Hadis Araştırma', version='0.1.0',docs_url=None,redoc_url=None)
    app.add_middleware(LocalReaderSecurity,public_origin=settings.public_origin)
    app.state.settings = settings
    response_headers={**SECURITY_HEADERS,**({'Strict-Transport-Security':'max-age=31536000'} if settings.environment=='production' else {})}

    @app.exception_handler(Exception)
    async def unexpected_error(request,exc):
        return JSONResponse({'detail':'İstek işlenemedi. Yeniden deneyebilirsiniz.'},status_code=500,headers=response_headers)

    @app.exception_handler(sqlite3.OperationalError)
    async def source_unavailable(request,exc):
        return JSONResponse({'detail':'Kaynak sorgusu şu anda tamamlanamadı. Aramayı daraltıp yeniden deneyebilirsiniz.'},status_code=503,headers=response_headers)

    def localize_records(records, language, entity_type='narrator'):
        if settings.postgres_dsn:
            try:
                working=WorkingStore(settings.postgres_dsn,settings.postgres_schema,read_only=True)
                localized=LocalizationStore(working).for_records(
                    source_snapshot,entity_type,records,language)
                return apply_controlled_terms(working,source_snapshot,records,localized,language) if entity_type=='narrator' else localized
            except psycopg.Error:
                pass
        return {key:empty_localization(record,language,available=False,entity_type=entity_type) for key,record in records.items()}

    def localize_opinions(narrator_id, rows, language):
        records={opinion_key(record):record for row in rows if (record:=opinion_record(narrator_id,row))}
        localized=localize_records(records,language,'critic_opinion')
        critics=source.critic_records({row['alem_id'] for row in rows})
        critic_names=localize_records(critics,language,'critic')
        for row in rows:
            key=opinion_key(opinion_record(narrator_id,row))
            row['key']=key
            row['localization']=localized[key]
            identity=str(row['alem_id'])
            if identity in critics:
                row['localization']=merge_critic_name(row['localization'],row['critic'],critics[identity],critic_names[identity])

    @app.get('/api/health')
    def health():
        return health_report(settings)

    @app.get('/api/status')
    def status():
        working = {'available': False}
        if settings.postgres_dsn:
            try:
                working = {'available': True, 'counts': WorkingStore(settings.postgres_dsn, settings.postgres_schema,read_only=True).counts()}
            except psycopg.Error:
                pass
        return {'primary_language': 'ar', 'source': 'Cevâmiu’l-Kelim 4.5',
                'source_counts': {'books': 1400, 'text_blocks': 824841, 'narrators': 49845, 'sanads': 638237},
                'working': working, 'stage': 'local_research_reader'}

    @app.get('/api/books')
    def books(q: str = Query('', max_length=120), limit: int = Query(100, ge=1, le=200), offset: Offset = 0):
        return source.books(q, limit, offset)

    @app.get('/api/books/{book_id}')
    def book(book_id: BookId):
        value = source.book(book_id)
        if value is None:
            raise HTTPException(404, 'Eser bulunamadı.')
        return value

    @app.get('/api/books/{book_id}/hadiths')
    def book_hadiths(book_id: BookId, limit: int = Query(30, ge=1, le=100), offset: Offset = 0):
        if source.book(book_id) is None:
            raise HTTPException(404, 'Eser bulunamadı.')
        return source.hadiths(book_id, limit, offset)

    @app.get('/api/hadith/{bhid}')
    def hadith(bhid: HadithId):
        value = source.hadith(bhid)
        if value is None:
            raise HTTPException(404, 'Hadis kaydı bulunamadı.')
        return value

    @app.get('/api/hadith/{bhid}/sanads')
    def sanads(bhid: HadithId, limit: int = Query(20, ge=1, le=100), offset: Offset = 0, language: Language = 'tr'):
        value = source.sanads(bhid, limit, offset)
        if value is None:
            raise HTTPException(404, 'Hadis kaydı bulunamadı.')
        records=source.narrator_records({m['source_id'] for row in value['items'] for m in row['members'] if m['kind']=='narrator'})
        localized=localize_records(records,language)
        for row in value['items']:
            for member in row['members']:
                if member['kind']=='narrator':
                    member['localization']=localized[str(member['source_id'])]
        return value

    @app.get('/api/hadith/{bhid}/translations')
    def translations(bhid: HadithId):
        current = source.hadith(bhid)
        if current is None:
            raise HTTPException(404, 'Hadis kaydı bulunamadı.')
        _, version, _ = text_identity(source_snapshot, 'gk45:ar', bhid,
                                      current['arabic']['raw_text'], current['arabic']['text'])
        if settings.postgres_dsn:
            try:
                data=WorkingStore(settings.postgres_dsn, settings.postgres_schema,read_only=True).translations(bhid, version)
                return {**data,'items':[{**row,'presentation':source_presentation(row['display_text'],
                                           'tr' if row.get('provider')=='fawazahmed0' and row.get('namespace','').startswith('fawaz:tur-') else None)}
                                       for row in data['items']]}
            except psycopg.Error:
                pass
        return {'available': False, 'items': [], 'total': 0,
                'message': 'Çeviri çalışma verisine şu anda erişilemiyor.'}

    @app.get('/api/hadith/{bhid}/components')
    def hadith_components(bhid: HadithId, language: Language = 'tr'):
        if language.split('-')[0] == 'ar':
            raise HTTPException(422, 'Arapça asıl metin hadis kaydında bulunur; burada çeviri dili seçilir.')
        if source.hadith(bhid) is None:
            raise HTTPException(404, 'Hadis kaydı bulunamadı.')
        if settings.postgres_dsn:
            try:
                return component_report(WorkingStore(settings.postgres_dsn, settings.postgres_schema,read_only=True), settings, bhid, language)
            except psycopg.Error:
                pass
        return {'available': False, 'items': [], 'coverage': {}, 'hadith_core_complete': False,
                'blockers': ['working_data_unavailable'], 'language': language, 'bhid': bhid,
                'message': 'Türkçe bölüm incelemelerine şu anda erişilemiyor. Arapça asıl metin okunabilir.'}

    @app.get('/api/narrator/{narrator_id}')
    def narrator(narrator_id: NarratorId, language: Language = 'tr'):
        value = source.narrator(narrator_id)
        if value is None:
            raise HTTPException(404, 'Ravi kaydı bulunamadı.')
        record=narrator_record(value)
        value['localization']=localize_records({str(narrator_id):record},language)[str(narrator_id)]
        localize_opinions(narrator_id,value['opinions'],language)
        if value['opinions_total']>len(value['opinions']) or any(not row['localization']['complete'] for row in value['opinions']):
            value['localization']['pending_fields'].append('critic_opinions')
            value['localization']['complete']=False
        return value

    @app.get('/api/narrator/{narrator_id}/opinions')
    def narrator_opinions(narrator_id: NarratorId, language: Language = 'tr',
                         limit: int = Query(30,ge=1,le=100), offset: Offset = 0):
        value=source.critic_opinions(narrator_id,limit,offset)
        if value is None:
            raise HTTPException(404,'Ravi kaydı bulunamadı.')
        localize_opinions(narrator_id,value['items'],language)
        return value

    @app.get('/api/search')
    def search(q: str = Query('', max_length=160), book_id: str | None = Query(None, pattern=r'^\d+$',max_length=20),
               limit: int = Query(30, ge=1, le=100), offset: Offset = 0,
               language: str = Query('auto', pattern=r'^(auto|tr|en|ar)$')):
        q = q.strip()
        if book_id is not None:book_id=canonical_digits(book_id)
        if re.fullmatch(r'\d+_\d+', q):
            q=canonical_digits(q)
            row = source.hadith(q)
            facets = [] if row is None else [{'book_id':row['book']['book_id'],'name':row['book']['name'],
                        'name_tr':row['book'].get('name_tr'),'count':1}]
            items = [] if row is None or (book_id and row['book']['book_id'] != book_id) else [{
                'bhid':q, 'book_id':row['book']['book_id'], 'book_name':row['book']['name'],
                'hadith_num':row['internal_number'], 'snippet':row['arabic']['text'][:360], 'language':'ar'}]
            return {'available':True, 'items':[present_result(item,'') for item in items[offset:offset+limit]], 'books':facets,'total':len(items), 'limit':limit,'offset':offset}
        if language == 'ar' or (language == 'auto' and re.search(r'[\u0621-\u064a]',q)):
            data = source.search(q, book_id, limit, offset)
            for item in data['items']:
                item['language'] = 'ar'
            return {**data, 'available':True, 'language':'ar'}
        return search_index.search(q, language, book_id, limit, offset)

    @app.get('/api/hadith/{bhid}/search-translations')
    def search_translations(bhid: HadithId, language: str = Query('tr', pattern=r'^(tr|en)$')):
        value = source.hadith(bhid)
        if value is None:
            raise HTTPException(404, 'Hadis kaydı bulunamadı.')
        checksum = hashlib.sha256(value['arabic']['raw_text'].encode()).hexdigest()
        return search_index.translations(bhid, language, checksum)

    static = FilePath(__file__).parent / 'static'
    if static.exists():
        app.mount('/assets', StaticFiles(directory=static), name='assets')

        @app.get('/')
        def index(hadith: str | None = Query(None, pattern=r'^\d+_\d+$', max_length=50)):
            if hadith:
                return RedirectResponse('/hadith/'+hadith, status_code=307)
            return FileResponse(static / 'home.html')

        @app.get('/research')
        def research():
            return FileResponse(static / 'index.html')

        @app.get('/hadith/{bhid}')
        def hadith_page(bhid: HadithId):
            if source.hadith(bhid) is None:
                raise HTTPException(404, 'Hadis kaydı bulunamadı.')
            html = (static/'index.html').read_text(encoding='utf-8')
            return HTMLResponse(html.replace('<body>', f'<body data-page="hadith" data-hadith="{bhid}">'))

    return app
