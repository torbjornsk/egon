---
inclusion: auto
---

# Architecture Reference

## Layers

```
Entry points (run_*.py, run_gui.py)
    └── src/bot/          Bot lifecycle, position management, main loops
        ├── base.py       BaseTradingBot — shared candle-based loop (M5, M1, M15)
        ├── sniper_bot.py SniperBot — hybrid candle + second-by-second
        ├── tick_scalper.py TickScalper — fully tick-based (1-second)
        └── zone_bot.py   ZoneBot — limit order placement at liquidity zones
    └── src/strategy/     ONLY entry/exit logic (no broker, no risk, no lifecycle)
        ├── base.py       TradingStrategy Protocol
        ├── m5_scalping.py   RSI entries, simple RSI exits
        ├── m1_scalping.py   RSI with smart cooldown, confirmation, reversal entry
        ├── m15_scalping.py  Wider RSI bands, fewer trades
        ├── m5_sniper.py     RSI level limit orders + mean-revert exit
        └── liquidity_zones.py  Zone detection + limit order specs
    └── src/core/         Infrastructure (broker, risk, config, indicators)
        ├── broker.py     Broker Protocol + constants (ORDER_TYPE_BUY, DEAL_REASON_SL, etc.)
        ├── mt5_broker.py MT5Broker (wraps MT5Client, implements Broker protocol)
        ├── mt5_client.py Thin wrapper around MetaTrader5 library (all MT5 calls here)
        ├── config.py     TradingConfig dataclass (80+ fields), load_config()
        ├── indicators.py compute_indicators() — RSI, EMA, ATR; shared by all
        ├── position.py   PositionManager — peak tracking, profit protection, exit reasons
        ├── risk.py       RiskManager — drawdown, daily loss, consecutive losses, weekend
        ├── timezone.py   MT5 timestamp conversion (broker time is EET, NOT UTC)
        ├── trend.py      TrendAnalyzer — multi-TF trend scoring (-1 to +1)
        ├── tick_analysis.py TickAnalyzer — entry/exit scoring, VelocityTracker
        ├── rsi_levels.py    Reverse-engineer price for target RSI (sniper limit levels)
        └── liquidity.py     Zone detection (swing points + order blocks)
    └── src/services/     GUI support
        ├── bot_manager.py  BotManager — start/stop bots in threads, state access
        ├── market_data.py  MarketDataService — account, chart, trade history for GUI
        └── trade_history.py  Exit reason loading for GUI display
    └── src/gui/          Tkinter dashboard
        ├── app.py        EgonGUI — 3-column layout, 4 BotSlot instances, chart, history
        └── theme.py      Dark mode colors and ttk styles
```

## Bot Types and Magic Numbers

| Bot       | Magic  | Config              | Class                    | Strategy              | Loop     |
|-----------|--------|---------------------|--------------------------|-----------------------|----------|
| M5 RSI    | 234000 | m5_params.json      | BaseTradingBot           | M5ScalpingStrategy    | Candle   |
| M1 RSI    | 234001 | m1_params.json      | BaseTradingBot           | M1ScalpingStrategy    | Candle   |
| M15 RSI   | 234015 | m15_params.json     | BaseTradingBot           | M15ScalpingStrategy   | Candle   |
| M5 Sniper | 234050 | m5_params.json      | SniperBot                | M5SniperStrategy      | Hybrid   |
| LZ Zones  | 234100 | lz_params.json      | ZoneBot                  | LiquidityZoneStrategy | Candle   |
| Tick      | 234200 | tick_params.json    | TickScalper              | (self-contained)      | 1-second |

## Broker Protocol Pattern

All trading logic works against the `Broker` protocol (`src/core/broker.py`):
- `MT5Broker` for live trading (wraps MT5Client)
- `SimBroker` (`tests/sim_broker.py`) for backtesting (models spread + slippage)

