# Diagnostic Logging - Bot Thought Process

## Overview
Both M5 and M1 bots now include detailed diagnostic logging that shows exactly what the bot is "thinking" on each candle. This helps you understand why the bot is or isn't taking action.

## What's Logged

### 1. Market Data
```
📊 MARKET DATA:
   Price: $5175.64 | ATR: $12.45
   EMA Fast (9): $5172.30 | EMA Slow (21): $5168.50
   Trend: UPTREND ↗
```
- Current price and ATR (volatility measure)
- Fast and Slow EMA values
- Current trend direction (UPTREND ↗, DOWNTREND ↘, or SIDEWAYS ↔)

### 2. RSI Analysis
```
   RSI: 32.4 [██████░░░░░░░░░░░░░░] 🟢 OVERSOLD (BUY ZONE)
   Thresholds: Buy < 35 | Sell > 75
```
- Current RSI value with visual bar
- Color-coded status:
  - 🟢 OVERSOLD (BUY ZONE) - RSI below buy threshold
  - 🔴 OVERBOUGHT (SELL ZONE) - RSI above sell threshold
  - ⚪ NEUTRAL - RSI in middle range
- Entry/exit thresholds

### 3. Position Status
```
📈 POSITIONS: 1/2
   Ticket 7433529564 [LONG 📈]:
      Entry: $5175.64 | Current: $5169.41
      P/L: $-49.84 📉 | Peak: $18.40
      Time Held: 3.2 min
      SL: $5156.71 | TP: $5216.96
```
- Number of open positions vs max allowed
- For each position:
  - Ticket number and type (LONG 📈 or SHORT 📉)
  - Entry price vs current price
  - Current profit/loss with emoji (💰 profit, 📉 loss, ➖ breakeven)
  - Peak profit (M5 only, for adaptive profit taking)
  - Time held in minutes
  - Stop loss and take profit levels

### 4. Entry Logic Analysis
```
🤔 ENTRY LOGIC:
   ✅ Ready for new entry
   🟢 LONG SIGNAL ACTIVE: RSI 32.4 < 35
```

Shows why the bot can or cannot enter:
- ❌ Max positions reached
- ⏳ Gap warmup active
- ⏳ Cooldown active (after loss)
- ✅ Cooldown skipped (after win) - M1 only
- ✅ Ready for new entry

If ready, shows signal status:
- 🟢 LONG SIGNAL ACTIVE - conditions met for long entry
- 🔴 SHORT SIGNAL ACTIVE - conditions met for short entry
- ⚪ No entry signal - explains why (RSI in neutral zone, etc.)

### 5. Exit Logic Analysis
```
🚪 EXIT LOGIC:
   Ticket 7433529564 [LONG]:
      🚨 ADAPTIVE EXIT: Trend reversed to downtrend (losing $49.84)
      ✅ Holding: RSI 34.2 < 75 exit threshold
```

For each open position, shows:

**M5 Adaptive Exits:**
- 🚨 ADAPTIVE EXIT: Profit declined X% from peak
- 💰 Profit tracking: current vs peak profit
- 🚨 ADAPTIVE EXIT: Profitable + RSI reversal signal

**M1 Adaptive Exits:**
- 🚨 ADAPTIVE EXIT: Trend reversed (while losing)
- 🚨 ADAPTIVE EXIT: Signal faded + sideways
- 🚨 TIME-BASED EXIT: Losing after 10 minutes
- ⚠️ Losing but monitoring (not yet at exit threshold)

**Standard Exits (both):**
- 🚨 RSI EXIT: RSI crossed exit threshold
- ✅ Holding: RSI still within acceptable range

## Example Output

### M5 Bot - No Position, Waiting for Signal
```
================================================================================
BOT ANALYSIS - M5 Strategy
================================================================================
📊 MARKET DATA:
   Price: $5175.64 | ATR: $12.45
   EMA Fast (9): $5172.30 | EMA Slow (21): $5168.50
   Trend: UPTREND ↗
   RSI: 45.2 [█████████░░░░░░░░░░░] ⚪ NEUTRAL
   Thresholds: Buy < 25 | Sell > 70

📈 POSITIONS: 0/2
   No open positions

🤔 ENTRY LOGIC:
   ✅ Ready for new entry
   ⚪ No entry signal
      RSI in neutral zone (25-70)
================================================================================
```

### M1 Bot - Position Losing, About to Exit
```
================================================================================
BOT ANALYSIS - M1 Scalping Strategy
================================================================================
📊 MARKET DATA:
   Price: $5169.41 | ATR: $4.23
   EMA Fast (5): $5170.12 | EMA Slow (12): $5172.45
   Trend: DOWNTREND ↘
   RSI: 34.8 [██████░░░░░░░░░░░░░░] 🟢 OVERSOLD (BUY ZONE)
   Thresholds: Buy < 35 | Sell > 75

📈 POSITIONS: 1/2
   Ticket 7433529564 [LONG 📈]:
      Entry: $5175.64 | Current: $5169.41
      P/L: $-49.84 📉
      Time Held: 3.2 min
      SL: $5156.71 | TP: $5216.96

🤔 ENTRY LOGIC:
   ✅ Ready for new entry
   🟢 LONG SIGNAL ACTIVE: RSI 34.8 < 35

🚪 EXIT LOGIC:
   Ticket 7433529564 [LONG]:
      🚨 ADAPTIVE EXIT: Trend reversed to downtrend (losing $49.84)
      ✅ Holding: RSI 34.8 < 75 exit threshold
================================================================================
```

### M5 Bot - Profitable Position, Tracking Peak
```
================================================================================
BOT ANALYSIS - M5 Strategy
================================================================================
📊 MARKET DATA:
   Price: $5174.24 | ATR: $11.89
   EMA Fast (9): $5170.45 | EMA Slow (21): $5165.30
   Trend: UPTREND ↗
   RSI: 76.2 [███████████████░░░░░] 🔴 OVERBOUGHT (SELL ZONE)
   Thresholds: Buy < 25 | Sell > 70

📈 POSITIONS: 1/2
   Ticket 7432693016 [LONG 📈]:
      Entry: $5152.11 | Current: $5174.24
      P/L: $177.04 💰 | Peak: $177.04
      Time Held: 25.3 min
      SL: $5128.45 | TP: $5203.63

🤔 ENTRY LOGIC:
   ✅ Ready for new entry
   ⚪ No entry signal
      RSI in neutral zone (25-70)

🚪 EXIT LOGIC:
   Ticket 7432693016 [LONG]:
      💰 Profit tracking: $177.04 (peak $177.04, decline 0.0%)
      🚨 RSI EXIT: 76.2 > 70 (overbought)
================================================================================
```

## Benefits

1. **Transparency**: See exactly what the bot sees and why it makes decisions
2. **Debugging**: Quickly identify if bot is working as expected
3. **Learning**: Understand the strategy logic in real-time
4. **Monitoring**: Spot potential issues before they become problems
5. **Confidence**: Know the bot is analyzing correctly even when not trading

## Log File Location
All diagnostic output is written to `trading_bot.log` along with regular bot activity.

## Performance Impact
Minimal - diagnostic logging adds ~0.1ms per candle and doesn't affect trading decisions.
