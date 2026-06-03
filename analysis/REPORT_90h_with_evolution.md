# 90-Hour Performance Report (May 31 - Jun 3, 2026)

## Executive Summary

| Bot | 90h Trades | 90h P/L | Best Day | Worst Day |
|-----|-----------|---------|----------|-----------|
| Tick Scalper (V6) | 325 | **-$128** | Mon +$98 | Tue -$131 |
| M5 Sniper (V4) | 80 | **+$90** | Wed +$139 | Tue -$29 |
| **Combined** | 405 | **-$39** | Mon +$78 | Tue -$159 |

---

## Day-by-Day Breakdown

### Monday Jun 1 (Volatile Down: -$33 net, Range $98, ATR $5.05)
**Market**: Big volatile day. Gold dropped from $4521 to $4488 but with a $98 intraday range. High choppiness (0.54), moderate directionality (0.34). RSI crossed buy 6x, sell 3x. RSI mean 48.

| Bot | Trades | P/L | WR | Story |
|-----|--------|-----|-----|-------|
| TICK | 170 | **+$98** | 53% | Best day. High volatility = clear momentum signals. 42 big wins (+$448) offset 46 big losses (-$350). Shorts outperformed longs (+$74 vs +$25). |
| M5S | 11 | **-$20** | 64% | 3 mean reverts (+$57) couldn't cover 4 losses (-$90). Volatile chop = RSI dips hit SL before reverting. |

**Insight**: The tick bot (V6 with old exit logic) thrived on high-volatility momentum. The M5S needs directional clarity, not just volatility.

---

### Tuesday Jun 2 (Mixed Flat: +$1 net, Range $78, ATR $4.11)
**Market**: Worst possible conditions for both bots. Net movement was +$1 (nowhere) but range was $78 (massive chop). Directionality 0.01, choppiness 0.49. RSI mean dead-center at 50. Equal buy/sell signals (6/4).

| Bot | Trades | P/L | WR | Story |
|-----|--------|-----|-----|-------|
| TICK | 106 | **-$131** | 70% | Textbook R:R problem. 70% WR but avg win $2 vs avg loss $10. 29 big losses (-$289) vs 9 big wins (+$74). |
| M5S | 32 | **-$29** | 62% | 5 mean reverts (+$91) but 12 losses (-$156). Entries get stopped because RSI dips don't revert cleanly in chop. |

**Insight**: Both bots are mean-reversion strategies at heart. In a directionless market, mean-reversion signals are noise — price doesn't "revert" anywhere, it just oscillates randomly.

---

### Wednesday Jun 3 (Mixed Down: -$40 net, Range $70, ATR $4.80)
**Market**: Clean downtrend with directionality 0.56 (best of the 3 days). Gold dropped from $4489 to $4449. RSI mean 46 (biased oversold), 10 buy crosses vs only 2 sell crosses.

| Bot | Trades | P/L | WR | Story |
|-----|--------|-----|-----|-------|
| TICK | 49 | **-$96** | 73% | Same R:R problem persists despite tuning (changes applied late in day). 13 big losses (-$169) vs 4 big wins (+$52). |
| M5S | 37 | **+$139** | 65% | **Best day.** 12 mean-revert wins (+$257). Directional drop created deep RSI dips that bounced hard. |

**Insight**: The M5S is perfectly designed for trending markets where RSI extremes mean-revert reliably. The tick bot's problem is structural (R:R), not about market conditions.

---

## Evolution Context: What Changed When

### Tick Bot Timeline (V2 → V6)
| Version | Dates | Key Change | Result |
|---------|-------|-----------|--------|
| V2-V3 | May 26 | M5 ATR stops, velocity exit | $+11/day, 48% WR |
| V4 | May 27-31 | Longer exit windows (60/120s) | **+$98/day**, 53% WR |
| V5 | Jun 1 | Entry state machine, trend bias | -$47/19h, 72% WR (too tight exits) |
| V6 | Jun 2 | Progressive trailing, 2x ATR SL | -$121/8h, 51% WR |
| V6.1 | Jun 3 (late) | **Our changes**: 1.5x ATR SL, hybrid C+B exit, tighter trail | Not yet enough data |

**The paradox**: V4 was most profitable (+$98/day) with a 53% win rate because it let winners run. V5/V6 improved win rate to 72% by tightening exits, but destroyed profitability because wins became too small. Monday's +$98 was likely residual V5/V6 behavior in high-volatility conditions where even small exits captured meaningful profit.