Key methods: `connect()`, `get_tick()`, `get_historical_data()`, `place_order()`,
`close_position()`, `modify_sl()`, `partial_close()`, `get_open_positions()`,
`calculate_lot_size()`, `get_deal_history()`

## GUI Architecture

- `EgonGUI` creates 4 `BotSlot` instances in a 3-column PanedWindow
- Each slot has a bot type selector, start/stop buttons, mode/PP toggles
- Bots run in daemon threads via `BotRunner` (part of `BotManager`)
- State flows one-way: bot `get_state()` dict -> GUI rendering (no reverse calls)
- Chart uses matplotlib TkAgg backend, updates every second
- Trade history fetched from MT5 deal history, matched with exit_reasons JSON files
- Log tab captures per-bot logger output via `StreamHandler` to `StringIO`

## Position Lifecycle

1. **Entry**: Strategy signals -> bot calls `place_order()` -> `PositionManager.register_open()`
2. **Tracking**: Each tick/candle: `register_existing()` updates peak profit
3. **Exit paths**:
   - Bot exit (strategy signal, profit protection, exit score) -> `close_position()` -> `save_exit()`
   - MT5 exit (SL/TP hit) -> detected by `_check_mt5_closes()` -> `save_exit()`
4. **Exit reasons**: Persisted to `data/exit_reasons_{bot}.json` (last 200 per bot)

## Trailing Stop Implementations

- **Tick bot**: Progressive sqrt-curve trailing. Lock-in% = min(0.60, 0.31 * sqrt(profit/ATR)).
  Progress to full trail at 1.5 ATR. Uses `modify_sl()` every second.
- **Sniper bot**: Breakeven at 0.7 ATR, then trail at 1.5 ATR behind price. Every second.
- **Zone bot**: Breakeven at configurable trigger, partial close at target, 3-bar reversal exit.
- **Base bot (M5/M1/M15)**: No trailing (relies on RSI exit + profit protection).

## Exit Score System (Tick Bot Only)

Hybrid C+B approach (as of 2026-06-03):
- **Zone 1 (losing, price < entry)**: Exit if score >= 0.85 for 8 ticks (early damage control)
- **Zone 2 (< 0.5 ATR profit)**: Exit scoring disabled (only trailing/SL can close)
- **Zone 3 (>= 0.5 ATR profit)**: Dynamic threshold = base(0.75) + (1 - profit_ratio) * 0.20
  - At 0.5 ATR: threshold 0.95 (near impossible)
  - At 1.5 ATR: threshold 0.75 (normal sensitivity)
  - Confirmation: 5 ticks base (12 with-trend), +1 tick per $5 profit

## Config System

- All params in `TradingConfig` dataclass with defaults
- Loaded from JSON via `load_config()` — keys starting with `_` are comments
- Per-position size = `position_size_pct / max_positions`
- New fields must have defaults (backward compatible with existing JSON files)

## Testing Infrastructure

- `tests/sim_broker.py` — SimBroker with spread/slippage modeling
- `tests/simulator_v2.py` — Bar-by-bar simulation engine
- `tests/run_backtest.py` — Single config backtest
- `tests/run_comparison.py` — A vs B config comparison
- `tests/run_abc_comparison.py` — Multiple config comparison
- `tests/run_monte_carlo.py` — Statistical significance testing
- `tests/run_replay.py` — Trade-by-trade replay with charts
- `tests/data_cache.py` — Pickle cache for historical data (avoid re-fetching)
- Cache files in `tests/cache/` (e.g., `XAUUSD.p_365d_m5.pkl`)

## Key Patterns

- Exit logic runs BEFORE entry logic (same candle can exit + re-enter)
- `get_local_now()` must be patched in tests (imported in timezone, position, base, risk)
- MT5 timestamps are broker server time (EET/EEST), not UTC
- `copy_rates_from_pos` caps at 99,999 bars per request
- Symbol is `XAUUSD.p` (with the `.p` suffix)
- Use `.venv/Scripts/python.exe` to run commands
