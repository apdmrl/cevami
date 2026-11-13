"""Source-bound comparison and real copy actions with a clipboard boundary."""
import argparse
from playwright.sync_api import sync_playwright, expect
expect.set_options(timeout=15000)


def compare(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        page.goto(url+'/hadith/146_1')
        rows=page.request.get(url+'/api/hadith/146_1/components').json()['items']
        expect(page.locator('.translation-component').first).to_be_attached()
        toggle=page.locator('#compare-components')
        expect(toggle).to_be_visible(timeout=3000)
        toggle.click();expect(toggle).to_have_attribute('aria-pressed','true')
        for row in rows:
            if row.get('arabic_text'):
                original=page.locator('#component-arabic-'+row['id'])
                expect(original).to_be_visible()
                assert original.text_content()==row['arabic_text']
        pair=page.locator('.component-pair').first
        tr=pair.locator('.component-rendering').bounding_box()
        ar=pair.locator('.component-arabic-preview').bounding_box()
        if width>=1200: assert ar['x']>tr['x']+tr['width']-1
        else: assert ar['y']>tr['y']
        page.mouse.move(ar['x']+10,ar['y']+10)
        page.mouse.move(5,5)
        expect(page.locator('.component-arabic-text').first).to_be_visible()
        page.locator('#read-en').click();expect(toggle).not_to_be_visible()
        page.locator('#read-tr').click();expect(toggle).to_have_attribute('aria-pressed','true')
        toggle.click();expect(page.locator('.component-arabic-text').first).not_to_be_visible()
        toggle.click();page.locator('#next-record').click()
        expect(page.locator('#hadith-number')).to_have_text('2')
        expect(page.locator('#compare-toolbar')).to_be_visible()
        expect(toggle).to_have_attribute('aria-pressed','false')
        page.goto(url+'/hadith/146_4412')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        expect(page.locator('#auxiliary-status')).not_to_be_visible()
        expect(page.locator('#compare-toolbar')).not_to_be_visible()
        page.goto(url+'/hadith/146_6')
        expect(page.locator('.problem-text').first).to_be_attached()
        page.locator('#compare-components').click()
        for problem in page.locator('.problem-text').all():
            assert problem.get_attribute('open') is None
            expect(problem.locator('.component-translation,.translation-text').first).not_to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        print(f'PASS {width}x{height}: exact Arabic, paired layout, hover/language/reset, absent and disputed sources')
    finally:page.close()


def copying(browser,url,width,height):
    page=browser.new_page(viewport={'width':width,'height':height})
    try:
        page.add_init_script('''window.copyMode='success';
          Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text)=>{
            if(window.copyMode==='deny')throw new DOMException('Denied','NotAllowedError');
            if(window.copyMode==='delay')return new Promise((resolve,reject)=>{window.rejectCopy=()=>reject(new DOMException('Denied','NotAllowedError'))});
            window.copiedText=text;
          }}});''')
        page.goto(url+'/research?hadith=146_1&q=niyet&book_id=146')
        expect(page.locator('#hadith-paper')).to_have_attribute('aria-busy','false')
        page.locator('#translation-toggle').click();page.locator('#read-en').click()
        page.locator('#section-navigation a[href="#sanad-list"]').click()
        page.locator('#copy-link').click()
        expected=url+'/hadith/146_1?translation=en#sanad-list'
        assert page.evaluate('window.copiedText')==expected
        page.locator('#copy-citation').click()
        copied=page.evaluate('window.copiedText')
        assert expected in copied and 'İç kayıt sırası: 1' in copied and 'GK kayıt kimliği: 146_1' in copied
        assert 'q=niyet' not in copied and '/research?' not in copied
        page.evaluate("window.copyMode='delay'");page.locator('#copy-link').click()
        page.evaluate("window.oldReject=window.rejectCopy;window.copyMode='success'")
        page.locator('#copy-citation').click();page.evaluate('window.oldReject()')
        expect(page.locator('#copy-fallback')).not_to_be_visible()
        page.evaluate("window.copyMode='deny'");page.locator('#copy-link').click()
        field=page.locator('#copy-text')
        expect(page.locator('#copy-fallback')).to_be_visible();expect(field).to_have_value(expected)
        expect(field).to_be_focused()
        assert field.evaluate('(e)=>e.readOnly && e.selectionStart===0 && e.selectionEnd===e.value.length')
        page.locator('#next-record').click();expect(page.locator('#hadith-number')).to_have_text('2')
        expect(page.locator('#copy-fallback')).not_to_be_visible()
        page.evaluate("window.copyMode='delay'");page.locator('#copy-link').click()
        page.locator('#next-record').click();expect(page.locator('#hadith-number')).to_have_text('3')
        page.evaluate('window.rejectCopy()')
        expect(page.locator('#copy-fallback')).not_to_be_visible()
        print(f'PASS {width}x{height}: canonical share/citation, denied clipboard fallback, clean navigation and delayed rejection')
    finally:page.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--case',default='all',choices=['all','compare','copy']);args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',headless=True)
        try:
            for size in [(1440,1000),(390,844)]:
                if args.case in ('all','compare'):compare(browser,args.url,*size)
                if args.case in ('all','copy'):copying(browser,args.url,*size)
        finally:browser.close()
