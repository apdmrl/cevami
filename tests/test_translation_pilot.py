from pathlib import Path

import pytest

from hadis_web.config import Settings
from test_hadith_source_reviews import reviewed_store


def test_selection_is_numeric_stable_and_contains_1000_existing_ids():
    from hadis_web.translation_pilot import select_pilot_bhids
    settings = Settings.load()
    selected = select_pilot_bhids(settings.source_db)
    assert len(selected) == len(set(selected)) == 1000
    assert selected == select_pilot_bhids(settings.source_db)
    assert selected.index('146_2') < selected.index('146_10')
    assert selected[:3] == ['146_1', '146_2', '146_3']
    with pytest.raises(ValueError):
        select_pilot_bhids(settings.source_db, limit=0)


def test_multiple_candidates_and_split_case_stay_unresolved(reviewed_store):
    from hadis_web.translation_pilot import build_pilot_inventory
    store, settings, data = reviewed_store
    members = {m['role']: m['id'] for m in data['cases'][0]['members']}
    store.add_alignment(members['target_arabic'], members['bridge_arabic'],
                        members['translation'], {'method': 'test-alternative'}, scope='matn_only')
    result = build_pilot_inventory(store, settings)
    rows = {row['bhid']: row for row in result['items']}
    assert len(result['selection']['bhids']) == len(rows) == 1000
    assert len(rows['146_1']['candidate_revision_ids']) == 2
    assert 'multiple_candidates' in rows['146_1']['risk_flags']
    assert 'possible_split_or_merge' in rows['146_3']['risk_flags']
    assert rows['146_1']['bibliography_status'] == 'unverified'
    assert rows['146_3']['component_coverage']['isnad'] == 'unknown'
    assert result['summary']['fully_compared_targets'] == 0
    assert all(row['status'] == 'requires_review' for row in rows.values())


def test_inventory_writes_no_working_or_source_rows(reviewed_store):
    from hadis_web.translation_pilot import build_pilot_inventory, working_state
    store, settings, _ = reviewed_store
    before = working_state(store)
    source_stat = settings.source_db.stat()
    build_pilot_inventory(store, settings, limit=10)
    assert working_state(store) == before
    after = settings.source_db.stat()
    assert (source_stat.st_size, source_stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
