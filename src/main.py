"""
Pipeline (har symbol ke liye):  HeatCharting CSV -> clean -> BADSHA OB signals -> ntfy
Sab time IST me dikhte aur save hote hain.

python -m src.main                         # sab symbols (config.SYMBOLS)
python -m src.main --csv f.csv --symbol EURUSD   # download skip, local CSV se test
python -m src.main --dry-run               # ntfy nahi bhejta, state save nahi karta
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from . import config, data, notify, state as state_mod
from .fetch_heat import FetchError, download_csvs
from .indicators.badsha_ob import Params, Signal, generate_signals

INDICATOR_VERSION = "badsha-svc-ob-pine-1"
TF = lambda: config.TF_LABELS.get(config.TIMEFRAME_MIN, f"{config.TIMEFRAME_MIN}m")  # noqa: E731


def _ist(ts: pd.Timestamp) -> str:
    return f"{config.to_ist(ts):%d-%b %H:%M} IST"


def _fmt(symbol: str, sig: Signal) -> tuple[str, str, str, str]:
    px = lambda x: config.fmt_price(symbol, x)  # noqa: E731
    bar_close = sig.time + pd.Timedelta(minutes=config.TIMEFRAME_MIN)
    if sig.type == "ENTRY":
        title = f"{symbol} {TF()} ENTRY (Bullish OB)"
        tags, prio = "chart_with_upwards_trend,green_circle", "high"
    else:
        title = f"{symbol} {TF()} EXIT (Bearish OB)"
        tags, prio = "chart_with_downwards_trend,red_circle", "high"
    msg = (
        f"{sig.type} @ {px(sig.price)}\n"
        f"OB zone: {px(sig.ob.bottom)} - {px(sig.ob.top)}\n"
        f"Pivot volume: {sig.ob.rvol:.1f}x avg\n"
        f"Bar close: {_ist(bar_close)}"
    )
    return title, msg, prio, tags


def _error_alert(st: dict, err: str, dry: bool) -> None:
    print(f"ERROR: {err}")
    if dry or not config.NOTIFY_ON_ERROR:
        return
    now = config.now_ist()
    last = st.get("last_error_alert")
    if last and now - pd.Timestamp(last) < pd.Timedelta(hours=config.ERROR_ALERT_COOLDOWN_H):
        return
    try:
        notify.send("HeatCharting bot ERROR", err, priority="urgent", tags="warning")
        st["last_error_alert"] = now.isoformat()
    except Exception as e:  # noqa: BLE001
        print(f"error alert bhi nahi gaya: {e}")


def _params() -> Params:
    return Params(
        length=config.PIVOT_LEN, mitigation=config.MITIGATION, min_strength=config.MIN_STRENGTH,
        show_weak_ob=config.SHOW_WEAK_OB, vol_len=config.VOL_LEN, use_legacy=config.USE_LEGACY,
        high_factor=config.HIGH_FACTOR, extreme_factor=config.EXTREME_FACTOR,
        detect_mode=config.DETECT_MODE, z_high=config.Z_HIGH, z_extreme=config.Z_EXTREME,
        use_pct=config.USE_PCT, pct_min=config.PCT_MIN,
    )


def _process(symbol: str, path, st_sym: dict, dry: bool) -> dict:
    """Ek symbol: CSV -> signals -> alerts. Updated per-symbol state return karta hai."""
    df = data.load_csv(path)
    df = data.drop_unclosed(df, config.TIMEFRAME_MIN)
    data.validate(df, config.TIMEFRAME_MIN, symbol)

    signals = generate_signals(df, _params(), mode=config.SIGNAL_MODE)
    last_bar = df.index[-1]
    print(
        f"[{symbol}] Bars: {len(df)} | last closed bar: {_ist(last_bar + pd.Timedelta(minutes=config.TIMEFRAME_MIN))}"
        f" | signals in history: {len(signals)}"
    )
    for sg in signals[-8:]:
        piv = df.index[sg.ob.pivot_idx]
        print(
            f"  {sg.type:5} | chart label candle: {_ist(piv)} | "
            f"confirm (bar close): {_ist(sg.time + pd.Timedelta(minutes=config.TIMEFRAME_MIN))} | "
            f"zone {config.fmt_price(symbol, sg.ob.bottom)}-{config.fmt_price(symbol, sg.ob.top)} | vol {sg.ob.rvol:.1f}x"
        )

    last_alerted = st_sym.get("last_alerted_bar")
    if last_alerted is None and config.SILENT_FIRST_RUN:
        print(f"[{symbol}] Pehli run: baseline set (alert nahi bheja).")
        return {"last_alerted_bar": config.to_ist(last_bar).isoformat(),
                "last_signal": signals[-1].type if signals else None}

    cutoff = pd.Timestamp(last_alerted) if last_alerted else None
    new = [s for s in signals if cutoff is None or s.time > cutoff]
    out = dict(st_sym)
    for s in new:
        title, msg, prio, tags = _fmt(symbol, s)
        print(f"[{symbol}] NEW SIGNAL -> {title} | {msg!r}")
        if not dry:
            notify.send(title, msg, priority=prio, tags=tags)
        out["last_alerted_bar"] = config.to_ist(s.time).isoformat()
    out["last_signal"] = signals[-1].type if signals else None
    out["last_run"] = config.now_ist().isoformat()
    if not new:
        print(f"[{symbol}] Koi naya signal nahi.")
    return out


def run(csv_path: str | None = None, dry: bool = False, symbols: list[str] | None = None) -> int:
    symbols = [s.upper() for s in (symbols or config.SYMBOLS)]
    st = state_mod.load()
    if st.get("indicator_version") != INDICATOR_VERSION:
        st = {"indicator_version": INDICATOR_VERSION}      # indicator badla -> naya silent baseline
    st.setdefault("symbols", {})
    # Purana single-symbol state (EURUSD) migrate
    if "last_alerted_bar" in st:
        st["symbols"].setdefault("EURUSD", {"last_alerted_bar": st.pop("last_alerted_bar"),
                                             "last_signal": st.pop("last_signal", None)})
    for k in ("position", "last_run"):
        st.pop(k, None)

    errors: dict[str, str] = {}
    if csv_path:
        files = {symbols[0]: csv_path}
    else:
        try:
            files, errors = download_csvs(symbols)
        except FetchError as e:
            _error_alert(st, str(e), dry)
            if not dry:
                state_mod.save(st)
            return 1

    for sym in symbols:
        if sym not in files:
            continue
        try:
            st["symbols"][sym] = _process(sym, files[sym], st["symbols"].get(sym, {}), dry)
        except data.DataError as e:
            errors[sym] = str(e)
            print(f"[{sym}] ERROR: {e}")
        if not dry:
            state_mod.save(st)          # har symbol ke baad, taaki crash par duplicate alert na aaye

    if errors:
        _error_alert(st, "\n".join(f"{k}: {v}" for k, v in errors.items()), dry)
        if not dry:
            state_mod.save(st)
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="download skip karke local CSV use karo (ek symbol)")
    ap.add_argument("--symbol", help="--csv ke saath symbol ka naam")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.csv, a.dry_run, [a.symbol] if a.symbol else None))
