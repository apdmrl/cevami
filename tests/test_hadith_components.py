from copy import deepcopy
import hashlib

import psycopg
import pytest

from hadis_web.source import SourceReader, open_readonly
from hadis_web.working import REQUIRED_DIMENSIONS
from test_hadith_source_reviews import reviewed_store


def component_case(store, settings, data, index=0):
    case = data['cases'][index]
    member = next(m for m in case['members'] if m['role'] == 'target_arabic')
    text = SourceReader(settings).hadith(case['bhid'])['arabic']['text']
    ref = {'url': 'gk45:hadith:' + case['bhid'], 'title': 'Test kaynak bağı',
           'locator': member['raw_sha256'], 'accessed_on': '2026-11-04'}
    reviews = [{'dimension': d, 'outcome': 'pass', 'actor_kind': 'assistant_source_review',
                'rationale': 'Only a test fixture, not production translation evidence.', 'sources': [ref]}
               for d in REQUIRED_DIMENSIONS]
    cut = len(text) // 2
    with open_readonly(settings.source_db) as c:
        sanads = [dict(r) for r in c.execute('SELECT * FROM sanad WHERE bhid=? ORDER BY sanad_id', (case['bhid'],))]
    components = []
    for kind, start, end in [('isnad', 0, cut), ('matn', cut, len(text))]:
        components.append({'kind': kind, 'ordinal': 0, 'source_bindings': [
            {'text_version_id': member['id'], 'raw_sha256': member['raw_sha256'],
             'display_sha256': hashlib.sha256(text.encode()).hexdigest(),
             'start_codepoint': start, 'end_codepoint': end}],
            'translation_text': 'Test sened çevirisi' if kind == 'isnad' else 'Test metin çevirisi',
            'origin': 'assistant_translation', 'reviews': deepcopy(reviews),
            'bibliography': {'status': 'not_applicable', 'rationale': 'Test assistant rendering has no published Turkish translator.'},
            'source_search': {'status': 'not_found_in_checked_sources', 'missing_scope': 'Test fixture gap', 'sources': [ref]},
            'source_sanad_ids': [r['sanad_id'] for r in sanads] if kind == 'isnad' else [],
            'reuses_component_id': None})
    return {'bhid': case['bhid'], 'target_version_id': member['id'],
            'target_raw_sha256': member['raw_sha256'], 'target_display_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'segmentation_version': 'test-v1', 'language': 'tr', 'components': components,
            'source_refs': [ref], 'source_sanads': sanads, 'supersedes_id': None,
            'notes_absence_review': {'outcome': 'not_applicable', 'actor_kind': 'assistant_source_review',
                                     'rationale': 'Explicit test-only absence decision.', 'sources': [ref]}}


def batch(*cases):
    return {'schema_version': 'hadith-components-v1', 'language': 'tr',
            'actor_kind': 'assistant_source_review', 'cases': list(cases)}


