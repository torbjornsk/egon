# Analysis Scripts

This folder contains historical analysis and testing scripts used during bot development. Most are one-off explorations and don't need to be run regularly.

## Useful Scripts

### Performance Analysis
- **None currently** - Use `../evaluate_live_trades.py` in root for live performance

### Strategy Testing
- **test_market_conditions.py** - Test bots in different market conditions (uptrend, downtrend, crash)
- **test_extreme_scenarios.py** - Stress test during worst historical periods
- **walk_forward_test.py** - Walk-forward validation of strategy

### Safety Analysis
- **analyze_losing_streaks.py** - Analyze consecutive loss patterns
- **analyze_drawdown_limits.py** - Validate drawdown thresholds

## Historical/Archived Scripts

These were used during development but are no longer needed:

### M1 Optimization Attempts
- test_m1_*.py (15 files) - Various M1 strategy tests
- analyze_m1_*.py - M1 performance analysis

### Strategy Development
- *_strategy.py - Old strategy implementations
- test_*_configs.py - Configuration testing

### Backtest Variations
- accurate_backtest.py - High/low aware backtesting
- simulation.py - Basic simulation
- monte_carlo_test.py - Monte Carlo validation

## Running Analysis Scripts

Most scripts follow this pattern:
```bash
python analysis/script_name.py
```

They will:
1. Connect to MT5
2. Fetch historical data
3. Run analysis
4. Print results

## Note

These scripts are kept for reference but are not part of the core bot functionality. The live bots in the root directory are what you should run for actual trading.
