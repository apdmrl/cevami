"""Research search lifecycle, real paging and non-destructive number navigation."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


def ready(page,url):
    page.goto(url+'/research?hadith=146_1')
    expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')


def lifecycle(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        ready(page,url)
        page.locator('#query').press('Enter')
        expect(page.locator('.result-button')).to_have_count(30)
        page.evaluate('''window.realFetch=fetch;window.fetch=async(...args)=>{
          const r=await window.realFetch(...args);
          if(String(args[0]).startsWith('/api/search?'))await new Promise(r=>window.releaseSearch=r);return r;
        }''')
        query=page.locator('#query');query.fill('الله');query.press('Enter')
        page.locator('#close-results').click()
        page.wait_for_function('typeof window.releaseSearch==="function"');page.evaluate('window.releaseSearch()')
        page.wait_for_timeout(100)
        assert not page.locator('#search-results').is_visible(), 'closed results reopened after late response'
        page.evaluate('window.fetch=window.realFetch')
        query.fill('');query.press('Enter')
        expect(page.locator('.result-button')).to_have_count(30)
        first=page.locator('.result-button').first.text_content()
        page.locator('.result-button').nth(1).click()
        expect(page.locator('#identity-short')).to_have_text('GK 146_2')
        expect(page.locator('#reopen-results')).to_be_visible()
        page.locator('#reopen-results').click()
        expect(page.locator('.result-button')).to_have_count(30)
        assert page.locator('.result-button').first.text_content()==first
        expect(query).to_have_value('')
        page.locator('#close-results').click()
        old_url=page.url
        page.evaluate('''window.fetch=async(...args)=>{
          const response=await window.realFetch(...args);
          if(String(args[0])==='/api/hadith/146_3')await new Promise(resolve=>window.releaseReopenedJump=resolve);
          return response;
        }''')
        jump=page.locator('#jump-number');jump.fill('3');jump.press('Enter')
        page.wait_for_function('typeof window.releaseReopenedJump==="function"')
        page.locator('#reopen-results').click()
        page.evaluate('window.releaseReopenedJump();window.fetch=window.realFetch')
        expect(page.locator('#search-results')).to_be_visible()
        expect(page.locator('#identity-short')).to_have_text('GK 146_2')
        expect(page.locator('#jump-status')).to_be_empty()
        assert page.url==old_url, 'late number lookup overrode return to search results'
        page.locator('#close-results').click()
        if width<761:page.locator('#mobile-library').click()
        page.locator('[data-book-id="158"]').click()
        expect(page.locator('#identity-short')).to_have_text('GK 158_1')
        expect(page.locator('#reopen-results')).not_to_be_visible()
        expect(page.locator('#search-results')).not_to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        print(f'PASS {width}x{height}: closed late results, retained same-book context, reopened results cancel pending jump, cleared new book')
    finally:page.close()


def paging(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000})
    try:
        ready(page,url)
        page.locator('#query').press('Enter')
        expect(page.locator('.result-button')).to_have_count(30)
        offsets=[]
        def fail(route):
            offsets.append('30');route.fulfill(status=503,json={'detail':'unavailable'})
        pattern='**/api/books/146/hadiths?*offset=30*'
        page.route(pattern,fail);page.locator('#more-results').click()
        expect(page.locator('#research-search-status')).to_contain_text('yüklenemedi')
        expect(page.locator('.result-button')).to_have_count(30)
        page.unroute(pattern)
        page.evaluate('''window.realFetch=fetch;window.offsets=[];window.fetch=async(...args)=>{
          const path=String(args[0]);if(path.startsWith('/api/books/146/hadiths')){
            window.offsets.push(new URL(path,location.origin).searchParams.get('offset'));
            await new Promise(r=>setTimeout(r,400));}return window.realFetch(...args);
        }''')
        page.locator('#retry-research-search').click()
        page.evaluate('document.querySelector("#more-results").click()')
        expect(page.locator('.result-button')).to_have_count(60)
        assert page.evaluate('window.offsets')==['30']
        expected=page.request.get(url+'/api/books/146/hadiths?offset=0&limit=60').json()['items']
        actual=page.locator('.result-button').evaluate_all('(rows)=>rows.map(e=>e.dataset.bhid)')
        assert actual==[r['bhid'] for r in expected]
        print('PASS paging: failed page retains results; retry same offset; simultaneous click guard; exact source order')
    finally:page.close()


def numbers(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        ready(page,url)
        original=page.url;query=page.locator('#query')
        query.fill('999999');query.press('Enter')
        expect(page.locator('#research-search-status')).to_contain_text('bulunamadı')
        expect(page.locator('#hadith-paper')).to_be_visible()
        expect(page.locator('#identity-short')).to_have_text('GK 146_1')
        assert page.url==original
        query.fill('١٤٦_٢');query.press('Enter')
        expect(page.locator('#identity-short')).to_have_text('GK 146_2')
        jump=page.locator('#jump-number');jump.fill('۳');jump.press('Enter')
        expect(page.locator('#identity-short')).to_have_text('GK 146_3')
        jump.fill('0');jump.press('Enter')
        expect(page.locator('#jump-status')).to_contain_text('pozitif tam sayı')
        expect(page.locator('#identity-short')).to_have_text('GK 146_3')
        expect(page.locator('#hadith-paper')).to_be_visible()
        jump.fill('1.5');jump.press('Enter')
        expect(page.locator('#jump-status')).to_contain_text('pozitif tam sayı')
        page.route('**/api/hadith/146_4',lambda route:route.fulfill(status=503,json={'detail':'unavailable'}))
        jump.fill('4');jump.press('Enter')
        expect(page.locator('#jump-status')).to_contain_text('erişilemiyor')
        expect(page.locator('#identity-short')).to_have_text('GK 146_3')
        page.unroute('**/api/hadith/146_4');jump.press('Enter')
        expect(page.locator('#identity-short')).to_have_text('GK 146_4')
        query.fill('158_1');query.press('Enter')
        expect(page.locator('#identity-short')).to_have_text('GK 158_1')
        print(f'PASS {width}x{height}: missing/invalid numbers preserve text+URL, Arabic/Persian digits, retry, explicit other-book GK')
    finally:page.close()


def races(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000})
    try:
        ready(page,url)
        page.evaluate('''window.realFetch=fetch;window.holdSearch=true;window.fetch=async(...args)=>{
          if(window.holdSearch&&String(args[0]).startsWith('/api/search?')){
            window.holdSearch=false;return new Promise((resolve,reject)=>window.rejectSearch=()=>reject(new Error('old transport failure')));
          }return window.realFetch(...args);
        }''')
        query=page.locator('#query');query.fill('الله');query.press('Enter')
        page.wait_for_function('typeof window.rejectSearch==="function"')
        query.fill('niyet');query.press('Enter')
        expect(page.locator('.result-button').first).to_be_visible()
        title=page.locator('#search-title').text_content();count=page.locator('.result-button').count()
        page.evaluate('window.rejectSearch()');page.wait_for_timeout(100)
        assert page.locator('#search-title').text_content()==title
        assert page.locator('.result-button').count()==count
        expect(page.locator('#retry-research-search')).not_to_be_visible()
        expect(page.locator('#error-banner')).not_to_be_visible()
        page.evaluate('window.holdSearch=true');query.fill('الله');query.press('Enter')
        page.wait_for_function('window.holdSearch===false')
        page.locator('[data-book-id="158"]').click()
        expect(page.locator('#identity-short')).to_have_text('GK 158_1')
        page.evaluate('window.rejectSearch()');page.wait_for_timeout(100)
        expect(page.locator('#search-results')).not_to_be_visible()
        expect(page.locator('#error-banner')).not_to_be_visible()
        ready(page,url)
        page.evaluate('''window.realFetch=fetch;window.heldTarget='/api/hadith/146_2';window.requestPaths=[];
          window.fetch=async(...args)=>{const path=String(args[0]);window.requestPaths.push(path);
            const r=await window.realFetch(...args);
            if(path===window.heldTarget){window.heldTarget=null;await new Promise(resolve=>window.releaseJump=resolve);}return r;
          }''')
        jump=page.locator('#jump-number');jump.fill('2');jump.press('Enter')
        page.wait_for_function('typeof window.releaseJump==="function"')
        page.evaluate('window.releaseOldJump=window.releaseJump');jump.fill('3');jump.press('Enter')
        expect(page.locator('#identity-short')).to_have_text('GK 146_3')
        page.evaluate('window.releaseOldJump()');page.wait_for_timeout(100)
        expect(page.locator('#identity-short')).to_have_text('GK 146_3')
        assert page.evaluate('window.requestPaths.filter(p=>p==="/api/hadith/146_3").length')==1
        page.evaluate("window.heldTarget='/api/hadith/146_5';window.releaseJump=null")
        jump.fill('5');jump.press('Enter');page.wait_for_function('typeof window.releaseJump==="function"')
        page.locator('#next-record').click()
        expect(page.locator('#identity-short')).to_have_text('GK 146_4')
        page.evaluate('window.releaseJump()');page.wait_for_timeout(100)
        expect(page.locator('#identity-short')).to_have_text('GK 146_4')
        page.evaluate("window.heldTarget='/api/hadith/146_6';window.releaseJump=null")
        query.fill('146_6');query.press('Enter');page.wait_for_function('typeof window.releaseJump==="function"')
        page.locator('#close-results').click();page.evaluate('window.releaseJump()');page.wait_for_timeout(100)
        expect(page.locator('#identity-short')).to_have_text('GK 146_4')
        expect(page.locator('#search-results')).not_to_be_visible()
        print('PASS races: stale errors ignored after query/book changes; latest jump/navigation/close wins; no duplicate core fetch')
    finally:page.close()


def timeout_recovery(browser,url):
    page=browser.new_page(viewport={'width':390,'height':844})
    held=[]
    try:
        ready(page,url)
        page.route('**/api/hadith/146_2',lambda r:held.append(r))
        jump=page.locator('#jump-number');jump.fill('2');jump.press('Enter')
        expect(page.locator('#jump-status')).to_contain_text('erişilemiyor',timeout=11000)
        expect(page.locator('#hadith-paper')).to_be_visible()
        expect(page.locator('#identity-short')).to_have_text('GK 146_1')
        for route in held:route.abort()
        held.clear();page.unroute('**/api/hadith/146_2');jump.press('Enter')
        expect(page.locator('#identity-short')).to_have_text('GK 146_2')
        page.locator('#query').fill('xyznotahadith92813');page.locator('#query').press('Enter')
        expect(page.locator('#results-list')).to_contain_text('bulunamadı')
        expect(page.locator('#retry-research-search')).not_to_be_visible()
        print('PASS timeout: bounded number lookup preserves text, retry recovers; real empty search stays distinct')
    finally:
        for route in held:route.abort()
        page.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--case',default='all',choices=['all','lifecycle','paging','numbers','races','timeout']);args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            for width,height in [(1440,1000),(390,844)]:
                if args.case in ('all','lifecycle'):lifecycle(browser,args.url,width,height)
                if args.case in ('all','numbers'):numbers(browser,args.url,width,height)
            if args.case in ('all','paging'):paging(browser,args.url)
            if args.case in ('all','races'):races(browser,args.url)
            if args.case in ('all','timeout'):timeout_recovery(browser,args.url)
        finally:browser.close()
