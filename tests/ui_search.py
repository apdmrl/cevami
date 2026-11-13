"""Live end-to-end search/reader checks; optional playwright, isolated profile."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


def run(browser, url, width, height):
    page = browser.new_page(viewport={'width':width,'height':height})
    errors = []
    page.on('pageerror',lambda e: errors.append(str(e)))
    try:
        page.goto(url+'/')
        query = page.get_by_role('combobox',name='Hadis ara')
        expect(page.locator('.workspace')).to_have_count(0)
        query.fill('niyet')
        first = page.locator('.suggestion').first
        expect(first).to_be_visible()
        expect(page.locator('.suggestion-snippet').first).to_have_attribute('lang','tr')
        query.press('ArrowDown')
        expect(first).to_have_attribute('aria-selected','true')
        href = first.get_attribute('href')
        query.press('Enter')
        page.wait_for_url('**/hadith/**')
        expect(page.locator('#translations-panel')).to_be_visible()
        expect(page.locator('#arabic-text .inline-narrator').first).to_be_visible()
        expect(page.locator('#open-research')).to_have_attribute('href',__import__('re').compile(r'/research\?hadith=\d+_\d+'))
        direct_url = page.url
        page.reload()
        expect(page.locator('#translations-panel')).to_be_visible()
        page.go_back()
        expect(query).to_have_value('niyet')
        expect(first).to_be_visible()
        page.go_forward()
        expect(page.locator('#arabic-text')).to_be_visible()
        page.goto(url+'/?q=intentions&language=en')
        expect(first).to_be_visible()
        expect(page.locator('.suggestion-snippet').first).to_have_attribute('lang','en')
        first.click()
        expect(page.locator('#english-content .translation-text').first).to_be_visible()
        page.goto(url+'/?q=إنما%20الأعمال&language=ar')
        expect(first).to_be_visible()
        expect(page.locator('.suggestion-snippet').first).to_have_attribute('dir','rtl')
        page.goto(url+'/?q=146_1')
        expect(first).to_contain_text('146_1')
        page.goto(url+'/hadith/146_1')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        expect(page.locator('#hadith-number')).to_have_text('1')
        page.locator('#next-record').click()
        expect(page.locator('#hadith-number')).to_have_text('2')
        page.locator('#read-en').click()
        expect(page.locator('#english-content')).to_be_visible()
        page.go_back()
        expect(page.locator('#hadith-number')).to_have_text('1')
        expect(page.locator('#turkish-content')).to_be_visible()
        page.goto(url+'/research?hadith=146_1')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        page.locator('#translation-toggle').click()
        page.locator('#read-en').click()
        expect(page.locator('#english-content .translation-text').first).to_contain_text('intentions')
        page.locator('#next-record').click()
        expect(page.locator('#hadith-number')).to_have_text('2')
        expect(page.locator('#english-content .translation-text').first).to_contain_text('Inspiration')
        page.goto(url+'/?q=zzzzzznoresult')
        expect(page.locator('#search-status')).to_contain_text('bulunamadı')
        # A genuinely old response arrives after a newer query, despite abort.
        page.add_init_script('''const realFetch=window.fetch;
          window.fetch=(...args)=>realFetch(...args).then(response=>
            String(args[0]).includes('q=niyet') ? new Promise(resolve=>setTimeout(()=>resolve(response),900)) : response);''')
        page.goto(url+'/')
        query.fill('niyet')
        page.wait_for_timeout(350)
        query.fill('intentions')
        expect(first).to_be_visible()
        page.wait_for_timeout(1100)
        expect(page.locator('.suggestion-snippet').first).to_have_attribute('lang','en')
        query.fill('')
        expect(page.locator('#suggestion-panel')).not_to_be_visible()
        # Transport failure is visible, and submitting again recovers.
        page.route('**/api/search?**',lambda route:route.abort())
        query.fill('mercy')
        expect(page.locator('#search-status')).to_contain_text('yapılamıyor')
        page.unroute('**/api/search?**')
        form_button = page.locator('#home-search button[type=submit]')
        form_button.click()
        expect(first).to_be_visible()
        page.goto(url+'/research?hadith=146_1004')
        expect(page.locator('#hadith-number')).to_have_text('1004')
        expect(page.locator('.library')).to_be_attached()
        assert not errors, errors
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
        print(f'PASS {width}x{height}: TR/EN/AR, suggestions, direct URL, history, races, empty/error/retry, research')
    finally:
        page.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8766')
    args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            for size in [(1280,850),(390,700)]: run(browser,args.url,*size)
        finally: browser.close()
