import hashlib
import html
import json
from pathlib import Path
import re

from hadis_web.hadeethenc import load_hadeethenc_selection
from hadis_web.hadith_components import component_report, load_component_batch
from hadis_web.source import SourceReader
from hadis_web.working import text_identity
from test_localization import environment


def test_first10_packet_binds_all_real_sources_and_keeps_known_problems_visible(environment):
    settings, store, snapshot = environment
    path = Path(__file__).resolve().parents[1] / 'hadis_web/data/hadith-component-batches/bukhari-first10-tr-v2.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '4932da1be896777c0069b603a6f39f7ce630270151ce8b7c83a957fb64300fa8'
    packet = json.loads(path.read_text(encoding='utf-8'))
    needed = {binding['text_version_id'] for case in packet['cases'] for comp in case['components'] for binding in comp['source_bindings']}
    reader = SourceReader(settings)
    for case in packet['cases']:
        source = reader.hadith(case['bhid'])['arabic']
        identity = store.add_text(snapshot, 'gk45:ar', case['bhid'], 'ar', source['raw_text'], source['text'],
                                  {'table': 'hadith_text', 'key': case['bhid'], 'book_id': '146'})
        assert str(identity) == case['target_version_id']
    folder = settings.project_root / 'references/turkish/fawazahmed0'
    coverage = json.loads((folder / 'coverage.json').read_text(encoding='utf-8'))
    bukhari = next(c for c in coverage['collections'] if c['book'] == 'bukhari')
    for prefix in ('ara', 'tur'):
        artifact = prefix + '-bukhari.json'
        source_snapshot = store.add_snapshot('fawazahmed0', coverage['revision'], bukhari[prefix]['sha256'], artifact)
        records = json.loads((folder / artifact).read_text(encoding='utf-8'))['hadiths']
        for index, row in enumerate(records[:20]):
            raw = row['text']
            display = html.unescape(re.sub('<[^>]+>', '', raw))
            namespace = 'fawaz:' + artifact[:-5]
            _, identity, _ = text_identity(source_snapshot, namespace, str(row['hadithnumber']), raw, display)
            if str(identity) in needed:
                store.add_text(source_snapshot, namespace, str(row['hadithnumber']), 'ar' if prefix == 'ara' else 'tr', raw, display,
                               {'json_pointer': f'/hadiths/{index}', 'hadithnumber': row['hadithnumber'],
                                'arabicnumber': row.get('arabicnumber'), 'reference': row.get('reference'), 'bibliography_status': 'unverified'})
    load_hadeethenc_selection(store, settings, [66303, 10843, 10101])
    with store.connection() as c:
        stored = {str(r['id']) for r in c.execute('SELECT id FROM text_versions')}
    assert needed <= stored
    assert load_component_batch(store, settings, data=packet) == {'cases': 10, 'inserted': 10, 'unchanged': 0}
    assert load_component_batch(store, settings, data=packet) == {'cases': 10, 'inserted': 0, 'unchanged': 10}
    old_case10 = component_report(store, settings, '146_10')['set_id']
    for correction_path in sorted(path.parent.glob('bukhari-first10-tr-v[3-9].json')):
        if correction_path.name == 'bukhari-first10-tr-v3.json':
            assert hashlib.sha256(correction_path.read_bytes()).hexdigest() == '105f09acf03e3fd7db5c2367afb4a4beffc7bd144494e756ea6cc8825391754b'
        correction = json.loads(correction_path.read_text(encoding='utf-8'))
        assert load_component_batch(store, settings, data=correction) == {'cases': 10, 'inserted': 1, 'unchanged': 9}
        assert load_component_batch(store, settings, data=correction) == {'cases': 10, 'inserted': 0, 'unchanged': 10}
    reports = {case['bhid']: component_report(store, settings, case['bhid']) for case in packet['cases']}
    assert reports['146_10']['coverage']['matn'] == 'needs_review'
    question = [i for i in reports['146_10']['items'] if 'أَيُّ الْإِسْلَامِ أَفْضَلُ' in i['arabic_text']]
    assert len(question) == 1 and question[0]['kind'] == 'matn' and question[0]['status'] == 'needs_review'
    assert all('يَا رَسُولَ اللَّهِ' not in i['arabic_text'] for i in reports['146_10']['items'] if i['kind'] == 'isnad')
    assert sum(len(report['items']) for report in reports.values()) == 40
    assert reports['146_10']['set_id'] != old_case10
    with store.connection() as c:
        original = c.execute('SELECT payload FROM hadith_component_sets WHERE id=%s', (old_case10,)).fetchone()
    assert original['payload'] == packet['cases'][9]
    assert all(not report['hadith_core_complete'] and not report['expert_reviewed'] for report in reports.values())
    assert any(i['status'] == 'problem_detected' for i in reports['146_4']['items'])
    assert any(i['kind'] == 'matn' and i['status'] == 'problem_detected' for i in reports['146_6']['items'])
    assert len(reports['146_5']['source_sanads']) == 3
    assert len(reports['146_9']['source_sanads']) == 4
    assert store.counts()['review_events'] == 0
