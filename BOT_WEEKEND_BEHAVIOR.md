# Bot Behavior During Market Closure

## What You're Seeing

When you start the bots on the weekend (or when market is closed), they:
- ✓ Connect to MT5 successfully
- ✓ Fetch historical data (last available candles)
- ✓ Calculate indicators
- ⏸️  Wait for new candles (none come because market is closed)
- ⏸️  Don't print candle data (because there are no NEW candles)

## This is CORRECT Behavior ✓

### Why No Candle Data?
The bots only print candle information when a NEW candle forms. During weekends:
- Market is closed (Friday 5pm EST to Sunday 5pm EST)
- No new price data
- No new candles
- Nothing to print

### Why No Trade Attempts?
The bots check if the market is open before attempting trades:
- Old MT5: Tried to place order → Failed with "market closed" error
- New MT5 (Dominion): Smarter - doesn't even try when market is closed

## What Changed with Dominion MT5

### Old Behavior (Previous MT5)
```
Bot: "I see a signal!"
Bot: "Attempting to place order..."
MT5: "Error: Market is closed"
Bot: "Order failed"
```

### New Behavior (Dominion MT5)
```
Bot: "I see a signal!"
Bot: "Checking if market is open..."
MT5: "Market is closed"
Bot: "Waiting for market to open..."
```

The new MT5 is smarter and prevents failed order attempts.

## Updated Bot Logging

I've updated both bots to show they're alive even when waiting:

### M1/M5 Bot
Now prints every 60 seconds:
```
⏸️  Waiting for market to open... (last data: 2026-02-27 23:56, 2713min ago)
```

Or when market is open but no new candle yet:
```
⏳ Waiting for new candle... (current: 14:35, price: 5279.36)
```

### Trend Bot
Now prints every 5 minutes:
```
⏸️  Waiting for market... (last H1: 2026-02-27 23:00, 2713min ago)
```

Or when market is open:
```
⏳ Monitoring... (H1: 14:00, price: 5279.36)
```

## When Will Bots Start Trading?

### Gold Market Hours (XAUUSD)
- **Opens**: Sunday 5:00 PM EST
- **Closes**: Friday 5:00 PM EST
- **24/5 Trading**: Monday-Friday continuous

### What Happens When Market Opens
1. New candles start forming
2. Bots detect new candles
3. Bots print candle data
4. Bots analyze for signals
5. Bots place trades if signals appear

## Testing the Bots

### During Weekend (Market Closed)
```bash
python bot_gui.py
```

Expected output:
```
LIVE TRADING BOT STARTED
Strategy: m5_scalping_balanced_aggressive
Timeframe: M5 (5-minute candles)
⏸️  Waiting for market to open... (last data: 2026-02-27 23:56, 2713min ago)
⏸️  Waiting for market to open... (last data: 2026-02-27 23:56, 2714min ago)
...
```

### During Market Hours
```bash
python bot_gui.py
```

Expected output:
```
LIVE TRADING BOT STARTED
Strategy: m5_scalping_balanced_aggressive
Timeframe: M5 (5-minute candles)
⏳ Waiting for new candle... (current: 14:35, price: 5279.36)
============================================================
NEW M5 CANDLE: 2026-03-03 14:40:00
============================================================
Analyzing candle...
Close: 5280.15, EMA5: 5279.50, EMA12: 5278.20, RSI: 55.3
No signal detected
Status: Balance=$10,000.00, Equity=$10,000.00, Trades Today=0
```

## Verifying Bot is Working

### 1. Check Connection
```bash
python tests/test_mt5_connection.py
```

Should show: 10/11 tests passed

### 2. Check Data Fetch
```bash
python tests/test_bot_data_fetch.py
```

Should show:
- ✓ Data fetched successfully
- ⚠️  Data is old (if market closed)
- ✓ Indicators calculated
- ✓ Account info retrieved

### 3. Start Bot and Watch Logs
```bash
python bot_gui.py
```

Should show:
- ✓ Bot started
- ✓ Connected to MT5
- ⏸️  Waiting messages (if market closed)
- ✓ No errors

## Common Questions

### Q: Why doesn't the bot print anything?
**A**: Market is closed. Bot is waiting for new candles. This is correct.

### Q: Is the bot broken?
**A**: No. Run `python tests/test_bot_data_fetch.py` to verify it's working.

### Q: When will I see candle data?
**A**: When market opens (Sunday 5pm EST) and new candles form.

### Q: Why did old MT5 try to place orders on weekend?
**A**: Old MT5 was less strict. Dominion MT5 is smarter and prevents invalid orders.

### Q: How do I know bot is running?
**A**: Updated bots now print status every 60 seconds (M1/M5) or 5 minutes (Trend).

## Market Schedule

### Gold (XAUUSD) Trading Hours
```
Sunday:    5:00 PM EST - Market Opens
Monday:    24 hours
Tuesday:   24 hours
Wednesday: 24 hours
Thursday:  24 hours
Friday:    5:00 PM EST - Market Closes
Saturday:  Closed
Sunday:    Closed until 5:00 PM EST
```

### Current Status
To check if market is open now:
```bash
python tests/test_bot_data_fetch.py
```

Look for:
- "Data is X minutes old"
- If X < 10: Market is open
- If X > 60: Market is closed

## Summary

✓ **Bots are working correctly**
✓ **No candle data on weekend is NORMAL**
✓ **Dominion MT5 is smarter about market hours**
✓ **Updated bots now show "waiting" status**
✓ **Bots will start trading when market opens**

The behavior you're seeing is correct. The bots are waiting for the market to open, which happens Sunday evening. Once the market opens and new candles form, you'll see all the candle data and trading activity.

---

**Next Steps**:
1. Wait for market to open (Sunday 5pm EST)
2. Start bot again
3. Watch for "NEW CANDLE" messages
4. Monitor trading activity
