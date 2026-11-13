"""First-use help and context-preserving reading/research transitions."""
import argparse
from urllib.parse import parse_qs,urlparse
from playwright.sync_api import sync_playwright,expect
expect.set_options(timeout=15000)


def guide(browser,url,width,height,mode):
    page=browser.new_page(viewport={'width':width,'height':height})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        route='/?q=niyet&language=tr&book_id=146' if mode=='home' else '/research?hadith=146_1' if mode=='research' else '/hadith/146_1'
        page.goto(url+route)
        if mode=='home':expect(page.locator('.suggestion').first).to_be_visible()
        else:expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        original=page.url
        dialog=page.locator('#usage-dialog');trigger=page.locator('#open-guide')
        assert trigger.count()==1,'A visible help entry is required'
        expect(dialog).not_to_be_visible()
        trigger.click();expect(dialog).to_be_visible()
        close=page.locator('#close-guide');expect(close).to_be_focused()
        expect(dialog).to_contain_text('Kullanım rehberi')
        if mode=='home':expect(dialog).to_contain_text('kelime')
        else:expect(dialog).to_contain_text('uzman onayı değildir')
        body=page.locator('#usage-body')
        before=close.bounding_box();root_scroll=page.evaluate('scrollY')
        if body.evaluate('(e)=>e.scrollHeight>e.clientHeight'):
            body.hover();page.mouse.wheel(0,1500)
            page.wait_for_function('document.querySelector("#usage-body").scrollTop>0')
        after=close.bounding_box();assert abs(before['y']-after['y'])<1
        assert page.evaluate('scrollY')==root_scroll
        close.focus();page.keyboard.press('Shift+Tab')
        assert dialog.evaluate('(e)=>e.contains(document.activeElement)')
        page.keyboard.press('Tab');expect(close).to_be_focused()
        page.keyboard.press('Escape');expect(dialog).not_to_be_visible();expect(trigger).to_be_focused()
        assert page.url==original
        if mode=='home':
            expect(page.locator('#home-query')).to_have_value('niyet')
            expect(page.locator('#search-book')).to_have_value('146')
            expect(page.locator('.suggestion').first).to_be_visible()
        trigger.click();expect(body).to_have_js_property('scrollTop',0)
        page.mouse.click(4,4);expect(dialog).not_to_be_visible();expect(trigger).to_be_focused()
        trigger.click()
        if mode=='home':
            page.locator('#guide-example').click()
            expect(page.locator('#home-query')).to_have_value('niyet')
            assert parse_qs(urlparse(page.url).query).get('book_id') is None
        else:
            page.locator('[data-guide-section="#sanad-list"]').click()
            expect(dialog).not_to_be_visible();assert urlparse(page.url).fragment=='sanad-list'
            expect(page.locator('#sanad-list')).to_be_focused()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print(f'PASS {width}x{height} {mode}: manual help, fixed close/scroll/trap/Escape/backdrop, state preservation, real action',flush=True)
    finally:page.close()


