"""Resolve audit witnesses from registered local artifacts, without writing them."""
from contextlib import ExitStack
import hashlib
import html
import json
import re

from .source import open_readonly, arabic_content
from .working import stable_id


class WitnessError(ValueError):
    """A public audit code, never an exception containing credentials or raw SQL."""


def digest_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


class SourceWitnesses:
    def __init__(self,settings,source_sha):
        self.settings,self.source_sha=settings,source_sha
        self.fingerprints={'gk45:jawami.db':source_sha}
        self.warnings=[];self._snapshots={};self._hashes={};self._documents={};self._contents={};self._control_paths={};self.artifact_files={};self._editions={}

    def __enter__(self):
        self.stack=ExitStack()
        try:
            self.source=self.stack.enter_context(open_readonly(self.settings.source_db))
            self.manifest=json.loads((self.settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text(encoding='utf-8'))
            return self
        except Exception:
            self.stack.close();raise

    def __exit__(self,*args):
        self.stack.close()

    def _json(self,path):
        if path not in self._documents:
            if path not in self._contents:self._contents[path]=path.read_bytes()
            self._documents[path]=json.loads(self._contents[path])
        return self._documents[path]

    def _verify(self,path,expected,label):
        if path not in self._hashes:
            if path.suffix=='.json':
                if path not in self._contents:self._contents[path]=path.read_bytes()
                self._hashes[path]=hashlib.sha256(self._contents[path]).hexdigest()
            else:self._hashes[path]=digest_file(path)
        actual=self._hashes[path];self.fingerprints[label]=actual
        if actual!=expected:raise WitnessError('artifact_hash')
        self.artifact_files[label]=path.relative_to(self.settings.project_root).as_posix()

    def verify_unchanged(self):
        for path,checksum in self._hashes.items():
            if digest_file(path)!=checksum:raise WitnessError('artifact_changed_during_audit')

    def snapshot(self,row):
        signature=tuple(row[key] for key in ('provider','revision','artifact_sha256','artifact_name'))
        identity=str(row['id']);provider,revision,checksum,name=signature
        if identity!=str(stable_id('snapshot',provider,revision,checksum)):
            raise WitnessError('snapshot_identity')
        if identity in self._snapshots:
            old,verified=self._snapshots[identity]
            if signature!=old:raise WitnessError('snapshot_metadata')
            return verified
        verified=True
        if provider=='gk45':
            if revision!='4.5' or name!='jawami.db' or checksum!=self.manifest['database_sha256'] or checksum!=self.source_sha:
                raise WitnessError('source_snapshot')
        elif provider=='fawazahmed0':
            match=re.fullmatch(r'(ara|tur)-(bukhari|muslim|abudawud|nasai|tirmidhi|ibnmajah|malik)\.json',name)
            if not match:raise WitnessError('artifact_name')
            folder=self.settings.project_root/'references/turkish/fawazahmed0'
            coverage=self._json(folder/'coverage.json')
            collection=next((c for c in coverage['collections'] if c['book']==match[2]),None)
            if coverage['revision']!=revision or collection is None or collection[match[1]]['sha256']!=checksum:
                raise WitnessError('artifact_manifest')
            self._verify(folder/name,checksum,provider+':'+name)
        elif provider=='hadeethenc':
            from .hadeethenc import ARCHIVE,REVISION
            match=re.fullmatch(re.escape(ARCHIVE)+r'/(ar|tr)\.sqlite',name)
            if not match or revision!=REVISION:raise WitnessError('artifact_name')
            folder=self.settings.project_root/'references/turkish'/ARCHIVE
            entry=next((r for r in self._json(folder/'schema-manifest.json') if r['language']==match[1]),None)
            if entry is None or entry['sha256']!=checksum:raise WitnessError('artifact_manifest')
            self._verify(folder/(match[1]+'.sqlite'),checksum,provider+':'+name)
        elif provider=='controlled-vocabulary':
            if name!='controlled-terms-tr-v1.json':raise WitnessError('artifact_name')
            folder=self.settings.project_root/'app/hadis_web/data'
            registry={'controlled-terms-tr-v1':'controlled-terms-tr-v1-research.json',
                      'controlled-terms-tr-v2-ravi-scope':'controlled-terms-tr-v1.json'}
            if revision not in registry:raise WitnessError('controlled_revision')
            path=folder/registry[revision]
            if not path.is_file() and revision=='controlled-terms-tr-v1':
                self.warnings.append({'code':'historical_artifact_unavailable','snapshot_id':identity,'provider':provider,'revision':revision})
                verified=False
            else:
                if self._json(path).get('revision')!=revision:raise WitnessError('controlled_revision')
                self._verify(path,checksum,provider+':'+revision);self._control_paths[identity]=path
        else:raise WitnessError('unsupported_provider')
        self._snapshots[identity]=(signature,verified)
        return verified

    def text(self,row):
        snapshot={key:row[key] for key in ('provider','revision','artifact_sha256','artifact_name')}
        snapshot['id']=row['snapshot_id']
        if not self.snapshot(snapshot):raise WitnessError('unverified_text_source')
        provider=row['provider'];locator=row['locator']
        if provider=='gk45':
            if row['namespace']!='gk45:ar' or row['language']!='ar':raise WitnessError('text_metadata')
            source=self.source.execute('SELECT * FROM hadith_text WHERE bhid=?',(row['source_key'],)).fetchone()
            if source is None:raise WitnessError('text_source_missing')
            if locator!={'table':'hadith_text','key':row['source_key'],'book_id':source['book_id']}:
                raise WitnessError('text_locator')
            return source['raw_text'],arabic_content(source['raw_text'])['text']
        if provider=='fawazahmed0':
            name=row['artifact_name'];language='ar' if name.startswith('ara-') else 'tr'
            if row['namespace']!='fawaz:'+name[:-5] or row['language']!=language:raise WitnessError('text_metadata')
            entries=self._json(self.settings.project_root/'references/turkish/fawazahmed0'/name)['hadiths']
            pointer=locator.get('json_pointer','')
            if not re.fullmatch(r'/hadiths/\d+',pointer):raise WitnessError('text_locator')
            ordinal=int(pointer.rsplit('/',1)[1])
            if ordinal>=len(entries):raise WitnessError('text_locator')
            source=entries[ordinal]
            if str(source['hadithnumber'])!=row['source_key']:raise WitnessError('text_metadata')
            expected={'json_pointer':pointer,'hadithnumber':source['hadithnumber'],'arabicnumber':source.get('arabicnumber'),
                      'reference':source.get('reference'),'bibliography_status':'unverified'}
            if locator!=expected:raise WitnessError('text_locator')
            raw=source['text'];return raw,html.unescape(re.sub(r'<[^>]+>','',raw))
        if provider=='hadeethenc':
            from .hadeethenc import validate_hadeethenc_text,_row
            key=row['source_key']
            if not key.isdigit() or str(int(key))!=key or int(key)<=0:raise WitnessError('text_metadata')
            validate_hadeethenc_text(self.settings,row)
            if row['language']=='tr':
                _row(self.settings,'ar',int(key),row['locator']['ar_version'])
            return row['raw_text'],row['display_text']
        raise WitnessError('unsupported_text_provider')

    def _edition(self,path,checksum):
        self._verify(path,checksum,'fawazahmed0:'+path.name)
        if path not in self._editions:
            rows=self._json(path)['hadiths']
            entries={str(r['hadithnumber']):r for r in rows}
            if len(entries)!=len(rows):raise WitnessError('ambiguous_source_key')
            self._editions[path]=entries
        return self._editions[path]

    def search_document(self,row):
        from .corpus import COLLECTIONS,arabic_tokens,plain_for_comparison
        match=re.fullmatch(r'(tur|eng)-(bukhari|muslim|abudawud|nasai|tirmidhi|ibnmajah|malik)',row['edition'])
        if not match:raise WitnessError('search_edition')
        prefix,book=match.groups()
        if row['language']!=('tr' if prefix=='tur' else 'en') or row['book_id']!=COLLECTIONS[book][0]:raise WitnessError('search_metadata')
        tr_folder=self.settings.project_root/'references/turkish/fawazahmed0'
        en_folder=self.settings.project_root/'references/search/fawazahmed0-20261104'
        coverage=self._json(tr_folder/'coverage.json')
        collection=next((c for c in coverage['collections'] if c['book']==book),None)
        if collection is None or row['revision']!=coverage['revision']:raise WitnessError('search_revision')
        if prefix=='eng':
            manifest=self._json(en_folder/'manifest.json')
            pin=next((p for p in manifest['sources'] if p['edition']==row['edition']),None)
            if manifest['revision']!=row['revision'] or pin is None:raise WitnessError('search_revision')
            folder,checksum=en_folder,pin['sha256']
        else:folder,checksum=tr_folder,collection['tur']['sha256']
        translated=self._edition(folder/(row['edition']+'.json'),checksum).get(row['source_key'])
        arabic=self._edition(tr_folder/('ara-'+book+'.json'),collection['ara']['sha256']).get(row['source_key'])
        if translated is None or arabic is None:raise WitnessError('search_source_key')
        if translated['text']!=row['text']:raise WitnessError('search_source_content')
        expected_url=f"https://github.com/fawazahmed0/hadith-api/blob/{row['revision']}/editions/{row['edition']}.json"
        if row['source_url']!=expected_url:raise WitnessError('search_source_url')
        target=self.source.execute('''SELECT t.*,b.name AS book_name FROM hadith_text t JOIN books b ON b.book_id=t.book_id WHERE bhid=?''',(row['bhid'],)).fetchone()
        if (target is None or target['book_id']!=row['book_id'] or target['book_name']!=row['book_name']
                or target['hadith_num']!=row['hadith_num'] or hashlib.sha256(target['raw_text'].encode()).hexdigest()!=row['target_raw_sha256']):
            raise WitnessError('search_target_metadata')
        tokens=tuple(arabic_tokens(plain_for_comparison(target['raw_text']),fold=True))
        if len(''.join(tokens))<80 or tokens!=tuple(arabic_tokens(arabic['text'],fold=True)):raise WitnessError('search_arabic_binding')
        return True

    def claim(self,row,snapshot):
        if not self.snapshot(snapshot):return None
        kind,key=row['entity_type'],row['entity_key']
        if kind=='controlled_term' and snapshot['provider']=='controlled-vocabulary':
            path=self._control_paths[str(snapshot['id'])]
            term=next((t for t in self._json(path)['terms'] if t['key']==key),None)
            if term is None:raise WitnessError('claim_source_missing')
            return {k:term[k] for k in ('key','value','allowed_fields')}
        if snapshot['provider']!='gk45':raise WitnessError('claim_snapshot')
        if kind in ('narrator','critic'):
            table,column=('narrators','id') if kind=='narrator' else ('critics','alem_id')
            record=self.source.execute(f'SELECT * FROM {table} WHERE {column}=?',(key,)).fetchone()
            if record is None:raise WitnessError('claim_source_missing')
            return dict(record)
        if kind=='critic_opinion':
            stored=row['source_record']
            record=self.source.execute('''SELECT o.alem_id,cr.name AS critic,o.opinion,count(*) AS source_occurrences
                FROM critic_opinions o LEFT JOIN critics cr ON cr.alem_id=o.alem_id
                WHERE o.rawy_id=? AND o.alem_id=? AND o.opinion=? GROUP BY o.alem_id,cr.name,o.opinion''',
                (str(stored['narrator_id']),stored['alem_id'],stored['opinion'])).fetchone()
            if record is None:raise WitnessError('claim_source_missing')
            return {'narrator_id':int(stored['narrator_id']),**dict(record)}
        raise WitnessError('unsupported_claim_type')
