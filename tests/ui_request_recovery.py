"""Read-only request recovery checks in isolated browser profiles."""
import argparse
import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=15000)


def stall_transport(page, fragment):
    page.evaluate('''fragment=>{window.recoveryTransport=window.fetch;
      window.fetch=(input,options)=>String(input).includes(fragment)
        ? new Promise((resolve,reject)=>options.signal.addEventListener('abort',
            ()=>reject(new DOMException('test stalled transport','AbortError')),{once:true}))
        : window.recoveryTransport(input,options); }''', fragment)


def keyboard(browser,url,width,height,case):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        page.goto(url+'/?q=niyet')
        query=page.locator('#home-query');results=page.locator('.suggestion')
        expect(results).to_have_count(12)
        if case=='escape':
            original_url=page.url
            query.focus();query.press('Escape')
            assert query.input_value()=='niyet','Escape cleared the submitted query'
            assert page.url==original_url
            expect(results).to_have_count(12)
            expect(page.locator('#suggestion-panel')).not_to_be_visible()
            query.press('ArrowDown');expect(results.first).to_be_visible()
            query.press('Escape')
            stall_transport(page,'q=niyet')
            submit=page.locator('#home-search button[type=submit]');submit.click()
            expect(page.locator('#suggestions')).to_have_attribute('aria-busy','true')
            submit.press('Escape')
            assert page.locator('#suggestions').get_attribute('aria-busy')=='false','Escape from submit did not cancel pending search'
            page.evaluate('window.fetch=window.recoveryTransport')
        elif case=='controls':
            stall_transport(page,'q=niyet')
            submit=page.locator('#home-search button[type=submit]');submit.click()
            expect(page.locator('#suggestions')).to_have_attribute('aria-busy','true')
            submit.press('Escape')
            assert page.locator('#suggestions').get_attribute('aria-busy')=='false','Escape from submit did not cancel pending search'
            page.evaluate('window.fetch=window.recoveryTransport')
        elif case=='focus':
            more=page.locator('#home-more');more.focus();more.press('Enter')
            expect(query).to_be_focused()
            expect(results).to_have_count(24)
            total=page.request.get(url+'/api/search?q=niyet&limit=1').json()['total']
            while more.is_visible():
                count=results.count();more.focus();more.press('Enter')
                expect(query).to_be_focused()
                expect(results).to_have_count(min(count+12,total))
            expect(query).to_be_focused()
        else:
            page.route('**/api/search?**',lambda route:route.fulfill(status=503,json={'detail':'unavailable'}))
            page.locator('#home-more').click()
            retry=page.locator('#home-page-retry')
            expect(retry).to_be_in_viewport()
            expect(page.locator('#home-page-status')).to_be_in_viewport()
            expect(page.locator('#home-page-status')).to_contain_text('yüklenemedi')
            expect(results).to_have_count(12)
            retry.focus();retry.press('Escape')
            expect(page.locator('#suggestion-panel')).not_to_be_visible()
            expect(query).to_be_focused()
        print(f'PASS {width}x{height} {case}: native query/button keyboard and viewport recovery',flush=True)
    finally:page.close()


