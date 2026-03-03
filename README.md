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
   - Ensure XAUUSD is visible in Market Watch

3. Start a bot:
   ```bash
   # M5 bot (5-minute scalping)
   start_egon_m5.bat

   # M1 bot (1-minute scalping)
   start_egon_m1.bat

   # Dashboard GUI
   start_egon_gui.bat
   ```

   Or from the command line:
   ```bash
   python run_m5.py
   python run_m1.py
   python run_gui.py
   ```

## Strategies

### M5 Bot (Balanced Aggressive)
- Timeframe: 5 minutes
- Position: 18% at 27x leverage, split across up to 2 positions (9% each)
- Entry: RSI 38 (buy) / 62 (sell) with EMA trend filter
- Exit: RSI 60 (long) / 40 (short), take profit at 2.8%
- Stop loss: 2.0x ATR (adaptive, reduces to 1.5x in high volatility)
- Profit protection: activates at 4% of invested amount, tightens over time

### M1 Bot (Scalping)
- Timeframe: 1 minute
- Position: 15% at 25x leverage, split across up to 2 positions (7.5% each)
- Entry: RSI 35 (buy) / 65 (sell) with EMA trend filter
- Exit: RSI 75 (long) / 25 (short) with confirmation, take profit at 0.8%
- Stop loss: 2.75x ATR (adaptive, reduces to 2.0x in high volatility)
- Profit protection: activates at 2% of invested amount, tightens over time
- Smart cooldown: skips cooldown after wins when reversal conditions are met
- Loss backoff: exponential cooldown increase after consecutive losses

## Safety Features

- Drawdown limit: pauses at 35% (M5) / 40% (M1)
- Daily loss limit: pauses after 15% loss in 24 hours
- Rapid loss detection: pauses after 10% loss in 1 hour
- Consecutive loss limit: pauses after 8 (M5) / 7 (M1) losses in a row
- Emergency threshold: closes all positions if equity drops 50%
- Profit protection: prevents green-to-red by tracking peak profit and exiting on drawdown
- Loss backoff: exponential cooldown after consecutive losses to avoid catching falling knives

## Project Structure

```
egon/
├── src/                         # Core package
│   ├── bot/                     # Bot implementations
│   │   ├── base.py              # Base trading bot (shared logic)
│   │   ├── m1_bot.py            # M1 bot factory
│   │   └── m5_bot.py            # M5 bot factory
│   ├── core/                    # Core modules
│   │   ├── config.py            # TradingConfig dataclass
│   │   ├── indicators.py        # Technical indicators (RSI, EMA, ATR)
│   │   ├── mt5_client.py        # MetaTrader 5 connection wrapper
│   │   ├── position.py          # Position management and exit logic
│   │   ├── risk.py              # Risk management and safety checks
│   │   └── timezone.py          # Timezone handling (EET/EEST)
│   ├── gui/                     # Dashboard GUI
│   │   ├── app.py               # Main GUI application
│   │   └── theme.py             # Visual theme
│   ├── services/                # Services
│   │   ├── bot_manager.py       # Multi-bot orchestration
│   │   ├── market_data.py       # Market data fetching
│   │   └── trade_history.py     # Trade history tracking
│   └── strategy/                # Strategy implementations
│       ├── base.py              # Base strategy interface
│       ├── m1_scalping.py       # M1 scalping strategy
│       └── m5_scalping.py       # M5 scalping strategy
├── config/                      # Bot configurations
│   ├── m1_params.json           # M1 bot parameters
│   └── m5_params.json           # M5 bot parameters
├── data/                        # Runtime data
│   ├── exit_reasons_m1.json     # M1 exit reason tracking
│   └── exit_reasons_m5.json     # M5 exit reason tracking
├── analysis/                    # Analysis and diagnostic scripts
├── run_m1.py                    # M1 bot entry point
├── run_m5.py                    # M5 bot entry point
├── run_gui.py                   # Dashboard entry point
├── evaluate_live_trades.py      # Live performance analysis
├── trade_report.py              # Detailed trade reporting
├── start_egon_m1.bat            # Windows launcher (M1)
├── start_egon_m5.bat            # Windows launcher (M5)
└── start_egon_gui.bat           # Windows launcher (GUI)
```

## Monitoring

Analyze live performance:
```bash
python evaluate_live_trades.py
```

Generate a detailed trade report:
```bash
python trade_report.py --hours 48 --bot m1
```

## Requirements

- Windows (MetaTrader 5 only runs on Windows)
- Python 3.10+
- MetaTrader 5 terminal with active account
- XAUUSD symbol available in Market Watch

## Risk Warning

Trading involves substantial risk of loss. These bots use high leverage. Past performance does not guarantee future results. Only trade with money you can afford to lose. Test in demo mode first and monitor regularly.
