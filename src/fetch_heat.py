"""HeatCharting par saved session se login karke chart ka CSV download karta hai."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from . import config

MENU_ITEM_TEXT = "Download chart data (CSV)"
MENU_ITEM = ".menu .mi"  # DevTools: <div class="menu"><div class="mi"><span class="ml">...


class FetchError(Exception):
    pass


def _menu_item(page):
    return page.locator(MENU_ITEM).filter(has_text=MENU_ITEM_TEXT).first


def _check_session(page) -> None:
    if "/welcome" in page.url:
        raise FetchError("SESSION_EXPIRED: /welcome par redirect hua.")
    me = page.evaluate(
        """async () => {
            try {
                const r = await fetch('/app/auth/me', { cache: 'no-store' });
                if (!r.ok) return null;
                const j = await r.json();
                return j.user || null;
            } catch (e) { return null; }
        }"""
    )
    if not me:
        raise FetchError("SESSION_EXPIRED: /app/auth/me ne user nahi diya.")


def _current_symbol(page) -> str:
    try:
        return page.locator("#symTxt").inner_text(timeout=3000).strip()
    except Exception:
        return ""


def _set_timeframe(page) -> None:
    label = config.TF_LABELS.get(config.TIMEFRAME_MIN)
    if not label:
        return
    try:
        page.locator("#tfQuick").get_by_text(label, exact=True).first.click(timeout=3000)
        page.wait_for_timeout(3000)
    except Exception:
        pass  # validate() baad me timeframe mismatch pakad lega


def _symbol_via_button(page) -> None:
    """DevTools se mila: <button id="symBtn"> kholta hai search, <span id="symTxt"> current symbol dikhata hai."""
    sym = config.SYMBOL.upper()
    if _current_symbol(page).upper() == sym:
        return
    page.locator("#symBtn").click(timeout=5000)
    page.wait_for_timeout(800)
    page.keyboard.type(config.SYMBOL, delay=80)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(Path(config.DOWNLOAD_DIR) / "03_search_open.png"))

    def changed() -> bool:
        return _current_symbol(page).upper() == sym

    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    if changed():
        return
    # Enter se nahi badla -> dropdown me exact-match row par click
    for loc in (
        page.locator(f'[role="option"]:has-text("{config.SYMBOL}")'),
        page.locator(f'li:has-text("{config.SYMBOL}")'),
        page.locator(f'.row:has-text("{config.SYMBOL}")'),
        page.get_by_text(config.SYMBOL, exact=True),
    ):
        try:
            loc.first.click(timeout=2500)
            page.wait_for_timeout(3000)
            if changed():
                return
        except Exception:
            continue
    raise FetchError(f"symbol {config.SYMBOL} select nahi hua (03_search_open.png dekho).")


def _symbol_via_watchlist(page) -> None:
    """Right side watchlist me symbol ki row par click (screenshot me EURUSD row dikhti hai)."""
    row = page.get_by_text(config.SYMBOL, exact=True).last
    row.click(timeout=5000)
    page.wait_for_timeout(5000)


def _symbol_via_search(page) -> None:
    """Top-left symbol search box se."""
    box = page.locator('input[type="search"], input[type="text"], input').first
    box.click(timeout=5000)
    box.press("Control+A")
    box.type(config.SYMBOL, delay=80)
    page.wait_for_timeout(2000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(5000)


SYMBOL_METHODS = (_symbol_via_button, _symbol_via_watchlist, _symbol_via_search)


def _open_more_menu(page) -> bool:
    for sel in ('[aria-label*="more" i]', '[title*="more" i]'):
        loc = page.locator(sel).first
        if loc.count():
            try:
                loc.click(timeout=2000)
                if _menu_item(page).is_visible():
                    return True
            except Exception:
                pass
    # Fallback: "Install app" ke theek pehle wala icon button = "..."
    ok = page.evaluate(
        """() => {
            const els = [...document.querySelectorAll('button, a, div[role=button]')];
            const install = els.find(e => e.textContent.trim() === 'Install app');
            if (!install) return false;
            let prev = install.previousElementSibling;
            if (!prev && install.parentElement) prev = install.parentElement.previousElementSibling;
            if (!prev) return false;
            (prev.querySelector('button') || prev).click();
            return true;
        }"""
    )
    if ok:
        page.wait_for_timeout(500)
        return _menu_item(page).is_visible()
    return False


def _download_once(page, out: Path) -> Path:
    if not _open_more_menu(page):
        page.screenshot(path=str(out / "debug_menu.png"))
        raise FetchError("'...' menu nahi khula (debug_menu.png dekho).")
    try:
        with page.expect_download(timeout=30_000) as dl:
            _menu_item(page).click()
    except PWTimeout:
        page.screenshot(path=str(out / "debug_download.png"))
        raise FetchError("CSV download trigger nahi hua (debug_download.png dekho).")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = out / f"{stamp}_{dl.value.suggested_filename}"
    dl.value.save_as(str(target))
    return target


def download_csv() -> Path:
    out = Path(config.DOWNLOAD_DIR)
    out.mkdir(parents=True, exist_ok=True)
    state = Path(config.HEAT_STATE_FILE)
    if not state.exists():
        raise FetchError(f"{state} nahi mili (HEAT_STATE secret decode hua?).")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        ctx = browser.new_context(
            storage_state=str(state), accept_downloads=True, viewport={"width": 1600, "height": 900}
        )
        page = ctx.new_page()
        try:
            page.goto(config.HEAT_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(config.CHART_LOAD_WAIT_MS)
            _check_session(page)
            page.screenshot(path=str(out / "01_loaded.png"))

            last_err = "symbol set nahi hua"
            # Pehle jo symbol chart par hai wahi check karo, phir methods try karo
            for attempt, method in enumerate((None,) + SYMBOL_METHODS):
                try:
                    if method is not None:
                        method(page)
                    _set_timeframe(page)
                    page.screenshot(path=str(out / f"02_attempt{attempt}.png"))
                    cur = _current_symbol(page)
                    if cur and cur.upper() != config.SYMBOL.upper():
                        raise FetchError(f"chart par abhi {cur} hai, {config.SYMBOL} nahi")
                    target = _download_once(page, out)
                except Exception as e:  # noqa: BLE001
                    last_err = f"{getattr(method, '__name__', 'current')}: {e}"
                    continue
                if config.SYMBOL.lower() in target.name.lower():
                    print(f"Downloaded: {target}")
                    return target
                last_err = f"galat symbol file mili: {target.name} (chahiye {config.SYMBOL})"
                target.unlink(missing_ok=True)
            raise FetchError(f"{config.SYMBOL} select nahi ho paya. Last error: {last_err}")
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        download_csv()
    except FetchError as e:
        sys.exit(str(e))
