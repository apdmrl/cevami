"""Compare existing Turkish sources across verified books, without approving them."""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata
from psycopg.types.json import Jsonb
from .importer import digest, batch, verify_artifact
from .source import open_readonly, arabic_content
from .working import stable_id, text_identity

# Identity is checked against the source catalogue, never inferred from a
# coincident hadith number. Nawawi has no matching work in this catalogue.
COLLECTIONS={
    'bukhari':('146','صحيح البخاري','محمد بن إسماعيل البخاري'),
    'muslim':('158','صحيح مسلم','مسلم بن الحجاج'),
    'abudawud':('184','سنن أبي داود','أبو داود السجستاني'),
    'tirmidhi':('195','جامع الترمذي','محمد بن عيسى الترمذي'),
    'nasai':('319','سنن النسائى الصغرى','النسائي'),
    'ibnmajah':('173','سنن ابن ماجه','ابن ماجة القزويني'),
    'malik':('19','موطأ مالك رواية يحيى الليثي','مالك بن أنس'),
}


def plain_for_comparison(raw):
    value=re.sub(r'^\$\d+\s+\d+\s*','',raw)
    value=re.sub(r'@[^@]*@','',value)
    return re.sub(r'/\d+|L\d+','',value)


def arabic_tokens(text, fold=False):
    text=unicodedata.normalize('NFKC',text)
    text=''.join(c for c in text if not unicodedata.category(c).startswith('M') and c!='ـ')
    if fold:
        text=text.translate(str.maketrans({'أ':'ا','إ':'ا','آ':'ا','ٱ':'ا','ى':'ي'}))
    return re.findall(r'[\u0621-\u064a]+',text)


def normalized_arabic(text):
    return ''.join(arabic_tokens(text,True))


def compare_arabic(gk_raw, source_text, turkish_text):
    plain=plain_for_comparison(gk_raw)
    gt,at=arabic_tokens(plain),arabic_tokens(source_text)
    gf,af=arabic_tokens(plain,True),arabic_tokens(source_text,True)
    if gt==at: category='same_arabic_tokens_without_diacritics'
    elif gf==af: category='same_tokens_after_orthographic_folding'
    else: category='equal_concatenated_letters_but_word_boundaries_differ'
    diffs=[]
    if gf!=af:
        for op,g0,g1,a0,a1 in SequenceMatcher(None,gf,af,autojunk=False).get_opcodes():
            if op!='equal':
                diffs.append({'operation':op,'gk_tokens':gf[g0:g1],'source_tokens':af[a0:a1],
                              'gk_token_range':[g0,g1],'source_token_range':[a0,a1]})
    flags=[]
    if re.search(r'<[^>]+>',turkish_text): flags.append('contains_html_markup')
    if re.search(r'tekrar|tahric|izahı|tıkla',turkish_text,re.I): flags.append('contains_editorial_or_navigation_text')
    if turkish_text.rstrip().endswith(':'): flags.append('ends_with_colon_requires_context_review')
    if '\ufffd' in turkish_text: flags.append('unicode_replacement_character')
    return {'arabic_comparison':category,'gk_token_count':len(gt),'source_token_count':len(at),
            'token_differences':diffs,'translation_flags':flags,'translation_scope':'unclassified_requires_review',
            'translation_bibliography':'unverified','translation_completeness':'unreviewed','editorial_status':'unreviewed',
            'comparison_actor':'automated_script','gk_raw_sha256':hashlib.sha256(gk_raw.encode()).hexdigest(),
            'source_arabic_sha256':hashlib.sha256(source_text.encode()).hexdigest(),
            'source_turkish_sha256':hashlib.sha256(turkish_text.encode()).hexdigest()}


