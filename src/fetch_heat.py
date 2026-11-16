"""HeatCharting par saved session se login karke, ek hi browser session me kai symbols ka CSV download karta hai."""
from __future__ import annotations

import sys
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


def _wait_chart_loaded(page, extra_ms: int = 4000) -> None:
    """Chart par 'Loading EX:EURUSD...' khatam hone tak ruko."""
    try:
        page.wait_for_function(
            "() => !/Loading\\s+\\S+/.test(document.body.innerText)", timeout=60_000
        )
    except Exception:
        pass
    page.wait_for_timeout(extra_ms)


def _set_timeframe(page) -> None:
    label = config.TF_LABELS.get(config.TIMEFRAME_MIN)
    if not label:
        return
    try:
        page.locator("#tfQuick").get_by_text(label, exact=True).first.click(timeout=3000)
        _wait_chart_loaded(page, 3000)
    except Exception:
        pass  # validate() baad me timeframe mismatch pakad lega


def _symbol_via_button(page, symbol: str, out: Path) -> None:
    """<button id="symBtn"> search kholta hai, <span id="symTxt"> current symbol dikhata hai."""
    sym = symbol.upper()
    if _current_symbol(page).upper() == sym:
        return
    page.locator("#symBtn").click(timeout=5000)
    page.wait_for_timeout(800)
    page.keyboard.type(symbol, delay=80)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(out / f"{symbol}_03_search_open.png"))

    def changed() -> bool:
        return _current_symbol(page).upper() == sym

    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    if changed():
        return
    for loc in (
        page.locator(f'[role="option"]:has-text("{symbol}")'),
        page.locator(f'li:has-text("{symbol}")'),
        page.locator(f'.row:has-text("{symbol}")'),
        page.get_by_text(symbol, exact=True),
    ):
        try:
            loc.first.click(timeout=2500)
            page.wait_for_timeout(3000)
            if changed():
                return
        except Exception:
            continue
    raise FetchError(f"symbol {symbol} select nahi hua ({symbol}_03_search_open.png dekho).")


def _symbol_via_watchlist(page, symbol: str, out: Path) -> None:
    page.get_by_text(symbol, exact=True).last.click(timeout=5000)
    page.wait_for_timeout(5000)


SYMBOL_METHODS = (_symbol_via_button, _symbol_via_watchlist)


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


def _download_once(page, out: Path, symbol: str) -> Path:
    if not _open_more_menu(page):
        page.screenshot(path=str(out / f"{symbol}_debug_menu.png"))
        raise FetchError("'...' menu nahi khula.")
    try:
        with page.expect_download(timeout=30_000) as dl:
            _menu_item(page).click()
    except PWTimeout:
        page.screenshot(path=str(out / f"{symbol}_debug_download.png"))
        raise FetchError("CSV download trigger nahi hua.")
    stamp = config.now_ist().strftime("%Y%m%d_%H%M%S_IST")
    target = out / f"{stamp}_{dl.value.suggested_filename}"
    dl.value.save_as(str(target))
    return target


def _fetch_symbol(page, out: Path, symbol: str) -> Path:
    last_err = "symbol set nahi hua"
    for attempt, method in enumerate((None,) + SYMBOL_METHODS):
        on_symbol = _current_symbol(page).upper() == symbol.upper()
        if method is None and not on_symbol:
            continue
        try:
            if method is not None:
                method(page, symbol, out)
            _wait_chart_loaded(page)
            _set_timeframe(page)
            page.screenshot(path=str(out / f"{symbol}_02_attempt{attempt}.png"))
            cur = _current_symbol(page)
            if cur and cur.upper() != symbol.upper():
                raise FetchError(f"chart par abhi {cur} hai, {symbol} nahi")
            target = None
            for _try in range(4):
                target = _download_once(page, out, symbol)
                rows = sum(1 for _ in open(target, encoding="utf-8", errors="ignore")) - 1
                if rows >= 20:
                    break
                print(f"[{symbol}] CSV me sirf {rows} rows (chart load nahi hua), {_try + 1}/4 retry...")
                target.unlink(missing_ok=True)
                page.wait_for_timeout(10_000)
        except Exception as e:  # noqa: BLE001
            last_err = f"{getattr(method, '__name__', 'current')}: {e}"
            continue
        if symbol.lower() in target.name.lower():
            print(f"[{symbol}] Downloaded: {target}")
            return target
        last_err = f"galat symbol file mili: {target.name}"
        target.unlink(missing_ok=True)
    raise FetchError(f"{symbol} select nahi ho paya. Last error: {last_err}")


def download_csvs(symbols: list[str]) -> tuple[dict[str, Path], dict[str, str]]:
    """Ek browser session me sab symbols. Return: (files, errors). Session expire hone par FetchError raise."""
    out = Path(config.DOWNLOAD_DIR)
    out.mkdir(parents=True, exist_ok=True)
    state = Path(config.HEAT_STATE_FILE)
    if not state.exists():
        raise FetchError(f"{state} nahi mili (HEAT_STATE secret decode hua?).")

    files: dict[str, Path] = {}
    errors: dict[str, str] = {}
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
            for sym in symbols:
                try:
                    files[sym] = _fetch_symbol(page, out, sym)
                except FetchError as e:
                    errors[sym] = str(e)
                    print(f"[{sym}] ERROR: {e}")
        finally:
            browser.close()
    return files, errors


if __name__ == "__main__":
    try:
        f, e = download_csvs(config.SYMBOLS)
    except FetchError as ex:
        sys.exit(str(ex))
    sys.exit(1 if e else 0)
