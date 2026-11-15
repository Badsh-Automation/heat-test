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

INDICATOR_VERSION = "badsha-svc-ob-pine-1"


def _fmt(sig: Signal) -> tuple[str, str, str, str]:
    tf = config.TF_LABELS.get(config.TIMEFRAME_MIN, f"{config.TIMEFRAME_MIN}m")
    ist = sig.time + timedelta(minutes=config.TIMEFRAME_MIN) + timedelta(hours=5, minutes=30)
    zone = f"{sig.ob.bottom:.5f} - {sig.ob.top:.5f}"
    if sig.type == "ENTRY":
        title = f"{config.SYMBOL} {tf} ENTRY (Bullish OB)"
        tags, prio = "chart_with_upwards_trend,green_circle", "high"
    else:
        title = f"{config.SYMBOL} {tf} EXIT (Bearish OB)"
        tags, prio = "chart_with_downwards_trend,red_circle", "high"
    msg = (
        f"{sig.type} @ {sig.price:.5f}\n"
        f"OB zone: {zone}\n"
        f"Pivot volume: {sig.ob.rvol:.1f}x avg\n"
        f"Bar close: {ist:%d-%b %H:%M} IST"
    )
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
    if st.get("indicator_version") != INDICATOR_VERSION:
        st = {"indicator_version": INDICATOR_VERSION}   # indicator badla -> naya silent baseline
    try:
        path = csv_path or download_csv()
        df = data.load_csv(path)
        df = data.drop_unclosed(df, config.TIMEFRAME_MIN)
        data.validate(df, config.TIMEFRAME_MIN)
    except (FetchError, data.DataError) as e:
        _error_alert(st, str(e), dry)
        return 1

    params = Params(
        length=config.PIVOT_LEN,
        mitigation=config.MITIGATION,
        min_strength=config.MIN_STRENGTH,
        show_weak_ob=config.SHOW_WEAK_OB,
        vol_len=config.VOL_LEN,
        use_legacy=config.USE_LEGACY,
        high_factor=config.HIGH_FACTOR,
        extreme_factor=config.EXTREME_FACTOR,
        detect_mode=config.DETECT_MODE,
        z_high=config.Z_HIGH,
        z_extreme=config.Z_EXTREME,
        use_pct=config.USE_PCT,
        pct_min=config.PCT_MIN,
    )
    signals = generate_signals(df, params, mode=config.SIGNAL_MODE)
    last_bar = df.index[-1]
    print(f"Bars: {len(df)} | last closed bar: {last_bar} | signals in history: {len(signals)}")

    # Chart se compare karne ke liye: pichhle signals ki list (label chart par PIVOT candle par dikhta hai)
    for sg in signals[-8:]:
        piv = df.index[sg.ob.pivot_idx]
        conf_close = sg.time + timedelta(minutes=config.TIMEFRAME_MIN)
        print(
            f"  {sg.type:5} | chart label candle: {piv:%d-%b %H:%M} UTC | "
            f"confirm (bar close): {conf_close:%d-%b %H:%M} UTC | zone {sg.ob.bottom:.5f}-{sg.ob.top:.5f} "
            f"| vol {sg.ob.rvol:.1f}x"
        )

    last_alerted = st.get("last_alerted_bar")
    if last_alerted is None and config.SILENT_FIRST_RUN:
        # Baseline: purane signals ka alert nahi, sirf yaad rakho
        st["last_alerted_bar"] = last_bar.isoformat()
        st["last_signal"] = signals[-1].type if signals else None
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
    st["last_signal"] = signals[-1].type if signals else None
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
