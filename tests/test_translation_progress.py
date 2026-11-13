import json
import pytest
from test_localization import environment
from test_hadith_source_reviews import reviewed_store


def test_global_progress_cannot_confuse_pilot_or_candidates_with_completed_translation(environment,tmp_path):
    from hadis_web.progress import write_translation_progress
    settings,store,_=environment
    output=tmp_path/'progress.json'
    report=write_translation_progress(store,settings,output)
    assert report['source_scope']['hadith_texts']==824841
    assert report['source_scope']['books']==1400
    assert report['source_scope']['narrators']==49842
    assert report['source_scope']['distinct_critic_opinions']==129843
    assert report['source_scope']['dictionary_roots']==13331
    assert report['source_scope']['narrator_field_cells']>100000
    assert report['working']['hadith_targets_with_candidates']==0
    assert report['working']['source_compared_hadith_targets']==0
    assert report['project_complete'] is False
    assert json.loads(output.read_text(encoding='utf-8'))==report
    assert 'bibliography' in report['additional_translation_surfaces']


def test_matn_scope_comparison_is_separate_from_full_hadith_completion(reviewed_store, tmp_path):
    from hadis_web.progress import write_translation_progress
    from hadis_web.working import REQUIRED_DIMENSIONS
    store, settings, data = reviewed_store
    members = {m['role']: m['id'] for m in data['cases'][0]['members']}
    revision = store.add_alignment(members['target_arabic'], members['bridge_arabic'],
                                   members['translation'], {'method': 'test'}, scope='matn_only')
    for dimension in REQUIRED_DIMENSIONS:
        store.record_review(revision, 'fixture-reviewer', 'assistant_source_review', dimension,
                            'pass', 'Test-only matn scope, upper chains remain outside this comparison.',
                            [{'url': 'gk45:hadith:146_1', 'title': 'Fixture', 'locator': 'matn', 'accessed_on': '2026-11-04'}])
    assert store.assessment(revision)['status'] == 'source_compared'
    report = write_translation_progress(store, settings, tmp_path / 'progress.json')
    assert report['working']['text_scope_source_compared_targets'] == 1
    assert report['working']['source_compared_hadith_targets'] == 0
    assert report['project_complete'] is False


@pytest.mark.parametrize('component_kind,expected_complete', [('matn', 1), ('unclassified', 0)])
def test_component_translation_without_legacy_alignment_is_counted_as_a_candidate(reviewed_store, tmp_path, component_kind, expected_complete):
    import hashlib
    from hadis_web.hadith_components import load_component_batch
    from hadis_web.progress import write_translation_progress
    from hadis_web.source import SourceReader
    from hadis_web.working import stable_id
    from test_hadith_components import component_case, batch
    store, settings, _ = reviewed_store
    source = SourceReader(settings).hadith('146_4')['arabic']
    manifest = json.loads((settings.project_root / 'references/datasets/jawami3_alkalem/verification.json').read_text(encoding='utf-8'))
    snapshot = stable_id('snapshot', 'gk45', '4.5', manifest['database_sha256'])
    version = store.add_text(snapshot, 'gk45:ar', '146_4', 'ar', source['raw_text'], source['text'],
                             {'table': 'hadith_text', 'key': '146_4', 'book_id': '146'})
    fixture = {'cases': [{'bhid': '146_4', 'members': [{'role': 'target_arabic', 'id': str(version),
                                                     'raw_sha256': hashlib.sha256(source['raw_text'].encode()).hexdigest()}]}]}
    case = component_case(store, settings, fixture)
    case['components'][1]['kind'] = component_kind
    load_component_batch(store, settings, data=batch(case))
    report = write_translation_progress(store, settings, tmp_path / 'progress.json')
    assert report['working']['alignment_targets_with_candidates'] == 3
    assert report['working']['hadith_targets_with_candidates'] == 4
    assert report['working']['source_compared_hadith_targets'] == expected_complete
