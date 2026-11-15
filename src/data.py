"""HeatCharting CSV -> clean OHLCV DataFrame (UTC index)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config

TIME_COLS = ("time", "date", "datetime", "timestamp", "t")


class DataError(Exception):
    pass


def _find(cols: dict, *names):
    for n in names:
        if n in cols:
            return cols[n]
    return None


def load_csv(path: str | Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    cols = {str(c).strip().lower(): c for c in raw.columns}

    tcol = _find(cols, *TIME_COLS)
    o, h, l, c = (_find(cols, k) for k in ("open", "high", "low", "close"))
    v = _find(cols, "volume", "vol", "tick_volume", "tickvolume")
    if tcol is None or None in (o, h, l, c):
        raise DataError(f"CSV columns samajh nahi aaye: {list(raw.columns)}")

    t = raw[tcol]
    if pd.api.types.is_numeric_dtype(t):
        unit = "ms" if t.iloc[0] > 1e11 else "s"
        idx = pd.to_datetime(t, unit=unit, utc=True)
    else:
        idx = pd.to_datetime(t, utc=True, errors="coerce")

    df = pd.DataFrame(
        {
            "open": raw[o].astype(float),
            "high": raw[h].astype(float),
            "low": raw[l].astype(float),
            "close": raw[c].astype(float),
            "volume": raw[v].astype(float) if v is not None else 0.0,
        }
    )
    df.index = pd.DatetimeIndex(idx)
    df = df[~df.index.isna()].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def drop_unclosed(df: pd.DataFrame, tf_min: int, now: datetime | None = None) -> pd.DataFrame:
    """Abhi ban rahi (forming) candle hata do -> signals repaint nahi karte."""
    now = now or datetime.now(timezone.utc)
    close_time = df.index + pd.Timedelta(minutes=tf_min)
    return df[close_time <= pd.Timestamp(now)]


def validate(df: pd.DataFrame, tf_min: int) -> None:
    if len(df) < config.MIN_BARS:
        raise DataError(f"Sirf {len(df)} bars mile (min {config.MIN_BARS}).")
    diffs = df.index.to_series().diff().dropna()
    median_min = diffs.median().total_seconds() / 60
    if abs(median_min - tf_min) > 0.5:
        raise DataError(
            f"Timeframe mismatch: data ~{median_min:.0f}m ka hai, expected {tf_min}m. "
            "Chart par sahi timeframe select hua?"
        )
    last = float(df["close"].iloc[-1])
    if not (config.PRICE_MIN <= last <= config.PRICE_MAX):
        raise DataError(
            f"Price {last} range {config.PRICE_MIN}-{config.PRICE_MAX} se bahar. Galat symbol download hua?"
        )
    if df["volume"].sum() <= 0:
        raise DataError("CSV me volume nahi hai; volume-based indicator nahi chalega.")
