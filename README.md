# heat-signal-bot

HeatCharting se EURUSD ka CSV download -> BADSHA OB indicator chalao -> signal aaye to ntfy (phone) par push.
GitHub Actions har 15m candle ke baad apne aap chalata hai.

```
GitHub Actions (cron)
  -> src/fetch_heat.py   saved Google session se login, "..." menu -> Download chart data (CSV)
  -> src/data.py         CSV clean + forming candle hatao + timeframe/price/volume checks
  -> src/indicators/badsha_ob.py   volume-pivot OB, BUY / EXIT state machine
  -> src/notify.py       ntfy push
  -> state/state.json    last alert yaad rakhta hai (duplicate alert nahi)
```

## Signal rules
- Bullish OB banta hai aur position FLAT hai -> **BUY**
- Bearish OB banta hai aur position LONG hai -> **EXIT**
- EXIT hone tak koi nayi entry nahi, reversal (short) nahi. SL/TP/ATR logic nahi.
- Pivot confirm hone ke baad hi signal aata hai (PIVOT_LEN candles ki delay) -> repaint nahi.

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

## Settings (env vars, defaults `src/config.py` me)
SYMBOL, TIMEFRAME_MIN, PIVOT_LEN (3), USE_WICK_ZONE, REQUIRE_RVOL / RVOL_LEN / RVOL_MULT, SILENT_FIRST_RUN, NOTIFY_ON_ERROR.

## Dhyan rakhne wali baatein
- **Session expire hoti hai.** Aisa hone par ntfy par "HeatCharting bot ERROR (SESSION_EXPIRED)" aayega (6 ghante me ek baar). Phir `save_state.py` se cookies dobara save karo, `encode_state.py` chalao, secret update karo.
- **Actions minutes:** public repo me free unlimited. Private repo (free plan) me 2000 min/month; ye bot ~1.5-2 min/run x 96 runs/din x ~22 din ~ 3000-4000 min, yani limit se upar. Private rakhna ho to cron 30m/1h karo ya paid plan lo.
- GitHub cron me 5-15 min delay normal hai; exact-second alerts ki guarantee nahi.
- CSV me volume HeatCharting ka hona zaroori hai; chart par symbol/timeframe galat ho to `validate()` error dega (alert nahi dega).
- `src/indicators/badsha_ob.py` abhi notes ke hisaab se OB logic use karta hai. Pine ka exact code milne par sirf `find_obs()` match karna hai.
