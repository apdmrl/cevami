"""Read-only source-chain comparisons in an isolated browser profile."""
import argparse
import json

from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=15000)


def assert_column(column, row):
    expect(column.get_by_role('heading', name=f"Sened {row['sanad_id']}", exact=True)).to_be_visible()
    assert column.locator('.narrator-source-position').all_text_contents() == [f"{m['position'] + 1}. sıra" for m in row['members']]
    assert column.locator('.sanad-compare-name').all_text_contents() == [m['label'] or 'Kaynakta ravi kimliği yok' for m in row['members']]
    expect(column.locator('li')).to_have_count(len(row['members']))
    expect(column.locator('button')).to_have_count(sum(m['kind'] == 'narrator' for m in row['members']))
    assert column.locator('.sanad-compare-marker button').count() == 0


def check(browser, url, width, height, reading=False):
    page = browser.new_page(viewport={'width': width, 'height': height})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        data = page.request.get(url + '/api/hadith/146_3/sanads').json()
        first, second = data['items'][:2]
        page.goto(url + ('/hadith/146_3' if reading else '/research?hadith=146_3'))
        toggle = page.locator('#compare-sanads')
        expect(toggle).to_be_enabled()
        expect(page.locator('#sanad-comparison')).not_to_be_visible()
        toggle.focus()
        toggle.press('Enter')
        expect(page.locator('#sanad-compare-first')).to_be_focused()
        expect(toggle).to_have_attribute('aria-expanded', 'true')
        page.locator('#section-navigation a[href="#sanad-list"]').click()
        expect(page.locator('#sanad-comparison-title')).to_be_in_viewport()
        expect(page.locator('#sanad-comparison')).to_be_focused()
        columns = page.locator('.sanad-comparison-column')
        expect(columns).to_have_count(2)
        assert_column(columns.nth(0), first)
        assert_column(columns.nth(1), second)
        ids = lambda row: {m['source_id'] for m in row['members'] if m['kind'] == 'narrator' and m['source_id'] is not None}
        shared = ids(first) & ids(second)
        expect(page.locator('#sanad-comparison-status')).to_contain_text(f'Ortak kaynak ravi kimliği: {len(shared)}')
        expected = sum(m['kind'] == 'narrator' and m['source_id'] in shared for row in [first, second] for m in row['members'])
        expect(page.locator('.sanad-shared-key')).to_have_count(expected)
        if shared:
            common_id = next(iter(shared))
            expect(page.get_by_role('button', name=f'Ortak kaynak ravi kimliği: {common_id}')).to_have_count(
                sum(m['kind'] == 'narrator' and m['source_id'] == common_id for row in [first, second] for m in row['members']))
        expect(page.locator('#sanad-comparison-coverage')).to_contain_text(f"Yüklenen {len(data['items'])} / kayıtta {data['total']} sened")
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')

        # A source marker remains in place; the next person opens source position 3.
        person = next(m for m in first['members'] if m['kind'] == 'narrator' and m['position'] >= 2)
        button = columns.nth(0).get_by_role('button', name=f"Ravi bilgisi: {person['label']}, sened {first['sanad_id']}, {person['position'] + 1}. sıra")
        button.click()
        expect(page.locator('#narrator-context-label')).to_have_text(f"Sened {first['sanad_id']} · {person['position'] + 1}. sıra · GK 146_3")
        expect(page.locator('.narrator-profile')).to_have_attribute('aria-busy', 'false')
        page.keyboard.press('Escape')
        expect(button).to_be_focused()

        page.locator('#sanad-compare-second').select_option(str(first['sanad_id']))
        expect(columns).to_have_count(0)
        expect(page.locator('#sanad-comparison-status')).to_have_text('İki farklı sened seçin.')
        expect(page.locator('#sanad-compare-second')).to_have_value(str(first['sanad_id']))
        page.locator('#sanad-compare-second').select_option(str(second['sanad_id']))
        expect(columns).to_have_count(2)
        toggle.click()
        expect(page.locator('#sanad-comparison')).not_to_be_visible()
        expect(toggle).to_be_focused()
        toggle.press('Tab')
        assert page.evaluate("!document.activeElement.closest('#sanad-comparison')")

        page.goto(url + '/research?hadith=146_1')
        expect(page.locator('.sanad-item')).to_have_count(1)
        expect(toggle).to_be_disabled()
        expect(page.locator('#sanad-comparison')).not_to_be_visible()
        assert not errors, errors
        print(f'PASS {width}x{height} {"reading" if reading else "research"}: source order/markers, ID-only shared count, exact narrator context, same-chain warning, keyboard focus and single-chain reset')
    finally:
        page.close()


def paging(browser, url):
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    try:
        first_page = page.request.get(url + '/api/hadith/1006_33/sanads').json()
        second_page = page.request.get(url + '/api/hadith/1006_33/sanads?offset=20').json()
        assert len(first_page['items']) == 20 and first_page['total'] == 24
        page.goto(url + '/research?hadith=1006_33')
        expect(page.locator('#compare-sanads')).to_be_enabled()
        page.locator('#compare-sanads').click()
        left, right = first_page['items'][19], first_page['items'][18]
        page.locator('#sanad-compare-first').select_option(str(left['sanad_id']))
        page.locator('#sanad-compare-second').select_option(str(right['sanad_id']))
        pattern = '**/api/hadith/1006_33/sanads?offset=20'
        page.route(pattern, lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'test unavailable'})))
        page.locator('#more-sanads').click()
        expect(page.locator('#sanad-page-error')).to_be_visible()
        expect(page.locator('#sanad-compare-first option')).to_have_count(20)
        expect(page.locator('#sanad-comparison-coverage')).to_contain_text('Yüklenen 20 / kayıtta 24')
        page.unroute(pattern)
        held = []
        page.route(pattern, lambda route: held.append(route))
        page.locator('#more-sanads').click()
        # While the next page is pending, inspect an already selected source.
        trigger = page.locator('.sanad-comparison-column').first.locator('button').first
        trigger.focus()
        trigger.press('Enter')
        expect(page.locator('.narrator-profile')).to_have_attribute('aria-busy', 'false')
        assert len(held) == 1
        held[0].fulfill(status=200, content_type='application/json', body=json.dumps(second_page))
        expect(page.locator('#sanad-compare-first option')).to_have_count(24)
        page.keyboard.press('Escape')
        expect(trigger).to_be_focused()
        expect(page.locator('#sanad-compare-first')).to_have_value(str(left['sanad_id']))
        expect(page.locator('#sanad-compare-second')).to_have_value(str(right['sanad_id']))
        expect(page.locator('#sanad-comparison-coverage')).to_contain_text('Yüklenen 24 / kayıtta 24')
        assert_column(page.locator('.sanad-comparison-column').nth(0), left)
        assert_column(page.locator('.sanad-comparison-column').nth(1), right)
        late_row = second_page['items'][-1]
        page.locator('#sanad-compare-second').select_option(str(late_row['sanad_id']))
        assert_column(page.locator('.sanad-comparison-column').nth(1), late_row)
        print('PASS paging: 20/24 source coverage, failed page keeps comparison, same selections after retry, all24 source options usable')
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
            check(browser, args.url, 1440, 1000, reading=True)
            paging(browser, args.url)
        finally:
            browser.close()
