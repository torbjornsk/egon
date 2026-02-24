import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from strategies.scalping import ScalpingStrategy
from backtesting.optimizer import ParameterOptimizer
from backtesting.backtester import Backtester
from datetime import datetime, timedelta
import json

def main():
    # Load config
    with open('config/trading_params.json', 'r') as f:
        config = json.load(f)
    
    # Connect to MT5
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    # Get historical data (request 1 year, will get maximum available)
    print("Fetching historical data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    print(f"Symbol: {config['symbol']}")
    print(f"Timeframe: {config['timeframe']}")
    print(f"Requesting date range: {start_date} to {end_date}")
    data = mt5.get_historical_data(config['symbol'], config['timeframe'], start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data fetched: {len(data)} bars")
    print(f"Actual date range: {data['time'].min()} to {data['time'].max()}")
    print(f"Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    
    # Define parameter ranges to optimize
    param_ranges = {
        'fast_ema': (5, 15, 1),
        'slow_ema': (20, 40, 2),
        'atr_multiplier': (1.0, 3.0, 0.5),
        'take_profit_pips': (30, 80, 10),
        'stop_loss_pips': (20, 50, 5)
    }
    
    print("\nStarting parameter optimization...")
    print(f"Parameter ranges: {param_ranges}")
    
    optimizer = ParameterOptimizer(ScalpingStrategy, data, param_ranges)
    
    # Run genetic algorithm optimization (reduced for faster execution with large dataset)
    best_params, logbook = optimizer.optimize_genetic(population_size=30, generations=15)
    
    print("\n" + "="*50)
    print("OPTIMIZATION RESULTS")
    print("="*50)
    print(f"Best parameters found: {best_params}")
    
    # Test best parameters
    print("\nTesting optimized parameters...")
    full_params = {**config['scalping'], **best_params}
    strategy = ScalpingStrategy(full_params)
    backtester = Backtester(strategy, initial_balance=10000)
    results = backtester.run(data, risk_per_trade=config['risk_per_trade'])
    
    print(f"\nBacktest with optimized parameters:")
    print(f"Total Trades: {results['total_trades']}")
    print(f"Win Rate: {results['win_rate']:.2%}")
    print(f"Total Profit: ${results['total_profit']:.2f}")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown']:.2%}")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"Return: {results['return_pct']:.2f}%")
    
    # Save optimized parameters
    config['scalping'].update(best_params)
    with open('config/trading_params_optimized.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\nOptimized parameters saved to config/trading_params_optimized.json")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
