"""Delayed real English responses must never replace another hadith's text."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8766')
    args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            page=browser.new_page()
            page.add_init_script('''const realFetch = window.fetch;
              window.fetch = (...args) => realFetch(...args).then(response => {
                if (!window.delayTranslations) return response;
                const url = String(args[0]);
                const delay = url.includes('/api/hadith/146_2') && !url.includes('search-translations') ? 800
                  : url.includes('/api/hadith/146_1/search-translations') ? 2500 : 0;
                return new Promise(resolve => setTimeout(() => resolve(response), delay));
              });''')
            page.goto(args.url+'/hadith/146_1')
            expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
            page.evaluate('window.delayTranslations=true')
            page.locator('#next-record').click()
            expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','true')
            page.locator('#read-en').click()
            expect(page.locator('#hadith-number')).to_have_text('2')
            expected = page.request.get(args.url+'/api/hadith/146_2/search-translations?language=en').json()['items'][0]['text']
            text=page.locator('#english-content .translation-text').first
            expect(text).to_have_text(expected)
            page.wait_for_timeout(3000)
            expect(text).to_have_text(expected)
            expect(page.locator('#hadith-number')).to_have_text('2')
            print('PASS: delayed previous English response cannot replace current hadith')
        finally: browser.close()