def prepare_corpus(settings, collections=None):
    selected=list(COLLECTIONS) if collections is None else list(collections)
    if not selected or len(set(selected))!=len(selected) or any(k not in COLLECTIONS for k in selected):
        raise ValueError('Unknown or duplicate source collection')
    folder=settings.project_root/'references/turkish/fawazahmed0'
    coverage=json.loads((folder/'coverage.json').read_text(encoding='utf-8'))
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    verify_artifact(settings.source_db,manifest['database_sha256'])
    pins={row['book']:row for row in coverage['collections']}
    prepared=[];links=[];summaries=[]
    with open_readonly(settings.source_db) as c:
        for key in selected:
            book_id,name,author=COLLECTIONS[key]
            book=c.execute('SELECT * FROM books WHERE book_id=?',(book_id,)).fetchone()
            if not book or book['name']!=name or book['author']!=author:
                raise ValueError(f'Book identity changed for {key}')
            edition=pins[key]
            external={}
            for prefix in ('ara','tur'):
                path=folder/f'{prefix}-{key}.json'
                if digest(path)!=edition[prefix]['sha256']:
                    raise ValueError(f'Translation source checksum differs: {prefix}-{key}')
                rows=json.loads(path.read_text(encoding='utf-8'))['hadiths']
                external[prefix]={str(row['hadithnumber']):(ordinal,row) for ordinal,row in enumerate(rows)}
                if len(external[prefix])!=len(rows):
                    raise ValueError('Duplicate external source keys')
            targets=[dict(row) for row in c.execute('SELECT * FROM hadith_text WHERE book_id=? ORDER BY hadith_num',(book_id,))]
            by_text=defaultdict(list)
            for row in targets:
                norm=normalized_arabic(plain_for_comparison(row['raw_text']))
                if len(norm)>=80: by_text[norm].append(row)
            categories=Counter();collection_links=[]
            for source_key,(_,ar) in external['ara'].items():
                pair=external['tur'].get(source_key)
                if not pair or not pair[1].get('text','').strip(): continue
                norm=normalized_arabic(ar.get('text',''))
                if len(norm)<80: continue
                matches=by_text.get(norm,[])
                for row in matches:
                    evidence=compare_arabic(row['raw_text'],ar['text'],pair[1]['text'])
                    categories[evidence['arabic_comparison']]+=1
                    collection_links.append({'collection':key,'gk_book_id':book_id,'gk_bhid':row['bhid'],
                        'source_key':source_key,'source_revision':coverage['revision'],'edition':f'tur-{key}',
                        'source_arabicnumber':ar.get('arabicnumber'),'language':'tr',
                        'match_method':'normalized_full_arabic_equality','normalization_version':'research-v1',
                        'normalized_arabic_sha256':hashlib.sha256(norm.encode()).hexdigest(),
                        'gk_candidates_for_source':len(matches),'status':'candidate_requires_review',
                        'translator_verified':False,'exact_gk_variant_translation_verified':False,
                        'publication_permission_verified':False,'comparison':evidence})
            summary={'collection':key,'gk_book_id':book_id,'target_texts':len(targets),
                     'source_turkish_texts':len(external['tur']),
                     'source_turkish_nonempty':sum(bool(row.get('text','').strip()) for _,row in external['tur'].values()),
                     'candidate_pairs':len(collection_links),'targets_with_candidates':len({row['gk_bhid'] for row in collection_links}),
                     'arabic_categories':dict(categories),'approved_pairs':0}
            summaries.append(summary);links.extend(collection_links)
            prepared.append({'key':key,'book_id':book_id,'targets':targets,'external':external,'pin':edition})
    return {'collections':prepared,'links':links,'revision':coverage['revision'],
            'source_sha256':manifest['database_sha256'],
            'summary':{'collections':summaries,'target_texts':sum(r['target_texts'] for r in summaries),
                       'candidate_pairs':len(links),'targets_with_candidates':len({r['gk_bhid'] for r in links}),
                       'approved_pairs':0,'unmapped_local_collection':'nawawi — no matching work in source catalogue'}}


