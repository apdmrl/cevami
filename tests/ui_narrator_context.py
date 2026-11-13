"""Exercise source-chain context and keyboard focus in an isolated browser profile."""
import argparse
import json

from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=15000)


def check(browser, url, width, height):
    page = browser.new_page(viewport={'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        source = page.request.get(url + '/api/hadith/146_3/sanads').json()['items'][0]
        members = source['members']
        people = [member for member in members if member['kind'] == 'narrator']
        assert any(member['kind'] == 'structural_marker' for member in members)
        page.goto(url + '/research?hadith=146_3')
        card = page.locator('.sanad-item').first
        card.locator('button.chain-node').first.click()
        body = page.locator('#narrator-content')
        profile = page.locator('.narrator-profile')
        position = page.locator('#narrator-context-label')
        expect(profile).to_have_attribute('aria-busy', 'false')
        expect(position).to_contain_text(f"Sened {source['sanad_id']} · 1. sıra")
        page.get_by_text('Kaynak zincirinin tamamı', exact=True).click()
        expect(page.locator('.narrator-context-members > li')).to_have_count(len(members))
        expect(page.locator('.narrator-context-person')).to_have_count(len(people))
        expect(page.locator('.narrator-context-person[aria-current="true"]')).to_have_count(1)
        assert page.locator('.narrator-context-marker button').count() == 0

        # Traverse both ends with the keyboard; the disabled control must not lose focus.
        page.locator('.narrator-context-person').last.click()
        expect(profile).to_have_attribute('aria-busy', 'false')
        page.locator('#previous-narrator').focus()
        page.locator('#previous-narrator').press('Enter')
        expect(profile).to_have_attribute('aria-busy', 'false')
        page.locator('#next-narrator').focus()
        page.locator('#next-narrator').press('Enter')
        expect(position).to_contain_text(f"{people[-1]['position'] + 1}. sıra")
        expect(page.locator('#next-narrator')).to_be_disabled()
        assert page.evaluate('document.activeElement.id') == 'narrator-content'
        expect(profile).to_have_attribute('aria-busy', 'false')
        page.get_by_text('Kaynak zincirinin tamamı', exact=True).click()
        page.locator('.narrator-context-person').first.click()
        expect(profile).to_have_attribute('aria-busy', 'false')
        page.locator('#next-narrator').click()
        expect(position).to_contain_text(f"{people[1]['position'] + 1}. sıra")
        expect(profile).to_have_attribute('aria-busy', 'false')
        page.locator('#previous-narrator').focus()
        page.locator('#previous-narrator').press('Enter')
        expect(position).to_contain_text('1. sıra')
        expect(page.locator('#previous-narrator')).to_be_disabled()
        assert page.evaluate('document.activeElement.id') == 'narrator-content'
        expect(profile).to_have_attribute('aria-busy', 'false')

        # A failed profile leaves the already loaded source list available.
        pattern = f"**/api/narrator/{people[1]['source_id']}"
        page.route(pattern, lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'test unavailable'})))
        page.locator('#next-narrator').click()
        retry = page.get_by_role('button', name='Ravi kaydını yeniden yükle', exact=True)
        expect(retry).to_be_visible()
        expect(page.get_by_text('Kaynak zincirinin tamamı', exact=True)).to_be_visible()
        expect(page.locator('.narrator-context-members > li')).to_have_count(len(members))
        retry.focus()
        page.unroute(pattern)
        retry.press('Enter')
        expect(profile).to_have_attribute('aria-busy', 'false')
        expect(position).to_contain_text(f"{people[1]['position'] + 1}. sıra")
        assert page.evaluate('document.activeElement.id') == 'narrator-content'
        body.press('End')
        for selector in ('#close-narrator', '#narrator-context'):
            box = page.locator(selector).bounding_box()
            assert box and box['y'] >= 0 and box['y'] + box['height'] <= height
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.keyboard.press('Escape')
        expect(page.locator('#narrator-dialog')).not_to_be_visible()

        # A text link does not guess a branch, even on the same hadith.
        page.locator('#arabic-text .inline-narrator').first.click()
        expect(page.locator('#narrator-context')).not_to_be_visible()
        expect(profile).to_have_attribute('aria-busy', 'false')
        page.locator('#close-narrator').click()
        assert not errors, errors
        print(f'PASS {width}x{height}: exact source list/markers, both keyboard boundaries, error+retry focus, fixed controls and inline reset')
    finally:
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe', headless=True)
        try:
            for width, height in [(1440, 1000), (390, 844), (700, 390)]:
                check(browser, args.url, width, height)
        finally:
            browser.close()
