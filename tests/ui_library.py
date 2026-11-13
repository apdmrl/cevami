"""Library keyboard access and real-source asynchronous navigation."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


def ready(page, url):
    page.goto(url+'/research?hadith=146_1')
    expect(page.locator('.book-button')).to_have_count(60)
    expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')


def mobile(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        ready(page,url)
        trigger=page.locator('#mobile-library'); library=page.locator('#library')
        assert library.evaluate('(e)=>e.inert'), 'closed mobile library must be inert'
        trigger.focus();page.keyboard.press('Tab')
        assert not page.evaluate('document.activeElement.closest("#library")')
        trigger.click()
        expect(library).to_have_attribute('role','dialog')
        expect(trigger).to_have_attribute('aria-expanded','true')
        expect(page.locator('#book-search')).to_be_focused()
        assert page.locator('#reading').evaluate('(e)=>e.inert')
        page.locator('#close-library').focus();page.keyboard.press('Shift+Tab')
        expect(page.locator('#more-books')).to_be_focused()
        page.keyboard.press('Tab');expect(page.locator('#close-library')).to_be_focused()
        bounds=library.bounding_box()
        assert bounds['y']>=71 and bounds['y']+bounds['height']<=height+1
        page.locator('#book-list').hover();page.mouse.wheel(0,500)
        page.wait_for_function('document.querySelector("#book-list").scrollTop>0')
        initial=page.evaluate('scrollY')
        page.mouse.move(width-30,height-30);page.mouse.wheel(0,500)
        page.wait_for_timeout(200);assert page.evaluate('scrollY')==initial
        page.keyboard.press('Escape');expect(trigger).to_be_focused()
        expect(trigger).to_have_attribute('aria-expanded','false')
        trigger.click();page.locator('#library-backdrop').click(position={'x':width-30,'y':height-30})
        expect(trigger).to_be_focused()
        trigger.click();page.set_viewport_size({'width':1280,'height':900})
        expect(library).not_to_have_attribute('role','dialog')
        assert not library.evaluate('(e)=>e.inert')
        assert not page.locator('#reading').evaluate('(e)=>e.inert')
        page.locator('#library-nav').click();expect(page.locator('#book-search')).to_be_focused()
        page.locator('#book-search').focus();page.set_viewport_size({'width':width,'height':height})
        expect(trigger).to_be_focused();assert library.evaluate('(e)=>e.inert')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        print(f'PASS {width}x{height}: hidden focus, modal keyboard/backdrop, scroll, responsive reset')
    finally:page.close()


def selection(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000})
    try:
        ready(page,url)
        page.evaluate('''window.realFetch=window.fetch;window.fetch=async (...args)=>{
          const response=await window.realFetch(...args);
          if(String(args[0]).startsWith('/api/books/158/hadiths'))await new Promise(r=>setTimeout(r,1800));
          return response;
        };''')
        page.locator('[data-book-id="158"]').click()
        page.locator('[data-book-id="146"]').click()
        expect(page.locator('#identity-short')).to_have_text('GK 146_1')
        page.wait_for_timeout(2200)
        expect(page.locator('#identity-short')).to_have_text('GK 146_1')
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#mobile-library').click();page.locator('[data-book-id="158"]').click()
        page.keyboard.press('Escape');page.wait_for_timeout(2200)
        expect(page.locator('#identity-short')).to_have_text('GK 146_1')
        expect(page.locator('#mobile-library')).to_be_focused()
        print('PASS selection: latest book wins; Escape cancels pending selection')
    finally:page.close()


def listing(browser,url):
    page=browser.new_page(viewport={'width':1440,'height':1000})
    try:
        ready(page,url)
        page.evaluate('''window.realFetch=window.fetch;window.fetch=async (...args)=>{
          const path=String(args[0]);const response=await window.realFetch(...args);
          if(path.startsWith('/api/books?')&&new URL(path,location.origin).searchParams.get('q')==='بخاري')await new Promise(r=>setTimeout(r,1800));
          return response;
        };''')
        field=page.locator('#book-search')
        field.fill('بخاري');field.press('Enter');field.fill('مسلم');field.press('Enter')
        actual=page.request.get(url+'/api/books?limit=60&offset=0&q=مسلم').json()
        page.wait_for_timeout(2200)
        assert page.locator('.book-button').evaluate_all('(rows)=>rows.map(e=>e.dataset.bookId)')==[b['book_id'] for b in actual['items']]
        field.fill('');field.press('Enter');expect(page.locator('.book-button')).to_have_count(60)
        page.evaluate('''window.pageOffsets=[];window.failPage=true;window.fetch=async (...args)=>{
          const path=String(args[0]);
          if(path.startsWith('/api/books?')&&new URL(path,location.origin).searchParams.get('offset')!=='0'){
            window.pageOffsets.push(new URL(path,location.origin).searchParams.get('offset'));
            await new Promise(r=>setTimeout(r,300));
            if(window.failPage){window.failPage=false;return new Response('{"detail":"test unavailable"}',{status:503});}
          }return window.realFetch(...args);
        };''')
        page.locator('#more-books').click()
        expect(page.locator('#retry-books')).to_be_visible()
        expect(page.locator('.book-button')).to_have_count(60)
        page.locator('#retry-books').click()
        page.evaluate('document.querySelector("#more-books").click()')
        expect(page.locator('.book-button')).to_have_count(120)
        assert page.evaluate('window.pageOffsets')==['60','60']
        assert len(set(page.locator('.book-button').evaluate_all('(rows)=>rows.map(e=>e.dataset.bookId)')))==120
        print('PASS listing: latest query, local error, same-page retry, duplicate click guard')
    finally:page.close()


def recovery(browser,url):
    page=browser.new_page(viewport={'width':390,'height':844})
    try:
        page.route('**/api/books?**',lambda route:route.fulfill(status=503,json={'detail':'unavailable'}))
        page.goto(url+'/research?hadith=146_1')
        page.locator('#mobile-library').click()
        expect(page.locator('#book-status')).to_contain_text('yüklenemedi')
        expect(page.locator('.book-button')).to_have_count(0)
        expect(page.locator('#library-count')).not_to_have_text('0 eser')
        page.unroute('**/api/books?**');page.locator('#retry-books').click()
        expect(page.locator('.book-button')).to_have_count(60)
        page.route('**/api/books/158/hadiths?**',lambda route:route.fulfill(status=503,json={'detail':'unavailable'}))
        page.locator('[data-book-id="158"]').click()
        expect(page.locator('#book-selection-status')).to_contain_text('yüklenemedi')
        expect(page.locator('#retry-book-selection')).to_be_visible()
        expect(page.locator('#library')).to_have_attribute('role','dialog')
        expect(page.locator('#error-banner')).not_to_be_visible()
        page.unroute('**/api/books/158/hadiths?**');page.locator('#retry-book-selection').click()
        expect(page.locator('#identity-short')).to_have_text('GK 158_1')
        expect(page.locator('#mobile-library')).to_be_focused()
        expect(page.locator('#library')).to_have_attribute('aria-hidden','true')
        page.locator('#mobile-library').click()
        field=page.locator('#book-search');field.fill('xyznotabook9283');field.press('Enter')
        expect(page.locator('#book-status')).to_contain_text('bulunamadı')
        expect(page.locator('#library-count')).to_have_text('0 eser')
        expect(page.locator('#retry-books')).not_to_be_visible()
        page.keyboard.press('Escape')
        print('PASS recovery: mobile list/selection errors, retry, accepted selection focus, genuine zero results')
    finally:page.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--case',default='all',choices=['all','mobile','selection','listing','recovery']);args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            if args.case in ('all','mobile'):
                for size in [(390,844),(700,390)]:mobile(browser,args.url,*size)
            if args.case in ('all','selection'):selection(browser,args.url)
            if args.case in ('all','listing'):listing(browser,args.url)
            if args.case in ('all','recovery'):recovery(browser,args.url)
        finally:browser.close()
