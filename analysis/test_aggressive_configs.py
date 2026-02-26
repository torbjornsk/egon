import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

# Import the bidirectional backtest function
exec(open('bidirectional_strategy.py').read().split('def main()')[0])

def main():
    # Connect and get data
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching maximum available data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data: {len(data)} bars from {data['time'].min()} to {data['time'].max()}")
    days_span = (data['time'].max() - data['time'].min()).days
    print(f"Time span: {days_span} days\n")
    
    # Test aggressive configurations
    configs = {
        "Conservative (Baseline)": {
            'fast_ema': 20, 'slow_ema': 30, 'rsi_period': 10,
            'rsi_buy': 35, 'rsi_sell': 75,
            'atr_multiplier': 3.0, 'profit_target_pct': 0.025,
            'enable_shorts': True, 'enable_compounding': True
        },
        "Moderate Aggressive": {
            'fast_ema': 15, 'slow_ema': 25, 'rsi_period': 10,
            'rsi_buy': 40, 'rsi_sell': 65,  # Wider range = more trades
            'atr_multiplier': 3.5, 'profit_target_pct': 0.04,  # Higher target
            'enable_shorts': True, 'enable_compounding': True
        },
        "High Aggressive": {
            'fast_ema': 10, 'slow_ema': 20, 'rsi_period': 10,
            'rsi_buy': 45, 'rsi_sell': 60,  # Very wide = many trades
            'atr_multiplier': 4.0, 'profit_target_pct': 0.05,  # 5% target
            'enable_shorts': True, 'enable_compounding': True
        },
        "Maximum Risk": {
            'fast_ema': 10, 'slow_ema': 20, 'rsi_period': 10,
            'rsi_buy': 50, 'rsi_sell': 55,  # Trade almost always
            'atr_multiplier': 5.0, 'profit_target_pct': 0.06,  # 6% target
            'enable_shorts': True, 'enable_compounding': True
        }
    }
    
    results = {}
    
    for name, params in configs.items():
        print(f"\n{'='*80}")
        print(f"Testing: {name}")
        print(f"{'='*80}")
        
        balance, trades, equity = run_bidirectional_backtest(
            data, capital=1000, **params
        )
        
        metrics = calculate_metrics(balance, trades, equity, 1000)
        
        if metrics:
            results[name] = {
                'params': params,
                'metrics': metrics,
                'equity': equity,
                'trades': trades
            }
            
            print(f"Final Balance: ${metrics['balance']:.2f}")
            print(f"Return: {metrics['return']:.2f}%")
            print(f"Total Trades: {metrics['trades']}")
            if metrics['long_trades'] > 0:
                print(f"Long Trades: {metrics['long_trades']} (Win: {metrics['long_win_rate']:.1f}%)")
            if metrics['short_trades'] > 0:
                print(f"Short Trades: {metrics['short_trades']} (Win: {metrics['short_win_rate']:.1f}%)")
            print(f"Win Rate: {metrics['win_rate']:.2f}%")
            print(f"Max Drawdown: {abs(metrics['max_dd']):.2f}%")
            print(f"Avg Win: ${metrics['avg_win']:.2f}")
            print(f"Avg Loss: ${metrics['avg_loss']:.2f}")
    
    # Find best by return
    best_name = max(results.keys(), key=lambda k: results[k]['metrics']['return'])
    best = results[best_name]
    
    print("\n" + "="*80)
    print(f"BEST CONFIGURATION: {best_name}")
    print("="*80)
    print(f"Return: {best['metrics']['return']:.2f}%")
    print(f"Max Drawdown: {abs(best['metrics']['max_dd']):.2f}%")
    print(f"Risk/Reward Ratio: {best['metrics']['return'] / abs(best['metrics']['max_dd']):.2f}")
    
    # Save best
    config = {
        'strategy': 'aggressive_bidirectional',
        **best['params']
    }
    
    with open('config/aggressive_strategy_params.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nBest configuration saved to: config/aggressive_strategy_params.json")
    
    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curves
    ax = axes[0, 0]
    colors = ['green', 'blue', 'orange', 'red']
    for (name, result), color in zip(results.items(), colors):
        ax.plot(result['equity'], label=name, linewidth=2, color=color, alpha=0.8)
    ax.set_title('Equity Curves Comparison', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='black', linestyle='--', alpha=0.3)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')
    
    # Returns comparison
    ax = axes[0, 1]
    names = list(results.keys())
    returns = [results[name]['metrics']['return'] for name in names]
    bars = ax.bar(range(len(names)), returns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Return Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add value labels
    for bar, ret in zip(bars, returns):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{ret:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    # Max drawdown comparison
    ax = axes[1, 0]
    drawdowns = [abs(results[name]['metrics']['max_dd']) for name in names]
    ax.bar(range(len(names)), drawdowns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Max Drawdown Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Max Drawdown (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Return vs Risk scatter
    ax = axes[1, 1]
    for (name, result), color in zip(results.items(), colors):
        ax.scatter([abs(result['metrics']['max_dd'])], [result['metrics']['return']],
                  s=200, color=color, alpha=0.7, label=name, edgecolors='black', linewidths=2)
    ax.set_title('Return vs Risk', fontsize=14, fontweight='bold')
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('Return (%)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Add diagonal lines for risk/reward ratios
    max_dd = max(drawdowns)
    max_ret = max(returns)
    for ratio in [1, 2, 3, 5]:
        x = np.linspace(0, max_dd, 100)
        y = x * ratio
        ax.plot(x, y, 'k--', alpha=0.2, linewidth=0.5)
        ax.text(max_dd * 0.9, max_dd * ratio * 0.9, f'{ratio}:1', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('results/aggressive_comparison.png', dpi=150)
    print(f"Chart saved to: results/aggressive_comparison.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
