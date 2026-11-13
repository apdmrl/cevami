"""Live scope and partial-service failure regressions, isolated browser profiles."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


def filters(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        page.goto(url+'/?q=niyet&language=tr')
        book=page.locator('#search-book')
        expect(book.locator('option[value="146"]')).to_be_attached()
        book.select_option('146')
        expect(page.locator('.suggestion').first).to_have_attribute('href',__import__('re').compile('/hadith/146_.*book_id=146'))
        assert all('/hadith/146_' in h for h in page.locator('.suggestion').evaluate_all('(nodes)=>nodes.map(n=>n.href)'))
        if page.locator('#home-more').is_visible():
            size=page.locator('.suggestion').count()
            page.locator('#home-more').click()
            expect(page.locator('.suggestion')).not_to_have_count(size)
        page.locator('.suggestion').first.click()
        expect(page.locator('#back-search')).to_have_attribute('href',__import__('re').compile('book_id=146'))
        page.go_back();expect(book).to_have_value('146')
        page.reload();expect(book).to_have_value('146')
        page.goto(url+'/?q=146_1&book_id=158')
        expect(page.locator('#search-status')).to_contain_text('Seçili eserde')
        expect(book.locator('option[value="158"]')).to_contain_text('0 kayıt')
        page.locator('#clear-book').click()
        expect(page.locator('.suggestion').first).to_contain_text('146_1')
        assert 'book_id' not in page.url
        print(f'PASS {width}x{height}: book scope, pagination, URLs, back/reload, zero results and clear')
    finally:page.close()


def failures(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        patterns=['**/api/hadith/*/sanads','**/api/hadith/*/translations','**/api/hadith/*/components']
        for pattern in patterns: page.route(pattern,lambda r:r.abort())
        page.goto(url+'/hadith/146_1')
        expect(page.locator('#arabic-text')).to_contain_text('إِنَّمَا')
        expect(page.locator('#hadith-paper')).to_be_visible()
        expect(page.locator('#auxiliary-status')).to_contain_text('erişilemiyor')
        expect(page.locator('#sanad-list')).to_contain_text('yüklenemedi')
        expect(page.locator('#translations-content')).not_to_contain_text('adayı henüz bulunmuyor')
        for pattern in patterns:page.unroute(pattern)
        page.locator('#retry-auxiliary').click()
        expect(page.locator('#sanad-list .sanad-item').first).to_be_visible()
        expect(page.locator('#components-content .translation-component').first).to_be_attached()
        expect(page.locator('#auxiliary-status')).not_to_be_visible()
        page.route('**/api/hadith/146_2',lambda r:r.fulfill(status=503,json={'detail':'Kaynak geçici olarak erişilemiyor.'}))
        page.locator('#next-record').click()
        expect(page.locator('#error-banner')).to_contain_text('erişilemiyor')
        expect(page.locator('#hadith-paper')).not_to_be_visible()
        expect(page.locator('#retry-hadith')).to_be_visible()
        page.unroute('**/api/hadith/146_2')
        page.locator('#retry-hadith').click()
        expect(page.locator('#hadith-number')).to_have_text('2')
        expect(page.locator('#hadith-paper')).to_be_visible()
        page.route('**/api/hadith/146_3',lambda r:r.fulfill(status=404,json={'detail':'Hadis kaydı bulunamadı.'}))
        page.locator('#next-record').click()
        expect(page.locator('#error-banner')).to_contain_text('bulunamadı')
        expect(page.locator('#hadith-paper')).not_to_be_visible()
        expect(page.locator('#retry-hadith')).not_to_be_visible()
        page.unroute('**/api/hadith/146_3')
        page.route('**/api/hadith/146_1',lambda r:r.abort())
        page.goto(url+'/hadith/146_1')
        expect(page.locator('#error-banner')).to_contain_text('yüklenemiyor')
        expect(page.locator('#hadith-paper')).not_to_be_visible()
        page.unroute('**/api/hadith/146_1')
        page.locator('#retry-hadith').click()
        expect(page.locator('#hadith-number')).to_have_text('1')
        expect(page.locator('#hadith-paper')).to_be_visible()
        assert not errors,errors
        print(f'PASS {width}x{height}: auxiliary failures preserve Arabic, retry, core error hides old record')
    finally:page.close()


def delayed(browser,url):
    page=browser.new_page()
    try:
        page.add_init_script(r'''const realFetch=window.fetch; window.pendingAuxiliary=0;
          window.fetch=(...args)=>realFetch(...args).then(response=>{
            if (!String(args[0]).match(/146_1\/(sanads|translations|components)/)) return response;
            ++window.pendingAuxiliary;
            return new Promise(resolve=>setTimeout(()=>{--window.pendingAuxiliary;resolve(response)},3500));
          });''')
        page.goto(url+'/hadith/146_1')
        expect(page.locator('#arabic-text')).to_contain_text('إِنَّمَا')
        page.wait_for_function('window.pendingAuxiliary>0')
        assert page.locator('#hadith-paper').get_attribute('aria-busy') == 'false'
        page.locator('#next-record').click()
        expect(page.locator('#hadith-number')).to_have_text('2')
        expected=page.request.get(url+'/api/hadith/146_2/sanads').json()['items'][0]['sanad_id']
        expect(page.locator('#sanad-list .sanad-label').first).to_contain_text(str(expected))
        page.wait_for_function('window.pendingAuxiliary===0')
        expect(page.locator('#hadith-number')).to_have_text('2')
        expect(page.locator('#sanad-list .sanad-label').first).to_contain_text(str(expected))
        print('PASS: early Arabic while auxiliaries pending, delayed old chains cannot replace new record')
    finally:page.close()


def stalled(browser,url):
    page=browser.new_page()
    held=[]
    try:
        page.route('**/api/hadith/*/components',lambda r:held.append(r))
        page.goto(url+'/hadith/146_1')
        expect(page.locator('#arabic-text')).to_contain_text('إِنَّمَا')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        expect(page.locator('#auxiliary-status')).to_contain_text('erişilemiyor')
        expect(page.locator('#retry-auxiliary')).to_be_visible()
        for request in held: request.abort()
        page.unroute('**/api/hadith/*/components')
        page.locator('#retry-auxiliary').click()
        expect(page.locator('#components-content .translation-component').first).to_be_attached()
        expect(page.locator('#auxiliary-status')).not_to_be_visible()
        print('PASS: stalled auxiliary is bounded, Arabic remains usable, retry restores source components')
    finally:page.close()


def focus_intent(browser,url):
    page=browser.new_page();held=[]
    try:
        page.route('**/api/hadith/*/components',lambda r:held.append(r))
        page.goto(url+'/hadith/146_1#translations-panel')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        page.locator('#jump-number').click()
        page.locator('#jump-number').fill('7')
        expect(page.locator('#auxiliary-status')).to_contain_text('erişilemiyor')
        expect(page.locator('#jump-number')).to_be_focused()
        expect(page.locator('#jump-number')).to_have_value('7')
        print('PASS: delayed section restoration respects newer user focus/input')
    finally:
        for request in held:request.abort()
        page.close()


def pagination_recovery(browser,url):
    page=browser.new_page();held=[]
    try:
        page.goto(url+'/hadith/1006_33')
        expect(page.locator('#sanad-list .sanad-item')).to_have_count(20)
        pattern='**/api/hadith/1006_33/sanads?offset=20'
        page.route(pattern,lambda r:held.append(r))
        more=page.locator('#more-sanads');more.click()
        page.wait_for_timeout(9500)
        expect(more).to_be_enabled(timeout=1000)
        expect(page.locator('#sanad-page-error')).to_contain_text('yüklenemedi')
        for request in held:request.abort()
        held.clear();page.unroute(pattern)
        more.click()
        expect(page.locator('#sanad-list .sanad-item')).to_have_count(24)
        expect(more).not_to_be_visible()
        print('PASS: stalled sanad pagination recovers at same offset and exposes all24 real source chains')
    finally:
        for request in held:request.abort()
        page.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8767');parser.add_argument('--case',default='all',choices=['all','filters','failures','delayed','stalled','focus','pagination']);args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            for size in [(1280,850),(390,700)]:
                if args.case in ('all','filters'):filters(browser,args.url,*size)
                if args.case in ('all','failures'):failures(browser,args.url,*size)
            if args.case in ('all','delayed'):delayed(browser,args.url)
            if args.case in ('all','stalled'):stalled(browser,args.url)
            if args.case in ('all','focus'):focus_intent(browser,args.url)
            if args.case in ('all','pagination'):pagination_recovery(browser,args.url)
        finally:browser.close()
