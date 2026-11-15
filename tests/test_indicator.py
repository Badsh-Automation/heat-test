from src.indicators.badsha_ob import Params, find_obs, generate_signals


def test_obs_detected(df_signals):
    obs = find_obs(df_signals, Params(pivot_len=3))
    pivots = {(o.pivot_idx, o.kind) for o in obs}
    assert (50, "bull") in pivots and (90, "bear") in pivots


def test_state_machine_buy_exit_only(df_signals):
    sigs = generate_signals(df_signals, Params(pivot_len=3))
    assert [s.type for s in sigs] == ["BUY", "EXIT", "BUY", "EXIT"]
    # signal pivot ke 3 bars baad aata hai (confirmation)
    assert [s.ob.confirm_idx for s in sigs] == [53, 93, 123, 153]


def test_no_repaint_last_bars(df_signals):
    # Agar data pivot confirm hone se pehle kat jaye to signal nahi aana chahiye
    cut = df_signals.iloc[:52]  # pivot 50, confirm 53 -> abhi confirm nahi
    assert generate_signals(cut, Params(pivot_len=3)) == []
