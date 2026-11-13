from fastapi.testclient import TestClient
import pytest

from hadis_web.app import create_app


@pytest.fixture(scope='module')
def client():
    return TestClient(create_app(),base_url='http://127.0.0.1')


def test_arabic_is_primary_and_source_is_unchanged(client):
    response = client.get('/api/hadith/146_1')
    assert response.status_code == 200
    row = response.json()
    assert row['primary_language'] == 'ar'
    assert row['bhid'] == '146_1'
    assert 'إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ' in row['arabic']['text']
    assert row['arabic']['raw_text'].startswith('$1  1 /2')
    assert row['book']['name'] == 'صحيح البخاري'
    assert row['citation']['page_reference_raw'].strip() == '1 : 2'


def test_all_seven_sanads_are_available_not_just_five(client):
    response = client.get('/api/hadith/146_3/sanads')
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 7
    assert len(data['items']) == 7
    assert [r['sanad_id'] for r in data['items']] == [74259, 74260, 74261, 74262, 74263, 74264, 74265]


def test_sanad_order_and_structural_markers_are_preserved(client):
    data = client.get('/api/hadith/146_3/sanads').json()
    members = data['items'][0]['members']
    assert [m['source_id'] for m in members] == [6817, 30001, 4864, 6641, 5688, 7272, 5594, 4049]
    assert [m['position'] for m in members] == list(range(8))
    assert members[1]['kind'] == 'structural_marker'
    assert members[1]['label'] == 'موضع تعليق'


def test_inline_narrators_are_not_used_as_a_fabricated_sanad(client):
    data = client.get('/api/hadith/146_4412/sanads').json()
    assert data['total'] == 0
    assert data['items'] == []
    hadith = client.get('/api/hadith/146_4412').json()
    assert hadith['arabic']['inline_narrator_ids'] == [1548, 896, 1302, 3954, 4049]


def test_compiler_remains_in_recorded_sanad(client):
    data = client.get('/api/hadith/146_1/sanads').json()
    assert [m['source_id'] for m in data['items'][0]['members']] == [6817, 4698, 3443, 8272, 6796, 5719, 5913]


def test_sanad_pagination_exposes_the_rest(client):
    data = client.get('/api/hadith/146_3/sanads?limit=5&offset=5').json()
    assert data['total'] == 7
    assert [r['sanad_id'] for r in data['items']] == [74264, 74265]


def test_narrator_profile_comes_from_recorded_source(client):
    response = client.get('/api/narrator/4698')
    assert response.status_code == 200
    profile = response.json()
    assert profile['id'] == 4698
    assert profile['shohra'] == 'الحميدي عبد الله بن الزبير'
    assert profile['source'] == 'Cevâmiu’l-Kelim 4.5'


def test_missing_record_and_invalid_identifier_are_distinct(client):
    assert client.get('/api/hadith/146_99999999').status_code == 404
    assert client.get('/api/hadith/146_OR_1').status_code == 422


def test_book_filter_and_quoted_search_are_safe(client):
    response = client.get('/api/books/146/hadiths?limit=2')
    assert response.status_code == 200
    assert response.json()['total'] == 7031
    assert [x['bhid'] for x in response.json()['items']] == ['146_1', '146_2']
    assert client.get('/api/search', params={'q': '" OR 1=1 --', 'book_id': '146'}).status_code == 200


def test_search_finds_arabic_without_diacritics(client):
    response = client.get('/api/search', params={'q': 'إنما الأعمال بالنيات', 'book_id': '146'})
    assert response.status_code == 200
    assert '146_1' in [x['bhid'] for x in response.json()['items']]