### M5 Sniper Timeline (V1 → V4)
| Version | Dates | Key Change | Result |
|---------|-------|-----------|--------|
| V1 | May 26 | RSI limit orders at 35/65 | +$8 backtest |
| V2 | May 27 | Deeper sniper (RSI 25/75), mean-revert exit at 50 | Too early exits |
| V3 | Jun 1 | Trailing stop every second, exit at RSI 55/45 | PP competing with trail |
| V4 | Jun 2+ | PP disabled, SL 1.75 ATR, RSI 55/45 exit | **+$90/90h** |
| V4.1 | Jun 3 (today) | **Our change**: `short_requires_downtrend: false` | Not yet tested |

**V4 is working.** The combination of deep sniper entry (RSI 25) + mean-revert exit (RSI 55) + trailing stop (BE at 0.7 ATR, trail at 1.5 ATR) is profitable in directional markets.

---

## Market Condition Sensitivity

### What Works Where

| Market Type | TICK Bot | M5S Bot | Combined |
|-------------|----------|---------|----------|
| **High vol + trending** (Mon) | +$98 (momentum) | -$20 (SL before revert) | +$78 |
| **Low vol + choppy** (Tue) | -$131 (R:R death) | -$29 (no clean reverts) | -$159 |
| **Moderate vol + trending** (Wed) | -$96 (R:R still bad) | +$139 (perfect mean-revert) | +$43 |

### Session Performance (90h aggregated)

| Session | TICK | M5S | Combined | Notes |
|---------|------|-----|----------|-------|
| 00-04 Asian | -$66 | -$7 | **-$73** | Both lose. Thin liquidity, noise. |
| 04-08 Asian/London | -$184 | +$50 | **-$134** | TICK disaster. Volatile opens. |
| 08-12 London | +$29 | -$50 | -$21 | M5S struggles in London (choppy?). |
| 12-16 London/NY | +$1 | -$2 | -$2 | Both flat. Overlap session. |
| 16-20 NY | **+$91** | **+$36** | **+$127** | **Best session for both.** |
| 20-24 NY/Asian | +$1 | **+$63** | +$64 | M5S strong in late NY. |

---

## SL Analysis: Initial vs Trailed (M5S)

A critical finding from detailed deal analysis:

| Period | Initial SL (genuine wrong entries) | Trailed SL (was in profit, reversed) |
|--------|-----------------------------------|------------------------------------|
| Wednesday (trending) | 6x, avg -$11.91 | 20x, avg +$0.09 (breakeven!) |
| Tuesday (choppy) | 3x, avg -$11.70 | 19x, avg **-$5.30** (giving back profit) |

**In trending markets**, the trailed SL works perfectly — positions that move into profit stay in profit (trail catches the top). **In choppy markets**, positions go up $2-5, trail moves SL to near-entry, then price reverses $8-9 blowing through the trailed stop.

The trailing parameters (BE at 0.7 ATR, trail at 1.5 ATR) are optimized for trending conditions. In chop, a tighter trail (1.0 ATR) or lower BE trigger (0.5 ATR) would help.

---

## Key Problems Identified

### Tick Bot: The R:R Problem
- Win rate is consistently 65-75% across all versions since V5
- Avg win is $1-3 (holding 1-8 minutes)
- Avg loss is $10-13 (holding until SL at 1.5-2.0 ATR)
- **Even with 73% WR, expected value is negative**: 0.73 × $2 - 0.27 × $12 = -$1.78/trade
- The hybrid C+B exit we implemented today should help by preventing exits below 0.5 ATR and allowing early exit on losing positions

### M5S: Market Regime Dependence
- Profitable in directional markets (+$139 on Wednesday's -$40 move)
- Unprofitable in choppy/flat markets (-$29 on Tuesday's +$1 move)
- The trailing stop is the differentiator: works when trends produce clean V-shaped pullbacks, fails when pullbacks are followed by continuation

### Both Bots: Session Sensitivity
- Combined +$191 during 16:00-24:00 vs -$230 during 00:00-12:00
- The tick bot alone: -$250 during 00-08, +$91 during 16-20
- A simple "don't trade before 10:00" rule would have saved ~$200

---

## Recommendations (Priority Order)

1. **Session filter for tick bot**: Only trade 10:00-22:00 local time. Would have turned -$128 into approximately +$122 over these 90 hours.

2. **Accept the tick bot's V6.1 changes need time**: The hybrid C+B exit is the right approach conceptually (don't exit for crumbs, exit early on losers). Need 48-72h of live data to validate.

3. **M5S is working — don't overtune**: V4 is net profitable. The `short_requires_downtrend: false` change enables it to profit from uptrends too. Let it run.

4. **Consider regime detection for M5S trailing**: Tighter trail (1.0 ATR) in choppy conditions, wider (1.5-2.0 ATR) in trending. ATR stability or RSI mean position could signal the regime.

5. **Tick bot V4 was the best**: The aggressive exit-at-any-profit approach worked in high volatility. Consider whether the tick bot should have two modes: "scalp mode" (high vol, exit quickly) and "trend mode" (moderate vol, let winners run).
