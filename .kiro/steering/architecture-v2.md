# Architecture v2 — Session Changes (June 2026)

## Overview

Major refactor from per-bot-type code to a config-driven framework. The sniper bot is now fully configurable — timeframe, RSI levels, offsets, sizing, trailing, schedule — all from JSON. New bots are created by writing config files, not code.

## Key Architectural Changes

### 1. Unified Sniper Strategy (`src/strategy/sniper.py`)

- Single `SniperStrategy` class replaces M1SniperStrategy, M5SniperStrategy, M15SniperStrategy
- All behavior driven by `TradingConfig` fields (timeframe, sniper_rsi_offset, exit_rsi, trail distances, etc.)
- Old files (`m1_sniper.py`, `m5_sniper.py`, `m15_sniper.py`) are thin re-export wrappers for backward compat
- `SniperBot` (`src/bot/sniper_bot.py`) reads all constants from config — no hardcoded values

### 1b. Breakout Strategy (`src/strategy/breakout.py`)

- `BreakoutStrategy` class: N-bar high/low breakout with EMA 9/21 trend filter
- No RSI — purely momentum-based entry (price breaks above/below recent range)
- No candle-based exit — relies entirely on trailing stop in BaseTradingBot
- Uses `BaseTradingBot` directly (no custom bot class needed)
- `get_strategy_state(df)` provides breakout levels for GUI display
- Config fields: `breakout_bars`, `breakout_min_atr`, `breakout_re_entry_bars`, `breakout_sl_atr_mult`, `breakout_trail_atr_mult`
- Risk fields: `breakout_max_daily_loss_pct`, `breakout_max_daily_trades`, `breakout_max_drawdown_pct`
- Magic number: 234300, label: BRK
- GUI shows breakout-specific indicators (ATR, trend, breakout high/low levels) instead of RSI

### 2. Position Sizing Modes

Three modes available via `sizing_mode` field:
- `risk_pct` — risk X% of account per trade, SL distance determines lot size (recommended)
- `fixed` — use exact lot size
- `atr_adaptive` — risk_pct but scaled down in high-ATR regimes

Legacy mode (`position_size_pct * leverage`) still works for old configs but is not exposed in GUI.

New broker method: `calculate_lot_size_from_risk(risk_amount, stop_distance)` in MT5Client, MT5Broker, and SimBroker.

### 3. Bot Registry (`src/services/bot_manager.py`)

- `BOT_REGISTRY` dict maps `bot_type` string → factory function
- `start_from_config(path)` reads `bot_type` from JSON, no more if/elif chain
- `LEGACY_LABEL_MAP` provides backward compat for `start_bot('M5S')` style calls
- `list_available_configs()` scans `config/` directory for GUI discovery
- Adding a new bot type = one factory function + one registry entry

### 4. Config System (`src/core/config.py`)

New identity fields in `TradingConfig`:
- `config_name`, `bot_type`, `symbol`, `timeframe`, `magic_number`, `bot_label`, `order_comment`

Sniper-specific fields:
- `sniper_rsi_offset` — limit order RSI depth (replaces per-class hardcoded offsets)
- `exit_rsi` — configurable mean-revert exit target (default 50)
- `adaptive_exit_enabled` — toggle for trend-based exit shift
- `exit_rsi_trend_threshold`, `exit_rsi_trend_shift` — adaptive parameters
- `trail_atr_after_breakeven`, `trail_atr_before_breakeven` — trailing distances
- `tp_fallback_atr_mult` — TP fallback when RSI calc fails

Schedule (flat fields):
- `schedule_enabled`, `schedule_mon`..`schedule_sun` — per-day "HH:MM-HH:MM"
- `schedule_closed` — list of "YYYY-MM-DD HH:MM-HH:MM" news event windows

Volatility guard (flat fields):
- `vg_enabled`, `vg_atr_spike_multiplier`, `vg_cooldown_minutes`, `vg_resume_below_multiplier`

Removed from sniper usage:
- `rsi_exit_long` / `rsi_exit_short` (redundant — mean-revert exit handles this)
- `sniper_rsi_min` / `sniper_rsi_max` (clamping done in code as 0-100)

