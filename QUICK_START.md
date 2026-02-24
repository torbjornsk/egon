# Quick Start Guide - Gold Trading Bot

## 🚀 Get Started in 3 Steps

### Step 1: Test the Bot (DEMO MODE)

```bash
# Double-click this file or run:
start_bot_demo.bat
```

This runs the bot in dry-run mode - it will analyze the market but NOT place actual trades. Perfect for testing!

### Step 2: Monitor Performance

Open a second terminal and run:

```bash
python monitor_bot.py
```

This shows real-time stats:
- Current balance and profit
- Open positions
- Recent trades
- Win rate

### Step 3: Go Live (When Ready)

```bash
# Double-click this file or run:
start_bot.bat
```

⚠️ **WARNING:** This will trade with real money!

## 📊 What to Expect

Based on 8-month backtest with the **Aggressive (15% @ 25x)** configuration:

- **Return:** ~150% over 8 months (~225% annualized)
- **Max Drawdown:** ~30%
- **Win Rate:** ~61%
- **Trades:** ~185 per month

## 🎯 Strategy Overview

**Entry Signals:**
- **LONG:** RSI < 30 (oversold - buy the dip)
- **SHORT:** RSI > 75 AND downtrend (overbought in bear market)

**Exit Signals:**
- RSI opposite extreme (75 for longs, 30 for shorts)
- 3% profit target
- ATR-based stop loss (3x ATR)

**Position Sizing:**
- Uses 15% of balance per trade
- 25x leverage applied
- Effective position: 375% of balance

## 🛡️ Safety Features

1. **Stop Losses:** Every trade has automatic stop loss
2. **Drawdown Limit:** Bot pauses if drawdown exceeds 35%
3. **Position Limits:** Only 15% of balance at risk per trade
4. **Margin Protection:** Prevents over-leveraging

## 📁 Configuration Files

Choose your risk level:

| File | Strategy | Return | Drawdown | Risk Level |
|------|----------|--------|----------|------------|
| `safe_leveraged_params.json` | **Aggressive** | 150% | 30% | ⚠️ High |
| `bidirectional_strategy_params.json` | Moderate | 27% | 5.5% | ✓ Medium |
| `hybrid_strategy_params.json` | Conservative | 28% | 4.5% | ✓✓ Low |

To change strategy:

```bash
python live_trading_bot.py --config config/bidirectional_strategy_params.json
```

## 📝 Daily Checklist

- [ ] Check bot is running
- [ ] Review `trading_bot.log` for errors
- [ ] Monitor current drawdown (should be < 35%)
- [ ] Verify trades are executing as expected

## 🆘 Emergency Stop

1. Press `Ctrl+C` in the bot terminal
2. Bot will stop gracefully
3. Close any open positions manually in MT5 if needed

## 📞 Need Help?

1. Read `LIVE_TRADING_GUIDE.md` for detailed instructions
2. Check `trading_bot.log` for error messages
3. Test with demo mode first (`start_bot_demo.bat`)

## ⚠️ Final Warnings

- **Start with DEMO** - Test for at least 1-2 weeks
- **Start small** - Use only money you can afford to lose
- **Monitor daily** - Don't set and forget
- **Understand risks** - Leverage amplifies both gains AND losses
- **Have a plan** - Know when to stop (e.g., if drawdown > 40%)

## 🎓 Learning Resources

- `STRATEGY_SUMMARY.md` - Comparison of all tested strategies
- `LIVE_TRADING_GUIDE.md` - Comprehensive setup and monitoring guide
- `trading_bot.log` - Real-time bot activity log

---

**Remember:** Past performance doesn't guarantee future results. Trade responsibly!
