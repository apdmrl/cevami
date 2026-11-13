from hadis_web.presentation import excerpt, book_title_tr
import pytest


def test_excerpt_finds_late_match_and_preserves_source_characters():
    text = 'Başlangıç açıklaması. '*45 + 'Ameller niyetlere göredir. Son cümle.'
    data = excerpt(text, 'niyet', limit=120)
    assert 'niyetlere' in data['snippet']
    assert len(data['snippet']) <= 128
    assert data['snippet'].startswith('… ')
    assert ''.join(part['text'] for part in data['snippet_parts']) == data['snippet']
    assert [p['text'] for p in data['snippet_parts'] if p['match']] == ['niyetlere']


def test_highlights_turkish_case_and_arabic_diacritics_without_rewriting():
    tr = excerpt('İNSAN için karşılık vardır.', 'insan karsilik')
    assert [p['text'] for p in tr['snippet_parts'] if p['match']] == ['İNSAN', 'karşılık']
    ar = excerpt('قَالَ إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ', 'إنما الأعما')
    assert [p['text'] for p in ar['snippet_parts'] if p['match']] == ['إِنَّمَا', 'الْأَعْمَالُ']
    assert ar['snippet'] == 'قَالَ إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ'


def test_source_markup_is_plain_text_and_unmatched_excerpt_is_valid():
    text = '<img src=x onerror=alert(1)> intentions & actions'
    data = excerpt(text,'intentions')
    assert data['snippet'] == text
    assert all(isinstance(p['text'],str) and type(p['match']) is bool for p in data['snippet_parts'])
    assert excerpt('Kısa kaynak metni.','bulunmayan')['snippet_parts'] == [{'text':'Kısa kaynak metni.','match':False}]
    assert excerpt('', '') == {'snippet':'','snippet_parts':[]}
    assert book_title_tr('146') == 'Buhârî · el-Câmiʿu’s-sahîh'
    assert book_title_tr('999999') is None


def test_arabic_ligature_with_multiple_normalized_words_is_not_duplicated():
    original = 'قال ﷺ اليوم'
    for q in ['صلى الله','صلى الله عليه وسلم']:
        data=excerpt(original,q)
        assert data['snippet'] == original
        assert [p['text'] for p in data['snippet_parts'] if p['match']] == ['ﷺ']


@pytest.mark.parametrize('original,expected',[
    ('١٤٦_١','146_1'),('۱۴۶_۱','146_1'),('1٤۶_1','146_1'),('٠١٤٦_٠١','0146_01'),
    ('niyet ١','niyet 1'),('146_1','146_1'),('²_1','²_1')])
def test_decimal_digits_are_canonical_without_renumbering(original,expected):
    from hadis_web.presentation import canonical_digits
    assert canonical_digits(original)==expected


@pytest.mark.parametrize('note',[
    'İzah için buraya tıklayın','MÜSLİM HADİSİ VE İZAH İÇİN TIKLA',
    'EBU DAVUD HADİSİ VE İZAH İÇ,İN TIKLA'])
def test_registered_navigation_suffix_has_a_separate_source_preserving_view(note):
    from hadis_web.presentation import source_presentation
    original='Yayımlanmış kaynak metni. '+note
    view=source_presentation(original,'tr')
    assert view=={'text':'Yayımlanmış kaynak metni.','navigation_note':note}
    assert original=='Yayımlanmış kaynak metni. '+note


@pytest.mark.parametrize('text,language',[
    ('Buraya tıklayın ve ardından okuyun.','tr'),
    ('İzah için buraya tıklayın. Ardından kaynak notu gelir.','tr'),
    ('Dedi ki: "İzah için buraya tıklayın"','tr'),
    ('Dedi ki: “İzah için buraya tıklayın”','tr'),
    ('Metin. Bilinmeyen bağlantıya tıkla','tr'),
    ('Metin. İzah için buraya tıklayın','en'),
    ('النص. İzah için buraya tıklayın','ar')])
def test_unknown_interior_quoted_or_non_turkish_content_is_never_rewritten(text,language):
    from hadis_web.presentation import source_presentation
    assert source_presentation(text,language)=={'text':text,'navigation_note':''}


def test_preview_uses_reading_view_but_does_not_classify_a_hadith_or_change_source():
    from hadis_web.presentation import present_result
    row={'book_id':'173','language':'tr','search_text':'Yemin niyete bağlıdır. MÜSLİM HADİSİ VE İZAH İÇİN TIKLA'}
    data=present_result(row,'niyet')
    assert data['snippet']=='Yemin niyete bağlıdır.'
    assert data['source_navigation_present'] is True
    assert data['record_label']=='Kaynak metni'
    assert row['search_text'].endswith('TIKLA')