def test_matn_only_or_unverified_bibliography_cannot_complete_core(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    case = component_case(store, settings, data)
    for component in case['components']:
        component['bibliography']['status'] = 'unverified'
    load_component_batch(store, settings, data=batch(case))
    report = component_report(store, settings, case['bhid'])
    assert report['hadith_core_complete'] is False
    assert any('bibliography' in b for b in report['blockers'])


def test_distinct_isnads_are_not_merged_by_equal_matn(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    cases = [component_case(store, settings, data, i) for i in (0, 1)]
    result = load_component_batch(store, settings, data=batch(*cases))
    assert result['inserted'] == 2
    a, b = [component_report(store, settings, c['bhid']) for c in cases]
    assert a['set_id'] != b['set_id']
    assert a['source_sanads'] != b['source_sanads']
    assert a['hadith_core_complete'] is b['hadith_core_complete'] is True


def test_late_invalid_case_rolls_back_entire_batch_and_reimport_is_idempotent(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first, second = [component_case(store, settings, data, i) for i in (0, 1)]
    second['target_raw_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        load_component_batch(store, settings, data=batch(first, second))
    assert component_report(store, settings, first['bhid'])['items'] == []
    result = load_component_batch(store, settings, data=batch(first))
    assert result == {'cases': 1, 'inserted': 1, 'unchanged': 0}
    assert load_component_batch(store, settings, data=batch(first)) == {'cases': 1, 'inserted': 0, 'unchanged': 1}


def test_changed_source_or_segmentation_invalidates_reuse(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    load_component_batch(store, settings, data=batch(first))
    old = component_report(store, settings, first['bhid'])
    newer = deepcopy(first)
    newer['supersedes_id'] = old['set_id']
    newer['segmentation_version'] = 'changed-v2'
    reused = newer['components'][1]
    reused['origin'] = 'reused_rendering'
    reused['reuses_component_id'] = old['items'][1]['id']
    reused['reviews'].append({**deepcopy(reused['reviews'][0]), 'dimension': 'reuse_context'})
    with pytest.raises(ValueError, match='[Ss]egmentation'):
        load_component_batch(store, settings, data=batch(newer))
    newer['segmentation_version'] = first['segmentation_version']
    newer['target_raw_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        load_component_batch(store, settings, data=batch(newer))


def test_unicode_ranges_cover_source_without_loss_or_overlap(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    bad = deepcopy(first)
    bad['components'][1]['source_bindings'][0]['start_codepoint'] -= 1
    with pytest.raises(ValueError, match='[Oo]verlap'):
        load_component_batch(store, settings, data=batch(bad))
    load_component_batch(store, settings, data=batch(first))
    report = component_report(store, settings, first['bhid'])
    actual = ''.join(item['arabic_text'] for item in report['items'])
    assert actual == SourceReader(settings).hadith(first['bhid'])['arabic']['text']


def test_automated_check_cannot_approve_meaning(reviewed_store):
    from hadis_web.hadith_components import load_component_batch
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    first['components'][0]['reviews'][0]['actor_kind'] = 'automated_check'
    with pytest.raises(ValueError, match='[Aa]utomated'):
        load_component_batch(store, settings, data=batch(first))


def test_missing_chain_branch_and_unclassified_part_are_visible_blockers(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    first['components'][0]['source_sanad_ids'] = []
    first['components'][1]['kind'] = 'unclassified'
    load_component_batch(store, settings, data=batch(first))
    report = component_report(store, settings, first['bhid'])
    assert report['hadith_core_complete'] is False
    assert 'missing_sanad_coverage' in report['blockers']
    assert 'unclassified_source_part' in report['blockers']


def test_corrections_preserve_history_and_reject_stale_or_cross_target_parent(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    load_component_batch(store, settings, data=batch(first))
    root = component_report(store, settings, first['bhid'])['set_id']
    child = deepcopy(first)
    child['supersedes_id'] = root
    child['components'][1]['translation_text'] = 'Corrected test-only rendering'
    load_component_batch(store, settings, data=batch(child))
    assert component_report(store, settings, first['bhid'])['set_id'] != root
    child['components'][1]['translation_text'] = 'Competing child'
    with pytest.raises(ValueError):
        load_component_batch(store, settings, data=batch(child))
    other = component_case(store, settings, data, 1)
    other['supersedes_id'] = root
    with pytest.raises(ValueError):
        load_component_batch(store, settings, data=batch(other))
    with pytest.raises(psycopg.Error):
        with store.connection() as c:
            c.execute('DELETE FROM hadith_component_sets WHERE id=%s', (root,))


def test_reuse_cannot_launder_pending_turkish_source_search(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    first['components'][1]['source_search']['status'] = 'candidate_unverified'
    load_component_batch(store, settings, data=batch(first))
    report = component_report(store, settings, first['bhid'])
    assert report['hadith_core_complete'] is False
    child = deepcopy(first)
    child['supersedes_id'] = report['set_id']
    child['components'][1]['origin'] = 'reused_rendering'
    child['components'][1]['reuses_component_id'] = report['items'][1]['id']
    child['components'][1]['reviews'].append({**deepcopy(child['components'][1]['reviews'][0]), 'dimension': 'reuse_context'})
    with pytest.raises(ValueError, match='eligible'):
        load_component_batch(store, settings, data=batch(child))


def test_reviewed_exact_reuse_keeps_current_case_and_chain_bindings(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    first = component_case(store, settings, data)
    load_component_batch(store, settings, data=batch(first))
    old = component_report(store, settings, first['bhid'])
    child = deepcopy(first)
    child['supersedes_id'] = old['set_id']
    child['components'][1]['origin'] = 'reused_rendering'
    child['components'][1]['reuses_component_id'] = old['items'][1]['id']
    child['components'][1]['reviews'].append({**deepcopy(child['components'][1]['reviews'][0]), 'dimension': 'reuse_context'})
    load_component_batch(store, settings, data=batch(child))
    current = component_report(store, settings, first['bhid'])
    assert current['hadith_core_complete'] is True
    assert current['source_sanads'] == old['source_sanads']
    assert current['items'][1]['origin'] == 'reused_rendering'


def test_turkish_editorial_note_does_not_require_inventing_an_arabic_span(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    case = component_case(store, settings, data)
    member = next(m for m in data['cases'][0]['members'] if m['role'] == 'translation')
    with store.connection() as c:
        text = c.execute('SELECT display_text FROM text_versions WHERE id=%s', (member['id'],)).fetchone()['display_text']
    note = deepcopy(case['components'][1])
    note.update(kind='notes', origin='published_translation', translation_text=text,
                source_bindings=[{'text_version_id': member['id'], 'raw_sha256': member['raw_sha256'],
                                  'display_sha256': hashlib.sha256(text.encode()).hexdigest(),
                                  'start_codepoint': 0, 'end_codepoint': len(text)}],
                bibliography={'status': 'unverified'})
    case['components'].append(note)
    case.pop('notes_absence_review')
    load_component_batch(store, settings, data=batch(case))
    report = component_report(store, settings, case['bhid'])
    assert report['items'][2]['arabic_text'] == ''
    assert report['items'][2]['translation_text'] == text
    assert report['hadith_core_complete'] is False


def test_unicode_binding_uses_codepoints_instead_of_utf16_units():
    from hadis_web.hadith_components import _binding
    class Sources:
        def version(self, identity):
            return {'raw_sha256': 'a' * 64, 'display_text': 'أ😀ب'}
    binding = {'text_version_id': 'fixture', 'raw_sha256': 'a' * 64,
               'display_sha256': hashlib.sha256('أ😀ب'.encode()).hexdigest(),
               'start_codepoint': 1, 'end_codepoint': 2}
    assert _binding(binding, Sources())[1] == '😀'


def test_reuse_of_a_superseded_translation_cannot_restore_a_corrected_reading(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    root = component_case(store, settings, data)
    load_component_batch(store, settings, data=batch(root))
    old = component_report(store, settings, root['bhid'])
    correction = deepcopy(root)
    correction['supersedes_id'] = old['set_id']
    correction['components'][1]['translation_text'] = 'Corrected test reading'
    load_component_batch(store, settings, data=batch(correction))
    current = component_report(store, settings, root['bhid'])
    stale = deepcopy(root)
    stale['supersedes_id'] = current['set_id']
    stale['components'][1]['origin'] = 'reused_rendering'
    stale['components'][1]['reuses_component_id'] = old['items'][1]['id']
    stale['components'][1]['reviews'].append({**deepcopy(stale['components'][1]['reviews'][0]), 'dimension': 'reuse_context'})
    with pytest.raises(ValueError, match='[Ss]uperseded'):
        load_component_batch(store, settings, data=batch(stale))


def test_failed_meaning_review_is_a_visible_problem_not_a_pending_translation(reviewed_store):
    from hadis_web.hadith_components import load_component_batch, component_report
    store, settings, data = reviewed_store
    case = component_case(store, settings, data)
    case['components'][1]['reviews'][1]['outcome'] = 'fail'
    load_component_batch(store, settings, data=batch(case))
    report = component_report(store, settings, case['bhid'])
    assert report['items'][1]['status'] == 'problem_detected'
    assert report['coverage']['matn'] == 'problem_detected'
    assert report['hadith_core_complete'] is False
