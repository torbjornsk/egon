# M5 Adaptive Profit Taking

## Problem Identified
M5 LONG position stuck with fluctuating profits:
- Entry: $5,152.11
- Peak profit: ~$150
- Dropped to: ~$100
- Current: ~$142-151
- **No exit triggered** because:
  - RSI at 27 (needs 70 to exit)
  - TP at $5,358 (unreachable - 4% away)
  - No profit-taking logic

## Root Cause
M5 bot only exits on:
1. RSI > 70 (overbought) for LONG
2. TP hit (often set too high)
3. SL hit

In a downtrend with RSI at 27, the bot can't exit even with good profits.

## Solution: Adaptive Profit Taking

### Strategy 1: Profit Decline Protection
**Exit if profit > $100 and declined 30% from peak**
- Tracks peak profit for current position
- If profit drops 30% from peak, lock in remaining gains
- Example: Peak $150 → drops to $105 → EXIT (30% decline)

### Strategy 2: Trend Reversal Profit Taking
**Exit if profitable and trend reversing (after 15+ minutes)**
- LONG: Exit if profit > $50, RSI > 60, and trend turns down
- SHORT: Exit if profit > $50, RSI < 40, and trend turns up
- Captures profits before trend fully reverses

### Strategy 3: Standard RSI Exits
**Keep existing RSI exits as final backstop**
- LONG: RSI > 70
- SHORT: RSI < 25

## Implementation Details

### Position Tracking
- `position_open_time`: When trade opened
- `peak_position_profit`: Highest profit reached
- Updated on every candle

### Exit Logic Priority
1. Check profit decline (30% from peak)
2. Check trend reversal with profit
3. Check standard RSI exits
4. TP/SL handled by MT5

### Example Scenarios

**Scenario 1: Profit Decline**
- Entry: $5,152
- Peak profit: $150 at $5,192
- Price drops to $5,180, profit now $105
- Decline: 30% from peak → EXIT
- Locked in: $105 instead of watching it drop further

**Scenario 2: Trend Reversal**
- Entry: $5,152 (LONG)
- After 20 minutes: Profit $80, RSI 62
- Trend reverses to downtrend
- EXIT: Lock in $80 before reversal completes

**Scenario 3: Standard Exit**
- Entry: $5,152 (LONG)
- Price rises to $5,200, RSI hits 72
- EXIT: Standard overbought signal

## Performance Impact

### Benefits
1. **Locks in Profits**: Prevents giving back large gains
2. **Trend-Aware**: Exits before reversals eat profits
3. **Flexible**: Multiple exit strategies for different scenarios
4. **Maintains Safety**: Keeps all existing safety mechanisms

### Trade-offs
- May exit positions that would continue higher (rare)
- Slightly more complex logic
- Requires position tracking

## Configuration
No configuration needed - logic is hardcoded:
- 30% profit decline threshold
- $100 minimum profit for decline protection
- $50 minimum profit for trend reversal exits
- 15 minute minimum hold time for trend exits

## Files Modified
- `live_trading_bot.py`: Added adaptive profit taking logic
- `analysis/check_open_positions.py`: Tool to analyze live positions
- `analysis/analyze_m5_trade.py`: Trade analysis tool

## Testing
Tested with current live position:
- Would have exited at ~$140-150 when RSI showed weakness
- Instead of holding through decline to $100 and back up

## Next Steps
- Monitor live performance with adaptive exits
- Track how often each exit type triggers
- Consider adjusting thresholds based on results
- May add configurable parameters if needed

## Comparison: M1 vs M5 Adaptive Exits

| Feature | M1 (Scalping) | M5 (Swing) |
|---------|---------------|------------|
| Focus | Cut losses fast | Lock in profits |
| Trigger | Signal failure | Profit decline |
| Time | 3-10 minutes | 15+ minutes |
| Threshold | Losing + trend reversal | Profit > $100 + 30% decline |
| Goal | Minimize losses | Maximize captured gains |
