---
inclusion: manual
---

# Tick Bot V4 Restoration Plan

## Goal
Restore the exit factor time windows to V4's short windows (5-15 seconds) 
while keeping V7's other improvements (entry confirmation, trend bias, M5 ATR for stops).

V4 was the only profitable version (+$98/day, 53% WR, $6 avg win, $6 avg loss).
The key difference: V4's exit score used SHORT windows (5-15 ticks) which fired frequently
on small signals and happened to close at decent profit levels.

## Changes needed in `src/core/tick_analysis.py`

### 1. Revert `_calc_momentum_exhaustion` to short windows
Currently uses multi-period 30s/60s/120s. Revert to:
- Compare velocity of last 5 ticks vs previous 10 ticks
- Single window, no weighting

```python
def _calc_momentum_exhaustion(self, direction: str) -> float:
    if len(self.ticks) < 15:
        return 0.0
    recent = [self.ticks[-i].mid for i in range(1, 6)]
    older = [self.ticks[-i].mid for i in range(6, 16)]
    recent_velocity = abs(recent[0] - recent[-1]) / 5
    older_velocity = abs(older[0] - older[-1]) / 10
    if older_velocity <= 0:
        return 0.0
    ratio = recent_velocity / older_velocity
    if ratio < 1.0:
        return min(1.0, (1.0 - ratio) * 2)
    return 0.0
```

### 2. Revert `_calc_profit_stall` to 30-tick window
Currently uses 60s/120s. Revert to:
- Check price movement over last 30 ticks only

```python
def _calc_profit_stall(self, direction: str, entry_price: float) -> float:
    if len(self.ticks) < 30:
        return 0.0
    prices = [self.ticks[-i].mid for i in range(1, 31)]
    current = prices[0]
    thirty_ago = prices[-1]
    if direction == "LONG":
        progress = current - thirty_ago
    else:
        progress = thirty_ago - current
    atr = self._calc_tick_atr()
    if atr <= 0:
        return 0.0
    if progress < 0:
        return min(1.0, -progress / atr)
    if progress < atr * 0.1:
        return 0.3
    return 0.0
```

### 3. Keep everything else as V7
- SL: 6x M5 ATR
- Trail: 3x M5 ATR fixed
- Exit threshold: 0.55
- Exit confirmation: 5 ticks + profit reluctance
- Entry: 5-tick turn confirmation
- Trend bias: keep
- Spread filter: keep

## Why this might work
V4's short windows made the exit score very reactive — it fired frequently on small
momentum changes. Combined with the 6x ATR SL (which rarely got hit), this produced
$6 average wins because the score closed at the first sign of slowing, which was often
after a decent move. The longer V5 windows made the score too slow to fire, defaulting
to the trailing stop which produced tiny wins.

## Risk
V4's short windows also caused 62% premature exits. But net it was still +$98/day
because the other 38% were correct exits saving $2-3 each, and the wide SL meant
losses were infrequent. The math worked: many $6 wins + few $15 losses = positive.

## The problem V5 tried to solve (and failed)

In V4, we analyzed the exit-score exits and found:
- 62% of exits were "premature" — price continued $10-17 in our favor after we exited
- 38% were correct — price reversed after exit, saving $2-3
- The exit score was reacting to 5-second pauses within longer trends
- Example: bot exits at +$2 profit, price continues $17 more (missed $17)
- Total profit left on table: $643 in 19 hours across 50 premature exits

V5/V6 attempted fixes:
1. Longer exit windows (60s/120s) — made score too slow, defaulted to trail for tiny wins
2. Higher exit threshold (0.65, 0.75) — score rarely fired, trail handled exits poorly
3. More confirmation ticks (10-15) — same effect, delayed good exits
4. Progressive trailing stop — conservative early, never locked enough profit
5. Tighter SL (2-4x ATR) — capped big moves, more SL hits

All of these reduced the number of score exits but the REPLACEMENT (trailing stop)
produced worse results ($2.50 avg wins vs V4's $6 avg wins).

## The unsolved problem

How to keep V4's $6 avg wins while reducing the 62% premature exit rate.
Potential approaches not yet tried:
- Exit score tightens the trailing stop instead of closing (proposed, not implemented)
- Session filter (V4 was profitable during active hours, losing during quiet)
- Higher entry threshold (fewer trades but better quality entries)
- Partial close on exit score (close 50%, trail the rest)
- Only allow exit score when profit > some minimum (e.g. > $3)

## Files to modify
- `src/core/tick_analysis.py`: _calc_momentum_exhaustion, _calc_profit_stall
- No config changes needed (already set to V7 levels)