def home(browser, url, width, height):
    page = browser.new_page(viewport={'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(url + '/?q=niyet')
        query, results = page.locator('#home-query'), page.locator('.suggestion')
        expect(results).to_have_count(12)
        original = results.all_text_contents()
        query.press('ArrowUp')
        expect(query).to_have_attribute('aria-activedescendant', 'suggestion-11')
        attempts = []
        pattern = '**/api/search?**'

        def fail_page(route):
            attempts.append(route.request.url)
            route.fulfill(status=503, json={'detail': 'test unavailable'})

        page.route(pattern, fail_page)
        page.locator('#home-more').click()
        retry = page.locator('#home-page-retry')
        expect(retry).to_be_visible()
        assert results.all_text_contents() == original
        assert query.get_attribute('aria-activedescendant') is None
        expect(retry).to_be_in_viewport()
        expect(page.locator('#home-page-status')).to_be_in_viewport()
        page.unroute_all(behavior='ignoreErrors')
        page.on('request', lambda request: attempts.append(request.url) if '/api/search?' in request.url else None)
        retry.focus()
        retry.press('Enter')
        expect(results).to_have_count(24)
        assert results.all_text_contents()[:12] == original
        expect(query).to_be_focused()
        assert parse_qs(urlparse(attempts[0]).query)['offset'] == ['12']
        assert parse_qs(urlparse(attempts[1]).query)['offset'] == ['12']

        retry = page.locator('#home-retry')
        stall_transport(page, 'q=mercy')
        query.fill('mercy')
        expect(retry).to_be_visible(timeout=12000)
        expect(page.locator('#search-status')).to_contain_text('uzun sürdü')
        expect(page.locator('#suggestions')).to_have_attribute('aria-busy', 'false')
        expect(results).to_have_count(0)
        page.evaluate('window.fetch=window.recoveryTransport')
        retry.click()
        expect(results.first).to_be_visible()
        expect(retry).not_to_be_visible()
        results.first.focus()
        results.first.press('Escape')
        expect(query).to_be_focused()
        expect(page.locator('#suggestion-panel')).not_to_be_visible()
        query.press('ArrowDown')
        expect(page.locator('#suggestion-panel')).to_be_visible()

        # Delay a fully read real response, so abort alone cannot discard it.
        page.evaluate('''window.recoveryFetch=window.fetch;
          window.fetch=async(...args)=>{const response=await window.recoveryFetch(...args);
            if(String(args[0]).includes('q=niyet')){const text=await response.text();
              return new Promise(resolve=>window.releaseRecoveryHome=()=>resolve(new Response(text,{status:response.status,headers:response.headers})));}
            return response;};''')
        query.fill('niyet')
        page.wait_for_function('typeof window.releaseRecoveryHome === "function"')
        query.press('Escape')
        page.evaluate('window.releaseRecoveryHome();window.fetch=window.recoveryFetch')
        page.wait_for_timeout(150)
        expect(page.locator('#suggestion-panel')).not_to_be_visible()
        expect(retry).not_to_be_visible()
        expect(page.locator('#suggestions')).to_have_attribute('aria-busy', 'false')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        print(f'PASS {width}x{height} home: exact page retry/source retention,8s deadline, focus, ArrowUp and Escape vs real late data', flush=True)
    finally:
        page.close()


def opinions(browser, url, width, height):
    page = browser.new_page(viewport={'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        profile = page.request.get(url + '/api/narrator/6817').json()
        offset, total = len(profile['opinions']), profile['opinions_total']
        assert offset < total
        page.goto(url + '/research?hadith=146_1')
        trigger = page.locator('.sanad-item').first.locator('button.chain-node').first
        trigger.click()
        expect(page.locator('.narrator-profile')).to_have_attribute('aria-busy', 'false')
        originals = page.locator('.opinion-original')
        expect(originals).to_have_count(offset)
        assert originals.all_text_contents() == [row['opinion'] for row in profile['opinions']]
        more, status = page.locator('.opinion-more'), page.locator('.opinion-page-status')
        pattern = f'**/api/narrator/6817/opinions?offset={offset}'
        page.route(pattern, lambda route: route.fulfill(status=503, json={'detail': 'test unavailable'}))
        more.click()
        expect(status).to_be_visible()
        expect(originals).to_have_count(offset)
        expect(more).to_be_enabled()
        page.unroute_all(behavior='ignoreErrors')

        stall_transport(page, f'/api/narrator/6817/opinions?offset={offset}')
        more.focus()
        more.press('Enter')
        expect(page.locator('#narrator-content')).to_be_focused()
        expect(status).to_be_visible(timeout=12000)
        expect(status).to_contain_text('yüklenemedi')
        expect(more).to_have_attribute('aria-busy', 'false')
        expect(originals).to_have_count(offset)
        assert originals.all_text_contents() == [row['opinion'] for row in profile['opinions']]
        page.evaluate('window.fetch=window.recoveryTransport')
        more.focus()
        more.press('Enter')
        expect(originals).to_have_count(total)
        expect(more).not_to_be_visible()
        expect(page.locator('#narrator-content')).to_be_focused()
        expect(status).not_to_be_visible()

        page.keyboard.press('Escape')
        trigger.click()
        expect(page.locator('.narrator-profile')).to_have_attribute('aria-busy', 'false')
        held = []
        page.route(pattern, lambda route: held.append(route))
        more.click()
        expect(more).to_have_attribute('aria-busy', 'true')
        page.locator('#close-narrator').click()
        assert len(held) == 1
        held[0].fulfill(status=503, json={'detail': 'CLOSED ERROR'})
        page.unroute_all(behavior='ignoreErrors')
        trigger.click()
        expect(page.locator('.narrator-profile')).to_have_attribute('aria-busy', 'false')
        expect(status).not_to_be_visible()
        expect(originals).to_have_count(offset)
        expect(page.locator('#close-narrator')).to_be_in_viewport()
        page.keyboard.press('Escape')
        expect(trigger).to_be_focused()
        assert not errors, errors
        print(f'PASS {width}x{height} opinions: real source30/41,503+timeout same offset, focus during/after paging, close/reopen late error', flush=True)
    finally:
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--case',default='all',choices=['all','original','escape','controls','focus','nearby'])
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe', headless=True)
        try:
            for width, height in [(1440, 1000), (390, 844)]:
                if args.case in ('all','original'):
                    home(browser, args.url, width, height)
                    opinions(browser, args.url, width, height)
                for case in ['escape','controls','focus','nearby']:
                    if args.case in ('all',case):keyboard(browser,args.url,width,height,case)
        finally:
            browser.close()
