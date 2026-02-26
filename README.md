# Gold Trading Bot

Automated trading system for XAUUSD (Gold) using MetaTrader5 with dual-bot strategy (M5 and M1 timeframes).

## Quick Start

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure MetaTrader5:**
   - Install MT5 on Windows
   - Login to your account
   - Ensure XAUUSD is visible in Market Watch

3. **Start the bots:**
   ```bash
   # M5 bot (5-minute timeframe)
   start_bot.bat

   # M1 bot (1-minute timeframe)  
   start_bot_m1.bat

   # Or run both simultaneously
   ```

See [QUICK_START.md](QUICK_START.md) for detailed setup instructions.

## Bot Overview

### M5 Bot (Safe Leveraged)
- **Timeframe:** 5 minutes
- **Strategy:** Mean reversion with bidirectional trading
- **Position:** 15% @ 25x leverage (375% effective)
- **Entry:** RSI 30 (buy) / 75 (sell)
- **Exit:** RSI 85 (long) / 15 (short)
- **Stop Loss:** 3.0x ATR
- **Take Profit:** 4.0%
- **Performance:** ~72% return over 50 days, 75% win rate

### M1 Bot (Aggressive Scalping)
- **Timeframe:** 1 minute
- **Strategy:** Mean reversion scalping with adaptive exits
- **Position:** 15% @ 25x leverage (375% effective)
- **Entry:** RSI 35 (buy) / 65 (sell)
- **Exit:** RSI 75 (long) / 25 (short) with adaptive logic
- **Stop Loss:** 4.0x ATR
- **Take Profit:** 0.8%
- **Performance:** ~237% return over 50 days (with adaptive exits), 66% win rate
- **New:** Adaptive exits cut losses early and let winners run (+42% improvement)

See [M1_ADAPTIVE_EXITS.md](M1_ADAPTIVE_EXITS.md) for details on the adaptive exit system.

See [STRATEGY_SUMMARY.md](STRATEGY_SUMMARY.md) for detailed strategy information.

## Safety Features

Both bots include comprehensive safety mechanisms:

1. **Drawdown Limit** - Pauses at 35% (M5) / 40% (M1) drawdown
2. **Daily Loss Limit** - Pauses if lose 15% in 24 hours
3. **Rapid Loss Detection** - Pauses if lose 10% in 1 hour (flash crash protection)
4. **Consecutive Loss Limit** - Pauses after 8 (M5) / 7 (M1) losses in a row
5. **Emergency Threshold** - Closes all positions if equity drops 50%

See [SAFETY_MECHANISMS.md](SAFETY_MECHANISMS.md) for details.

## Core Files

### Trading Bots
- `live_trading_bot.py` - M5 bot (5-minute timeframe)
- `live_trading_bot_m1.py` - M1 bot (1-minute timeframe)

### Configuration
- `config/safe_leveraged_params.json` - M5 bot parameters
- `config/m1_scalping_params.json` - M1 bot parameters

### Analysis Tools
- `evaluate_live_trades.py` - Analyze actual MT5 trade performance
- `trade_report.py` - Generate detailed trade reports

### Batch Files
- `start_bot.bat` - Start M5 bot
- `start_bot_m1.bat` - Start M1 bot
- `start_bot_demo.bat` - M5 demo mode (no real trades)
- `start_bot_m1_demo.bat` - M1 demo mode

## Documentation

- [QUICK_START.md](QUICK_START.md) - Setup and installation
- [DUAL_BOT_GUIDE.md](DUAL_BOT_GUIDE.md) - Running both bots together
- [SAFETY_MECHANISMS.md](SAFETY_MECHANISMS.md) - Safety features explained
- [STRATEGY_SUMMARY.md](STRATEGY_SUMMARY.md) - Strategy details and performance

## Monitoring

### Check Live Performance
```bash
python evaluate_live_trades.py
```

Shows:
- Win rate and profit/loss
- Average win/loss amounts
- Stop loss rate
- Risk/reward ratio
- Recommendations

### View Trade History
```bash
python trade_report.py
```

Generates detailed report of all trades with entry/exit prices, SL/TP levels, and P/L.

### Logs
- `trading_bot.log` - All bot activity and trades

## Project Structure

```
goldtrade/
├── live_trading_bot.py          # M5 bot
├── live_trading_bot_m1.py        # M1 bot
├── evaluate_live_trades.py      # Performance analysis
├── trade_report.py              # Trade reporting
├── config/                      # Bot configurations
│   ├── safe_leveraged_params.json
│   └── m1_scalping_params.json
├── src/                         # Core modules
│   ├── mt5_connector.py
│   ├── risk_management.py
│   ├── strategies/
│   └── backtesting/
├── analysis/                    # Historical analysis scripts
├── examples/                    # Example scripts
└── docs/                        # Documentation
```

## Requirements

- Windows (MetaTrader5 only runs on Windows)
- Python 3.11+
- MetaTrader5 terminal
- Active trading account with XAUUSD access

## Risk Warning

⚠️ **Trading involves substantial risk of loss.**

- These bots use 25x leverage (high risk)
- Past performance does not guarantee future results
- Only trade with money you can afford to lose
- Test in demo mode first
- Monitor regularly, especially during high volatility

## Support

For issues or questions:
1. Check the documentation files
2. Review `trading_bot.log` for errors
3. Run `evaluate_live_trades.py` to diagnose performance issues

## License

This project is for educational purposes. Use at your own risk.