def load_corpus(working, settings, collections=None):
    data=prepare_corpus(settings,collections)
    snapshot=working.add_snapshot('gk45','4.5',data['source_sha256'],'jawami.db')
    units=[];versions=[];ids={}
    def collect(snap,namespace,key,language,raw,display,locator):
        unit,identity,checksum=text_identity(snap,namespace,str(key),raw,display)
        units.append((unit,namespace,str(key)))
        versions.append((identity,unit,snap,language,raw,display,checksum,Jsonb(locator)))
        ids[(namespace,str(key))]=identity
    for collection in data['collections']:
        key=collection['key']
        for row in collection['targets']:
            collect(snapshot,'gk45:ar',row['bhid'],'ar',row['raw_text'],arabic_content(row['raw_text'])['text'],
                    {'table':'hadith_text','key':row['bhid'],'book_id':collection['book_id']})
        for prefix,language in [('ara','ar'),('tur','tr')]:
            snap=working.add_snapshot('fawazahmed0',data['revision'],collection['pin'][prefix]['sha256'],f'{prefix}-{key}.json')
            for source_key,(ordinal,row) in collection['external'][prefix].items():
                text=row.get('text','')
                collect(snap,f'fawaz:{prefix}-{key}',source_key,language,text,html.unescape(re.sub(r'<[^>]+>','',text)),
                        {'json_pointer':f'/hadiths/{ordinal}','hadithnumber':row['hadithnumber'],
                         'arabicnumber':row.get('arabicnumber'),'reference':row.get('reference'),'bibliography_status':'unverified'})
    with working.connection() as c:
        batch(c,'INSERT INTO text_units VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',units)
        batch(c,'INSERT INTO text_versions(id,unit_id,snapshot_id,language,raw_text,display_text,raw_sha256,locator) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',versions)
        existing={str(row['id']) for row in c.execute('SELECT id FROM alignment_revisions')}
        cases=[];revisions=[];members=[];evidence=[];seal=[]
        for link in data['links']:
            key=link['collection'];source_key=link['source_key']
            target=ids[('gk45:ar',link['gk_bhid'])]
            bridge=ids[(f'fawaz:ara-{key}',source_key)]
            translation=ids[(f'fawaz:tur-{key}',source_key)]
            fingerprint=hashlib.sha256(json.dumps([str(target),str(bridge),str(translation),'unclassified']).encode()).hexdigest()
            case=stable_id('case',fingerprint);revision=stable_id('alignment',str(case),1)
            if str(revision) in existing: continue
            cases.append((case,fingerprint));revisions.append((revision,case,'unclassified'))
            members.extend((revision,identity,role,0) for role,identity in
                           [('target_arabic',target),('bridge_arabic',bridge),('translation',translation)])
            evidence.append((stable_id('evidence',str(revision),'initial'),revision,'research-v1-and-v2',
                             Jsonb({'v1':{k:v for k,v in link.items() if k!='comparison'},'v2':link['comparison']})))
            seal.append((revision,))
        batch(c,'INSERT INTO alignment_cases VALUES(%s,%s) ON CONFLICT DO NOTHING',cases)
        batch(c,'INSERT INTO alignment_revisions(id,case_id,revision,scope) VALUES(%s,%s,1,%s)',revisions)
        batch(c,'INSERT INTO alignment_members VALUES(%s,%s,%s,%s)',members)
        batch(c,'UPDATE alignment_revisions SET sealed=true WHERE id=%s',seal)
        batch(c,'INSERT INTO comparison_evidence VALUES(%s,%s,%s,%s)',evidence)
    output=settings.project_root/'research/corpus-review'
    output.mkdir(parents=True,exist_ok=True)
    (output/'comparison-summary.json').write_text(json.dumps(data['summary'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (output/'candidate-comparisons.jsonl').open('w',encoding='utf-8') as stream:
        for link in data['links']:stream.write(json.dumps(link,ensure_ascii=False)+'\n')
    return data['summary']
