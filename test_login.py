from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(storage_state="heat_state.json")
    page = ctx.new_page()
    page.goto("https://heatcharting.com/chart")
    page.wait_for_timeout(8000)
    page.screenshot(path="test.png")
    b.close()