"""Signal message + GitHub table (SIGNALS.md).

Format (ntfy message aur table dono me yahi fields):
  Symbol | Signal | Zone | Pip Diff | Time | Confirm | SL

SL logic:
  EXIT  -> zone ka UPAR wala price + SL_POINTS points
  ENTRY -> zone ka NEECHE wala price - SL_POINTS points
  1 point = price ka sabse chhota step (5 digit pair: 0.00001, JPY: 0.001), isliye
  100 points = EURUSD me 0.00100, USDJPY me 0.100.
"""
from __future__ import annotations

from pathlib import Path

from . import config

RECENT_PER_SYMBOL = 3
COLUMNS = ("Symbol", "Signal", "Zone", "Pip Diff", "Time", "Confirm", "SL")


def sl_price(symbol: str, sig_type: str, bottom: float, top: float) -> float:
    off = config.SL_POINTS * config.point_size(symbol)
    return top + off if sig_type == "EXIT" else bottom - off


def pip_diff(symbol: str, bottom: float, top: float) -> float:
    """Zone ki width pips me."""
    return round((top - bottom) / config.pip_size(symbol), 1)


def make_row(symbol: str, sig_type: str, bottom: float, top: float, time_str: str, confirm_str: str) -> dict:
    """Ek signal ki display row (sab strings; state.json me aise hi save hoti hai)."""
    px = lambda x: config.fmt_price(symbol, x)  # noqa: E731
    return {
        "type": sig_type,
        "zone": f"{px(bottom)} - {px(top)}",
        "pip_diff": f"{pip_diff(symbol, bottom, top):.1f}",
        "time": time_str,
        "confirm": confirm_str,
        "sl": px(sl_price(symbol, sig_type, bottom, top)),
    }


def format_message(symbol: str, row: dict) -> str:
    return (
        f"{symbol} | {row['type']}\n"
        f"Zone: {row['zone']}\n"
        f"Pip Diff: {row['pip_diff']}\n"
        f"Time: {row['time']}\n"
        f"Confirm: {row['confirm']}\n"
        f"SL: {row['sl']}"
    )


def render_table(st: dict, symbols: list[str] | None = None) -> str:
    """state.json -> markdown. Har symbol ke last 3 signal, naya upar."""
    syms = st.get("symbols", {})
    order = [s for s in (symbols or config.SYMBOLS)] + [s for s in syms if s not in (symbols or config.SYMBOLS)]
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "|".join("---" for _ in COLUMNS) + "|",
    ]
    for sym in order:
        rows = syms.get(sym, {}).get("recent") or []
        if not rows:
            lines.append(f"| {sym} | - | - | - | - | - | - |")
            continue
        for r in rows:
            lines.append(
                f"| {sym} | {r['type']} | {r['zone']} | {r['pip_diff']} | {r['time']} | {r['confirm']} | {r['sl']} |"
            )
    return "\n".join(lines)


def write_signals_md(st: dict, path: str | None = None) -> None:
    path = path if path is not None else config.SIGNALS_MD_FILE
    if not path:
        return
    runs = [v.get("last_run") for v in st.get("symbols", {}).values() if v.get("last_run")]
    updated = max(runs) if runs else "-"
    body = (
        f"# Latest signals\n\n"
        f"Har symbol ke last {RECENT_PER_SYMBOL} signal (naya upar). Time IST me. "
        f"SL = zone ke bahar {config.SL_POINTS} points.\n\n"
        f"{render_table(st)}\n\n"
        f"_Last run: {updated}_\n"
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
