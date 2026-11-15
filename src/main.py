"""
Pipeline:  HeatCharting CSV download -> clean -> BADSHA OB signals -> ntfy

python -m src.main                  # full run
python -m src.main --csv file.csv   # download skip, local CSV se test
python -m src.main --dry-run        # ntfy nahi bhejta, state save nahi karta
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from . import config, data, notify, state as state_mod
from .fetch_heat import FetchError, download_csv
from .indicators.badsha_ob import Params, Signal, generate_signals


def _fmt(sig: Signal) -> tuple[str, str, str, str]:
    tf = config.TF_LABELS.get(config.TIMEFRAME_MIN, f"{config.TIMEFRAME_MIN}m")
    ist = sig.time + timedelta(minutes=config.TIMEFRAME_MIN) + timedelta(hours=5, minutes=30)
    zone = f"{sig.ob.bottom:.5f} - {sig.ob.top:.5f}"
    if sig.type == "BUY":
        title = f"{config.SYMBOL} {tf} BUY (Bullish OB)"
        tags, prio = "chart_with_upwards_trend,green_circle", "high"
    else:
        title = f"{config.SYMBOL} {tf} EXIT (Bearish OB)"
        tags, prio = "chart_with_downwards_trend,red_circle", "high"
    msg = f"{sig.type} @ {sig.price:.5f}\nOB zone: {zone}\nBar close: {ist:%d-%b %H:%M} IST"
    return title, msg, prio, tags


def _error_alert(st: dict, err: str, dry: bool) -> None:
    print(f"ERROR: {err}")
    if dry or not config.NOTIFY_ON_ERROR:
        return
    now = datetime.now(timezone.utc)
    last = st.get("last_error_alert")
    if last and now - datetime.fromisoformat(last) < timedelta(hours=config.ERROR_ALERT_COOLDOWN_H):
        return
    try:
        notify.send("HeatCharting bot ERROR", err, priority="urgent", tags="warning")
        st["last_error_alert"] = now.isoformat()
        state_mod.save(st)
    except Exception as e:  # noqa: BLE001
        print(f"error alert bhi nahi gaya: {e}")


def run(csv_path: str | None, dry: bool) -> int:
    st = state_mod.load()
    try:
        path = csv_path or download_csv()
        df = data.load_csv(path)
        df = data.drop_unclosed(df, config.TIMEFRAME_MIN)
        data.validate(df, config.TIMEFRAME_MIN)
    except (FetchError, data.DataError) as e:
        _error_alert(st, str(e), dry)
        return 1

    params = Params(
        pivot_len=config.PIVOT_LEN,
        use_wick_zone=config.USE_WICK_ZONE,
        require_rvol=config.REQUIRE_RVOL,
        rvol_len=config.RVOL_LEN,
        rvol_mult=config.RVOL_MULT,
    )
    signals = generate_signals(df, params)
    last_bar = df.index[-1]
    print(f"Bars: {len(df)} | last closed bar: {last_bar} | signals in history: {len(signals)}")

    last_alerted = st.get("last_alerted_bar")
    if last_alerted is None and config.SILENT_FIRST_RUN:
        # Baseline: purane signals ka alert nahi, sirf yaad rakho
        st["last_alerted_bar"] = signals[-1].time.isoformat() if signals else last_bar.isoformat()
        st["position"] = "LONG" if signals and signals[-1].type == "BUY" else "FLAT"
        print("Pehli run: baseline set (alert nahi bheja).")
        if not dry:
            state_mod.save(st)
        return 0

    cutoff = datetime.fromisoformat(last_alerted) if last_alerted else None
    new = [s for s in signals if cutoff is None or s.time.to_pydatetime() > cutoff]
    for s in new:
        title, msg, prio, tags = _fmt(s)
        print(f"NEW SIGNAL -> {title} | {msg!r}")
        if not dry:
            notify.send(title, msg, priority=prio, tags=tags)
        st["last_alerted_bar"] = s.time.isoformat()
    st["position"] = "LONG" if signals and signals[-1].type == "BUY" else "FLAT"
    st["last_run"] = datetime.now(timezone.utc).isoformat()
    if not new:
        print("Koi naya signal nahi.")
    if not dry:
        state_mod.save(st)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="download skip karke local CSV use karo")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.csv, a.dry_run))
