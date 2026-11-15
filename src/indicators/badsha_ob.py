"""
BADSHA OB  (volume-pivot Order Block + entry/exit state machine)

NOTE: Ye Pine indicator ka Python port hai jo notes ke hisaab se bana hai:
  - volume pivot (length = PIVOT_LEN) par Order Block banta hai
  - bullish OB  -> BUY   (neeche ke move ke bottom par)
  - bearish OB  -> EXIT  (upar ke top par)
  - EXIT hone tak koi nayi entry nahi, aur reversal (short) bhi nahi
Pine ka exact code milne par sirf is file ka `find_obs()` match karna hai; baaki repo same rehta hai.

Non-repainting: pivot tabhi confirm hota hai jab uske baad PIVOT_LEN candles band ho chuki hon,
isliye signal pivot candle se PIVOT_LEN bars baad aata hai (Pine me ta.pivothigh jaisa hi).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Params:
    pivot_len: int = 3
    use_wick_zone: bool = False
    require_rvol: bool = False
    rvol_len: int = 20
    rvol_mult: float = 1.5


@dataclass
class OB:
    kind: str            # "bull" | "bear"
    pivot_idx: int       # volume pivot candle
    confirm_idx: int     # jis bar par OB confirm hua (pivot_idx + pivot_len)
    top: float
    bottom: float
    mitigated: bool = False


@dataclass
class Signal:
    type: str            # "BUY" | "EXIT"
    time: pd.Timestamp   # confirmation bar ka open time
    price: float         # confirmation bar ka close
    ob: OB


def find_obs(df: pd.DataFrame, p: Params) -> list[OB]:
    n, L = len(df), p.pivot_len
    vol = df["volume"].to_numpy()
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))

    if p.require_rvol:
        avg = df["volume"].rolling(p.rvol_len).mean().shift(1).to_numpy()
    obs: list[OB] = []

    for i in range(L, n - L):
        window = vol[i - L : i + L + 1]
        # strict pivot high: sirf yahi candle sabse zyada volume ki, left me >, right me >=
        if not (vol[i] > vol[i - L : i].max() and vol[i] >= vol[i + 1 : i + L + 1].max()):
            continue
        if vol[i] <= 0 or window.max() != vol[i]:
            continue
        if p.require_rvol:
            if pd.isna(avg[i]) or avg[i] <= 0 or vol[i] < p.rvol_mult * avg[i]:
                continue

        if c[i] < o[i]:
            kind = "bull"       # volume spike down candle par -> demand zone
        elif c[i] > o[i]:
            kind = "bear"       # volume spike up candle par -> supply zone
        else:
            continue

        if p.use_wick_zone:
            top, bottom = float(h[i]), float(l[i])
        else:
            top, bottom = float(max(o[i], c[i])), float(min(o[i], c[i]))

        ob = OB(kind, i, i + L, top, bottom)
        # mitigation: price zone ke paar close kare
        for j in range(ob.confirm_idx + 1, n):
            if (kind == "bull" and c[j] < bottom) or (kind == "bear" and c[j] > top):
                ob.mitigated = True
                break
        obs.append(ob)
    return obs


def generate_signals(df: pd.DataFrame, p: Params) -> list[Signal]:
    """BUY pehle bullish OB par, EXIT pehle bearish OB par; beech me koi extra signal nahi."""
    obs = sorted(find_obs(df, p), key=lambda x: (x.confirm_idx, x.pivot_idx))
    close = df["close"].to_numpy()
    signals: list[Signal] = []
    in_long = False
    for ob in obs:
        if ob.kind == "bull" and not in_long:
            in_long = True
            signals.append(Signal("BUY", df.index[ob.confirm_idx], float(close[ob.confirm_idx]), ob))
        elif ob.kind == "bear" and in_long:
            in_long = False
            signals.append(Signal("EXIT", df.index[ob.confirm_idx], float(close[ob.confirm_idx]), ob))
    return signals