def transitions(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        page.goto(url+'/research?hadith=146_1&q=niyet&language=tr&book_id=146#unknown')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        switch=page.locator('#open-research')
        expect(switch).to_contain_text('Sade okumaya geç')
        expect(page.locator('#back-search')).to_be_visible()
        assert urlparse(switch.get_attribute('href')).fragment==''
        page.locator('#translation-toggle').click();page.locator('#read-en').click()
        page.locator('#section-navigation a[href="#sanad-list"]').click()
        switch.click()
        expect(page).to_have_url(__import__('re').compile(r'/hadith/146_1\?'))
        expect(page.locator('#read-en')).to_have_attribute('aria-pressed','true')
        assert urlparse(page.url).fragment=='sanad-list'
        query=parse_qs(urlparse(page.url).query)
        assert query['q']==['niyet'] and query['book_id']==['146'] and query['translation']==['en']
        expect(switch).to_contain_text('Araştırma alanına geç')
        switch.click()
        expect(page).to_have_url(__import__('re').compile(r'/research\?'))
        expect(page.locator('#read-en')).to_have_attribute('aria-pressed','true')
        page.reload();expect(page.locator('#read-en')).to_have_attribute('aria-pressed','true')
        page.locator('#next-record').click();expect(page.locator('#identity-short')).to_have_text('GK 146_2')
        assert '/hadith/146_2' in switch.get_attribute('href')
        page.locator('#section-navigation a[href="#translations-panel"]').click()
        page.locator('#read-tr').click()
        assert 'translation=en' not in switch.get_attribute('href')
        page.locator('#back-search').click()
        expect(page.locator('#home-query')).to_have_value('niyet')
        expect(page.locator('#search-book')).to_have_value('146')
        print(f'PASS {width}x{height}: distinct reading/research links, same record/EN/hash/query, reload/new record/TR/search return',flush=True)
    finally:page.close()


def readiness(browser,url):
    page=browser.new_page(viewport={'width':390,'height':844});held=[]
    try:
        page.route('**/api/hadith/146_1',lambda route:held.append(route))
        page.goto(url+'/research?hadith=146_1')
        page.locator('#open-guide').click()
        action=page.locator('[data-guide-section="#translations-panel"]')
        expect(action).to_be_disabled()
        page.wait_for_function('document.querySelector("#hadith-paper").getAttribute("aria-busy")==="true"')
        assert held;held.pop().continue_();page.unroute_all(behavior='ignoreErrors')
        expect(action).to_be_enabled();action.click()
        expect(page.locator('#translations-panel')).to_be_visible()
        expect(page.locator('#translations-panel')).to_be_focused()
        page.route('**/api/hadith/146_2',lambda r:r.fulfill(status=503,json={'detail':'unavailable'}))
        page.locator('#next-record').click()
        expect(page.locator('#retry-hadith')).to_be_visible()
        expect(page.locator('#open-research')).not_to_be_visible()
        page.locator('#open-guide').click();expect(action).to_be_disabled()
        page.keyboard.press('Escape');expect(page.locator('#back-search')).to_be_visible()
        print('PASS readiness: help available during load/error; section actions follow actual readiness without stale focus',flush=True)
    finally:
        page.unroute_all(behavior='ignoreErrors')
        for route in held:route.abort()
        page.close()


def initial_return(browser,url):
    for mode in ['research','hadith']:
        page=browser.new_page(viewport={'width':390,'height':844})
        try:
            page.route('**/api/hadith/146_1',lambda route:route.fulfill(status=503,json={'detail':'test unavailable'}))
            route='/research?hadith=146_1&' if mode=='research' else '/hadith/146_1?'
            page.goto(url+route+'q=niyet&language=tr&book_id=146')
            expect(page.locator('#retry-hadith')).to_be_visible()
            page.locator('#back-search').click()
            params=parse_qs(urlparse(page.url).query)
            assert params.get('q')==['niyet'] and params.get('language')==['tr'] and params.get('book_id')==['146'], 'Initial failed record lost search return context'
            expect(page.locator('#home-query')).to_have_value('niyet')
            expect(page.locator('#search-book')).to_have_value('146')
            expect(page.locator('input[name="language"][value="tr"]')).to_be_checked()
            print(f'PASS initial error return {mode}: actual search link preserves query/language/book before any record renders',flush=True)
        finally:page.close()


def bootstrap(browser,url):
    for mode in ['research','hadith']:
        page=browser.new_page(viewport={'width':390,'height':844});held=[]
        try:
            page.route('**/assets/app.js*',lambda route:held.append(route))
            route='/research?hadith=146_2&' if mode=='research' else '/hadith/146_2?'
            page.goto(url+route+'translation=en',wait_until='commit')
            expect(page.locator('#open-guide')).to_be_visible()
            switch=page.locator('#open-research')
            assert not switch.is_visible(), 'Bootstrap exposes a mode link before the correct record target exists'
            assert switch.get_attribute('href') is None, 'Bootstrap must not expose a default wrong-record target'
            assert held
            held.pop().continue_();page.unroute_all(behavior='ignoreErrors')
            expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
            expect(switch).to_be_visible()
            href=switch.get_attribute('href')
            assert ('hadith=146_2' if mode=='hadith' else '/hadith/146_2?') in href
            assert 'translation=en' in href
            print(f'PASS bootstrap {mode}: no default wrong-record link before app module; actual GK/EN target appears after ready',flush=True)
        finally:
            for route in held:route.continue_()
            page.unroute_all(behavior='ignoreErrors');page.close()


def missing_guidance(browser,url):
    page=browser.new_page(viewport={'width':390,'height':844})
    try:
        page.goto(url+'/research?hadith=999999999_999999999')
        expect(page.locator('#error-banner')).to_be_visible()
        expect(page.locator('#retry-hadith')).not_to_be_visible()
        page.locator('#open-guide').click()
        text=page.locator('.usage-ready-note').inner_text()
        assert 'Hadis ara' in text, 'Missing record guide must name an available recovery action'
        assert 'kaydı yeniden deneyebilirsiniz' not in text
        page.keyboard.press('Escape')
        page.locator('#back-search').click()
        expect(page.locator('#home-query')).to_be_visible()
        print('PASS missing record: real404 guide names available search action and actual return works',flush=True)
    finally:page.close()


def terminology(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000})
    try:
        page.goto(url+'/research?hadith=146_3')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        page.locator('#open-guide').click()
        text=page.locator('.usage-steps').inner_text()
        assert 'iki senedi yan yana inceleyebilirsiniz' in text, 'Guide must describe two source chains rather than two independent sources'
        print('PASS terminology: comparison described as two seneds in the same record',flush=True)
    finally:page.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--case',choices=['all','guide','transitions','readiness','initial_return','bootstrap','missing_guidance','terminology'],default='all');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            if args.case in ('all','guide'):
                for width,height,mode in [(1440,1000,'home'),(390,844,'home'),(1440,1000,'reading'),(390,844,'research'),(700,390,'research')]:guide(browser,args.url,width,height,mode)
            if args.case in ('all','transitions'):
                for size in [(1440,1000),(390,844)]:transitions(browser,args.url,*size)
            if args.case in ('all','readiness'):readiness(browser,args.url)
            for name,check in [('initial_return',initial_return),('bootstrap',bootstrap),('missing_guidance',missing_guidance),('terminology',terminology)]:
                if args.case in ('all',name):check(browser,args.url)
        finally:browser.close()
