import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets,load_field_review_batches
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import NARRATOR_FIELDS,opinion_record,opinion_key,record_digest,load_localization_pilot
FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(n):return json.loads((FOLDER/n).read_text(encoding='utf-8'))
def fields():return {e['field']:e for e in read('narrator-field-reviews-tr-v28.json')['people'][0]['fields']}
def opinions():return {e['expected_source']['alem_id']:e for e in read('opinions-ebu-usame-tr-v1.json')['narrators'][0]['opinions']}

def test_nine_fields_keep_mawla_nisbas_and_original_dates():
    f=fields();assert len(f)==9 and all(e['status']=='source_compared' for e in f.values())
    assert f['name']['text']=='Hammâd b. Üsâme b. Zeyd.'
    assert f['mawaaly']['text']=='Benî Hâşim’in mevlâsı.' and 'biyolojik' in f['mawaaly']['rationale']
    assert f['nasab']['text']=='Kureşî; Kûfî.'
    support=[v['translation_provenance']['turkish_availability'] for v in f.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[8,1,0]
    raw=read('narrator-field-reviews-tr-v28.json')['people'][0]['expected_source'];assert (raw['date_of_birth'],raw['death_year'],raw['age'],raw['tadleese'],raw['e5telat'])==('121','201',80,0,0)


def test_twelve_opinions_keep_all_books_qualifications_exclamation_and_nearly_never():
    e=opinions();assert len(e)==12 and all(v['status']=='source_compared' for v in e.values())
    assert all(x.casefold() in e['1011']['text'].casefold() for x in ('Takrîb','bazen tedlîs','son döneminde','başkalarının kitaplarından','Hedyü’s-sârî','mesnetsiz'))
    assert all(x.casefold() in e['2463']['text'].casefold() for x in ('sika','me’mûn','çok hadis','tedlîs yapar','açıklardı'))
    assert all(x.casefold() in e['751']['text'].casefold() for x in ('ne kadar','neredeyse hata yapmazdı','kitabı doğru','zabt','zeki','sadûk')) and e['751']['text'].count('Başka')==2
    assert 'hiç hata' not in e['751']['text'] and 'Hıdır' in e['751']['rationale']
    assert all(x.casefold() in e['1264']['text'].casefold() for x in ('Başka','es-Sikât','Sebt'))
    assert all(x in e['342']['text'] for x in ('es-Sünenü’l-kübrâ','Ma‘rifetü’s-sünen ve’l-âsâr'))
    assert 'es-Sikât' in e['431']['text'] and 'el-Müstedrek' in e['527']['text']
    assert 'gazetecilik' in e['1268']['rationale'] and 'mezhep' in e['1268']['rationale'] and 'hikmet' in e['779']['text']
    support=[v['translation_provenance']['turkish_availability'] for v in e.values()]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[0,10,2]


def test_twenty_one_full_pairs_api_provenance_all_old_names_and_repeat_ids(environment):
    settings,store,_=environment;fb=read('narrator-field-reviews-tr-v28.json');ob=read('opinions-ebu-usame-tr-v1.json')
    assert _load_datasets(store,settings,[fb])==dict(people=1,claims=9)
    assert _load_files(store,settings,['opinions-ebu-usame-tr-v1.json'])==dict(narrators=1,opinion_claims=12,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings);assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(14,63,63,63)
    reader=SourceReader(settings);raw=reader.narrator_records([2484])['2484'];p=fb['people'][0];assert raw==p['expected_source'] and record_digest(raw)==p['expected_record_sha256']
    assert {e['field'] for e in p['fields']}=={k for k in NARRATOR_FIELDS if raw.get(k)}
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/2484').json();pairs=[]
    for e in p['fields']:
        assert profile[e['field']]==e['expected_arabic'];pairs.append((profile['localization']['fields'][e['field']][0],e,raw))
    page=api.get('/api/narrator/2484/opinions?limit=100').json();assert page['total']==len(page['items'])==12
    live={opinion_key(r):r for row in reader.critic_opinions(2484,100)['items'] if (r:=opinion_record(2484,row))}
    for e in ob['narrators'][0]['opinions']:
        record=e['expected_source'];assert live[e['key']]==record and record_digest(record)==e['expected_record_sha256']
        row=next(r for r in page['items'] if str(r['alem_id'])==record['alem_id']);assert all(row[k]==record[k] for k in ('critic','opinion','source_occurrences')) and row['source_occurrences']==2
        pairs.append((row['localization']['fields']['opinion'][0],e,record))
        assert len(row['localization']['fields']['critic'])==1 and row['localization']['fields']['critic'][0]['status']=='source_compared'
    assert len(pairs)==21 and profile['localization']['complete'] is True
    for cl,e,record in pairs:
        assert cl['text']==e['text'] and cl['status']==e['status'] and cl['rationale']==e['rationale'] and cl['actor_kind']=='assistant_source_review' and cl['expert_reviewed'] is False
        assert all(cl[k]==v for k,v in e['translation_provenance'].items())
        with store.connection() as c:bound=c.execute('SELECT source_record,source_record_sha256,supersedes_id FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
        assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record) and bound['supersedes_id'] is None
    for b in (fb,ob):
        for a in b['review_artifacts']:assert hashlib.sha256((FOLDER.parents[2]/a['path']).read_bytes()).hexdigest()==a['sha256']
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_datasets(store,settings,[fb]);_load_files(store,settings,['opinions-ebu-usame-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}

def test_whole_registry_keeps_all_old_pilot_successors_and_nine_new_heads(environment):
    new=read('narrator-field-reviews-tr-v28.json');settings,store,_=environment;load_localization_pilot(store,settings);result=load_field_review_batches(store,settings)
    assert (result['batches'],result['people'],result['claims'],result['claim_versions'])==(28,106,974,996)
    api=TestClient(create_app(settings),base_url='http://127.0.0.1');profile=api.get('/api/narrator/2484').json()
    for e in new['people'][0]['fields']:
        claims=profile['localization']['fields'][e['field']];assert len(claims)==1 and claims[0]['text']==e['text']
    adem=api.get('/api/narrator/2').json()
    with store.connection() as c:
        for field,parent in {'shohra':'44f1c191-a5dc-5e59-a83c-a78a6e92fabd','wasf_rotba':'7b44ede7-7d6c-5b86-b31c-39093f61e645'}.items():
            claims=adem['localization']['fields'][field];assert len(claims)==1
            row=c.execute('SELECT supersedes_id FROM localization_claims WHERE id=%s',(claims[0]['id'],)).fetchone();assert str(row['supersedes_id'])==parent
