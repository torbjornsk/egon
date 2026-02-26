# Quick Start Guide

Get your gold trading bots running in 10 minutes.

## Prerequisites

- Windows PC (MetaTrader5 requirement)
- MetaTrader5 installed
- Trading account with XAUUSD access
- Python 3.11+ (recommended: use `uv` package manager)

## Step 1: Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

## Step 2: Configure MetaTrader5

1. **Open MT5** and login to your account
2. **Add XAUUSD to Market Watch:**
   - Right-click Market Watch
   - Select "Symbols"
   - Find "XAUUSD" (Gold)
   - Click "Show" and "OK"
3. **Verify connection:**
   - Check that prices are updating
   - Ensure you're logged in (not "No connection")

## Step 3: Test Connection

```bash
python -c "import MetaTrader5 as mt5; print('Connected!' if mt5.initialize() else 'Failed')"
```

Should print "Connected!"

## Step 4: Choose Your Bot

### Option A: M5 Bot Only (Recommended for beginners)
- More stable, fewer trades
- 5-minute timeframe
- ~$38 per trade average

```bash
start_bot.bat
```

### Option B: M1 Bot Only
- More aggressive, many trades
- 1-minute timeframe
- Higher variance

```bash
start_bot_m1.bat
```

### Option C: Both Bots (Advanced)
- Run in separate terminals
- Different magic numbers prevent conflicts
- See [DUAL_BOT_GUIDE.md](DUAL_BOT_GUIDE.md)

```bash
# Terminal 1
start_bot.bat

# Terminal 2
start_bot_m1.bat
```

## Step 5: Monitor

The bot will log all activity to console and `trading_bot.log`.

**What you'll see:**
```
2026-02-25 10:30:15 - INFO - Connected to MT5
2026-02-25 10:30:15 - INFO - Balance: $1000.00
2026-02-25 10:30:20 - INFO - >>> TRADE OPENED [LONG]
2026-02-25 10:30:20 - INFO -   Entry: $5185.50
2026-02-25 10:30:20 - INFO -   Stop Loss: $5175.20
2026-02-25 10:30:20 - INFO -   Take Profit: $5225.50
```

## Step 6: Check Performance

After a few hours/days:

```bash
python evaluate_live_trades.py
```

Shows win rate, profit/loss, and recommendations.

## Demo Mode (Testing)

Test without real money:

```bash
# M5 demo
start_bot_demo.bat

# M1 demo
start_bot_m1_demo.bat
```

**Note:** Demo mode simulates trades but doesn't place real orders. Use this to verify the bot works before going live.

## Stopping the Bot

Press `Ctrl+C` in the terminal. The bot will:
1. Close any open positions (managed by SL/TP)
2. Print a session summary
3. Exit gracefully

## Common Issues

### "MT5 initialization failed"
- Ensure MT5 is running and logged in
- Check that you're not in a virtual machine (MT5 doesn't work in VMs)

### "Symbol XAUUSD not found"
- Add XAUUSD to Market Watch (see Step 2)
- Verify your broker offers gold trading

### "No prices available"
- Market might be closed (gold trades 23/5)
- Check MT5 connection status

### Bot pauses trading
- Check logs for reason (drawdown limit, daily loss, etc.)
- See [SAFETY_MECHANISMS.md](SAFETY_MECHANISMS.md)
- Review with `python evaluate_live_trades.py`

## Next Steps

- Read [DUAL_BOT_GUIDE.md](DUAL_BOT_GUIDE.md) for running both bots
- Review [SAFETY_MECHANISMS.md](SAFETY_MECHANISMS.md) to understand protections
- Check [STRATEGY_SUMMARY.md](STRATEGY_SUMMARY.md) for strategy details

## Configuration

Bot parameters are in:
- `config/safe_leveraged_params.json` (M5)
- `config/m1_scalping_params.json` (M1)

**Don't modify unless you know what you're doing!** The current settings are optimized through extensive backtesting.

## Support

If something goes wrong:
1. Check `trading_bot.log` for errors
2. Run `python evaluate_live_trades.py` to see what happened
3. Review the documentation files

## Risk Warning

⚠️ **Start with small amounts!**

- Bots use 25x leverage (high risk)
- Test in demo mode first
- Only trade what you can afford to lose
- Monitor regularly during first week

Good luck! 🚀
