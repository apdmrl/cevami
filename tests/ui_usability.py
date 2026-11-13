"""Live usability contracts; isolated Chromium profile, no user window changes."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


def check(browser, url, width, height):
    page=browser.new_page(viewport={'width':width,'height':height})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto(url+'/?q=niyet')
        expect(page.locator('.suggestion .search-match').first).to_be_visible()
        expect(page.locator('.suggestion-book strong').first).not_to_be_empty()
        expect(page.locator('.suggestion-meta').first).to_contain_text('GK kaydı:')
        page.goto(url+'/hadith/146_1')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        page.locator('#record-identity summary').click()
        expect(page.locator('#record-identity')).to_contain_text('İç kayıt sırası')
        expect(page.locator('#record-identity')).to_contain_text('Metinde görünen numara')
        expect(page.locator('#record-identity')).to_contain_text('Kaynak indeksindeki atıf')
        expect(page.locator('#record-identity')).to_contain_text('146_1')
        page_ref=page.locator('#reference-details > div').filter(has_text='Cilt / sayfa').locator('dd')
        assert page_ref.evaluate('(el)=>getComputedStyle(el).direction') == 'ltr', 'Volume/page numbers appear reversed'
        expect(page.locator('#short-citation bdi')).to_have_attribute('dir','ltr')
        expect(page.locator('#short-citation bdi')).to_have_text('1 : 2')
        page.locator('#section-navigation a[href="#translations-panel"]').click()
        expect(page.locator('#translations-panel')).to_be_in_viewport()
        page.locator('#section-navigation a[href="#sanad-list"]').click()
        expect(page.locator('#sanad-list')).to_be_in_viewport()
        page.reload()
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        assert page.url.endswith('#sanad-list'), 'Section link disappeared on reload'
        expect(page.locator('#sanad-list')).to_be_focused()
        expect(page.locator('#sanad-list')).to_be_in_viewport()
        expect(page.locator('.chain .position-number').first).to_contain_text('1')
        page.locator('#section-navigation a[href="#source-details"]').click()
        expect(page.locator('#source-details')).to_be_in_viewport()
        page.locator('#section-navigation a[href="#arabic-text"]').click()
        expect(page.locator('#arabic-text')).to_be_in_viewport()
        # An unavailable index is distinct from an absent English translation.
        page.route('**/search-translations?language=en', lambda r:r.fulfill(json={'available':False,'items':[]}))
        page.locator('#read-en').click()
        expect(page.locator('#english-content')).to_contain_text('erişilemiyor')
        page.unroute('**/search-translations?language=en')
        page.goto(url+'/hadith/146_1?translation=en#sanad-list')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        expect(page.locator('#english-content .translation-text').first).to_be_attached()
        assert page.url.endswith('#sanad-list')
        expect(page.locator('#sanad-list')).to_be_focused()
        expect(page.locator('#sanad-list')).to_be_in_viewport()
        page.goto(url+'/hadith/146_6')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        problem=page.locator('.problem-text').first
        expect(problem).to_be_attached()
        assert problem.get_attribute('open') is None
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        print(f'PASS {width}x{height}: highlights, book names, identity, sections, unavailable vs absent, disputed text')
    finally: page.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8767');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            for size in [(1280,850),(390,700)]: check(browser,args.url,*size)
        finally: browser.close()
