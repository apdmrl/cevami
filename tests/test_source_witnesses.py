from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import sqlite3

import pytest

from hadis_web.config import Settings
from hadis_web.working import stable_id
from hadis_web.source import arabic_content
from hadis_web.source_witnesses import SourceWitnesses, WitnessError


def material(tmp_path):
    path=tmp_path/'source.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE hadith_text(bhid TEXT,book_id TEXT,raw_text TEXT);
            CREATE TABLE narrators(id INTEGER,name TEXT);
            CREATE TABLE critics(alem_id TEXT,name TEXT);
            CREATE TABLE critic_opinions(rawy_id TEXT,alem_id TEXT,opinion TEXT);''')
        conn.execute('INSERT INTO hadith_text VALUES(?,?,?)',('146_1','146','$1 1 نص المصدر'))
        conn.execute('INSERT INTO narrators VALUES(?,?)',(9,'اسم المصدر'))
        conn.execute('INSERT INTO critics VALUES(?,?)',('7','ناقد'))
        conn.execute('INSERT INTO critic_opinions VALUES(?,?,?)',('9','7','قول المصدر'))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    folder=tmp_path/'references/datasets/jawami3_alkalem';folder.mkdir(parents=True)
    (folder/'verification.json').write_text(json.dumps({'database_sha256':digest}))
    settings=replace(Settings.load(),source_db=path,project_root=tmp_path)
    snapshot={'id':str(stable_id('snapshot','gk45','4.5',digest)),'provider':'gk45','revision':'4.5','artifact_sha256':digest,'artifact_name':'jawami.db'}
    return settings,digest,snapshot


def text_row(snapshot):
    return {**{k:v for k,v in snapshot.items() if k!='id'},'snapshot_id':snapshot['id'],
        'namespace':'gk45:ar','source_key':'146_1','language':'ar','locator':{'table':'hadith_text','key':'146_1','book_id':'146'}}


def test_gk_witness_returns_actual_source_not_self_reported_hash_and_does_not_write(tmp_path):
    settings,digest,snapshot=material(tmp_path)
    before={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in settings.source_db.parent.iterdir() if p.is_file()}
    with SourceWitnesses(settings,digest) as sources:
        assert sources.snapshot(snapshot) is True
        raw,display=sources.text(text_row(snapshot))
        assert raw=='$1 1 نص المصدر' and display==arabic_content(raw)['text']
        row=text_row(snapshot);row['language']='tr'
        with pytest.raises(WitnessError,match='text_metadata'):sources.text(row)
        row=text_row(snapshot);row['locator']['book_id']='158'
        with pytest.raises(WitnessError,match='text_locator'):sources.text(row)
    assert before=={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in settings.source_db.parent.iterdir() if p.is_file()}
    assert hashlib.sha256(settings.source_db.read_bytes()).hexdigest()==digest


def fawaz(settings):
    folder=settings.project_root/'references/turkish/fawazahmed0';folder.mkdir(parents=True)
    data={'hadiths':[{'hadithnumber':1,'arabicnumber':4,'reference':{'book':1},'text':'<b>Kaynak &amp; metin</b>'}]}
    path=folder/'tur-bukhari.json';path.write_text(json.dumps(data),encoding='utf-8')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    (folder/'coverage.json').write_text(json.dumps({'revision':'pinned','collections':[{'book':'bukhari','tur':{'sha256':digest}}]}))
    snapshot={'id':str(stable_id('snapshot','fawazahmed0','pinned',digest)),'provider':'fawazahmed0','revision':'pinned','artifact_sha256':digest,'artifact_name':path.name}
    row={**{k:v for k,v in snapshot.items() if k!='id'},'snapshot_id':snapshot['id'],'namespace':'fawaz:tur-bukhari','source_key':'1','language':'tr',
        'locator':{'json_pointer':'/hadiths/0','hadithnumber':1,'arabicnumber':4,'reference':{'book':1},'bibliography_status':'unverified'}}
    return path,snapshot,row


def test_external_artifact_pointer_identity_metadata_and_cache(tmp_path):
    settings,digest,_=material(tmp_path);path,snapshot,row=fawaz(settings)
    with SourceWitnesses(settings,digest) as sources:
        assert sources.snapshot(snapshot)
        assert sources.text(row)==('<b>Kaynak &amp; metin</b>','Kaynak & metin')
        assert len(sources.fingerprints)==2
        wrong=deepcopy(row);wrong['locator']['json_pointer']='/hadiths/2'
        with pytest.raises(WitnessError,match='text_locator'):sources.text(wrong)
        wrong=deepcopy(row);wrong['locator']['reference']={'book':2}
        with pytest.raises(WitnessError,match='text_locator'):sources.text(wrong)
        wrong=deepcopy(row);wrong['source_key']='2'
        with pytest.raises(WitnessError,match='text_metadata'):sources.text(wrong)
    path.write_text('{}')
    with SourceWitnesses(settings,digest) as sources:
        with pytest.raises(WitnessError,match='artifact_hash'):sources.snapshot(snapshot)


@pytest.mark.parametrize('name',['../settings.json','/private.json','tur-../../private.json'])
def test_provider_artifact_path_is_never_followed(tmp_path,name):
    settings,digest,_=material(tmp_path)
    snap={'id':str(stable_id('snapshot','fawazahmed0','pinned',digest)),'provider':'fawazahmed0','revision':'pinned','artifact_sha256':digest,'artifact_name':name}
    with SourceWitnesses(settings,digest) as sources:
        with pytest.raises(WitnessError,match='artifact_name'):sources.snapshot(snap)


def test_snapshot_identity_and_unknown_provider_are_not_approved(tmp_path):
    settings,digest,snapshot=material(tmp_path)
    with SourceWitnesses(settings,digest) as sources:
        wrong={**snapshot,'id':'00000000-0000-0000-0000-000000000000'}
        with pytest.raises(WitnessError,match='snapshot_identity'):sources.snapshot(wrong)
        wrong={**snapshot,'provider':'unknown'};wrong['id']=str(stable_id('snapshot','unknown','4.5',digest))
        with pytest.raises(WitnessError,match='unsupported_provider'):sources.snapshot(wrong)


def test_missing_historical_dictionary_is_an_explicit_unverified_warning(tmp_path):
    settings,digest,_=material(tmp_path)
    folder=settings.project_root/'app/hadis_web/data';folder.mkdir(parents=True)
    (folder/'controlled-terms-tr-v1.json').write_text(json.dumps({'revision':'current','terms':[]}))
    revision='controlled-terms-tr-v1'
    snap={'id':str(stable_id('snapshot','controlled-vocabulary',revision,digest)),'provider':'controlled-vocabulary','revision':revision,'artifact_sha256':digest,'artifact_name':'controlled-terms-tr-v1.json'}
    with SourceWitnesses(settings,digest) as sources:
        assert sources.snapshot(snap) is False
        assert sources.warnings[0]['code']=='historical_artifact_unavailable'
        assert sources.claim({'entity_type':'controlled_term','entity_key':'x','source_record':{}},snap) is None


def test_registered_historical_dictionary_bytes_are_used_for_its_own_claims(tmp_path):
    settings,digest,_=material(tmp_path)
    folder=settings.project_root/'app/hadis_web/data';folder.mkdir(parents=True)
    (folder/'controlled-terms-tr-v1.json').write_text(json.dumps({'revision':'current','terms':[]}))
    record={'key':'old-term','value':'لفظ','allowed_fields':['wasf_rotba']}
    revision='controlled-terms-tr-v1'
    path=folder/'controlled-terms-tr-v1-research.json';path.write_text(json.dumps({'revision':revision,'terms':[record]}))
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    snap={'id':str(stable_id('snapshot','controlled-vocabulary',revision,checksum)),'provider':'controlled-vocabulary','revision':revision,'artifact_sha256':checksum,'artifact_name':'controlled-terms-tr-v1.json'}
    with SourceWitnesses(settings,digest) as sources:
        assert sources.snapshot(snap) is True
        assert sources.claim({'entity_type':'controlled_term','entity_key':'old-term','source_record':{}},snap)==record
        assert not sources.warnings


def test_json_source_is_the_exact_verified_bytes_and_later_changes_are_reported(tmp_path):
    settings,digest,_=material(tmp_path);path,snapshot,row=fawaz(settings)
    with SourceWitnesses(settings,digest) as sources:
        sources.snapshot(snapshot)
        data=json.loads(path.read_text());data['hadiths'][0]['text']='changed after hash'
        path.write_text(json.dumps(data))
        assert sources.text(row)==('<b>Kaynak &amp; metin</b>','Kaynak & metin')
        with pytest.raises(WitnessError,match='artifact_changed_during_audit'):sources.verify_unchanged()


def test_claims_bind_full_narrator_critic_and_exact_opinion_record(tmp_path):
    settings,digest,snapshot=material(tmp_path)
    with SourceWitnesses(settings,digest) as sources:
        assert sources.claim({'entity_type':'narrator','entity_key':'9','source_record':{}},snapshot)=={'id':9,'name':'اسم المصدر'}
        assert sources.claim({'entity_type':'critic','entity_key':'7','source_record':{}},snapshot)=={'alem_id':'7','name':'ناقد'}
        record={'narrator_id':9,'alem_id':'7','critic':'ناقد','opinion':'قول المصدر','source_occurrences':1}
        assert sources.claim({'entity_type':'critic_opinion','entity_key':'unused','source_record':record},snapshot)==record


@pytest.mark.parametrize('arabic_version',[2,1])
def test_hadeethenc_binds_the_archived_full_row_and_arabic_version(tmp_path,arabic_version):
    from hadis_web.hadeethenc import ARCHIVE,REVISION,_locator
    settings,digest,_=material(tmp_path)
    folder=settings.project_root/'references/turkish'/ARCHIVE;folder.mkdir(parents=True)
    manifest=[];raws={}
    for language in ('ar','tr'):
        path=folder/(language+'.sqlite')
        column='version' if language=='ar' else 'ar_version'
        with sqlite3.connect(path) as conn:
            conn.execute(f'CREATE TABLE hadeeths(id INTEGER,{column} INTEGER,hadeeth TEXT)')
            conn.execute('INSERT INTO hadeeths VALUES(?,?,?)',(1,arabic_version if language=='ar' else 2,'أصل' if language=='ar' else 'Kaynak'))
        raws[language]=hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append({'language':language,'sha256':raws[language]})
    (folder/'schema-manifest.json').write_text(json.dumps(manifest))
    snap={'id':str(stable_id('snapshot','hadeethenc',REVISION,raws['tr'])),'provider':'hadeethenc','revision':REVISION,
          'artifact_sha256':raws['tr'],'artifact_name':ARCHIVE+'/tr.sqlite'}
    row={**{k:v for k,v in snap.items() if k!='id'},'snapshot_id':snap['id'],'namespace':'hadeethenc:tr:hadeeth',
        'source_key':'1','language':'tr','raw_text':'Kaynak','display_text':'Kaynak',
        'locator':_locator({'id':1,'ar_version':2,'hadeeth':'Kaynak'},'tr')}
    with SourceWitnesses(settings,digest) as sources:
        if arabic_version!=2:
            with pytest.raises(ValueError):sources.text(row)
            return
        assert sources.text(row)==('Kaynak','Kaynak')
        wrong={**row,'source_key':'01'}
        with pytest.raises(ValueError):sources.text(wrong)
        row['locator']['ar_version']=1
        with pytest.raises(ValueError):sources.text(row)


@pytest.mark.parametrize('revision',['controlled-terms-tr-v2-ravi-scope','unknown'])
def test_current_or_unknown_dictionary_cannot_be_downgraded_to_historical_warning(tmp_path,revision):
    settings,digest,_=material(tmp_path)
    snap={'id':str(stable_id('snapshot','controlled-vocabulary',revision,digest)),'provider':'controlled-vocabulary',
        'revision':revision,'artifact_sha256':digest,'artifact_name':'controlled-terms-tr-v1.json'}
    with SourceWitnesses(settings,digest) as sources:
        with pytest.raises((WitnessError,FileNotFoundError)):sources.snapshot(snap)


def test_search_text_is_bound_to_pinned_translation_and_matching_arabic_witness(tmp_path):
    settings,_,_=material(tmp_path)
    arabic=' '.join(['نص المصدر العربي الثابت']*8)
    other=' '.join(['متن مختلف لا يطابق الشاهد']*8)
    with sqlite3.connect(settings.source_db) as conn:
        conn.execute('ALTER TABLE hadith_text ADD COLUMN hadith_num INTEGER')
        conn.execute('CREATE TABLE books(book_id TEXT,name TEXT)');conn.execute('INSERT INTO books VALUES(?,?)',('146','مصدر'))
        conn.execute('UPDATE hadith_text SET raw_text=?,hadith_num=1',(arabic,))
        conn.execute('INSERT INTO hadith_text VALUES(?,?,?,?)',('146_2','146',other,2))
    digest=hashlib.sha256(settings.source_db.read_bytes()).hexdigest()
    (settings.project_root/'references/datasets/jawami3_alkalem/verification.json').write_text(json.dumps({'database_sha256':digest}))
    tr=settings.project_root/'references/turkish/fawazahmed0';en=settings.project_root/'references/search/fawazahmed0-20261104'
    tr.mkdir(parents=True);en.mkdir(parents=True)
    def document(folder,name,value):
        path=folder/name;path.write_text(json.dumps({'hadiths':[{'hadithnumber':1,'text':value}]}))
        return hashlib.sha256(path.read_bytes()).hexdigest()
    ar_sha=document(tr,'ara-bukhari.json',arabic);tr_sha=document(tr,'tur-bukhari.json','Published Turkish fixture')
    en_sha=document(en,'eng-bukhari.json','Published English fixture')
    (tr/'coverage.json').write_text(json.dumps({'revision':'pinned','collections':[{'book':'bukhari','ara':{'sha256':ar_sha},'tur':{'sha256':tr_sha}}]}))
    (en/'manifest.json').write_text(json.dumps({'revision':'pinned','sources':[{'edition':'eng-bukhari','sha256':en_sha}]}))
    row={'bhid':'146_1','book_id':'146','book_name':'مصدر','hadith_num':1,'language':'en','text':'Published English fixture',
         'edition':'eng-bukhari','source_key':'1','revision':'pinned','target_raw_sha256':hashlib.sha256(arabic.encode()).hexdigest(),
         'source_url':'https://github.com/fawazahmed0/hadith-api/blob/pinned/editions/eng-bukhari.json'}
    with SourceWitnesses(settings,digest) as sources:
        assert sources.search_document(row) is True
        wrong={**row,'text':'Self-consistent but wrong indexed translation'}
        with pytest.raises(WitnessError,match='search_source_content'):sources.search_document(wrong)
        wrong={**row,'bhid':'146_2','hadith_num':2,'target_raw_sha256':hashlib.sha256(other.encode()).hexdigest()}
        with pytest.raises(WitnessError,match='search_arabic_binding'):sources.search_document(wrong)
