# Test Suite Quick Start

## First Time Setup

1. **Establish your baseline** (do this once):
```bash
python tests/establish_baseline.py
```

This will:
- Fetch historical data from MT5 and cache it
- Test your current M5 and M1 configurations
- Save baseline results to `tests/baseline_m5.json` and `tests/baseline_m1.json`
- Show performance across all time periods

Expected output:
```
M5 RESULTS:
==================================================================================
Period          Return       Trades   Win Rate   PF       Max DD     Sharpe  
----------------------------------------------------------------------------------
recent_30d      +12.5%       45       58.9%      1.63     -5.9%      2.83
recent_60d      +25.3%       89       57.2%      1.58     -6.2%      2.71
...
```

## Daily Workflow

### Option 1: Quick Test (Recommended)
```bash
python tests/compare_to_baseline.py
```

This compares your current config against the baseline and shows:
- What changed (parameters)
- Performance differences (↑ improvements, ↓ regressions)
- Overall summary

### Option 2: Full Test Suite
```bash
python tests/run_test_suite.py
```

This runs comprehensive tests including variations of your config.

## When to Use What

**Use `establish_baseline.py` when:**
- First time setup
- You've made significant changes and want to set a new baseline
- You want to refresh the cached data (weekly/monthly)

**Use `compare_to_baseline.py` when:**
- Testing parameter changes
- Validating optimization results
- Daily/hourly testing during development

**Use `run_test_suite.py` when:**
- Exploring different parameter combinations
- Learning how the test suite works
- Running custom comparisons

## Example Workflow

```bash
# 1. Establish baseline (once)
python tests/establish_baseline.py

# 2. Modify parameters in config/m5_params.json
# Change rsi_buy from 35 to 30

# 3. Test the change
python tests/compare_to_baseline.py

# 4. If good, commit the change
git add config/m5_params.json
git commit -m "Adjust M5 RSI buy threshold to 30"

# 5. Update baseline for future comparisons
python tests/establish_baseline.py
```

## Understanding Results

### Key Metrics

- **Total Return**: Cumulative % return (higher is better)
- **Trades**: Number of trades (more = more opportunities, but also more risk)
- **Win Rate**: % of winning trades (50%+ is good)
- **Profit Factor**: Gross profit / Gross loss (>1.5 is good)
- **Max Drawdown**: Largest peak-to-trough decline (smaller is better)
- **Sharpe Ratio**: Risk-adjusted return (>2.0 is excellent)

### What to Look For

✓ **Good signs:**
- Consistent positive returns across all periods
- Win rate > 50%
- Profit factor > 1.5
- Max drawdown < 10%
- Sharpe ratio > 2.0

✗ **Warning signs:**
- Negative returns in recent periods
- Win rate < 45%
- Profit factor < 1.2
- Max drawdown > 15%
- Large variance between periods (overfitting)

## Tips

1. **Don't optimize for one period** - If a config only works well on one period, it's likely overfit
2. **Recent periods matter more** - Focus on recent_30d and recent_60d as they reflect current market
3. **Balance metrics** - Don't just chase highest return; consider drawdown and Sharpe ratio
4. **Test before live** - Always run the test suite before deploying changes to live trading
5. **Keep baselines** - Commit baseline files to git so you can track improvements over time

## Troubleshooting

**"No cached data" error:**
```bash
python tests/establish_baseline.py
```

**MT5 connection failed:**
- Ensure MT5 is running
- Check you're logged in
- Verify XAUUSD is available

**Results seem wrong:**
- Check if you modified the strategy code
- Verify config files are correct
- Try force refresh: edit `establish_baseline.py` and set `force_refresh=True`

**Slow performance:**
- First run is slow (fetching data)
- Subsequent runs are fast (cached)
- Cache is in `tests/data_cache/`
