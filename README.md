# MetaTrader5 Gold Trading Bot

A sophisticated automated trading bot for gold (XAUUSD) using MetaTrader5, featuring backtesting, parameter optimization, and risk management.

## Features

- **Multiple Trading Strategies**: Scalping strategy with EMA crossovers, RSI, and ATR indicators
- **Risk Management**: Position sizing, leverage control, daily loss limits, max open positions
- **Backtesting Engine**: Test strategies against historical data
- **Parameter Optimization**: Genetic algorithms and grid search for finding optimal parameters
- **Demo & Live Trading**: Switch between demo and real money trading
- **Clean Configuration**: JSON-based parameter management

## Installation

1. Install MetaTrader5 terminal

2. Install [uv](https://docs.astral.sh/uv/) (fast Python package manager):
```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

3. Install dependencies:
```bash
# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .

# Or for development (includes testing and linting tools)
uv pip install -e ".[dev]"

# For Jupyter notebook support
uv pip install -e ".[notebook]"
```

Alternatively, use the Makefile:
```bash
make install      # Install base dependencies
make dev          # Install with dev dependencies
make notebook     # Install with notebook support
```

## Configuration

### Bot Configuration (`config/bot_config.json`)

- `mode`: "demo" or "live"
- `account_id`: Your MT5 account number (optional for demo)
- `password`: Your MT5 password (optional for demo)
- `server`: Your broker's server name (optional for demo)

### Trading Parameters (`config/trading_params.json`)

- `symbol`: Trading symbol (default: "XAUUSD")
- `timeframe`: Chart timeframe (M1, M5, M15, M30, H1, H4, D1)
- `risk_per_trade`: Risk percentage per trade (0.02 = 2%)
- `max_leverage`: Maximum leverage to use
- `max_daily_loss`: Maximum daily loss percentage (0.05 = 5%)
- `max_open_positions`: Maximum concurrent positions

Strategy-specific parameters in the `scalping` section.

## Usage

### Running the Bot

```python
from src.bot import GoldTradingBot

bot = GoldTradingBot()
bot.start()
```

### Backtesting

```python
from src.mt5_connector import MT5Connector
from src.strategies.scalping import ScalpingStrategy
from src.backtesting.backtester import Backtester
from datetime import datetime, timedelta

# Connect and get data
mt5 = MT5Connector()
mt5.connect()

end_date = datetime.now()
start_date = end_date - timedelta(days=365)
data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)

# Run backtest
params = {
    'fast_ema': 9,
    'slow_ema': 21,
    'rsi_period': 14,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'atr_period': 14,
    'atr_multiplier': 1.5,
    'take_profit_pips': 50,
    'stop_loss_pips': 30
}

strategy = ScalpingStrategy(params)
backtester = Backtester(strategy, initial_balance=10000)
results = backtester.run(data)

print(f"Total Trades: {results['total_trades']}")
print(f"Win Rate: {results['win_rate']:.2%}")
print(f"Total Profit: ${results['total_profit']:.2f}")
print(f"Profit Factor: {results['profit_factor']:.2f}")
print(f"Max Drawdown: {results['max_drawdown']:.2%}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
```

### Parameter Optimization

```python
from src.backtesting.optimizer import ParameterOptimizer
from src.strategies.scalping import ScalpingStrategy

# Define parameter ranges to optimize
param_ranges = {
    'fast_ema': (5, 15, 1),
    'slow_ema': (20, 40, 2),
    'atr_multiplier': (1.0, 3.0, 0.5)
}

optimizer = ParameterOptimizer(ScalpingStrategy, data, param_ranges)

# Use genetic algorithm (recommended for large parameter spaces)
best_params, logbook = optimizer.optimize_genetic(population_size=50, generations=20)

# Or use grid search (for small parameter spaces)
# best_params = optimizer.grid_search()

print(f"Optimal parameters: {best_params}")
```

## Safety Features

1. **Risk Management**
   - Position sizing based on account balance and risk percentage
   - Stop loss and take profit on every trade
   - Maximum leverage limits
   - Daily loss limits to prevent catastrophic losses

2. **Demo Mode**
   - Test strategies with virtual money before going live
   - Same execution logic as live trading

3. **Monitoring**
   - Comprehensive logging
   - Track all trades and performance metrics

## Important Notes

- **Start with Demo**: Always test thoroughly in demo mode before using real money
- **Monitor Performance**: Regularly review bot performance and adjust parameters
- **Market Conditions**: Strategies may perform differently in various market conditions
- **Leverage Risk**: Higher leverage increases both potential profits and losses
- **Broker Requirements**: Ensure your broker allows automated trading

## Disclaimer

Trading involves substantial risk. Past performance does not guarantee future results. This bot is provided for educational purposes. Use at your own risk.
