---
inclusion: manual
---

# M5 Sniper Strategy Description

## Core Concept
Mean-reversion scalping on M5 timeframe using pre-calculated limit orders.
The bot bets on "waves" — price oscillates around a mean, and RSI extremes
indicate the wave has gone too far and will bounce back.

## Entry Logic

### Primary: Limit orders at RSI levels (sniper)
1. Each M5 candle, calculate what price would make RSI hit 25 (buy) or 75 (sell)
2. Place a limit buy order at the RSI-25 price (deeper than config's 35)
3. Place a limit sell order at the RSI-75 price (deeper than config's 65)
4. Check every second if current tick has reached the limit level
5. If filled: enter at that price with no spread cost (limit = providing liquidity)
6. Cancel unfilled orders when new M5 candle forms (recalculate levels)

### Fallback: Market order on candle close
If the limit didn't fill but RSI crosses config threshold (35/65) on candle close,
enter with a market order. This catches moves that didn't wick deep enough for
the sniper level but still produced a valid RSI signal.

### Why RSI 25/75 for sniper (not 35/65)
RSI 35 is often just the start of a drop. By targeting RSI 25, the limit order
is placed deeper — closer to actual bottoms. The fallback at 35 catches the
less extreme signals.

## Exit Logic

### Mean revert exit (primary)
- Longs: exit when RSI crosses above 55 (wave returning to normal)
- Shorts: exit when RSI crosses below 45
- Rationale: the entry bet was "price bounces from extreme." Once RSI returns
  toward neutral, the bounce is done. Holding past this is a different bet (trend
  continuation) with no edge.

### Trailing stop (continuous, every second)
- Breakeven at 0.7× ATR of profit
- Then trail at 1.5× ATR behind current price
- Operates via `modify_sl()` on MT5 — instant execution at broker level
- This protects against sharp reversals between M5 candle checks

### Initial stop loss
- 1.75× M5 ATR below entry (for longs)
- This is the maximum loss if the trade goes straight against us

## Position Management
- Profit protection: DISABLED (trailing stop replaces it)
- Max positions: from config (typically 1-2)
- Breakeven + trail managed by `manage_trailing_continuous()` every second

## The "Wave" Philosophy
Price moves in waves. An RSI extreme entry bets on ONE wave (the bounce).
The exit should happen when that wave completes (RSI returns to neutral),
not when a new wave starts in the opposite direction. Holding through
RSI neutral into the next wave is hoping, not trading.

## Known Weaknesses
- Entering during strong trends: RSI can stay oversold for extended periods
  in a downtrend. The entry catches a bounce but the bounce is short-lived.
- SL exits are large relative to wins (R:R ~0.5:1 historically)
- The trailing stop at 1.5 ATR may be too tight for M5 candle wicks

## Config: `config/m5_params.json`
Key fields used by the sniper:
- `rsi_period`: 14 (RSI calculation period)
- `rsi_buy`: 35 (fallback entry threshold, sniper uses 25)
- `rsi_sell`: 65 (fallback entry threshold, sniper uses 75)
- `atr_multiplier`: 1.75 (initial SL distance)
- `breakeven_atr_trigger`: 0.7 (move SL to entry after this much profit)
