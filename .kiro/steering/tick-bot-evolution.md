---
inclusion: manual
---

# Tick Scalper Evolution

## V1: Initial Design (2026-05-25)
- Multi-factor entry scoring (7 factors, weighted)
- Tick-level analysis every second
- Fixed trailing stop using tick ATR
- Exit score with threshold
- **Problem**: Tick ATR too small ($0.10-0.30), everything too tight

## V2: M5 ATR for stops (2026-05-26)
- Switched SL/TP/trail from tick ATR to M5 ATR ($2-5)
- Entry confirmation: 5-tick turn detection before fill
- Spread filter (block entry when spread > 3x normal)
- **Problem**: Exit score firing too early (62% premature), tiny wins

## V3: Velocity-based exit (2026-05-26)
- Added VelocityTracker: measures price speed, detects exhaustion
- Partial close at 50% when velocity drops to 30% of peak
- Exit score now velocity-aware (30% weight)
- **Problem**: Velocity exhaustion triggered on every small pause

## V4: Longer exit windows (2026-06-01)
- Exit factors use 60s/120s windows instead of 5-15s
- Multi-period exhaustion detection (30s/60s/120s weighted)
- Peak drawdown uses M5 ATR instead of tick ATR
- Exit confirmation raised to 10 ticks + profit reluctance
- **Problem**: Still exiting too early, wins $2.50 vs losses $8

## V5: Entry state machine (2026-06-01)
- Entry goes through IDLE -> ARMED -> CONFIRMING -> FILL
- Waits for velocity to flip positive before entering (bottom confirmation)
- Spread narrowing as additional confirmation signal
- Multi-timeframe trend analyzer biases entry direction
- **Problem**: Trail too tight (1x ATR), closing on tiny pullbacks

## V6: Progressive trailing stop (2026-06-02)
- Replaced fixed ATR trail with progressive lock-in
- Uses sqrt curve: small profit = conservative, large profit = aggressive
- Caps at 50% lock-in, coeff 0.20, full trail at 3.0 ATR
- SL tightens from initial as profit grows (blend formula)
- Initial SL: 2x M5 ATR (~$10)
- Exit threshold raised to 0.75 (multi-factor agreement required)
- Exit confirmation: 5 ticks base + trend bonus + profit reluctance ($3/tick)
- Exit ONLY fires when profit > 0 (losers must ride to SL)
- **Problem**: Wins still $2.50 avg. Losses grew to $12.61 because losers can't exit early.

## V6.1: Hybrid C+B exit + tighter trail (2026-06-03)
- SL reduced from 2.0 to 1.5 ATR
- Trailing: tighter sqrt curve (0.31 coeff, 60% cap, full trail at 1.5 ATR instead of 3.0)
- Exit scoring restructured into 3 zones:
  - Zone 1 (losing): exit on score >= 0.85 with 8 tick confirm (early damage control)
  - Zone 2 (profit < 0.5 ATR): exit scoring disabled (only trail/SL can close)
  - Zone 3 (profit >= 0.5 ATR): dynamic threshold 0.95->0.75 based on profit ratio
- Partial close gate raised to >= 0.5 ATR
- With-trend confirmation reduced 15->12 ticks
- Profit reluctance: $5 per extra tick (was $3)
- **Status**: Applied late Jun 3. Not enough data yet to evaluate.
- **Concern**: Zone 2 gate at 0.5 ATR (~$2) still traps positions that should exit.
  Zone 1 threshold 0.85 is still very high — may not fire fast enough on losers.

## Key Metrics Over Time
| Version | Trades/day | WR | Avg Win | Avg Loss | PnL | Notes |
|---------|-----------|-----|---------|----------|-----|-------|
| V2-V3   | 138       | 48% | $5.94   | -$5.30   | +$10.74/day | |
| **V4**  | **175**   | **53%** | **$6.06** | **-$5.67** | **+$97.89/day** | **Best. Symmetric payoffs.** |
| V5      | 149       | 72% | $2.54   | -$7.59   | -$47.17/19h | Entry improved, exits broke |
| V6      | ~100/day  | 51% | $2.61   | -$9.90   | -$121/8h | |
| V6 (90h)| 325/90h   | 65% | $2.17   | -$12.61  | -$128/90h | Full 90h live data |

