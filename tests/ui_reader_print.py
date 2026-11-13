"""Source-bound print presentation in isolated browser profiles; no OS printing."""
import argparse
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=15000)


def reader(browser,url,width,height,route='/research?hadith=146_1'):
    page=browser.new_page(viewport={'width':width,'height':height})
    page.add_init_script("window.printCalls=0; window.print=()=>{window.printCalls++;window.dispatchEvent(new Event('beforeprint'));};")
    page.goto(url+route)
    expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
    return page


def prepare(page,click=True):
    if click:
        assert page.locator('#print-record').count()==1,'Missing reader print action'
        page.locator('#print-record').click()
    else:page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    assert page.locator('#print-view').count()==1,'Missing print-only source view'
    page.emulate_media(media='print')
    expect(page.locator('#print-view')).to_be_visible()


def finish(page):
    page.emulate_media(media='screen')
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    expect(page.locator('#print-view')).not_to_be_visible()
    assert page.locator('#print-view').evaluate('(e)=>e.childNodes.length')==0


def core(browser,url,width,height):
    page=reader(browser,url,width,height)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        arabic=page.locator('#arabic-text').text_content()
        source=page.request.get(url+'/api/hadith/146_1').json()
        assert page.locator('#print-record').count()==1,'Missing reader print action'
        expect(page.locator('#print-record')).to_have_text('Yazdır / PDF')
        size=page.locator('#print-record').bounding_box()
        assert size['width']>=44 and size['height']>=44,f'Print touch target is too small: {size}'
        expect(page.locator('#print-view')).not_to_be_visible()
        prepare(page)
        expect(page.locator('#print-arabic')).to_have_text(arabic,use_inner_text=False)
        assert page.locator('#print-arabic').text_content()==arabic
        text=page.locator('#print-view').inner_text()
        for expected in ('GK kayıt kimliği','146_1','İç kayıt sırası','Metinde görünen numara',source['book']['name'],source['citation']['hadith_reference_raw']):
            assert str(expected) in text,expected
        assert url+'/hadith/146_1' in text
        assert page.locator('#print-view [id]').evaluate_all('(els)=>new Set(els.map(e=>e.id)).size===els.length')
        assert page.evaluate('new Set([...document.querySelectorAll("[id]")].map(e=>e.id)).size===document.querySelectorAll("[id]").length')
        assert page.locator('#print-view button,#print-view input,#print-view select').count()==0
        expect(page.locator('.topbar')).not_to_be_visible()
        expect(page.locator('#print-translations')).to_have_count(0)
        finish(page)
        expect(page.locator('#arabic-text')).to_be_visible()
        assert not errors,errors
        print(f'PASS {width}x{height}: exact Arabic, real identity/source/link, hidden screen copy, print-only controls and clean afterprint',flush=True)
    finally:page.close()


def translations(browser,url,width,height):
    page=reader(browser,url,width,height,route='/hadith/146_1')
    try:
        expect(page.locator('#components-content .translation-component').first).to_be_visible()
        before=page.locator('#turkish-content').inner_text()
        prepare(page)
        expect(page.locator('#print-translations')).to_contain_text('Türkçe')
        expect(page.locator('#print-translations .component-evidence').first).to_have_attribute('open','')
        expect(page.locator('#components-content .component-evidence').first).not_to_have_attribute('open','')
        alternatives=page.locator('#print-translations .translation-alternatives')
        if alternatives.count():expect(alternatives).not_to_have_attribute('open','')
        finish(page)
        assert page.locator('#turkish-content').inner_text()==before
        page.locator('#read-en').click()
        expect(page.locator('#english-content .translation-text').first).to_be_visible()
        english=page.locator('#english-content .translation-text').all_text_contents()
        prepare(page)
        expect(page.locator('#print-translations')).to_contain_text('English')
        assert page.locator('#print-translations .translation-text').all_text_contents()==english
        assert page.locator('#print-translations .component-translation').count()==0
        expect(page.locator('#print-translations .translation-source-details').first).to_have_attribute('open','')
        finish(page)
        expect(page.locator('#read-en')).to_have_attribute('aria-pressed','true')
        page.locator('#translation-toggle').click();prepare(page)
        expect(page.locator('#print-translations')).to_have_count(0);finish(page)
        print(f'PASS {width}x{height}: selected TR/EN exact text, visible source evidence, closed alternatives and unchanged screen selection',flush=True)
    finally:page.close()


def partial_sanads(browser,url,width,height):
    page=reader(browser,url,width,height,route='/research?hadith=1006_33')
    try:
        expect(page.locator('.sanad-item')).to_have_count(20)
        original=[e for e in page.locator('.sanad-item').evaluate_all('(els)=>els.map(e=>e.open)')]
        prepare(page)
        expect(page.locator('#print-sanad-coverage')).to_contain_text('20 / 24')
        expect(page.locator('#print-sanads .sanad-item')).to_have_count(20)
        assert page.locator('#print-sanads .sanad-item').evaluate_all('(els)=>els.every(e=>e.open)')
        assert page.locator('#sanad-list .sanad-item').evaluate_all('(els)=>els.map(e=>e.open)')==original
        finish(page)
        page.locator('#more-sanads').click();expect(page.locator('#sanad-list .sanad-item')).to_have_count(24)
        prepare(page);expect(page.locator('#print-sanad-coverage')).to_contain_text('24 / 24');finish(page)
        print(f'PASS {width}x{height}: 20/24 then 24/24 source scope, exact ordered source chains, unchanged collapsed screen state',flush=True)
    finally:page.close()


