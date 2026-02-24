import sys
sys.path.append('src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategies.scalping import ScalpingStrategy
from backtesting.optimizer import ParameterOptimizer
from backtesting.backtester import Backtester
import json

def generate_sample_gold_data(days=365, timeframe_minutes=5):
    """Generate realistic sample gold price data"""
    np.random.seed(42)
    
    # Calculate number of bars
    bars_per_day = (24 * 60) // timeframe_minutes
    total_bars = days * bars_per_day
    
    # Generate timestamps
    start_date = datetime.now() - timedelta(days=days)
    timestamps = [start_date + timedelta(minutes=i*timeframe_minutes) for i in range(total_bars)]
    
    # Generate realistic gold prices (around $2000-2100)
    base_price = 2050
    trend = np.linspace(0, 50, total_bars)  # Slight upward trend
    noise = np.random.randn(total_bars) * 5  # Random volatility
    
    # Add some cyclical patterns
    cycle = 20 * np.sin(np.linspace(0, 20*np.pi, total_bars))
    
    close_prices = base_price + trend + noise + cycle
    
    # Generate OHLC data
    data = []
    for i, timestamp in enumerate(timestamps):
        close = close_prices[i]
        high = close + abs(np.random.randn() * 3)
        low = close - abs(np.random.randn() * 3)
        open_price = close_prices[i-1] if i > 0 else close
        
        data.append({
            'time': timestamp,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'tick_volume': np.random.randint(100, 1000),
            'spread': 0,
            'real_volume': 0
        })
    
    return pd.DataFrame(data)

def main():
    print("="*60)
    print("MT5 GOLD BOT - PARAMETER OPTIMIZATION (SAMPLE DATA)")
    print("="*60)
    
    # Load config
    with open('config/trading_params.json', 'r') as f:
        config = json.load(f)
    
    # Generate sample data
    print("\nGenerating sample gold price data...")
    data = generate_sample_gold_data(days=365, timeframe_minutes=5)
    print(f"Generated {len(data)} bars of data")
    print(f"Date range: {data['time'].min()} to {data['time'].max()}")
    print(f"Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    
    # Define parameter ranges to optimize
    param_ranges = {
        'fast_ema': (5, 15, 2),
        'slow_ema': (20, 40, 5),
        'atr_multiplier': (1.0, 3.0, 0.5),
    }
    
    print("\n" + "="*60)
    print("STARTING OPTIMIZATION")
    print("="*60)
    print(f"Parameter ranges:")
    for param, (min_val, max_val, step) in param_ranges.items():
        print(f"  {param}: {min_val} to {max_val} (step: {step})")
    
    print(f"\nOptimization method: Genetic Algorithm")
    print(f"Population size: 30")
    print(f"Generations: 15")
    print("\nThis may take a few minutes...")
    
    optimizer = ParameterOptimizer(ScalpingStrategy, data, param_ranges)
    
    # Run genetic algorithm optimization
    best_params, logbook = optimizer.optimize_genetic(population_size=30, generations=15)
    
    print("\n" + "="*60)
    print("OPTIMIZATION COMPLETE")
    print("="*60)
    print(f"\nBest parameters found:")
    for param, value in best_params.items():
        print(f"  {param}: {value}")
    
    # Test best parameters with backtest
    print("\n" + "="*60)
    print("BACKTESTING WITH OPTIMIZED PARAMETERS")
    print("="*60)
    
    full_params = {**config['scalping'], **best_params}
    strategy = ScalpingStrategy(full_params)
    backtester = Backtester(strategy, initial_balance=10000)
    results = backtester.run(data, risk_per_trade=config['risk_per_trade'])
    
    print(f"\nBacktest Results:")
    print(f"  Total Trades: {results['total_trades']}")
    print(f"  Winning Trades: {results['winning_trades']}")
    print(f"  Losing Trades: {results['losing_trades']}")
    print(f"  Win Rate: {results['win_rate']:.2%}")
    print(f"  Total Profit: ${results['total_profit']:.2f}")
    print(f"  Profit Factor: {results['profit_factor']:.2f}")
    print(f"  Max Drawdown: {results['max_drawdown']:.2%}")
    print(f"  Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"  Final Balance: ${results['final_balance']:.2f}")
    print(f"  Return: {results['return_pct']:.2f}%")
    
    # Save optimized parameters
    config['scalping'].update(best_params)
    with open('config/trading_params_optimized.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n" + "="*60)
    print(f"Optimized parameters saved to: config/trading_params_optimized.json")
    print("="*60)

if __name__ == "__main__":
    main()