## 90-Hour Analysis Findings (May 31 - Jun 3)

### Day-by-Day Performance
| Day | Market | Trades | WR | P/L | Notes |
|-----|--------|--------|-----|-----|-------|
| Mon Jun 1 | Volatile down (-$33, ATR $5.05, range $98) | 170 | 53% | **+$98** | Best day. High vol = clear momentum. |
| Tue Jun 2 | Flat chop (+$1, ATR $4.11, range $78) | 106 | 70% | **-$131** | Worst. WR high but R:R killed. |
| Wed Jun 3 | Directional down (-$40, ATR $4.80) | 49 | 73% | **-$96** | Same R:R problem. |

### Session Performance (90h aggregated)
| Session | Trades | P/L | WR |
|---------|--------|-----|-----|
| 00-04 Asian | 33 | **-$66** | 48% |
| 04-08 Asian/London | 77 | **-$184** | 49% |
| 08-12 London | 58 | +$29 | 59% |
| 12-16 London/NY | 63 | +$1 | 68% |
| 16-20 NY | 54 | **+$91** | 69% |
| 20-24 NY/Asian | 40 | +$1 | 80% |

A session filter (skip 00-08) would have turned -$128 into approximately +$122.

## Critical Insight: Why V4 Worked and V5/V6 Didn't

**V4 had symmetric payoffs** ($6.06 win vs $5.67 loss). Even at 53% WR = positive edge.

The problem identified in V4 was: "62% of exit score exits left money on table." The attempted fix (V5/V6) was to make exits harder to trigger. But this had TWO unintended consequences:
1. **Wins shrank to $2** — trail catches them at small profit, exit score never fires because threshold too high
2. **Losses grew to $12** — exit score too reluctant to fire on losers, they ride to full SL

**The V4 exit score (threshold 0.55) served a dual purpose not appreciated at the time:**
- On winners: closed at decent profit (~$6 avg, sometimes leaving money but reliably capturing)
- On losers: **closed BEFORE reaching SL** (cutting losses at ~$5 instead of riding to $12)

V5/V6 "fixes" broke both: wins got smaller AND losses got bigger. The "leaving money on table" problem was real but less costly than the alternative.

## What Changed Between V4 and V5/V6 (All Changes)

1. **Exit threshold**: 0.55 → 0.75 (made exits much harder to trigger)
2. **Exit scoring windows**: 5s/15s/30s → 30s/60s/120s (smoothed signals, slower to react)
3. **Exit confirmation**: instant → 5+ ticks (added delay before acting)
4. **Profit gating**: none → profit > 0 required (losers couldn't exit via score)
5. **Entry state machine**: immediate → IDLE/ARMED/CONFIRMING (better entries but fewer trades)
6. **Trail type**: fixed → progressive sqrt (conceptually better but slow to lock in)

## Recommendation for Next Iteration (V7)

Goal: restore V4's symmetric payoffs ($6/$6) while keeping V5/V6 structural improvements.

Key parameter changes needed:
- **Exit threshold**: 0.75 → **0.60** (between V4's 0.55 and current 0.75)
- **Minimum profit gate**: 0.5 ATR → **0.2 ATR** (allow exits at small profit, just not crumbs)
- **Losing exit threshold**: 0.85 → **0.70** (cut losses much faster)
- **Confirmation ticks**: 5 → **3** (faster reactions)
- **Exit scoring windows**: consider reverting 60/120s back to **15/30/60s** (faster signals)
- **Session filter**: add 10:00-22:00 local time gate (saves ~$200/90h)
- Keep: 1.5 ATR SL, tighter trail (0.31 coeff), entry state machine

The core philosophy should be: **exit fast on both winners and losers**. V4 proved that taking $6 and losing $5.67 at 53% WR beats taking $2 and losing $12 at 73% WR.

## Open Questions
- Should exit threshold go all the way back to 0.55, or compromise at 0.60?
- Should scoring windows fully revert to V4's shorter periods?
- Is the entry state machine (V5+) worth keeping given it reduces trade count?
- Session filter: 10:00-22:00 vs 08:00-20:00?
- Could exit score use different thresholds per-direction based on trend?
