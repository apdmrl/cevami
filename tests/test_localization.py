from dataclasses import replace
import json
import uuid
import pytest
import psycopg
from psycopg import sql
from fastapi.testclient import TestClient
from hadis_web.config import Settings
from hadis_web.source import SourceReader
from hadis_web.working import WorkingStore


@pytest.fixture
def environment():
    settings = replace(Settings.load(), postgres_schema='test_' + uuid.uuid4().hex)
    store = WorkingStore(settings.postgres_dsn, settings.postgres_schema)
    store.migrate()
    checksum = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text())['database_sha256']
    snapshot = store.add_snapshot('gk45', '4.5', checksum, 'jawami.db')
    yield settings, store, snapshot
    with psycopg.connect(settings.postgres_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(settings.postgres_schema)))


def claim(local, snapshot, record, **changes):
    values = dict(snapshot=snapshot, entity_type='narrator', entity_key=str(record['id']),
                  source_record=record, field='shohra', language='tr', text='Abdullah b. Zübeyr el-Humeydî',
                  rendering_kind='name_form', status='source_compared', actor_kind='assistant_source_review',
                  sources=[{'url':'https://islamansiklopedisi.org.tr/humeydi-abdullah-b-zubeyr', 'title':'TDV: Humeydî', 'locator':'Madde başlığı', 'accessed_on':'2026-10-31'}],
                  rationale='Arapça ad, alternatif ad ve ölüm tarihi kaynakla karşılaştırıldı.')
    values.update(changes)
    return local.add_claim(**values)


def test_field_translations_are_immutable_idempotent_and_bound_to_current_source(environment):
    from hadis_web.localization import LocalizationStore, narrator_record
    settings, store, snapshot = environment
    local = LocalizationStore(store)
    record = narrator_record(SourceReader(settings).narrator(4698))
    first = claim(local, snapshot, record)
    assert claim(local, snapshot, record) == first
    result = local.for_records(snapshot, 'narrator', {'4698':record}, 'tr')['4698']
    assert len(result['fields']['shohra']) == 1
    assert result['fields']['shohra'][0]['expert_reviewed'] is False
    assert local.for_records(snapshot, 'narrator', {'4698':{**record,'death_year':'220'}}, 'tr')['4698']['fields'] == {}
    other = store.add_snapshot('gk45', 'new', 'a'*64, 'other.db')
    assert local.for_records(other, 'narrator', {'4698':record}, 'tr')['4698']['fields'] == {}
    with pytest.raises(psycopg.Error):
        with store.connection() as c:
            c.execute('UPDATE localization_claims SET translated_text=%s WHERE id=%s', ('Değişti', first))


def test_field_corrections_preserve_history_and_cannot_supersede_another_entity(environment):
    from hadis_web.localization import LocalizationStore
    _, store, snapshot = environment
    local = LocalizationStore(store)
    record = {'id':4698,'shohra':'الحميدي'}
    first = claim(local, snapshot, record, status='needs_review')
    second = claim(local, snapshot, record, supersedes_id=first)
    data = local.for_records(snapshot, 'narrator', {'4698':record}, 'tr')['4698']
    assert [row['id'] for row in data['fields']['shohra']] == [str(second)]
    with pytest.raises((ValueError, psycopg.Error)):
        claim(local, snapshot, {'id':3443,'shohra':'سفيان'}, supersedes_id=second)
    with store.connection() as c:
        assert c.execute('SELECT COUNT(*) AS n FROM localization_claims').fetchone()['n'] == 2


def test_other_languages_and_conflicting_candidates_are_kept_separate(environment):
    from hadis_web.localization import LocalizationStore
    _, store, snapshot = environment
    local = LocalizationStore(store)
    record = {'id':4698,'shohra':'الحميدي'}
    claim(local, snapshot, record)
    claim(local, snapshot, record, text='Humeydî, Abdullah b. Zübeyr')
    claim(local, snapshot, record, language='en',text='Al-Humaydi')
    result = local.for_records(snapshot,'narrator',{'4698':record},'tr')['4698']
    assert len(result['fields']['shohra']) == 2
    assert result['conflicting_fields'] == ['shohra']
    assert result['complete'] is False


def test_automatic_or_unsourced_claims_cannot_be_called_source_compared(environment):
    from hadis_web.localization import LocalizationStore
    _, store, snapshot = environment
    local = LocalizationStore(store)
    record = {'id':4698,'shohra':'الحميدي'}
    with pytest.raises((ValueError, psycopg.Error)):
        claim(local,snapshot,record,actor_kind='automated_check')
    with pytest.raises((ValueError, psycopg.Error)):
        claim(local,snapshot,record,sources=[])
    with pytest.raises((ValueError, psycopg.Error)):
        claim(local,snapshot,record,sources=[{'url':'javascript:alert(1)','title':'x','locator':'x','accessed_on':'2026-10-31'}])


