import numpy as np
import pandas as pd
import pytest


def make_df(n=200, tf_min=15, start="2026-11-02 00:00", spikes=None):
    """Flat-ish EURUSD data, base volume 100. spikes = {idx: ('down'|'up', volume)}"""
    idx = pd.date_range(start, periods=n, freq=f"{tf_min}min", tz="UTC")
    rng = np.random.default_rng(1)
    close = 1.10 + np.cumsum(rng.normal(0, 0.00005, n))
    open_ = np.r_[close[0], close[:-1]]
    vol = np.full(n, 100.0)  # flat volume: natural pivots nahi, sirf hamare spikes
    for i, (d, v) in (spikes or {}).items():
        vol[i] = v
        if d == "down":
            open_[i], close[i] = open_[i] + 0.0004, open_[i] - 0.0004
        else:
            open_[i], close[i] = open_[i] - 0.0004, open_[i] + 0.0004
    high = np.maximum(open_, close) + 0.0001
    low = np.minimum(open_, close) - 0.0001
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx
    )


@pytest.fixture
def df_signals():
    spikes = {
        50: ("down", 1000),   # bull OB  -> BUY
        60: ("down", 900),    # 2nd bull OB while long -> ignore
        90: ("up", 1000),     # bear OB  -> EXIT
        100: ("up", 900),     # bear OB while flat -> ignore
        120: ("down", 1000),  # bull OB  -> BUY
        150: ("up", 1000),    # bear OB  -> EXIT
    }
    return make_df(spikes=spikes)
