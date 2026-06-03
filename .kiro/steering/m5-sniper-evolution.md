---
inclusion: manual
---

# M5 Sniper Evolution

## Origin
Born from the insight that RSI entries on M5 could be pre-calculated as limit orders,
avoiding spread cost and catching intra-candle wicks that close-only RSI misses.

## V1: RSI Level Limit Orders (2026-05-26)
- `src/core/rsi_levels.py`: reverse-calculates price where RSI would hit threshold
- Places limit buy at RSI 35 level, limit sell at RSI 65 level
- Fallback market order on candle close if RSI signal fires normally
- Standard RSI exit (RSI > 65 for longs, < 35 for shorts)
- **Problem**: Entering too early during drops (RSI 35 is often just the start)

## V2: Deeper sniper levels + mean revert exit (2026-05-27)
- Sniper targets RSI 25/75 (10 points more extreme than config) for limit orders
- Mean revert exit: close when RSI crosses back to 50 (wave done)
- Breakeven stop at 1.0 ATR, then trail at 1.5 ATR
- **Problem**: Mean revert at 50 closed winners too early, losses still large

## V3: Trailing stop every second (2026-06-01)
- `manage_trailing_continuous()` added to main loop (runs every tick, not every 5 min)
- Breakeven at 0.7 ATR trigger, then trail at 1.5 ATR behind price
- RSI exit loosened to 55 (longs) / 45 (shorts) — let winners run further
- Data refresh every 30 seconds for GUI RSI display
- **Problem**: Profit protection and trailing stop competing (both trying to close)

## V4: Simplified exit (2026-06-02)
- Profit protection DISABLED — trailing stop handles everything
- SL tightened from 2.25 to 1.75 ATR
- RSI exit at 55/45 (loosened from 50 to let winners develop)
- Trailing: breakeven first, then 1.5 ATR trail
- Live RSI display uses cached data (avoids MT5 thread conflicts)

## V4.1: Remove downtrend guard for shorts (2026-06-03)
- `short_requires_downtrend` set to `false` in config
- **Rationale**: The sniper is a mean-reversion bot. Mean reversion works COUNTER-trend:
  - In downtrend: buy oversold dips (RSI<35) = works great (proven by 90h data)
  - In uptrend: sell overbought spikes (RSI>65) = should work symmetrically
- The guard was blocking exactly the shorts that would profit (counter-trend in uptrend)
  and only allowing shorts in downtrend (where RSI barely reaches 65 anyway)
- 48h data showed: 61 longs vs 6 shorts. Those 6 shorts were mostly noise (-$3.24 total).
- **Status**: Live, waiting for next uptrend period to validate.

## Key Metrics
| Version | Trades/day | WR | Avg Win | Avg Loss | PnL |
|---------|-----------|-----|---------|----------|-----|
| V1      | ~2        | 55% | $20     | -$11     | +$8/8mo (backtest) |
| V2-V3   | 11/day    | 64% | $10     | -$22     | -$20/day |
| V4 (90h)| ~27/day   | 62% | $9.83   | -$12.03  | +$90/90h |

## 90-Hour Analysis Findings (May 31 - Jun 3)

### Day-by-Day Performance
| Day | Market | Trades | WR | P/L | Notes |
|-----|--------|--------|-----|-----|-------|
| Mon Jun 1 | Volatile down, ATR $5.05, choppy | 11 | 64% | **-$20** | Vol too high for clean mean-reversion |
| Tue Jun 2 | Flat chop, ATR $4.11, range $78 | 32 | 62% | **-$29** | Entries stopped before RSI reverts |
| Wed Jun 3 | Directional down, ATR $4.80, dir 0.56 | 37 | 65% | **+$139** | Perfect conditions for mean-reversion |

### Why Wednesday Worked
- Clear downtrend (net -$40, directionality 0.56) created deep RSI dips (RSI mean 46, min 15)
- 10 RSI buy crosses = abundant entry opportunities
- Each dip snapped back to RSI 55 producing $15-53 per mean-revert exit
- 12 mean-revert wins averaging +$21 = dominant profit source
- Trailed SL exits in trending market averaged +$0.09 (breakeven - perfect!)

### Why Tuesday Failed
- Flat market (net +$1, directionality 0.01) = RSI dips don't revert cleanly
- RSI crosses 35, bot buys, price goes sideways, then drops more → SL hit
- Trailed SL exits averaged **-$5.30** (trail moved up, then price crashed through)
- Same 7 mean-revert exits but smaller bounces (avg $13.56 vs Wed's $25.44)

### SL Analysis: Initial vs Trailed
| Market Type | Initial SL (bad entry) | Trailed SL (was profitable, reversed) |
|-------------|----------------------|--------------------------------------|
| Trending (Wed) | 6x, avg -$11.91 | 20x, avg **+$0.09** |
| Choppy (Tue) | 3x, avg -$11.70 | 19x, avg **-$5.30** |

Trailing params (BE at 0.7 ATR, trail at 1.5 ATR) are optimized for trends.
In chop, positions rally $2-5, trail kicks in, then reverse $8-9 through the moved SL.

### Long vs Short (48h)
- 61 LONG trades: +$110, 61% WR, R:R 0.90
- 6 SHORT trades: -$3, 83% WR, R:R 0.15
- Shorts barely fire (RSI rarely hits 65 in downtrend) and capture tiny moves
- The `short_requires_downtrend: false` change should fix this in uptrends

## Architecture
- `src/strategy/m5_sniper.py`: RSI level calc, entry/exit logic
- `src/bot/sniper_bot.py`: Main loop, trailing stop, sniper fill detection
- Config: `config/m5_params.json` (shared with M5 RSI bot)
- Sniper level uses RSI 25/75 (deeper than config's 35/65)

## Key Insights

1. **Mean reversion works best counter-trend**: In a downtrend, buy oversold. In uptrend, sell overbought. The guard was backwards.
2. **Trailing stop is regime-dependent**: perfect in trends (breakeven exits), harmful in chop (gives back gains then gets hit)
3. **The bot's edge is the mean-revert exit**: 7-12 trades per day at $15-25 avg. Everything else is noise/breakeven.
4. **Best sessions**: 16-20 NY (+$36), 20-24 (+$63). Worst: 08-12 London (-$50).

## Open Questions
- Should trailing params adapt to regime? (Tighter in chop: 1.0 ATR trail, 0.5 ATR BE)
- Is 1.75 ATR SL optimal or should it widen in choppy conditions?
- Should sniper have its own config file separate from M5 RSI?
- Would the entry benefit from "wait for turn" logic (like tick bot) to avoid falling knives?
- Can we detect choppy conditions and simply not trade?
