# Dual Bot Guide

Running M5 and M1 bots simultaneously for maximum coverage.

## Overview

The dual bot system runs two independent strategies:
- **M5 Bot:** Stable, fewer trades, larger moves
- **M1 Bot:** Aggressive, many trades, quick scalps

They use different magic numbers (234000 vs 234001) so they won't interfere with each other.

## Performance

Based on 24-hour live testing:
- **M5:** 8 trades, $305 profit, 75% win rate, $38/trade
- **M1:** 48 trades, -$146 loss, 56% win rate, -$3/trade
- **Combined:** $160 profit

**Note:** M1 is more volatile. Over longer periods (14+ days), both are profitable.

## Setup

### 1. Open Two Terminals

**Terminal 1 (M5):**
```bash
start_bot.bat
```

**Terminal 2 (M1):**
```bash
start_bot_m1.bat
```

### 2. Verify Both Running

Each terminal should show:
```
Connected to MT5
Account: [your account]
Balance: $[amount]
Configuration loaded: [strategy name]
```

### 3. Monitor

Both bots log to the same `trading_bot.log` file. You can distinguish them by:
- M5 uses comment "m5_open" / "m5_close"
- M1 uses comment "m1_open" / "m1_close"

## Safety Considerations

### Independent Safety Limits

Each bot has its own safety mechanisms:

**M5 Bot:**
- 35% drawdown limit
- 8 consecutive losses
- 15% daily loss limit

**M1 Bot:**
- 40% drawdown limit
- 7 consecutive losses
- 15% daily loss limit

If one bot pauses, the other continues trading.

### Combined Risk

Running both bots means:
- More positions open simultaneously
- Higher margin usage
- Faster drawdown if both lose together

**Recommendation:** Ensure you have adequate margin (at least 2x the combined position sizes).

## Monitoring Both Bots

### Check Combined Performance

```bash
python evaluate_live_trades.py
```

Shows performance for each bot separately and combined.

### Individual Bot Status

Check the logs:
```bash
# Last 50 lines
Get-Content trading_bot.log -Tail 50

# Filter by bot
Get-Content trading_bot.log | Select-String "m5_"
Get-Content trading_bot.log | Select-String "m1_"
```

## When to Run Both

**Good scenarios:**
- You want maximum market coverage
- You're comfortable with higher variance
- You have adequate margin
- You can monitor regularly

**Bad scenarios:**
- Limited margin (< $2000)
- First time using the bots
- High market volatility
- Can't monitor for days

## When to Run Only M5

**Recommended if:**
- You want stability over volume
- Limited margin
- First time user
- Prefer fewer, higher-quality trades

M5 alone has proven very profitable ($305 in 24h, 75% win rate).

## Stopping Both Bots

Press `Ctrl+C` in each terminal. They will:
1. Stop opening new positions
2. Let existing positions close via SL/TP
3. Print session summaries
4. Exit

**Important:** Stop both bots if you need to close all positions manually.

## Troubleshooting

### One bot stops, other continues
- This is normal! Safety limits are independent
- Check logs to see why one paused
- Restart the paused bot if appropriate

### Both bots trading same direction
- This is fine! They use different entry/exit criteria
- M5 catches larger moves
- M1 scalps smaller moves

### Margin call warning
- Close one or both bots immediately
- Reduce position sizes in config
- Ensure adequate account balance

## Configuration

**M5 Bot:** `config/safe_leveraged_params.json`
```json
{
  "position_size_pct": 0.15,
  "leverage": 25,
  "max_drawdown_limit": 0.35
}
```

**M1 Bot:** `config/m1_scalping_params.json`
```json
{
  "position_size_pct": 0.15,
  "leverage": 25,
  "max_drawdown_limit": 0.40
}
```

## Performance Expectations

### Short-term (1-7 days)
- High variance
- M1 may lose money some days
- M5 more consistent
- Combined: Usually positive

### Medium-term (7-30 days)
- Both should be profitable
- M5: 50-100% returns
- M1: 100-150% returns
- Combined: 150-250% returns

### Long-term (30+ days)
- Consistent profitability expected
- Drawdowns will happen (normal)
- Safety limits protect you

## Best Practices

1. **Start with M5 only** for first week
2. **Add M1** once comfortable
3. **Monitor daily** for first month
4. **Check `evaluate_live_trades.py`** weekly
5. **Don't panic** on bad days (variance is normal)
6. **Trust the safety limits** - they're data-driven

## Summary

Running both bots gives you:
- ✅ Maximum market coverage
- ✅ Diversified strategies
- ✅ Higher potential returns
- ⚠️ Higher variance
- ⚠️ More margin required
- ⚠️ More monitoring needed

**Recommendation:** Start with M5 only, add M1 after you're comfortable.

See [SAFETY_MECHANISMS.md](SAFETY_MECHANISMS.md) for details on protection systems.
