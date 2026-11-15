import numpy as np

from src.indicators.badsha_ob import Params, compute, generate_signals, pivot_high_volume, volume_flags
from tests.conftest import make_df

P = Params()


def test_obs_and_confirmation_delay(df_signals):
    res = compute(df_signals, P)
    got = [(o.kind, o.pivot_idx, o.confirm_idx) for o in res.obs]
    assert got == [
        ("bull", 40, 43), ("bull", 60, 63), ("bear", 90, 93),
        ("bear", 110, 113), ("bull", 130, 133), ("bear", 150, 153),
    ]


def test_zone_coordinates(df_signals):
    ob = compute(df_signals, P).obs[0]          # bullish: top=hl2[L], bottom=low[L]
    row = df_signals.iloc[40]
    assert ob.bottom == row["low"] and ob.top == (row["high"] + row["low"]) / 2
    bear = compute(df_signals, P).obs[2]        # bearish: top=high[L], bottom=hl2[L]
    row = df_signals.iloc[90]
    assert bear.top == row["high"] and bear.bottom == (row["high"] + row["low"]) / 2


def test_mode_all_matches_pine_both_ob(df_signals):
    sigs = generate_signals(df_signals, P, mode="all")
    assert [s.type for s in sigs] == ["ENTRY", "ENTRY", "EXIT", "EXIT", "ENTRY", "EXIT"]


def test_mode_state_entry_exit_alternate(df_signals):
    sigs = generate_signals(df_signals, P, mode="state")
    assert [s.type for s in sigs] == ["ENTRY", "EXIT", "ENTRY", "EXIT"]
    assert [s.ob.confirm_idx for s in sigs] == [43, 93, 133, 153]


def test_weak_volume_filtered_unless_enabled():
    df = make_df(spikes={50: ("bull", 150)})     # rvol 1.5 < 2.0 (legacy High)
    assert compute(df, P).obs == []
    weak = compute(df, Params(show_weak_ob=True)).obs
    assert len(weak) == 1 and weak[0].kind == "bull"


def test_extreme_strength_needs_2_5x():
    df = make_df(spikes={50: ("bull", 220)})     # rvol ~2.2: High haan, Extreme nahi
    assert len(compute(df, Params(min_strength="High")).obs) == 1
    assert compute(df, Params(min_strength="Extreme")).obs == []


def test_mitigation_wick_removes_bull_ob():
    df = make_df(spikes={50: ("bull", 1000)}, extra_low={80: 1.0985})   # OB bottom 1.0990 se neeche wick
    res = compute(df, P)
    assert len(res.obs) == 1 and res.obs[0].mitigated_idx == 80
    assert res.active_bull == []


def test_no_repaint_before_confirmation(df_signals):
    cut = df_signals.iloc[:42]                   # pivot 40, confirm 43 -> abhi nahi
    assert generate_signals(cut, P) == []
    assert len(generate_signals(df_signals.iloc[:44], P)) == 1


def test_pivot_ties_left_strict_right_inclusive():
    v = np.array([1, 1, 1, 5, 5, 1, 1, 1, 1], float)   # do barabar volume
    out = pivot_high_volume(v, 3)
    assert out[6] and not out[7]                        # pehla (index 3) pivot, dusra nahi


def test_volume_flags_legacy_thresholds():
    df = make_df(spikes={50: ("bull", 1000)})
    hi, ex, rvol = volume_flags(df, P)
    assert hi[50] and ex[50] and not hi[49]
