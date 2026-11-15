import numpy as np
import pandas as pd
import pytest

BASE = 1.1000


def make_df(n=200, tf_min=15, start="2026-11-02 00:00", spikes=None, extra_low=None):
    """
    Flat market: high=BASE+0.0003, low=BASE-0.0003, volume 100 (natural pivots nahi).
    spikes = {idx: ("bull"|"bear", volume)}
      bull: pivot candle ka low baaki se neeche (swing low)  -> os=1 -> bullish OB
      bear: pivot candle ka high baaki se upar (swing high) -> os=0 -> bearish OB
    extra_low = {idx: low}  (mitigation test ke liye)
    """
    idx = pd.date_range(start, periods=n, freq=f"{tf_min}min", tz="UTC")
    high = np.full(n, BASE + 0.0003)
    low = np.full(n, BASE - 0.0003)
    vol = np.full(n, 100.0)
    for i, (kind, v) in (spikes or {}).items():
        vol[i] = v
        if kind == "bull":
            low[i] = BASE - 0.0010
        else:
            high[i] = BASE + 0.0010
    for i, v in (extra_low or {}).items():
        low[i] = v
    open_ = np.full(n, BASE)
    close = np.full(n, BASE + 0.00005)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


@pytest.fixture
def df_signals():
    spikes = {
        40: ("bull", 1000),
        60: ("bull", 900),
        90: ("bear", 1000),
        110: ("bear", 900),
        130: ("bull", 1000),
        150: ("bear", 1000),
    }
    return make_df(spikes=spikes)
