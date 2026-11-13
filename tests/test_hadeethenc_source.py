from copy import deepcopy

import pytest

from test_localization import environment


def test_selected_official_rows_keep_arabic_versions_and_create_no_approvals(environment):
    from hadis_web.hadeethenc import load_hadeethenc_selection
    settings, store, _ = environment
    result = load_hadeethenc_selection(store, settings, [10843, 66511])
    assert set(result) == {'10843', '66511'}
    assert result['10843']['ar_version'] == 1
    assert result['66511']['ar_version'] == 2
    assert result['10843']['translation_version'] is None
    assert result['10843']['translator'] is None
    before = store.counts()
    assert load_hadeethenc_selection(store, settings, [10843, 66511]) == result
    assert store.counts() == before
    assert before['review_events'] == 0
    with store.connection() as c:
        assert c.execute('SELECT count(*) n FROM hadith_component_sets').fetchone()['n'] == 0


def test_hadeethenc_full_row_and_arabic_version_bindings_are_checked(environment):
    from hadis_web.hadeethenc import load_hadeethenc_selection, validate_hadeethenc_text
    settings, store, _ = environment
    result = load_hadeethenc_selection(store, settings, [10843])
    with store.connection() as c:
        row = c.execute('SELECT v.*,u.namespace,u.source_key,s.provider,s.revision,s.artifact_sha256,s.artifact_name '
                        'FROM text_versions v JOIN text_units u ON u.id=v.unit_id JOIN source_snapshots s ON s.id=v.snapshot_id '
                        'WHERE v.id=%s', (result['10843']['tr_version_id'],)).fetchone()
    validate_hadeethenc_text(settings, row)
    bad = deepcopy(row)
    bad['locator']['ar_version'] = 999
    with pytest.raises(ValueError):
        validate_hadeethenc_text(settings, bad)
    bad = deepcopy(row)
    bad['locator']['source_row_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        validate_hadeethenc_text(settings, bad)


def test_unknown_hadeethenc_selection_is_rejected_before_source_insert(environment):
    from hadis_web.hadeethenc import load_hadeethenc_selection
    settings, store, _ = environment
    before = store.counts()
    with pytest.raises(ValueError):
        load_hadeethenc_selection(store, settings, [10843, 999999999])
    assert store.counts() == before
