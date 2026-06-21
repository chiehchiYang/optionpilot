# ThetaData free tier (free option data with bid/ask + volume)

ThetaData's **free tier** serves end-of-day options data (OHLC + **volume** + **bid/ask**) for
US stocks — including small caps like ZETA — from a **local terminal**, at no per-query cost.
Verified working end-to-end with OptionPilot.

## What works on the free tier (verified)

- ✅ EOD chains with **bid/ask + volume** (same data fields as paid) → real spread costs +
  liquidity filter + unusual-activity all work.
- ✅ History depth: **recent ~2 years** (2024→present verified). Older data (2023 and before)
  returns `PERMISSION_DENIED` — needs a paid VALUE subscription.
- ⚠️ **Max 1 concurrent request** + rate limits → fetching a full year is **slow** (minutes),
  but it's cached to Parquet afterwards, so you pay the wait once per ticker/range.
- ❌ No real-time streaming (we don't need it — backtests use historical EOD).

> So: use ThetaData (free) for recent ~2-year single-stock backtests; use Databento for deep
> history / 2018–2020 stress tests. Switch with one env var.

## One-time setup

The **v3 terminal** is required for API-key auth and needs **Java 21**. On this box both are
already downloaded under `/media/user/data2/chiehchi/thetadata/`:
- `ThetaTerminalv3.jar`  (from <https://download-unstable.thetadata.us/ThetaTerminalv3.jar>)
- `jdk-21.0.11+10-jre/`  (Temurin JRE 21)

1. Get your **API key** (`td1_...`) from <https://www.thetadata.net> (free account).
2. **Launch the terminal** — Java 21 must be on PATH so the bootstrap's child process uses it:
   ```bash
   cd /media/user/data2/chiehchi/thetadata
   export JAVA_HOME=/media/user/data2/chiehchi/thetadata/jdk-21.0.11+10-jre
   export PATH=$JAVA_HOME/bin:$PATH
   java -jar ThetaTerminalv3.jar --api-key td1_your_key_here
   ```
   Wait for `Starting server at: http://0.0.0.0:25503/`. Leave it running (its own terminal).
   The API key is your credential — keep it secret, don't commit it.
3. **Point OptionPilot at it** — in `.env`:
   ```
   OPTIONPILOT_DATA_SOURCE=thetadata
   OPTIONPILOT_THETADATA_URL=http://127.0.0.1:25503
   ```

Now `run_backtest` / `detect_unusual_activity` pull free local data — no approval prompts
(nothing is purchased). Switch back any time with `OPTIONPILOT_DATA_SOURCE=databento`.

## Notes

- `ThetaDataSource` (in `optionpilot/data/sources.py`) calls the v3 endpoint
  `/v3/option/history/eod?symbol=...&expiration=*&start_date=...&end_date=...&format=ndjson`.
  Strikes are decimal dollars; `right` is CALL/PUT; the bar date is each row's `created` day
  (verified to equal the trading day). Normalization is unit-tested and verified live on ZETA.
- The terminal's child component is compiled for Java 21 — launching with an older `java` on
  PATH (this box's default is Java 8) fails with `UnsupportedClassVersionError`.
