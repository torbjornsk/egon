# Configuration Files

## Active Configs

### m5_params.json
Configuration for the M5 (5-minute) trading bot.

**Strategy:** RSI mean reversion on 5-minute timeframe
- Entry: RSI < 30 (buy dips)
- Exit: RSI > 85 or 4% profit target
- Position: 15% @ 25x leverage = 375% effective
- Stop loss: 3.0x ATR
- Max drawdown limit: 35%

**Note:** Parameters will be updated with optimized values from grid search.

### m1_params.json
Configuration for the M1 (1-minute) trading bot.

**Strategy:** Aggressive RSI scalping on 1-minute timeframe
- Entry: RSI < 35 (buy dips)
- Exit: RSI > 75 or 0.8% profit target
- Position: 15% @ 25x leverage = 375% effective
- Stop loss: 4.0x ATR (wider for M1 noise)
- Max drawdown limit: 40%
- Fast re-entry: Skips cooldown after profitable trades

**Performance:** 76% monthly return, 100% profitable over 30-day periods

### bot_config.json
General bot configuration (if used).

## Archive Folder

Contains old/experimental configurations:
- `aggressive_strategy_params.json` - Old aggressive strategy
- `bidirectional_strategy_params.json` - Long+short strategy (8-month backtest)
- `hybrid_strategy_params.json` - Hybrid EMA+RSI strategy
- `optimized_strategy_params.json` - Incomplete config
- `trading_params_optimized.json` - Genetic algorithm results
- `trading_params.json` - Old format config
- `safe_leveraged_params.json` - Old M5 config (underperforming)
- `m1_scalping_params.json` - Old M1 config name

These are kept for reference but not used by the live bots.

## Usage

**M5 Bot:**
```bash
# Uses m5_params.json by default
start_bot.bat
```

**M1 Bot:**
```bash
# Uses m1_params.json by default
start_bot_m1.bat
```

## Modifying Configs

When changing parameters:
1. Test in backtest first
2. Verify across multiple time periods
3. Check Sharpe ratio (return/drawdown)
4. Update this README with changes

## Key Parameters Explained

- `position_size_pct`: Percentage of balance per trade (0.15 = 15%)
- `leverage`: Multiplier for position size (25x)
- `max_drawdown_limit`: Auto-pause trading if exceeded
- `rsi_buy`: RSI threshold for entry (lower = more oversold)
- `rsi_exit_long`: RSI threshold for exit (higher = more overbought)
- `atr_multiplier`: Stop loss distance in ATR units
- `profit_target_pct`: Take profit percentage (0.008 = 0.8%)
- `enable_shorts`: Allow short positions (currently true for both)

## Safety Mechanisms

Both configs include multiple safety layers:
1. Drawdown limits (35% M5, 40% M1)
2. Daily loss limits (15% in 24h)
3. Rapid loss detection (10% in 1h)
4. Consecutive loss limits (8 M5, 7 M1)
5. Emergency threshold (50% equity)

See `SAFETY_MECHANISMS.md` for details.
