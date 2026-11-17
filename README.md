# heat-signal-bot

HeatCharting se EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD ka CSV download -> BADSHA OB indicator chalao -> signal aaye to ntfy (phone) par push.
GitHub Actions har 15m candle ke baad apne aap chalata hai.

```
GitHub Actions (cron)
  -> src/fetch_heat.py   saved Google session se login, "..." menu -> Download chart data (CSV)
  -> src/data.py         CSV clean + forming candle hatao + timeframe/price/volume checks
  -> src/indicators/badsha_ob.py   volume-pivot OB, BUY / EXIT state machine
  -> src/notify.py       ntfy push
  -> state/state.json    last alert yaad rakhta hai (duplicate alert nahi)
```

## Signal rules (Pine "UNKOWN BADSHA - Smart Volume Confirmed OB" ka exact port)
- Volume pivot (length 3) par OB banta hai, lekin tabhi jab pivot candle ka volume **High** ho (RVOL > 2.0x, legacy multipliers).
- `os` state (swing low/high) se bullish ya bearish OB decide hota hai.
- Bullish OB = **ENTRY**, Bearish OB = **EXIT** (Pine ke labels jaisa).
- `SIGNAL_MODE=all` (default): har naya OB par alert, Pine ke "BOTH OB" alert jaisa.
- `SIGNAL_MODE=state`: ENTRY sirf FLAT hone par, EXIT sirf LONG hone par; EXIT tak nayi entry nahi, reversal nahi.
- Jo OB alert aane se pehle hi mitigate ho chuka ho (price zone todkar nikal gaya), uska alert nahi aata (`SKIP_MITIGATED=1`, default). Log me `SKIPPED` dikhta hai.
- Alert me OB zone ke saath **abhi ka price aur zone se kitne pips door** hai, wo bhi aata hai.
- Pivot confirm hone ke baad hi signal aata hai (PIVOT_LEN candles ki delay) aur sirf closed candle par chalta hai -> repaint nahi.

## Setup (ek baar)
1. **Session secret:** `python tools/encode_state.py D:\heat_state.json` -> `heat_state.b64` banta hai -> uska poora content GitHub secret `HEAT_STATE` me paste karo (Settings -> Secrets and variables -> Actions).
2. **ntfy:** phone me ntfy app install karo, ek lamba random topic subscribe karo (jaise `badsha-eurusd-x7k2q9`). Wahi topic secret `NTFY_TOPIC` me daalo. (Self-hosted ho to `NTFY_SERVER`, `NTFY_TOKEN` bhi.)
3. Repo me **Settings -> Actions -> General -> Workflow permissions -> Read and write** karo (state commit ke liye).
4. Actions tab -> **signals** -> Run workflow. Pehli run silent hoti hai (sirf baseline set), purane signals ka alert nahi aata.

## Local test
```
pip install -r requirements.txt
python -m pytest -q
python -m src.main --csv downloads\your_file.csv --dry-run
```

## Settings (env vars; defaults Pine ke defaults hain, `src/config.py` me)
SYMBOLS (comma separated, default 5 forex pairs), TIMEFRAME_MIN, SIGNAL_MODE, PIVOT_LEN, MITIGATION (Wick/Close), MIN_STRENGTH (High/Extreme), SHOW_WEAK_OB, VOL_LEN, USE_LEGACY, HIGH_FACTOR, EXTREME_FACTOR, DETECT_MODE, Z_HIGH, Z_EXTREME, USE_PCT, PCT_MIN, SILENT_FIRST_RUN, NOTIFY_ON_ERROR.

## Symbols aur time
- Sab symbols ek hi browser session me download hote hain; har symbol ka state alag (`state/state.json` -> `symbols`). Naya symbol add karna ho to `SYMBOLS` me naam jodo (aur `src/config.py` ke `PRICE_RANGES` me uska price range).
- Log, ntfy message aur state ka saara time **IST** me hai. (GitHub cron khud UTC me hota hai, wo badal nahi sakta.)
- Naye symbol ki pehli run silent hoti hai (sirf baseline).

## Dhyan rakhne wali baatein
- **Session expire hoti hai.** Aisa hone par ntfy par "HeatCharting bot ERROR (SESSION_EXPIRED)" aayega (6 ghante me ek baar). Phir `save_state.py` se cookies dobara save karo, `encode_state.py` chalao, secret update karo.
- **Actions minutes:** public repo me free unlimited. Private repo (free plan) me 2000 min/month; ye bot 5 symbols ke saath ~3-4 min/run x 96 runs/din x ~22 din ~ 7000+ min, yani limit se upar. Private rakhna ho to cron 30m/1h karo ya paid plan lo.
- GitHub cron me 5-15 min delay normal hai; exact-second alerts ki guarantee nahi.
- CSV me volume HeatCharting ka hona zaroori hai; chart par symbol/timeframe galat ho to `validate()` error dega (alert nahi dega).
- Indicator badalne par state apne aap reset ho jaata hai (naya silent baseline), purane signals ka alert nahi aata.
- Pine me `ta.pivothigh` ties (barabar volume) ka rule aise liya hai: left strictly zyada, right >= (leftmost pivot). Chart se mismatch dikhe to bata dena.
- In-app alert "every time" intrabar fire ho sakta hai (pivot candle chalte volume se badalta hai). Ye bot sirf closed candle par chalta hai, isliye zyada bharosemand hai.