def test_narrator_and_sanads_expose_secondary_turkish_without_replacing_arabic(environment):
    from hadis_web.localization import LocalizationStore, narrator_record
    settings, store, snapshot = environment
    from hadis_web.app import create_app
    source = SourceReader(settings)
    local = LocalizationStore(store)
    record = narrator_record(source.narrator(4698))
    claim(local,snapshot,record)
    client = TestClient(create_app(settings),base_url='http://127.0.0.1')
    data = client.get('/api/narrator/4698').json()
    assert data['shohra'] == record['shohra']
    assert data['localization']['fields']['shohra'][0]['text'] == 'Abdullah b. Zübeyr el-Humeydî'
    assert 'baladekama' in data['localization']['pending_fields']
    assert client.get('/api/narrator/4698?language=en').json()['localization']['fields'] == {}
    chain = client.get('/api/hadith/146_1/sanads').json()['items'][0]['members']
    assert [p['source_id'] for p in chain] == [6817,4698,3443,8272,6796,5719,5913]
    assert chain[1]['localization']['fields']['shohra'][0]['text'] == 'Abdullah b. Zübeyr el-Humeydî'
    assert client.get('/api/hadith/146_3/sanads').json()['items'][0]['members'][1]['label_tr'] == 'Ta‘lîk yeri'
    assert client.get('/api/hadith/146_1/sanads').json()['items'][0]['source_judgement']['label_tr'] == 'Sahih'
    assert client.get('/api/narrator/4698?language=../../bad').status_code == 422


def test_arabic_remains_available_without_working_database():
    from hadis_web.app import create_app
    client = TestClient(create_app(replace(Settings.load(),postgres_dsn=None)),base_url='http://127.0.0.1')
    data=client.get('/api/narrator/4698').json()
    assert data['shohra'] == 'الحميدي عبد الله بن الزبير'
    assert data['localization']['available'] is False
    assert client.get('/api/hadith/146_3/sanads').json()['total'] == 7


def test_localization_pilot_import_is_idempotent_and_does_not_invent_complete_biographies(environment):
    from hadis_web.localization import load_localization_pilot, LocalizationStore, narrator_record
    settings, store, snapshot=environment
    first=load_localization_pilot(store,settings)
    second=load_localization_pilot(store,settings)
    assert first == second
    assert first['narrators'] == 7
    record=narrator_record(SourceReader(settings).narrator(4698))
    result=LocalizationStore(store).for_records(snapshot,'narrator',{'4698':record},'tr')['4698']
    assert result['fields']['biography_note'][0]['rendering_kind'] == 'source_summary'
    from hadis_web.app import create_app
    profile=TestClient(create_app(settings),base_url='http://127.0.0.1').get('/api/narrator/4698').json()
    assert profile['localization']['complete'] is False
    assert 'critic_opinions' in profile['localization']['pending_fields']
    bukhari=narrator_record(SourceReader(settings).narrator(6817))
    assert 'name' in LocalizationStore(store).for_records(snapshot,'narrator',{'6817':bukhari},'tr')['6817']['pending_fields']


def test_reviewed_pilot_rejects_any_source_record_drift(environment, monkeypatch):
    from hadis_web.localization import load_localization_pilot
    settings, store, _ = environment
    original=SourceReader.narrator
    def changed(self, identity):
        person=original(self,identity)
        if identity==4698:
            person['baladwafa']='المدينة'
        return person
    monkeypatch.setattr(SourceReader,'narrator',changed)
    with pytest.raises(ValueError,match='record changed'):
        load_localization_pilot(store,settings)
    with store.connection() as c:
        assert c.execute('SELECT COUNT(*) AS n FROM localization_claims').fetchone()['n']==0


def test_reviewed_pilot_rejects_another_source_artifact(environment, monkeypatch, tmp_path):
    from hadis_web.localization import load_localization_pilot
    settings,store,_=environment
    folder=tmp_path/'references/datasets/jawami3_alkalem'
    folder.mkdir(parents=True)
    (folder/'verification.json').write_text(json.dumps({'database_sha256':'a'*64}))
    with pytest.raises(ValueError,match='snapshot changed'):
        load_localization_pilot(store,replace(settings,project_root=tmp_path))


def test_summary_cannot_be_inserted_as_a_full_source_field_translation(environment):
    from hadis_web.localization import LocalizationStore
    _,store,snapshot=environment
    with pytest.raises((ValueError,psycopg.Error)):
        claim(LocalizationStore(store),snapshot,{'id':4698,'name':'الحميدي'},
              field='name',rendering_kind='source_summary',text='Kısa kişi notu')


