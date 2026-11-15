"""
UNKOWN BADSHA - Smart Volume Confirmed OB  (Pine v5 -> Python, line-by-line port)

Pine ke sections ka mapping:
  5. Smart Volume calculation   -> volume_flags()
  6. OB volume confirmation     -> approved = isHigh[length] / isExtreme[length]
  8. OB logic (os, pivothigh)   -> os_state(), pivot_high_volume(), compute()
  9. Mitigation                 -> compute() (remove_mitigated)
  Labels: bullish OB = "ENTRY", bearish OB = "EXIT"
  Alert "BOTH OB" = koi bhi naya bullish ya bearish OB

Non-repainting: sirf closed candles par chalao (main.py forming candle hata deta hai).
Signal confirmation bar par aata hai = pivot candle se `length` bars baad (Pine jaisa hi).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Params:
    length: int = 3                    # Volume Pivot Length
    mitigation: str = "Wick"           # "Wick" | "Close"
    min_strength: str = "High"         # "High" | "Extreme"
    show_weak_ob: bool = False
    vol_len: int = 20
    use_legacy: bool = True            # True => High 2.0x, Extreme 2.5x
    high_factor: float = 1.5
    extreme_factor: float = 2.5
    detect_mode: str = "RVOL only"     # "RVOL only" | "RVOL + Z-Score"
    z_high: float = 1.0
    z_extreme: float = 2.0
    use_pct: bool = False
    pct_min: float = 90.0


@dataclass
class OB:
    kind: str            # "bull" | "bear"
    pivot_idx: int       # volume pivot candle (OB candle)
    confirm_idx: int     # pivot_idx + length  (jab OB bana)
    top: float
    bottom: float
    avg: float
    rvol: float          # pivot candle ka RVOL
    mitigated_idx: int | None = None


@dataclass
class Signal:
    type: str            # "ENTRY" (bullish OB) | "EXIT" (bearish OB)
    time: pd.Timestamp   # confirmation bar ka open time
    price: float         # confirmation bar ka close
    ob: OB


@dataclass
class Result:
    obs: list[OB] = field(default_factory=list)          # sab OBs (mitigated bhi)
    active_bull: list[OB] = field(default_factory=list)
    active_bear: list[OB] = field(default_factory=list)


# ───────────────────────── 5. Smart Volume ─────────────────────────
def volume_flags(df: pd.DataFrame, p: Params):
    vol = df["volume"].fillna(0.0).to_numpy(float)
    n = len(vol)
    s = pd.Series(vol)
    vol_ma = s.rolling(p.vol_len).mean().to_numpy()
    vol_std = s.rolling(p.vol_len).std(ddof=0).to_numpy()      # ta.stdev = population stdev

    pct_rank = np.full(n, np.nan)                               # ta.percentrank: pichhli vol_len values <= current
    for i in range(p.vol_len, n):
        pct_rank[i] = 100.0 * np.sum(vol[i - p.vol_len : i] <= vol[i]) / p.vol_len

    with np.errstate(divide="ignore", invalid="ignore"):
        rvol = np.where(vol_ma > 0, vol / vol_ma, 0.0)
        zscore = np.where(vol_std > 0, (vol - vol_ma) / vol_std, 0.0)

    hi_mult = 2.0 if p.use_legacy else p.high_factor
    ex_mult = 2.5 if p.use_legacy else max(p.extreme_factor, p.high_factor)

    pct_ok = np.ones(n, bool) if not p.use_pct else (pct_rank >= p.pct_min)
    data_ok = (np.arange(n) >= p.vol_len) & (vol > 0)
    rvol_only = p.detect_mode == "RVOL only"

    hi_cond = (rvol > hi_mult) & (rvol_only | (zscore >= p.z_high)) & pct_ok
    ex_cond = (rvol > ex_mult) & (rvol_only | (zscore >= p.z_extreme)) & pct_ok
    is_high = data_ok & (hi_cond | ex_cond)
    is_extreme = data_ok & ex_cond
    return is_high, is_extreme, rvol


# ───────────────────────── 8. OB logic ─────────────────────────
def pivot_high_volume(vol: np.ndarray, L: int) -> np.ndarray:
    """ta.pivothigh(volume, L, L): out[i]=True => bar i-L pivot hai (bar i par confirm).
    Left L bars se strictly zyada, right L bars se >=  (ties: left-most pivot)."""
    n = len(vol)
    out = np.zeros(n, bool)
    for i in range(2 * L, n):
        pv = i - L
        if vol[pv] > vol[pv - L : pv].max() and vol[pv] >= vol[pv + 1 : i + 1].max():
            out[i] = True
    return out


def os_state(high: np.ndarray, low: np.ndarray, upper: np.ndarray, lower: np.ndarray, L: int) -> np.ndarray:
    """os := high[L] > upper ? 0 : low[L] < lower ? 1 : nz(os[1], 0)"""
    n = len(high)
    out = np.zeros(n, int)
    os_ = 0
    for i in range(n):
        if i >= L and not np.isnan(upper[i]):
            if high[i - L] > upper[i]:
                os_ = 0
            elif low[i - L] < lower[i]:
                os_ = 1
        out[i] = os_
    return out


def compute(df: pd.DataFrame, p: Params) -> Result:
    L = p.length
    n = len(df)
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    vol = df["volume"].fillna(0.0).to_numpy(float)
    hl2 = (h + l) / 2.0

    is_high, is_extreme, rvol = volume_flags(df, p)
    strong = is_high if p.min_strength == "High" else is_extreme

    hs, ls, cs = pd.Series(h), pd.Series(l), pd.Series(c)
    upper = hs.rolling(L).max().to_numpy()
    lower = ls.rolling(L).min().to_numpy()
    if p.mitigation == "Close":
        target_bull = cs.rolling(L).min().to_numpy()
        target_bear = cs.rolling(L).max().to_numpy()
    else:
        target_bull, target_bear = lower, upper

    os_arr = os_state(h, l, upper, lower, L)
    pivot = pivot_high_volume(vol, L)

    res = Result()
    for i in range(n):
        if pivot[i]:
            pv = i - L
            approved = bool(strong[pv]) or p.show_weak_ob          # isHigh[length] / isExtreme[length]
            if approved:
                if os_arr[i] == 1:      # Strong Bullish OB
                    top, btm = hl2[pv], l[pv]
                    ob = OB("bull", pv, i, float(top), float(btm), float((top + btm) / 2), float(rvol[pv]))
                    res.obs.append(ob)
                    res.active_bull.append(ob)
                elif os_arr[i] == 0:    # Strong Bearish OB
                    top, btm = h[pv], hl2[pv]
                    ob = OB("bear", pv, i, float(top), float(btm), float((top + btm) / 2), float(rvol[pv]))
                    res.obs.append(ob)
                    res.active_bear.append(ob)

        # 9. Mitigation (har bar, creation wale bar par bhi)
        if not np.isnan(target_bull[i]):
            for ob in [x for x in res.active_bull if target_bull[i] < x.bottom]:
                ob.mitigated_idx = i
                res.active_bull.remove(ob)
            for ob in [x for x in res.active_bear if target_bear[i] > x.top]:
                ob.mitigated_idx = i
                res.active_bear.remove(ob)
    return res


# ───────────────────────── Signals ─────────────────────────
def generate_signals(df: pd.DataFrame, p: Params, mode: str = "all") -> list[Signal]:
    """
    mode "all"  : Pine ke "BOTH OB" alert jaisa. Har naya bullish OB = ENTRY, har naya bearish OB = EXIT.
    mode "state": ENTRY sirf FLAT hone par, EXIT sirf LONG hone par (EXIT tak nayi entry nahi, reversal nahi).
    """
    res = compute(df, p)
    close = df["close"].to_numpy(float)
    signals: list[Signal] = []
    in_long = False
    for ob in sorted(res.obs, key=lambda x: (x.confirm_idx, x.pivot_idx)):
        typ = "ENTRY" if ob.kind == "bull" else "EXIT"
        if mode == "state":
            if typ == "ENTRY" and in_long:
                continue
            if typ == "EXIT" and not in_long:
                continue
            in_long = typ == "ENTRY"
        signals.append(Signal(typ, df.index[ob.confirm_idx], float(close[ob.confirm_idx]), ob))
    return signals
