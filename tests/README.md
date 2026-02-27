# Trading Strategy Test Suite

A comprehensive, fast, and repeatable test suite for validating trading strategies.

## Features

- **Realistic**: Uses real historical data from MetaTrader 5
- **Varied**: Tests across multiple time periods (30d, 60d, 90d, 120d, 250d)
- **Repeatable**: Cached data ensures consistent results across runs
- **Fast**: Data caching eliminates repeated MT5 fetches

## Quick Start

```bash
# Run the test suite
python tests/run_test_suite.py
```

On first run, it will:
1. Fetch historical data from MT5 (takes a few minutes)
2. Cache the data locally
3. Test your current M5 and M1 configurations
4. Show performance across all time periods

Subsequent runs are fast (seconds) because data is cached.

## Usage

### Basic Testing

```python
from tests.test_suite import TestSuite
import json

# Initialize
suite = TestSuite()

# Fetch and cache data (once per day)
suite.fetch_and_cache_data()

# Load your config
with open('config/m5_params.json') as f:
    config = json.load(f)

# Test it
results = suite.test_config('My Config', config, timeframe='M5')
```

### Comparing Configurations

```python
configs = {
    'Current': current_config,
    'Modified': modified_config,
    'Alternative': alternative_config
}

results = suite.compare_configs(configs, timeframe='M5')
```

### Custom Analysis

```python
# Load cached data
cache_key = suite._get_cache_key('XAUUSD', 'M5', 90)
df = suite._load_cached_data(cache_key)

# Compute indicators
df = suite.compute_indicators(df, fast_ema=12, slow_ema=26, rsi_period=14)

# Simulate strategy
trades = suite.simulate_strategy(df, config, max_positions=2)

# Analyze results
metrics = suite.analyze_results(trades)
```

## Test Periods

The suite tests across 5 different periods:

- **recent_30d**: Last 30 days (recent market conditions)
- **recent_60d**: Last 60 days (short-term validation)
- **recent_90d**: Last 90 days (medium-term validation)
- **recent_120d**: Last 120 days (longer-term validation)
- **full_history**: 250 days (comprehensive validation)

This ensures your strategy works across different market conditions, not just one specific period.

## Metrics Reported

For each test period, you get:

- **Total Return**: Cumulative percentage return
- **Total Trades**: Number of trades executed
- **Win Rate**: Percentage of winning trades
- **Profit Factor**: Gross profit / Gross loss
- **Max Drawdown**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted return metric

## Data Caching

Data is cached in `tests/data_cache/` with keys based on:
- Symbol (XAUUSD)
- Timeframe (M1/M5)
- Period length (days)
- Current date

Cache is automatically invalidated daily to ensure fresh data.

To force refresh:
```python
suite.fetch_and_cache_data(force_refresh=True)
```

## Integration with Optimization

Use the test suite to validate optimization results:

```python
# After running optimization
optimized_config = {...}

# Test on all periods
results = suite.test_config('Optimized', optimized_config, timeframe='M5')

# Compare with baseline
baseline_config = {...}
comparison = suite.compare_configs({
    'Baseline': baseline_config,
    'Optimized': optimized_config
}, timeframe='M5')
```

## Best Practices

1. **Establish Baseline**: Run the test suite on your current config before making changes
2. **Test All Periods**: Don't just optimize for one period - ensure consistency across all
3. **Compare Metrics**: Look at multiple metrics (return, win rate, drawdown, Sharpe) not just total return
4. **Refresh Data**: Run `fetch_and_cache_data(force_refresh=True)` periodically to get latest data
5. **Version Control**: Commit your baseline results so you can track improvements over time

## Troubleshooting

**"No cached data" error**: Run `suite.fetch_and_cache_data()` first

**MT5 connection issues**: Ensure MT5 is running and logged in

**Inconsistent results**: Make sure you're using cached data (don't force refresh between comparisons)

**Slow performance**: First run is slow (fetching data), subsequent runs are fast (cached)