def test_pilot_source_correction_supersedes_old_claim_and_is_repeatable(environment, monkeypatch):
    from pathlib import Path
    from hadis_web.localization import load_localization_pilot, LocalizationStore, narrator_record
    settings,store,snapshot=environment
    load_localization_pilot(store,settings)
    with store.connection() as c:
        before=c.execute('SELECT COUNT(*) AS n FROM localization_claims').fetchone()['n']
        previous=c.execute("SELECT id FROM localization_claims cl WHERE entity_key='4698' AND field='shohra' "
                           "AND NOT EXISTS (SELECT 1 FROM localization_claims newer WHERE newer.supersedes_id=cl.id)").fetchone()['id']
    original=Path.read_text
    data=json.loads(original(Path('hadis_web/data/narrators-tr-v1.json'),encoding='utf-8'))
    entry=next(e for p in data['narrators'] if p['id']==4698 for e in p['fields'] if e['field']=='shohra')
    entry['supersedes_id']=str(previous)
    entry['rationale']+=' Yeni Türkçe kaynak bilgisi eklendi.'
    def read(path,*args,**kwargs):
        if path.name=='narrators-tr-v1.json': return json.dumps(data,ensure_ascii=False)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    load_localization_pilot(store,settings)
    load_localization_pilot(store,settings)
    record=narrator_record(SourceReader(settings).narrator(4698))
    active=LocalizationStore(store).for_records(snapshot,'narrator',{'4698':record},'tr')['4698']['fields']['shohra']
    assert len(active)==1
    assert active[0]['id'] != str(previous)
    with store.connection() as c:
        assert c.execute('SELECT COUNT(*) AS n FROM localization_claims').fetchone()['n']==before+1


def test_translation_origin_distinguishes_assistant_draft_from_published_support(environment):
    from hadis_web.localization import LocalizationStore
    _,store,snapshot=environment
    local=LocalizationStore(store)
    record={'id':8272,'karaba':'أخو عبد ربه'}
    claim(local,snapshot,record,field='karaba',text='Abdürabbih’in kardeşi.',status='needs_review',
          rendering_kind='translation',sources=[{'url':'gk45:narrator:8272','title':'GK',
          'locator':'karaba','accessed_on':'2026-10-31','translation_origin':'assistant_translation',
          'turkish_availability':'not_found_in_checked_sources'}])
    result=local.for_records(snapshot,'narrator',{'8272':record},'tr')['8272']['fields']['karaba'][0]
    assert result['translation_origin']=='assistant_translation'
    assert result['turkish_availability']=='not_found_in_checked_sources'
    assert result['status']=='needs_review'
    assert result['expert_reviewed'] is False


def test_source_supported_wording_is_not_presented_as_verbatim_book_translation(environment):
    from hadis_web.localization import LocalizationStore
    _,store,snapshot=environment
    local=LocalizationStore(store)
    record={'id':4698,'shohra':'الحميدي'}
    refs=[{'url':'https://islamansiklopedisi.org.tr/humeydi-abdullah-b-zubeyr','title':'TDV',
           'locator':'18/357','accessed_on':'2026-10-31','support_scope':'supports_full_field',
           'verbatim_quote':False,'text_origin':'assistant_authored'}]
    claim(local,snapshot,record,sources=refs)
    result=local.for_records(snapshot,'narrator',{'4698':record},'tr')['4698']['fields']['shohra'][0]
    assert result['translation_origin']=='source_supported_rendering'
    assert result['verbatim_quote'] is False
    assert result['turkish_availability']=='source_support_found'


def test_legacy_claim_without_provenance_is_unknown_not_assumed_published(environment):
    from hadis_web.localization import LocalizationStore
    _,store,snapshot=environment
    local=LocalizationStore(store)
    record={'id':4698,'shohra':'الحميدي'}
    claim(local,snapshot,record)
    result=local.for_records(snapshot,'narrator',{'4698':record},'tr')['4698']['fields']['shohra'][0]
    assert result['translation_origin']=='unknown'
    assert result['turkish_availability']=='unknown'


def test_bukhari_queue_does_not_treat_unsearched_fields_as_missing_translations(environment, tmp_path):
    from hadis_web.translation_queue import write_narrator_queue
    from hadis_web.localization import LocalizationStore, narrator_record
    settings,store,snapshot=environment
    record=narrator_record(SourceReader(settings).narrator(8272))
    claim(LocalizationStore(store),snapshot,record,field='karaba',text='Abdürabbih’in kardeşi.',
      rendering_kind='translation',status='needs_review',sources=[{'url':'gk45:narrator:8272','title':'GK',
      'locator':'karaba','accessed_on':'2026-10-31','translation_origin':'assistant_translation',
      'turkish_availability':'not_found_in_checked_sources'}])
    output=tmp_path/'queue.jsonl'
    summary=write_narrator_queue(store,settings,output)
    rows=[json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
    assert summary['narrators']==1631
    assert not ({30000,30001,30002} & {row['narrator_id'] for row in rows})
    untouched=next(row for row in rows if row['narrator_id']==4698 and row['field']=='name')
    assert untouched['stage']=='source_search_not_started'
    assert untouched['turkish_availability']=='unknown'
    draft=next(row for row in rows if row['narrator_id']==8272 and row['field']=='karaba')
    assert draft['stage']=='translation_draft_review'
    assert draft['source_text']=='أخو عبد ربه'
