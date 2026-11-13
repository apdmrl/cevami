"""Live browser regression: python tests/ui_dialog.py [--url URL] [--browser EXE].

Requires the local app and the optional playwright package. Uses a fresh browser
profile; never connects to or closes the user's browser windows.
"""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def check_dialog(browser, base_url, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{base_url}/?hadith=146_1004")
        trigger = page.locator("#arabic-text .inline-narrator").first
        trigger.click()
        dialog = page.locator("#narrator-dialog")
        close = page.get_by_role("button", name="Ravi kartını kapat")
        page.locator("#narrator-title").wait_for()
        page.locator("#narrator-content .dialog-source").wait_for()
        expect(close).to_be_focused()
        initial = close.bounding_box()
        scroll_y = page.evaluate("window.scrollY")
        body = page.locator("#narrator-content")
        box = body.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + min(200, box["height"] / 2))
        page.mouse.wheel(0, 650)
        page.wait_for_function("""() => Math.max(
            document.querySelector('#narrator-content').scrollTop,
            document.querySelector('#narrator-dialog').scrollTop) > 100""")
        after = close.bounding_box()
        assert abs(after["y"] - initial["y"]) < 2, "Close button scrolls out of view"
        assert after["y"] >= 0 and after["y"] + after["height"] <= height
        assert dialog.evaluate("d => d.scrollTop") == 0
        assert body.evaluate("d => d.scrollTop") > 100
        # Arrow/Page navigation works when the scroll region has keyboard focus.
        body.focus()
        body.press("End")
        page.wait_for_function("""() => {
            const d = document.querySelector('#narrator-content');
            return d.scrollTop + d.clientHeight >= d.scrollHeight - 2;
        }""")
        page.mouse.wheel(0, 1500)
        # A real subsequent input flushes pending wheel/scroll animation.
        close.focus()
        expect(close).to_be_in_viewport()
        assert page.evaluate("window.scrollY") == scroll_y, "Background page scrolled"
        # Native modal focus containment, even at the end of the content.
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.querySelector('#narrator-dialog').contains(document.activeElement)")
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(trigger).to_be_focused()
        trigger.click()
        expect(body).to_have_js_property("scrollTop", 0)
        close.click()
        expect(dialog).not_to_be_visible()
        expect(trigger).to_be_focused()
        assert not errors, errors
        print(f"PASS {width}x{height}: wheel, fixed close, keyboard, Escape, focus, reopen")
    finally:
        page.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--browser", default=r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(Path(args.browser)), headless=True)
        try:
            for size in [(1280, 850), (390, 700), (700, 390)]:
                check_dialog(browser, args.url.rstrip("/"), *size)
        finally:
            browser.close()