### 5. Scheduler (`src/core/scheduler.py`)

- Per-day trading hours with "HH:MM-HH:MM" format
- Closed windows for news events (override daily schedule)
- When paused: exits still fire (trailing, PP), only new entries blocked
- Reads flat fields from TradingConfig

### 6. Volatility Guard (`src/core/volatility_guard.py`)

- Pauses entries when ATR > median × spike_multiplier
- Cooldown period before re-evaluating
- Resumes when ATR drops below resume_multiplier
- Reads flat fields from TradingConfig

### 7. GUI (`src/gui/app.py`)

Complete redesign:
- **Left panel**: Bot instance list (discovered from config/ files), account summary
- **Right panel**: Multi-column bot detail panels (open multiple bots side by side, horizontally scrollable)
- **Bottom**: Two side-by-side tabbed notebooks (Chart, Trades, Log, Market, Sizing Calc) — each independent
- **Close button** (X) on each bot panel stops the bot and removes the panel
- **"+ New" button** shows dialog: pick bot_type + name → auto-generates magic number + filename
- **Config editor**: dropdowns for enums/booleans, human-readable labels, read-only bot_type/magic_number
- **Sizing Calculator** tab: live lot size preview from balance + risk% + SL distance
- **Log tab**: captures ALL loggers via root handler (not just bot-specific)
- **Instance list**: updates in-place (no flashing), mousewheel scrollable

### 8. Timeframe Support (`src/core/broker.py`)

- Added `TIMEFRAME_H1`, `TIMEFRAME_H4` constants
- `TIMEFRAME_MAP` and `TIMEFRAME_MINUTES` dicts for string → MT5 constant lookup

### 9. CI/CD (`.github/workflows/build.yml`)

- GitHub Actions pipeline: triggers on push to master
- Auto-generates version: `v2.YYYY.MMDD.run_number`
- Runs import checks → PyInstaller build → zip → GitHub Release
- Windows runner (required for MT5 DLLs)

## File Structure (new/changed)

```
src/strategy/sniper.py          — Unified sniper strategy (NEW)
src/strategy/breakout.py        — N-bar breakout with EMA trend filter (NEW)
src/core/scheduler.py           — Time-based schedule (NEW)
src/core/volatility_guard.py    — ATR spike detection (NEW)
src/gui/app.py                  — Complete GUI rewrite
src/services/bot_manager.py     — Registry-based bot management
src/core/config.py              — Extended TradingConfig
src/core/broker.py              — Timeframe maps, new sizing method
src/core/mt5_broker.py          — calculate_lot_size_from_risk
src/core/mt5_client.py          — calculate_lot_size_from_risk
src/bot/sniper_bot.py           — Uses config values, scheduler, guard
config/breakout_params.json     — Breakout bot default config (NEW)
docs/sniper_bot_guide.html      — Sniper user guide (NEW)
docs/breakout_bot_guide.html    — Breakout user guide (NEW)
.github/workflows/build.yml     — CI/CD pipeline (NEW)
```

## Backward Compatibility

- Old configs without new fields load fine (defaults apply)
- `start_bot('M5S')` legacy label still works via LEGACY_LABEL_MAP
- Old strategy imports (`from src.strategy.m5_sniper import M5SniperStrategy`) work via re-export wrappers
- SimBroker has the new `calculate_lot_size_from_risk` method
- Configs with `sizing_mode: "legacy"` still work (old formula)

## Next Steps (discussed but not yet implemented)

### Supervisor (Phase 4)
- Rule-based market regime assessment: breakout detection (S/R levels + ATR), dead market detection
- Actions: pause, resume, switch config profile, adjust risk
- Key insight: sniper works well in BOTH trending and ranging markets (larger pullbacks = more profit)
- Primary dangers: breakouts through S/R levels, dead markets (ATR too low for commission)
- Support/resistance levels for breakout detection (extend liquidity zone code)
- Per-timeframe decisions (M5 good in trends, M1 better in tight ranges)
- Config switching: supervisor can apply different profiles based on regime
