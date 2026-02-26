# M1 Strategy Testing Results

## Summary

Tested multiple "improvements" for the M1 bot. Most hurt performance when tested across multiple time periods. The original simple strategy performs best.

## Current M1 Strategy (DEPLOYED)

**Configuration:**
- RSI entry: < 35 (buy dips)
- RSI exit: > 75 (sell peaks)
- ATR multiplier: 4.0 (wide stops for M1 noise)
- Profit target: 0.8%
- Position size: 15% @ 25x leverage
- Market orders (immediate execution)
- Simple RSI exits (no adaptive logic)
- Fast re-entry after wins (skip cooldown)

**Performance (60-day multi-period test):**
- 24 hours: 3.2% avg return, 85% profitable
- 3 days: 1.6% avg return, 75% profitable
- 7 days: 19.7% avg return, 80% profitable
- 14 days: 16.7% avg return, 60% profitable
- Win rate: 67%

## Tested "Improvements" (REJECTED)

### 1. Limit Orders (0.015% offset)

**Concept:** Place buy limits slightly below market, sell limits slightly above for better entry prices.

**Single backtest results:** +60% improvement (looked promising!)

**Multi-period robustness test:** -59% to -101% worse

**Why it failed:**
- Fill rate dropped significantly
- Missed many good moves that didn't retrace
- The 0.015% offset was too large for M1's fast moves
- Single backtest was misleading - not robust across different market conditions

**Verdict:** REJECTED - Hurts performance

### 2. Adaptive Exits

**Concept:** 
- Cut losses early when RSI reverses 10+ points against position
- Hold winners longer when momentum strong

**Single backtest results:** +42% improvement (looked great!)

**Multi-period robustness test:** -73% to -283% worse

**Why it failed:**
- Adaptive cuts triggered on 53% of exits (way too aggressive!)
- Win rate dropped from 67% to 38%
- The "RSI reversal" logic cut winners too early
- RSI can spike temporarily without invalidating the trade
- What looked like "early loss cutting" was actually "early winner cutting"

**Verdict:** REJECTED - Destroys win rate

### 3. Combined (Limit Orders + Adaptive Exits + Fast Re-entry)

**Multi-period robustness test:** -129% worse on average

**Why it failed:**
- Combined the worst of both approaches
- Limit orders missed trades
- Adaptive exits cut the trades that did fill
- Double whammy of reduced opportunities and reduced win rate

**Verdict:** REJECTED - Much worse than baseline

## Key Lessons Learned

### 1. Single Backtests Are Misleading

A strategy can look amazing on one 60-day period but fail miserably when tested across 20 random periods of the same length. Always test robustness across multiple time periods.

### 2. M1 Is Different From M5

- M5 has better signal quality (46% win rate baseline)
- M1 has more noise but higher win rate with simple strategy (67%)
- What works on M5 doesn't necessarily work on M1
- M1 needs simpler, more forgiving logic

### 3. Complexity Doesn't Mean Better

The simple strategy (buy dips, sell peaks, wide stops) outperforms complex adaptive logic. Sometimes the best improvement is no improvement.

### 4. Win Rate Matters More Than You Think

Dropping win rate from 67% to 38% is catastrophic, even if you're "cutting losses early." You need winners to compound gains.

### 5. Fast Re-entry After Wins DOES Help

This is the ONE improvement that tested well:
- Skip cooldown period after profitable trades
- Allows catching continuation moves
- Doesn't hurt win rate
- Simple to implement

**Status:** KEPT in current strategy

## Current Strategy Strengths

1. **High win rate (67%):** Simple RSI mean reversion works on M1
2. **Wide stops (4.0x ATR):** Survives M1 noise without getting stopped out
3. **Small profit target (0.8%):** Realistic for 1-minute moves
4. **Market orders:** Catches moves immediately, no missed opportunities
5. **Fast re-entry:** Capitalizes on momentum after wins

## What NOT To Do

❌ Don't add limit orders - misses too many trades
❌ Don't add adaptive exits - cuts winners too early
❌ Don't try to be too clever - simple works better on M1
❌ Don't trust single backtests - always test robustness
❌ Don't optimize for one metric - balance win rate, return, and consistency

## What TO Do

✅ Keep the simple strategy that's working
✅ Monitor live performance regularly
✅ Test any changes across multiple time periods before deploying
✅ Focus on risk management (drawdown limits, safety mechanisms)
✅ Be patient - M1 needs time to compound small gains

## Recommendation

**KEEP CURRENT STRATEGY** - It's simple, robust, and profitable across different market conditions. The "improvements" we tested all hurt performance when properly validated.

The M1 bot is now running the proven baseline strategy with only one enhancement: fast re-entry after wins.

