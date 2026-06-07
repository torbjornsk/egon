# Egon - Gold Trading Bot

Automated XAUUSD scalping system for MetaTrader 5 with dual-timeframe strategy (M1 and M5).

## Quick Start

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Configure MetaTrader 5:
   - Install MT5 on Windows
   - Login to your account
   - Ensure XAUUSD.p is visible in Market Watch

3. Start a bot:
   ```bash
   # M5 bot (5-minute scalping)
   start_egon_m5.bat

   # M1 bot (1-minute scalping)
   start_egon_m1.bat

   # Dashboard GUI
   start_egon_gui.bat
   ```

## Architecture

```
src/
├── bot/
│   ├── base.py              # BaseTradingBot: main loop, lifecycle, safety
│   ├── m1_bot.py            # M1 factory (thin wiring)
│   └── m5_bot.py            # M5 factory (thin wiring)
├── core/
│   ├── broker.py            # Broker Protocol (abstraction for live/sim)
│   ├── config.py            # TradingConfig dataclass + JSON loader
│   ├── indicators.py        # RSI, EMA, ATR (single source of truth)
│   ├── mt5_broker.py        # Live MT5 Broker implementation
│   ├── mt5_client.py        # Raw MT5 API wrapper
│   ├── position.py          # Position tracking + profit protection
│   ├── risk.py              # Safety: drawdown, daily loss, rapid loss, weekend
│   └── timezone.py          # MT5 timestamp handling (EET/EEST)
├── gui/
│   ├── app.py               # Tkinter dashboard (reads bot.get_state())
│   └── theme.py             # Dark mode constants
├── services/
│   ├── bot_manager.py       # Thread management, log capture
│   ├── market_data.py       # Chart data for GUI
│   └── trade_history.py     # Exit reason display
└── strategy/
    ├── base.py              # TradingStrategy Protocol
    ├── m1_scalping.py       # M1: fast RSI-5, confirmation exits, smart cooldown
    └── m5_scalping.py       # M5: wider RSI-14, simple exits, downtrend shorts
```

## Strategies

### M1 Bot (P4-Patient big SL)
- Timeframe: 1 minute
- Position: 15% at 25x leverage, single position
- Entry: RSI-5 < 30 (buy) / > 70 (sell), symmetric (no trend requirement)
- Exit: RSI > 78 (long) / < 22 (short) with 2-candle confirmation
- Stop loss: 3.50x ATR (adaptive, reduces in high volatility)
- Profit protection: auto-volatility (activates when ATR > 80th percentile)
- Loss backoff: 2-candle cooldown after 2 consecutive SL exits

### M5 Bot (P1-Patient std)
- Timeframe: 5 minutes
- Position: 18% at 27x leverage, split across 2 positions (9% each)
- Entry: RSI-14 < 35 (buy) / > 65 + downtrend (sell)
- Exit: RSI > 65 (long) / < 35 (short)
- Stop loss: 2.25x ATR (adaptive)
- Profit protection: auto-volatility, time-based tightening

## Safety Features

- **Drawdown limit**: pauses at 40% (M1) / 35% (M5)
- **Daily loss limit**: pauses after 15% loss in 24 hours
- **Rapid loss detection**: pauses after 10% loss in 1 hour
- **Consecutive loss limit**: pauses after 12 losses in a row
- **Emergency threshold**: closes all if equity drops 50%
- **Weekend protection**: closes positions 30min before Friday 5pm EST
- **Market gap detection**: warmup period after gaps > 15min
- **Profit protection**: tracks peak profit, exits on drawdown from peak
- **Loss backoff**: cooldown after consecutive stop-loss exits

## GUI Controls

- **PP button**: cycles Auto → ON → OFF → Auto (profit protection override)
- **Mode button**: cycles Both → Long → Short → Both (trading direction)
- **Position cards**: live P/L, peak profit, protection trigger level

## Backtesting

The simulator runs the REAL bot code against historical data (no duplicated logic):

```bash
# Single backtest
python -m tests.run_backtest --days 30

# Monte Carlo (random windows)
python -m tests.run_monte_carlo --runs 50

# A/B comparison with config overrides
python -m tests.run_comparison --override-b rsi_buy=25 rsi_sell=75
```

Key infrastructure:
- `tests/simulator_v2.py` — SimulatorV2 (runs BaseTradingBot against SimBroker)
- `tests/sim_broker.py` — SimBroker (Broker Protocol for backtesting)
- `tests/data_cache.py` — MT5 data fetching with disk caching

## Analysis Tools

```bash
# Live performance analysis
python evaluate_live_trades.py

# Detailed trade report
python trade_report.py --hours 48 --bot m1

# 12-hour deep analysis (streaks, hourly performance)
python -m analysis.analyze_12h

# M5 signal check
python -m analysis.check_m5_signals_24h

# MT5 connection test
python -m analysis.test_mt5_connection
```

## Configuration

All behavior is controlled via JSON configs in `config/`:
- `m1_params.json` — M1 production config
- `m5_params.json` — M5 production config
- `*_previous.json` — rollback references

Config changes take effect on bot restart. No code changes needed to adjust parameters.

## Requirements

- Windows (MetaTrader 5 only runs on Windows)
- Python 3.11+
- MetaTrader 5 terminal with active account
- XAUUSD.p symbol available in Market Watch

## Risk Warning

Trading involves substantial risk of loss. These bots use high leverage. Past performance does not guarantee future results. Only trade with money you can afford to lose.
