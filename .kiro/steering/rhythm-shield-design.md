# Market Rhythm & Breakout Shield

## Overview
Two new modules added to the sniper bot (June 2026):
1. **Market Rhythm Analyzer** (`src/core/rhythm.py`) -- determines if RSI swings are tradeable
2. **Breakout Shield** (`src/core/breakout_shield.py`) -- market-aware re-entry protection after SL

## Market Rhythm (`rhythm_enabled`, `rhythm_mode`)

Analyzes RSI cycle characteristics on the primary timeframe:
- **Cycle detection**: RSI midline (50) crossings, half-cycle length measurement
- **Amplitude**: How deep RSI swings go, price distance per swing
- **Regime classification**: swinging / trending / dead / chaotic
- **Support-aware sniper placement**: Caps sniper levels at liquidity zone edges

### Modes
- `manual` -- computed for logging/GUI but never blocks entries or changes params
- `gated` -- blocks entries when regime is trending/dead/chaotic, keeps manual params
- `dynamic` -- actively adjusts sniper offset, sizing scale, SL/trail distances, breakeven trigger

### Dynamic mode adjustments
- `sizing_scale`: reduces position size when swings are shallow (amplitude < target)
- `sl_scale`: tightens SL in stable cycles, widens in unstable/low-confidence cycles
- `sniper_offset_dynamic`: places limits at observed extreme depth (not fixed offset)
- `breakeven_trigger_scale`: faster BE in high-amplitude, slower in low-amplitude

### Multi-timeframe
- Primary TF: cycle/amplitude detection
- HTF (`rhythm_htf_timeframe`): regime confirmation (M15 for M5, M5 for M1)
- H1: always fetched for macro context

## Breakout Shield (`shield_enabled`)

After ANY stop-loss exit, blocks re-entry until market analysis confirms the breakout is over.
NOT timer-based -- lifts based on market normalization signals.

### Post-SL analysis
1. **Duration**: rapid SL (< `shield_rapid_sl_candles` bars) = higher severity
2. **Breakout level**: was SL near N-bar high/low that price broke through?
3. **HTF alignment**: do M15 + H1 agree with the direction that stopped you?

### Severity classification
- LIGHT: normal SL, need 1 normalization signal
- MEDIUM: rapid SL or breakout detected, need 1 signal + reduced size
- HEAVY: rapid + breakout + HTF aligned, need 2 signals

### Normalization signals (any of these can lift the shield)
- `price_return`: price retraces past entry level (breakout failed)
- `rsi_normalize`: RSI crosses back through 50 (momentum exhausted)
- `momentum_stall`: 3 consecutive small-body candles (absorption)
- `htf_reversal`: HTF RSI turning from extreme (macro unwinding)

### Direction-specific
Shield only blocks the direction that was stopped. Other direction remains tradeable.

### Post-shield sizing
After shield lifts, next N trades use reduced size (`shield_reduced_size_factor`).

## Config fields
```json
{
  "rhythm_enabled": true,
  "rhythm_mode": "gated",
  "rhythm_min_amplitude_atr": 0.8,
  "rhythm_max_cycle_bars": 35,
  "rhythm_min_cycle_bars": 6,
  "rhythm_dead_atr_factor": 0.5,
  "rhythm_htf_timeframe": "M15",
  "rhythm_support_aware_sniper": true,
  "shield_enabled": true,
  "shield_rapid_sl_candles": 3,
  "shield_reduced_size_factor": 0.5,
  "shield_reduced_size_trades": 2
}
```

## Per-timeframe recommended settings
| Param | M1 | M5 | M15 |
|---|---|---|---|
| `shield_rapid_sl_candles` | 6 | 3 | 2 |
| `rhythm_min_cycle_bars` | 8 | 6 | 5 |
| `rhythm_max_cycle_bars` | 50 | 35 | 30 |
| `rhythm_min_amplitude_atr` | 1.0 | 0.8 | 0.6 |
| `rhythm_htf_timeframe` | M5 | M15 | H1 |

## Integration points in SniperBot
1. `trading_logic()`: rhythm check after volatility guard, shield check before entry
2. `open_position()`: applies sizing_scale and sl_scale
3. `_manage_trailing()`: applies sl_scale to trail distances and be_trigger
4. `check_mt5_closed_positions()`: notifies shield on SL exits
5. `check_sniper_fills()`: shield check before acting on fills
6. `get_state()`: exposes rhythm and shield status for GUI
