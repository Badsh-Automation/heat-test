import json
from datetime import datetime, timezone

import pytest

from src import config, data, main
from src.data import DataError
from tests.conftest import make_df


def _write_csv(df, path, unix=False):
    out = df.copy()
    out.insert(0, "time", out.index.map(lambda t: int(t.timestamp())) if unix else out.index.strftime("%Y-%m-%dT%H:%M:%SZ"))
    out.to_csv(path, index=False)


def test_load_csv_variants(tmp_path, df_signals):
    for unix in (False, True):
        p = tmp_path / f"d{unix}.csv"
        _write_csv(df_signals, p, unix=unix)
        df = data.load_csv(p)
        assert len(df) == len(df_signals)
        assert df.index[0] == df_signals.index[0]


def test_drop_unclosed(df_signals):
    now = df_signals.index[-1] + __import__("pandas").Timedelta(minutes=5)  # last bar abhi forming
    out = data.drop_unclosed(df_signals, 15, now=now.to_pydatetime())
    assert len(out) == len(df_signals) - 1


def test_validate_rejects_wrong_tf_and_price(df_signals):
    with pytest.raises(DataError):
        data.validate(make_df(tf_min=5), 15, "EURUSD")
    bad = df_signals.copy()
    bad[["open", "high", "low", "close"]] += 60000  # BTC jaisa price
    with pytest.raises(DataError):
        data.validate(bad, 15, "EURUSD")


def test_main_first_run_silent_then_new_signal(tmp_path, monkeypatch, df_signals):
    sent = []
    monkeypatch.setattr(main.notify, "send", lambda *a, **k: sent.append(a) or True)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "MIN_BARS", 50)
    monkeypatch.setattr(data, "drop_unclosed", lambda df, tf, now=None: df)

    # Run 1: pehle 141 bars (history me 5 OB signals) -> silent baseline
    p1 = tmp_path / "a.csv"
    _write_csv(df_signals.iloc[:141], p1)
    assert main.run(str(p1), dry=False) == 0
    assert sent == []
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["symbols"]["EURUSD"]["last_signal"] == "ENTRY" and st["indicator_version"] == main.INDICATOR_VERSION

    # Run 2: pura data (EXIT @153 naya) -> 1 alert
    p2 = tmp_path / "b.csv"
    _write_csv(df_signals, p2)
    assert main.run(str(p2), dry=False) == 0
    assert len(sent) == 1 and "EXIT" in sent[0][0]

    # Run 3: same data dobara -> duplicate alert nahi
    assert main.run(str(p2), dry=False) == 0
    assert len(sent) == 1


def test_state_reset_when_indicator_version_changes(tmp_path, monkeypatch, df_signals):
    sent = []
    monkeypatch.setattr(main.notify, "send", lambda *a, **k: sent.append(a) or True)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "MIN_BARS", 50)
    monkeypatch.setattr(data, "drop_unclosed", lambda df, tf, now=None: df)
    # purani indicator ka state (old version, bahut purana baseline) -> backlog alert nahi aana chahiye
    (tmp_path / "state.json").write_text(json.dumps({"last_alerted_bar": "2020-01-01T00:00:00+00:00", "position": "FLAT"}))
    p = tmp_path / "c.csv"
    _write_csv(df_signals, p)
    assert main.run(str(p), dry=False) == 0
    assert sent == []


def test_multi_symbol_independent_state_and_ist(tmp_path, monkeypatch, df_signals):
    sent = []
    monkeypatch.setattr(main.notify, "send", lambda *a, **k: sent.append(a) or True)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "MIN_BARS", 50)
    monkeypatch.setattr(data, "drop_unclosed", lambda df, tf, now=None: df)
    p_old, p_new = tmp_path / "old.csv", tmp_path / "new.csv"
    _write_csv(df_signals.iloc[:141], p_old)
    _write_csv(df_signals, p_new)

    # GBPUSD ka state: pehle se baseline; EURUSD: bilkul naya (silent baseline)
    assert main.run(str(p_old), False, ["GBPUSD"]) == 0
    assert main.run(str(p_new), False, ["EURUSD"]) == 0
    assert sent == []
    assert main.run(str(p_new), False, ["GBPUSD"]) == 0     # GBPUSD me naya EXIT
    assert len(sent) == 1
    title, msg = sent[0][0], sent[0][1]
    assert title.startswith("GBPUSD 15m EXIT") and "IST" in msg and "UTC" not in msg
    st = json.loads((tmp_path / "state.json").read_text())
    assert set(st["symbols"]) == {"GBPUSD", "EURUSD"}
    assert st["symbols"]["GBPUSD"]["last_alerted_bar"].endswith("+05:30")


def test_old_single_symbol_state_migrates(tmp_path, monkeypatch, df_signals):
    sent = []
    monkeypatch.setattr(main.notify, "send", lambda *a, **k: sent.append(a) or True)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "MIN_BARS", 50)
    monkeypatch.setattr(data, "drop_unclosed", lambda df, tf, now=None: df)
    (tmp_path / "state.json").write_text(json.dumps({
        "indicator_version": main.INDICATOR_VERSION,
        "last_alerted_bar": df_signals.index[140].isoformat(), "last_signal": "ENTRY", "position": "LONG"}))
    p = tmp_path / "n.csv"
    _write_csv(df_signals, p)
    assert main.run(str(p), False, ["EURUSD"]) == 0
    assert len(sent) == 1 and "EXIT" in sent[0][0]
