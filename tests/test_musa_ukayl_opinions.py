import hashlib,json
from pathlib import Path
from fastapi.testclient import TestClient
from test_localization import environment
from hadis_web.app import create_app
from hadis_web.field_reviews import _load_datasets
from hadis_web.opinions import _load_files,load_critic_names
from hadis_web.critic_name_reviews import load_critic_name_reviews
from hadis_web.source import SourceReader
from hadis_web.localization import opinion_record,opinion_key,record_digest
FOLDER=Path(__file__).parents[1]/'hadis_web/data'
def read(name):return json.loads((FOLDER/name).read_text(encoding='utf-8'))
def entries(pid):return {e['expected_source']['alem_id']:e for e in next(p for p in read('opinions-musa-ukayl-tr-v1.json')['narrators'] if p['id']==pid)['opinions']}

def test_musa_full_rebuttal_books_and_indirect_transmission_remain_distinct():
    e=entries(7721);assert len(e)==11 and all(v['status']=='source_compared' for v in e.values())
    assert all(x in e['1011']['text'] for x in ('Takrîb','Hedyü’s-sârî','İbn Hırâş','Buhârî','çoğunluk'))
    assert 'tenkit' in e['1847']['text'] and 'sadûk' in e['1847']['text']
    assert 'ondan rivayet eden birinden' in e['2136']['text']
    assert 'es-Sikât' in e['431']['text'] and 'mutkin' in e['431']['text']
    assert 'Tesmiye' in e['583']['text'] and 'Ebî Dâvûd' in e['583']['text']
    for key in ('2757','2821'):
        assert e[key]['translation_provenance']['turkish_availability']=='source_support_found'
        assert e[key]['source_support']['hidir']['support_scope']=='supports_full_field'
    assert 'hidir' not in e['429']['source_support']

def test_ukayl_two_witness_readings_and_namesakes_stay_open_without_raw_repair():
    e=entries(5688);assert len(e)==16
    assert {k for k,v in e.items() if v['status']=='problem_detected'}=={'1268','1892','2803','466','855'}
    assert e['1268']['expected_source']['opinion']=='حافظ صاح كتاب'
    assert 'حافظ صاحب كتاب' in e['1268']['rationale'] and 'sâhib-i kitâb' in e['1268']['text']
    assert 'واليث ن وسلانة بن روح' in e['1892']['expected_source']['opinion']
    assert 'Leys b. Sa‘d' in e['1892']['text'] and 'Selâme b. Ravh' in e['1892']['text'] and 'Müştebih' in e['1892']['text']
    for key in ('1268','1892'):assert e[key]['translation_provenance']['translation_origin']=='assistant_source_corrected_rendering'
    assert 'الأنصاري' in e['2803']['expected_source']['critic'] or 'قيس' in e['2803']['expected_source']['critic']
    names={v['alem_id']:v for v in read('critic-name-reviews-tr-v7.json')['critics']}
    assert set(names)=={'2757','1635','2803','855'} and names['2803']['text']=='Yahyâ b. Saîd el-Ensârî [GK münekkit kaydı]'
    assert names['2803']['status']=='source_compared' and names['855']['status']=='problem_detected'
    assert names['2757']['expected_source']['death_date']=='227' and '125' in names['2757']['rationale']
    assert '864' in names['855']['rationale']
    batch=read('opinions-musa-ukayl-tr-v1.json');support=[v['translation_provenance']['turkish_availability'] for p in batch['narrators'] for v in p['opinions']]
    assert [support.count(k) for k in ('source_support_found','partial_support','not_found_in_checked_sources')]==[6,12,9]
    for a in batch['review_artifacts']:
        path=FOLDER.parents[2]/a['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==a['sha256']

def test_all_thirty_one_pairs_bind_source_and_roundtrip_real_api_idempotently(environment,monkeypatch):
    import hadis_web.critic_name_reviews as name_reviews
    original=name_reviews._read
    def pinned(name):
        value=original(name)
        if name=='critic-name-review-batches.json':value={**value,'files':value['files'][:7]}
        return value
    monkeypatch.setattr(name_reviews,'_read',pinned)
    settings,store,_=environment;reader=SourceReader(settings)
    _load_datasets(store,settings,[read('narrator-field-reviews-tr-v17.json'),read('narrator-field-reviews-tr-v18.json')])
    assert _load_files(store,settings,['opinions-musa-ukayl-tr-v1.json'])==dict(narrators=2,opinion_claims=27,critic_claims=0,batches=1)
    load_critic_names(store,settings);result=load_critic_name_reviews(store,settings)
    assert (result['batches'],result['critics'],result['claims'],result['claim_versions'])==(7,50,50,50)
    names={v['alem_id']:v for v in read('critic-name-reviews-tr-v7.json')['critics']};api=TestClient(create_app(settings),base_url='http://127.0.0.1');checked=set()
    for pid,count in ((7721,11),(5688,16)):
        page=api.get(f'/api/narrator/{pid}/opinions?limit=100').json();assert page['total']==len(page['items'])==count
        live={opinion_key(r):r for row in reader.critic_opinions(pid,100)['items'] if (r:=opinion_record(pid,row))}
        for entry in entries(pid).values():
            raw=entry['expected_source'];assert live[entry['key']]==raw and record_digest(raw)==entry['expected_record_sha256']
            row=next(r for r in page['items'] if str(r['alem_id'])==raw['alem_id']);assert all(row[k]==raw[k] for k in ('opinion','critic','source_occurrences'))
            pairs=[(row['localization']['fields']['opinion'][0],entry,raw)]
            if raw['alem_id'] in names:pairs.append((row['localization']['fields']['critic'][0],names[raw['alem_id']],names[raw['alem_id']]['expected_source']));checked.add(raw['alem_id'])
            for cl,expected,record in pairs:
                assert cl['text']==expected['text'] and cl['status']==expected['status'] and cl['expert_reviewed'] is False and cl['actor_kind']=='assistant_source_review'
                assert all(cl[k]==v for k,v in expected['translation_provenance'].items())
                with store.connection() as c:bound=c.execute('SELECT * FROM localization_claims WHERE id=%s',(cl['id'],)).fetchone()
                assert bound['source_record']==record and bound['source_record_sha256']==record_digest(record)
        assert api.get(f'/api/narrator/{pid}').json()['localization']['complete'] is (pid==7721)
    assert checked==set(names)
    with store.connection() as c:before={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
    _load_files(store,settings,['opinions-musa-ukayl-tr-v1.json']);load_critic_names(store,settings);load_critic_name_reviews(store,settings)
    with store.connection() as c:assert before=={str(r['id']) for r in c.execute('SELECT id FROM localization_claims')}
