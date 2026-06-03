---
inclusion: auto
---

# Project Status (updated 2026-06-03)

## Active Bots

### Tick Scalper (`src/bot/tick_scalper.py`, config: `config/tick_params.json`)
- **Status**: Live testing on demo, tuned 2026-06-03
- **Magic**: 234200
- **Approach**: Multi-factor entry scoring (tick-level), progressive trailing stop, velocity-based exit
- **Entry**: 7 factors scored 0-1, threshold 0.40, 5-tick turn confirmation before fill
- **Exit**: Hybrid C+B approach (see architecture.md for details)
  - Losing: exit on score >= 0.85 (8 ticks confirm) — early damage control
  - Small profit (< 0.5 ATR): exit scoring disabled, only trailing/SL
  - Meaningful profit (>= 0.5 ATR): dynamic threshold scales 0.95 -> 0.75
- **Trailing stop**: Progressive sqrt curve, 0.31 coeff, 60% cap, reaches full trail at 1.5 ATR
- **SL**: 1.5x M5 ATR initial (~$7.5-9)
- **TP**: 20x M5 ATR (never hit, exit score/trail handles real exit)
- **Sizing**: 10% at 30x leverage = 0.03 lots, ~$3/point
- **Trend**: Multi-timeframe trend analyzer (M5/M15/H1) biases entry direction
- **Last 22h performance (2026-06-03 pre-tuning)**:
  - 46 trades, 73.9% WR, -$77.66 total, avg win $2.17, avg loss $12.61, R:R 0.17
  - SL exits: -$140.80 (13 trades), structure exits: +$51.62 (15 trades)
  - Max consecutive losses: 3, max consecutive wins: 13
- **Known issues**:
  - Performance varies by session (good 08-11, 14-15, 17-20; bad 00-07)
  - "MT5 close" labels may be trailed-SL hits with wrong deal reason code

### M5 Sniper (`src/bot/sniper_bot.py`, config: `config/m5_params.json`)
- **Status**: Live testing on demo, performing well
- **Magic**: 234050
- **Approach**: RSI-level limit orders for entry, mean-revert exit, trailing stop
- **Entry**: Calculates price where RSI would hit 25/75, places limit order there. Fallback market order at RSI 35/65 on candle close.
- **Exit**: Mean revert (RSI crosses 55 for longs, 45 for shorts), trailing stop (1.5x ATR), RSI extreme safety
- **SL**: 1.75x M5 ATR
- **Trailing**: Every second via `manage_trailing_continuous()`, breakeven at 0.7 ATR then trail at 1.5 ATR
- **Profit protection**: DISABLED (trailing stop handles it)
- **Last 22h performance (2026-06-03)**:
  - 33 trades, 60.6% WR, +$108.44 total, avg win $12.59, avg loss $11.02, R:R 1.14
  - Mean revert exits: +$178.06 (7 trades, avg $25.44), SL exits: -$69.62 (26 trades)
  - Heavily long-biased (30/33), strong London/NY sessions
- **Known issues**:
  - SL exits still dominate loss count — entries occasionally catch falling knives
  - Sniper fill at RSI 25/75 helps but not immune to continued drops

### LZ (Liquidity Zones) (`src/bot/zone_bot.py`, config: `config/lz_params.json`)
- **Status**: Live, mostly working but low volume
- **Magic**: 234100
- **Approach**: Limit orders at detected support/resistance zones
- **Mode**: Long-only
- **Known issues**: Small lot size (0.01-0.02), low fill rate, SL at 1.0 ATR below zone

### M5 RSI (`src/bot/base.py` + `src/strategy/m5_scalping.py`, config: `config/m5_params.json`)
- **Status**: Running alongside sniper (shares config)
- **Magic**: 234000

## Architecture

- GUI: 4 bot slots (2 per side), tabbed, center chart + trade history + log tab
- BotManager: supports instance IDs for multiple same-type bots
- SimBroker: spread ($0.30) + slippage ($0.05) modeling
- Trailing stop: uses `modify_sl()` on MT5 (instant broker execution)
- MT5 API is NOT thread-safe — avoid fetching data from GUI thread

## Key Learnings

1. **Spread kills M1 scalping** — 4800 trades × $0.30 = impossible edge. M5+ timeframes viable.
2. **Limit orders save spread** — entering via limit = no spread cost on entry.
3. **Exit is harder than entry** — the main challenge is knowing when to close.
4. **Trailing stop > profit protection** — SL in MT5 executes instantly, bot-level PP has latency.
5. **Tick ATR is useless for stops** — use M5 ATR ($2-5) for all SL/TP/trail distances.
6. **Progressive trail works best** — starts conservative (limits loss), gets aggressive (locks profit).
7. **Exit score exits too early** — 62% of score exits left money on table. Higher threshold + confirmation helps.
8. **Pycache causes stale code** — always clear pycache + restart full GUI when changing bot code.
9. **Session matters** — tick bot profitable during London/NY, losing during Asian session.

## Recent Decisions

- **2026-06-03: Tick bot tuning** (commit 0eee136):
  - SL reduced from 2.0 to 1.5 ATR (smaller max loss per trade)
  - Trailing stop tightened: 0.31 coeff (was 0.20), 60% cap (was 50%), full trail at 1.5 ATR (was 3.0)
  - Exit scoring: hybrid C+B approach (see architecture.md)
  - Losing positions can now exit early (score >= 0.85, 8 tick confirm)
  - Small profit zone (< 0.5 ATR) cannot be exited by score (only trail/SL)
  - Dynamic threshold for meaningful profits: harder to exit small wins, normal for big wins
  - Profit reluctance changed from $3 to $5 per extra tick
  - With-trend confirmation reduced from 15 to 12 ticks
- Exit threshold raised to 0.75 (from 0.55) — only fire on multi-factor agreement
- Trailing: progressive (sqrt curve)
- M5 Sniper: disabled profit protection, relying on trailing stop only
- M5 Sniper: mean revert exit at RSI 55/45 (loosened from 50)
- M5 Sniper: SL tightened from 2.25 to 1.75 ATR

## Next Steps / Ideas

- Session filter for tick bot (only trade during active hours)
- Exit score tightens trailing stop instead of closing position
- Tune entry threshold higher to reduce trade frequency
- News filter (MT5 calendar + volatility spike detection)
- GUI: editable config parameters, multi-instance support (partially done)
