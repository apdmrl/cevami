import uuid
import pytest
import psycopg
from psycopg import sql

from hadis_web.config import Settings
from hadis_web.working import WorkingStore


@pytest.fixture
def store():
    dsn = Settings.load().postgres_dsn
    assert dsn, 'A real local PostgreSQL database is required.'
    schema = 'test_' + uuid.uuid4().hex
    value = WorkingStore(dsn, schema)
    yield value
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))


def test_repeated_import_preserves_distinct_keys_and_is_idempotent(store):
    store.migrate()
    snapshot = store.add_snapshot('test-source', 'r1', 'a' * 64, 'fixture.json')
    first = store.add_text(snapshot, 'fixture:ar', '1', 'ar', 'نص واحد', 'نص واحد', {'key': '1'})
    repeated = store.add_text(snapshot, 'fixture:ar', '1', 'ar', 'نص واحد', 'نص واحد', {'key': '1'})
    second = store.add_text(snapshot, 'fixture:ar', '2', 'ar', 'نص واحد', 'نص واحد', {'key': '2'})
    assert first == repeated
    assert first != second
    assert store.counts()['text_versions'] == 2


def test_source_text_version_cannot_be_rewritten(store):
    store.migrate()
    snapshot = store.add_snapshot('test-source', 'r1', 'a' * 64, 'fixture.json')
    identity = store.add_text(snapshot, 'fixture:ar', '1', 'ar', 'الأصل', 'الأصل', {})
    with pytest.raises(psycopg.errors.RaiseException):
        with store.connection() as c:
            c.execute('UPDATE text_versions SET raw_text=%s WHERE id=%s', ('تعديل', identity))


def new_case(store, key='1', scope='matn'):
    snapshot = store.add_snapshot('test-source', 'r1', 'a' * 64, 'fixture.json')
    target = store.add_text(snapshot, 'gk:ar', key, 'ar', 'الأصل', 'الأصل', {})
    bridge = store.add_text(snapshot, 'fixture:ar', key, 'ar', 'الأصل', 'الأصل', {})
    translation = store.add_text(snapshot, 'fixture:tr', key, 'tr', 'Çeviri', 'Çeviri', {})
    return store.add_alignment(target, bridge, translation, {'method': 'fixture'}, scope)


def test_assistant_source_review_does_not_require_or_imply_human_expert(store):
    store.migrate()
    revision = new_case(store)
    for dimension in ['arabic_relation', 'translation_meaning', 'translation_completeness', 'notes_separation']:
        store.record_review(revision, 'assistant', 'assistant_source_review', dimension, 'pass',
                            'Kaynak metinle karşılaştırıldı.', ['fixture:ar:1', 'fixture:tr:1'])
    result = store.assessment(revision)
    assert result['status'] == 'source_compared'
    assert result['expert_reviewed'] is False
    assert result['bibliography'] == 'pending'


def test_incomplete_translation_blocks_completed_status(store):
    store.migrate()
    revision = new_case(store)
    store.record_review(revision, 'assistant', 'assistant_source_review', 'translation_completeness',
                        'fail', 'Türkçe metin yarım kalıyor.', ['fixture:tr:1'])
    assert store.assessment(revision)['status'] == 'problem_detected'


def test_automatic_match_cannot_be_recorded_as_semantic_approval(store):
    store.migrate()
    revision = new_case(store)
    with pytest.raises((ValueError, psycopg.Error)):
        store.record_review(revision, 'script', 'automated_check', 'translation_meaning', 'pass',
                            'Harfler aynı.', ['fixture:ar:1'])


def test_another_text_revision_does_not_inherit_earlier_review(store):
    store.migrate()
    first = new_case(store, '1')
    store.record_review(first, 'assistant', 'assistant_source_review', 'arabic_relation', 'pass', 'İlk kayıt.', ['fixture:ar:1'])
    second = new_case(store, '2')
    assert store.assessment(second)['status'] == 'needs_review'
    assert store.assessment(second)['dimensions']['arabic_relation'] == 'pending'


def test_sealed_alignment_cannot_gain_members_after_review(store):
    store.migrate()
    revision = new_case(store)
    with pytest.raises(psycopg.errors.RaiseException):
        with store.connection() as c:
            c.execute('INSERT INTO alignment_members (revision_id,text_version_id,role,ordinal) '
                      'SELECT revision_id,text_version_id,role,99 FROM alignment_members WHERE revision_id=%s LIMIT 1', (revision,))


def test_not_applicable_does_not_claim_required_review_dimensions_passed(store):
    store.migrate()
    revision = new_case(store)
    for dimension in ['arabic_relation', 'translation_meaning', 'translation_completeness', 'notes_separation']:
        store.record_review(revision, 'assistant', 'assistant_source_review', dimension,
                            'not_applicable', 'Bu boyut incelenmedi.', ['fixture:ar:1'])
    result = store.assessment(revision)
    assert result['status'] == 'needs_review'
    assert result['dimensions']['translation_meaning'] == 'not_applicable'
