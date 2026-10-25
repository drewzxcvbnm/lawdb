"""Browser smoke test against a running app; uses system Chromium, no download."""
import os
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/sbin/chromium'), headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8000')
    expect(page.locator('.result-title').first).to_be_visible(timeout=30000)
    expect(page.locator('#collection-stats')).to_contain_text('searchable decisions',timeout=30000)
    page.screenshot(path='/tmp/lawdb-desktop.png',full_page=False)
    page.locator('#query').fill('darba līgums')
    page.locator('.search-row button').click()
    expect(page.locator('.snippet mark').first).to_be_visible(timeout=30000)
    page.locator('.read-link').first.click()
    expect(page.locator('#pdf-link')).to_be_visible(timeout=15000)
    expect(page.locator('#reader-text')).not_to_have_text('Loading source text…')
    assert '#page=' in page.locator('#pdf-link').get_attribute('href')
    page.keyboard.press('Escape')
    expect(page.locator('#reader')).not_to_be_visible()
    page.locator('#query').fill('zzzxxyyimpossibleword')
    page.locator('.search-row button').click()
    expect(page.get_by_role('heading',name='No decisions found')).to_be_visible(timeout=30000)
    page.set_viewport_size({'width':390,'height':844})
    page.goto('http://127.0.0.1:8000')
    expect(page.locator('.result-title').first).to_be_visible(timeout=30000)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path='/tmp/lawdb-mobile.png',full_page=False)
    # Untrusted source text must remain inert even if it resembles HTML.
    page.evaluate("""() => {const el=renderSnippet('<img src=x onerror=alert(1)> ⟦word⟧');document.body.append(el);} """)
    assert page.locator('.snippet img').count()==0
    assert not errors, errors
    print('Browser checks passed: desktop, mobile, search, empty results, reader, PDF link, escaped text, no JS errors.')
    browser.close()
