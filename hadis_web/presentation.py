"""Additive reading labels and source-preserving plain-text search excerpts."""
import re
import unicodedata

BOOK_TITLES_TR = {
    '146': 'Buhârî · el-Câmiʿu’s-sahîh',
    '158': 'Müslim · el-Câmiʿu’s-sahîh',
    '184': 'Ebû Dâvûd · es-Sünen',
    '195': 'Tirmizî · el-Câmiʿ',
    '319': 'Nesâî · es-Sünenü’s-suğrâ',
    '173': 'İbn Mâce · es-Sünen',
    '19': 'Mâlik · el-Muvattaʾ (Yahyâ el-Leysî rivayeti)',
}


def book_title_tr(book_id):
    return BOOK_TITLES_TR.get(str(book_id))


def canonical_digits(text):
    """Normalize decimal glyphs, without interpreting or renumbering source keys."""
    return ''.join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in text)


_NAVIGATION_SUFFIX = re.compile(
    r'(?<!\S)(?:İzah\s+için\s+buraya\s+tıklayın|'
    r'(?:MÜSLİM|EBU\s+DAVUD)\s+HADİSİ\s+VE\s+İZAH\s+İÇ,?İN\s+TIKLA)[.!]?\s*\Z',re.IGNORECASE)


def source_presentation(text,language):
    """Separate registered legacy navigation tails only in a derived reading view."""
    match=_NAVIGATION_SUFFIX.search(text) if language=='tr' else None
    if match is None:return {'text':text,'navigation_note':''}
    return {'text':text[:match.start()].rstrip(),'navigation_note':text[match.start():]}


def folded_with_positions(text):
    letters, positions = [], []
    for i, char in enumerate(text):
        for folded in unicodedata.normalize('NFKD', char.casefold()).replace('ı', 'i'):
            if not unicodedata.category(folded).startswith('M'):
                letters.append(folded)
                positions.append(i)
    return ''.join(letters), positions


def excerpt(text, q, limit=320):
    normalized, positions = folded_with_positions(text)
    terms = re.findall(r'[^\W_]+', folded_with_positions(q)[0])
    ranges = []
    for token in re.finditer(r'[^\W_]+', normalized):
        if any(token.group().startswith(term) for term in terms):
            begin, end = positions[token.start()], positions[token.end()-1]+1
            while end < len(text) and unicodedata.category(text[end]).startswith('M'):
                end += 1
            if ranges and begin < ranges[-1][1]:
                ranges[-1] = (ranges[-1][0],max(ranges[-1][1],end))
            else:
                ranges.append((begin,end))
    anchor = ranges[0][0] if ranges else 0
    start = max(0,anchor-min(80,limit//3))
    if start:
        boundary = text.find(' ',start,min(anchor,start+40))
        if boundary >= 0:
            start = boundary+1
    end = min(len(text),start+limit)
    if end < len(text):
        boundary = text.rfind(' ',max(anchor+1,end-40),end)
        if boundary >= 0:
            end = boundary
    parts = []
    def append(value, match=False):
        if value:
            parts.append({'text':value,'match':match})
    if start:
        append('… ')
    cursor = start
    for begin,finish in ranges:
        if begin >= end:
            break
        if finish <= start:
            continue
        begin,finish = max(begin,start),min(finish,end)
        append(text[cursor:begin]); append(text[begin:finish],True); cursor = finish
    append(text[cursor:end])
    if end < len(text):
        append(' …')
    return {'snippet': ''.join(p['text'] for p in parts), 'snippet_parts':parts}


def present_result(row, q):
    result = dict(row)
    text = result.pop('search_text', result.get('snippet',''))
    view=source_presentation(text,result.get('language'))
    result.update(excerpt(view['text'],q))
    result['source_navigation_present']=bool(view['navigation_note'])
    result['record_label']='Kaynak metni'
    result['book_name_tr'] = book_title_tr(result['book_id'])
    return result
