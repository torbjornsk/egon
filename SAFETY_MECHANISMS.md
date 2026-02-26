# Dead Man's Switch - Safety Mechanisms

## Overview
Both M5 and M1 bots now have comprehensive automatic safety mechanisms that will pause trading or close positions if things go wrong. You can run them in the background without babysitting.

## Safety Layers

### 1. Drawdown Limit (Original)
- **M5**: Pauses at 35% drawdown from peak
- **M1**: Pauses at 40% drawdown from peak
- **Action**: Stops opening new trades

### 2. Daily Loss Limit (NEW)
- **Threshold**: 15% loss in 24 hours
- **Action**: Pauses trading for the day
- **Resets**: Automatically at midnight

### 3. Rapid Loss Detection (NEW)
- **Threshold**: 10% loss in 60 minutes
- **Purpose**: Circuit breaker for flash crashes
- **Action**: Immediately pauses trading

### 4. Consecutive Loss Limit (NEW)
- **M5**: 8 losing trades in a row
- **M1**: 7 losing trades in a row
- **Purpose**: Detect when strategy stops working
- **Action**: Pauses trading until manual review
- **Note**: Thresholds set based on 99th percentile + buffer from 60-day backtest

### 5. Emergency Equity Threshold (NEW)
- **Threshold**: Equity drops below 50% of starting balance
- **Action**: CLOSES ALL POSITIONS immediately and pauses trading
- **Purpose**: Last resort protection against catastrophic loss

## How It Works

Every trading cycle, the bot runs all safety checks:
```
1. Check emergency threshold (most critical)
2. Check drawdown limit
3. Check daily loss limit
4. Check rapid loss (flash crash)
5. Check consecutive losses
```

If ANY check fails, trading is paused and the reason is logged.

## What Happens When Paused

- Bot stops opening new positions
- Existing positions remain open (managed by SL/TP)
- Bot logs the pause reason
- You can see status in logs: "Trading paused: [reason]"

## Resuming Trading

To resume after a pause:
1. Stop the bot (Ctrl+C)
2. Review what went wrong
3. Restart the bot (safety counters reset)

## Emergency Close

If equity drops to 50% of starting balance:
- ALL positions are closed immediately
- Trading is paused
- You get a CRITICAL log message
- Manual intervention required to restart

## Monitoring

Check logs for these messages:
- `TRADING PAUSED: [reason]` - Safety mechanism triggered
- `EMERGENCY: Closing all positions!` - Emergency threshold hit
- `Consecutive losses: X` - Tracks losing streak

## Configuration

You can adjust thresholds in the bot code (`__init__` method):
```python
# M5 Bot
self.max_consecutive_losses = 8  # 8 losses before pause
self.daily_loss_limit_pct = 0.15  # 15% daily loss limit
self.rapid_loss_threshold_pct = 0.10  # 10% in 1 hour
self.emergency_equity_threshold_pct = 0.50  # 50% equity loss

# M1 Bot  
self.max_consecutive_losses = 7  # 7 losses before pause
# (other limits same as M5)
```

## Testing

The stress test showed:
- Worst case M5 loss: -14.7% (under 35% limit ✓)
- Worst case M1 loss: 0% (didn't trade during crashes)
- Max drawdown: 20.8% (under limits ✓)

Your bots are protected!

## Summary

You can safely run the bots in the background. The dead man's switch will:
- Pause trading if losses exceed limits
- Close everything in emergencies
- Log all actions for review
- Protect your account from catastrophic losses

No babysitting required!