def lifecycle(browser,url):
    page=reader(browser,url,1280,850)
    try:
        prepare(page);page.emulate_media(media='screen')
        held=[]
        page.route('**/api/hadith/146_2',lambda route:held.append(route))
        page.locator('#next-record').click()
        expect(page.locator('#hadith-paper')).not_to_be_visible()
        assert page.locator('#print-view').evaluate('(e)=>e.childNodes.length')==0
        prepare(page,click=False)
        expect(page.locator('#print-view')).to_contain_text('Kayıt hazır değil')
        assert '146_1' not in page.locator('#print-view').text_content()
        finish(page)
        held[0].continue_();page.unroute('**/api/hadith/146_2')
        expect(page.locator('#identity-short')).to_have_text('GK 146_2')
        prepare(page);expect(page.locator('#print-view')).to_contain_text('146_2');finish(page)
        page.goto(url+'/research?hadith=146_999999999');expect(page.locator('#error-banner')).to_be_visible()
        prepare(page,click=False);expect(page.locator('#print-view')).to_contain_text('Kayıt hazır değil')
        assert '146_2' not in page.locator('#print-view').text_content()
        finish(page)
        print('PASS lifecycle: new record clears snapshot, delayed core/Ctrl+P and 404 never print stale source',flush=True)
    finally:page.close()


def source_states(browser,url):
    page=browser.new_page(viewport={'width':1280,'height':850})
    try:
        page.add_init_script("window.print=()=>window.dispatchEvent(new Event('beforeprint'))")
        held=[]
        page.route('**/api/hadith/146_1/sanads*',lambda route:held.append(route))
        page.goto(url+'/research?hadith=146_1')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        prepare(page);expect(page.locator('#print-sanads')).to_contain_text('yükleniyor')
        expect(page.locator('#print-sanad-coverage')).to_contain_text('henüz');finish(page)
        held[0].abort();page.unroute('**/api/hadith/146_1/sanads*')
        expect(page.locator('#sanad-list')).to_contain_text('yüklenemedi')
        prepare(page);expect(page.locator('#print-sanads')).to_contain_text('yüklenemedi');finish(page)
        print('PASS source states: pending/unreachable sened data stays distinct from absent sources',flush=True)
    finally:page.close()


def disputed_and_modal(browser,url):
    page=reader(browser,url,390,844,route='/hadith/146_47')
    try:
        problem=page.locator('#turkish-content .problem-text').first
        expect(problem).to_be_visible()
        expect(problem).not_to_have_attribute('open','')
        page.locator('#open-guide').click();expect(page.locator('#usage-dialog')).to_be_visible()
        focus=page.evaluate('document.activeElement.id');position=page.evaluate('scrollY');original=page.url
        prepare(page,click=False)
        expect(page.locator('#usage-dialog')).not_to_be_visible()
        assert page.locator('#print-translations .problem-text').count()>0,'Missing disputed source summary'
        for node in page.locator('#print-translations .problem-text .translation-text,#print-translations .problem-text .component-translation').all():
            expect(node).not_to_be_visible()
        expect(page.locator('#print-translations')).to_contain_text('uyuşmayan')
        finish(page)
        expect(page.locator('#usage-dialog')).to_be_visible()
        assert page.evaluate('document.activeElement.id')==focus,'Modal focus changed after printing'
        assert page.url==original,'Print changed current URL'
        assert page.evaluate('scrollY')==position,f"Print changed scroll: {position} -> {page.evaluate('scrollY')}"
        expect(problem).not_to_have_attribute('open','')
        print('PASS disputed/modal: closed problematic translation stays closed, its warning persists, modal/focus/URL/scroll preserved',flush=True)
    finally:page.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--case',default='all',choices=['all','core','translations','sanads','lifecycle','states','disputed']);args=parser.parse_args()
    failed=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            jobs=[]
            for name,function in [('core',core),('translations',translations),('sanads',partial_sanads)]:
                if args.case in ('all',name):jobs.extend((name,function,size) for size in [(1440,1000),(390,844)])
            for name,function in [('lifecycle',lifecycle),('states',source_states),('disputed',disputed_and_modal)]:
                if args.case in ('all',name):jobs.append((name,function,()))
            for name,function,size in jobs:
                try:function(browser,args.url,*size)
                except Exception as error:
                    failed.append(name);print(f'FAIL {name}{size}: {error}',flush=True)
        finally:browser.close()
    raise SystemExit(bool(failed))
