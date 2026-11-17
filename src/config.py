"""Saari settings env vars se aati hain (GitHub Actions me workflow se, local me set/export se)."""
import os


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in ("1", "true", "yes", "on")


# --- Chart / data ---
SYMBOLS = [x.strip().upper() for x in _env("SYMBOLS", "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD").split(",") if x.strip()]
TIMEFRAME_MIN = int(_env("TIMEFRAME_MIN", "15"))
HEAT_URL = _env("HEAT_URL", "https://heatcharting.com/chart")
HEAT_STATE_FILE = _env("HEAT_STATE_FILE", "heat_state.json")
HEADLESS = _bool("HEADLESS", True)
CHART_LOAD_WAIT_MS = int(_env("CHART_LOAD_WAIT_MS", "20000"))
DOWNLOAD_DIR = _env("DOWNLOAD_DIR", "downloads")
MIN_BARS = int(_env("MIN_BARS", "100"))
# Sanity range: galat symbol ka data pakadne ke liye (last close is range me hona chahiye)
PRICE_RANGES = {
    "EURUSD": (0.8, 1.5),
    "GBPUSD": (1.0, 1.8),
    "USDJPY": (100.0, 200.0),
    "AUDUSD": (0.5, 1.0),
    "USDCAD": (1.1, 1.6),
}

# --- Time: sab kuch IST me dikhta/save hota hai ---
TZ_NAME = "Asia/Kolkata"


def to_ist(ts):
    """pandas Timestamp (tz-aware) -> IST"""
    return ts.tz_convert(TZ_NAME)


def now_ist():
    import pandas as pd
    return pd.Timestamp.now(tz=TZ_NAME)


def pip_size(symbol: str) -> float:
    return 0.01 if "JPY" in symbol else 0.0001


def fmt_price(symbol: str, x: float) -> str:
    return f"{x:.{3 if 'JPY' in symbol else 5}f}"


# --- Indicator: UNKOWN BADSHA - Smart Volume Confirmed OB (Pine defaults) ---
PIVOT_LEN = int(_env("PIVOT_LEN", "3"))                    # Volume Pivot Length
MITIGATION = _env("MITIGATION", "Wick")                    # Wick | Close
MIN_STRENGTH = _env("MIN_STRENGTH", "High")                # High | Extreme
SHOW_WEAK_OB = _bool("SHOW_WEAK_OB", False)
VOL_LEN = int(_env("VOL_LEN", "20"))
USE_LEGACY = _bool("USE_LEGACY", True)                     # True => High 2.0x / Extreme 2.5x
HIGH_FACTOR = float(_env("HIGH_FACTOR", "1.5"))
EXTREME_FACTOR = float(_env("EXTREME_FACTOR", "2.5"))
DETECT_MODE = _env("DETECT_MODE", "RVOL only")             # "RVOL only" | "RVOL + Z-Score"
Z_HIGH = float(_env("Z_HIGH", "1.0"))
Z_EXTREME = float(_env("Z_EXTREME", "2.0"))
USE_PCT = _bool("USE_PCT", False)
PCT_MIN = float(_env("PCT_MIN", "90"))
# all  = har naya bullish/bearish OB par alert (Pine "BOTH OB" jaisa)
# state = ENTRY phir EXIT, EXIT tak nayi entry nahi
SIGNAL_MODE = _env("SIGNAL_MODE", "all")
# True: jo OB alert se pehle hi mitigate ho chuka ho (price zone todke nikal gaya), uska alert nahi bhejta
SKIP_MITIGATED = _bool("SKIP_MITIGATED", True)

# --- ntfy ---
NTFY_SERVER = _env("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = _env("NTFY_TOPIC", "")
NTFY_TOKEN = _env("NTFY_TOKEN", "")
NOTIFY_ON_ERROR = _bool("NOTIFY_ON_ERROR", True)
ERROR_ALERT_COOLDOWN_H = int(_env("ERROR_ALERT_COOLDOWN_H", "6"))

# --- State ---
STATE_FILE = _env("STATE_FILE", "state/state.json")
# True: pehli run me purane signals ka alert NAHI bhejta (sirf baseline set karta hai)
SILENT_FIRST_RUN = _bool("SILENT_FIRST_RUN", True)

TF_LABELS = {1: "1m", 5: "5m", 15: "15m", 60: "1h", 240: "4h", 1440: "D"}
