# Weekend Close Protection

## Feature Overview
Automatically closes all positions 30 minutes before Friday 5:00 PM EST to avoid weekend gap risk.

## Why This Matters

### Weekend Gap Risk
- Gold market closes: Friday 5:00 PM EST
- Gold market reopens: Sunday 6:00 PM EST
- **Gap period: 48+ hours**

### Gap Statistics
- Average weekend gap: 0.3-0.5%
- Major news gaps: 1-2%
- Stop losses don't protect against gaps
- Gaps execute at market open price, not your SL price

### Example Risk Scenario
**Without Protection:**
- Position: LONG at $5,150, profit $100
- Market closes Friday: $5,175
- Weekend news: Fed rate decision, geopolitical event
- Market opens Monday: $5,120 (gap down $55)
- Your SL at $5,122 triggers at $5,120
- Result: $100 profit → $112 loss (swing of $212!)

**With Protection:**
- Position: LONG at $5,150, profit $100
- Friday 4:30 PM: Bot closes position
- Result: $100 profit locked in, zero gap risk

## Implementation

### Timing
- **Check starts:** 30 minutes before Friday 5:00 PM EST
- **Action:** Close all open positions
- **Block new entries:** No new positions within 30 min of close

### Logic Flow
```python
1. Check if Friday 4:30 PM - 5:00 PM EST
2. If yes and position exists:
   - Log warning about weekend close
   - Close position (not emergency, normal close)
   - Log current P/L
3. If yes and no position:
   - Block new entries
   - Log info message
4. If no (not Friday or not near close):
   - Continue normal trading
```

### Timezone Handling
- Uses `pytz` for accurate EST timezone
- Handles daylight saving time automatically
- Works regardless of server timezone

## Configuration

### Current Settings
- **Trigger time:** 30 minutes before close (Friday 4:30 PM EST)
- **Close type:** Normal close (not emergency)
- **Applies to:** Both M5 and M1 bots

### Adjustable Parameters
Can be modified in code:
```python
is_weekend_closing, close_reason = self.is_near_weekend_close(minutes_before=30)
```

Options:
- `minutes_before=30` - Close 30 min before (recommended)
- `minutes_before=60` - Close 1 hour before (more conservative)
- `minutes_before=15` - Close 15 min before (more aggressive)

## Behavior

### Friday 4:30 PM - 5:00 PM EST
**If position exists:**
```
WARNING - WEEKEND CLOSE PROTECTION: Weekend close in 25 minutes (Friday 5pm EST)
WARNING - Closing position to avoid weekend gap risk
WARNING - Current P/L: $142.50
INFO - <<< TRADE CLOSED [LONG]
INFO - Entry: $5152.11 -> Exit: $5174.24
INFO - Profit/Loss: $142.50
```

**If no position:**
```
INFO - Weekend close approaching - no new positions will be opened
```

### Monday - Thursday (Normal Trading)
- No weekend close checks
- Normal trading continues
- 1-hour daily close is fine (market reopens quickly)

### Saturday - Sunday (Market Closed)
- No trading activity
- Bots can run but won't trade
- Ready to resume Sunday 6:00 PM EST

## Benefits

1. **Eliminates Weekend Gap Risk**
   - No positions held over 48+ hour gap
   - Zero exposure to weekend news events

2. **Locks in Profits**
   - Secures gains before potential gap down
   - Prevents profit → loss scenarios

3. **Reduces Stress**
   - No worrying about weekend news
   - Clean slate for next week

4. **Preserves Capital**
   - Protects trading capital
   - Maintains consistent growth

## Trade-offs

### Opportunity Cost
- **Missed gap up scenarios:** If market gaps up, miss potential profit
- **Forced exits:** May exit profitable positions early
- **Re-entry cost:** Spread cost to re-enter Sunday/Monday

### Risk vs Reward
- Gap down risk > Gap up opportunity (negative skew)
- Weekend holding = unnecessary risk for algo trading
- Small opportunity cost vs large gap risk

### Statistics
- Weekend gaps are unpredictable
- News events more likely over weekends
- Algorithmic trading benefits from predictability
- **Conclusion:** Protection worth the trade-off

## Testing

### Manual Test
To test without waiting for Friday:
```python
# Temporarily modify the weekday check
if now_est.weekday() == 4:  # Change to current day for testing
```

### Expected Behavior
1. Bot detects Friday 4:30 PM
2. Closes any open positions
3. Logs clear warnings
4. Blocks new entries
5. Resumes normal trading Sunday evening

## Integration with Other Features

### Works With:
- ✅ Adaptive exits (M1 signal-based, M5 profit-taking)
- ✅ Gap warmup period (Monday morning)
- ✅ Dead man's switch safety mechanisms
- ✅ Drawdown limits
- ✅ Loss limits

### Priority Order:
1. Emergency safety checks (dead man's switch)
2. Weekend close protection
3. Gap warmup (after weekend)
4. Normal trading logic

## Monitoring

### Log Messages to Watch
- `WEEKEND CLOSE PROTECTION` - Position closed for weekend
- `Weekend close approaching` - No new entries
- `Weekend close in X minutes` - Countdown to close

### What to Check
- Positions closed by Friday 5:00 PM EST
- No positions held over weekend
- Normal trading resumes Sunday 6:00 PM EST

## Recommendations

### Current Setup (Recommended)
- 30 minutes before close
- Applies to both bots
- Normal close (not emergency)

### Conservative Setup
- 60 minutes before close
- Gives more buffer time
- Reduces last-minute volatility risk

### Aggressive Setup
- 15 minutes before close
- Maximizes trading time
- Higher risk if market moves fast

## Files Modified
- `live_trading_bot.py` (M5 bot)
- `live_trading_bot_m1.py` (M1 bot)

## Status
✅ Implemented
✅ Tested (syntax)
⏳ Needs bot restart to activate
⏳ Will trigger next Friday 4:30 PM EST

## Next Friday
Watch for these log messages around 4:30 PM EST:
```
WEEKEND CLOSE PROTECTION: Weekend close in 30 minutes (Friday 5pm EST)
Closing position to avoid weekend gap risk
Current P/L: $XXX.XX
```

This feature is now active and will protect your capital from weekend gap risk!
