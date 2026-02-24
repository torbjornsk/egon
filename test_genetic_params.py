import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from strategies.scalping import ScalpingStrategy
from backtesting.backtester import Backtester
from datetime import datetime, timedelta
import json
import matplotlib.pyplot as plt

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
    
    print(f"Full dataset: {len(data)} bars from {data['time'].min()} to {data['time'].max()}")
    days_span = (data['time'].max() - data['time'].min()).days
    print(f"Time span: {days_span} days\n")
    
    # Also get 90-day subset (the period it was optimized on)
    start_90 = end_date - timedelta(days=90)
    data_90 = data[data['time'] >= start_90].copy()
    print(f"90-day subset: {len(data_90)} bars from {data_90['time'].min()} to {data_90['time'].max()}\n")
    
    # Load the genetic algorithm optimized parameters
    with open('config/trading_params_optimized.json', 'r') as f:
        config = json.load(f)
    
    genetic_params = config['scalping']
    
    print("="*80)
    print("GENETIC ALGORITHM OPTIMIZED PARAMETERS")
    print("="*80)
    print(f"Fast EMA: {genetic_params['fast_ema']:.2f}")
    print(f"Slow EMA: {genetic_params['slow_ema']:.2f}")
    print(f"ATR Multiplier: {genetic_params['atr_multiplier']:.2f}")
    print(f"Take Profit: {genetic_params['take_profit_pips']} pips")
    print(f"Stop Loss: {genetic_params['stop_loss_pips']:.2f} pips")
    
    # Test on 90-day period (what it was optimized on)
    print("\n" + "="*80)
    print("TESTING ON 90-DAY PERIOD (OPTIMIZATION PERIOD)")
    print("="*80)
    
    strategy_90 = ScalpingStrategy(genetic_params)
    backtester_90 = Backtester(strategy_90, initial_balance=10000)
    results_90 = backtester_90.run(data_90, risk_per_trade=0.02)
    
    print(f"Total Trades: {results_90['total_trades']}")
    print(f"Win Rate: {results_90['win_rate']:.2%}")
    print(f"Total Profit: ${results_90['total_profit']:.2f}")
    print(f"Profit Factor: {results_90['profit_factor']:.2f}")
    print(f"Max Drawdown: {results_90['max_drawdown']:.2%}")
    print(f"Final Balance: ${results_90['final_balance']:.2f}")
    print(f"Return: {results_90['return_pct']:.2f}%")
    
    # Test on full 8-month period
    print("\n" + "="*80)
    print("TESTING ON FULL 8-MONTH PERIOD (OUT-OF-SAMPLE)")
    print("="*80)
    
    strategy_full = ScalpingStrategy(genetic_params)
    backtester_full = Backtester(strategy_full, initial_balance=10000)
    results_full = backtester_full.run(data, risk_per_trade=0.02)
    
    print(f"Total Trades: {results_full['total_trades']}")
    print(f"Win Rate: {results_full['win_rate']:.2%}")
    print(f"Total Profit: ${results_full['total_profit']:.2f}")
    print(f"Profit Factor: {results_full['profit_factor']:.2f}")
    print(f"Max Drawdown: {results_full['max_drawdown']:.2%}")
    print(f"Final Balance: ${results_full['final_balance']:.2f}")
    print(f"Return: {results_full['return_pct']:.2f}%")
    
    # Compare with default parameters
    print("\n" + "="*80)
    print("COMPARISON: DEFAULT PARAMETERS ON FULL PERIOD")
    print("="*80)
    
    default_params = {
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
    
    strategy_default = ScalpingStrategy(default_params)
    backtester_default = Backtester(strategy_default, initial_balance=10000)
    results_default = backtester_default.run(data, risk_per_trade=0.02)
    
    print(f"Total Trades: {results_default['total_trades']}")
    print(f"Win Rate: {results_default['win_rate']:.2%}")
    print(f"Total Profit: ${results_default['total_profit']:.2f}")
    print(f"Profit Factor: {results_default['profit_factor']:.2f}")
    print(f"Max Drawdown: {results_default['max_drawdown']:.2%}")
    print(f"Final Balance: ${results_default['final_balance']:.2f}")
    print(f"Return: {results_default['return_pct']:.2f}%")
    
    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curves
    ax = axes[0, 0]
    ax.plot(results_90['equity_curve'], label='Genetic (90 days)', linewidth=2, color='green')
    ax.set_title('Genetic Params - 90 Day Period', fontsize=14, fontweight='bold')
    ax.set_xlabel('Trade Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=10000, color='red', linestyle='--', alpha=0.5)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    ax = axes[0, 1]
    ax.plot(results_full['equity_curve'], label='Genetic (8 months)', linewidth=2, color='blue')
    ax.plot(results_default['equity_curve'], label='Default (8 months)', linewidth=2, color='orange', alpha=0.7)
    ax.set_title('Full Period Comparison', fontsize=14, fontweight='bold')
    ax.set_xlabel('Trade Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=10000, color='red', linestyle='--', alpha=0.5)
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Returns comparison
    ax = axes[1, 0]
    strategies = ['Genetic\n(90 days)', 'Genetic\n(8 months)', 'Default\n(8 months)']
    returns = [results_90['return_pct'], results_full['return_pct'], results_default['return_pct']]
    colors = ['green', 'blue', 'orange']
    bars = ax.bar(strategies, returns, color=colors, alpha=0.7)
    ax.set_title('Return Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar, ret in zip(bars, returns):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{ret:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    # Key metrics comparison
    ax = axes[1, 1]
    metrics = ['Win Rate', 'Profit Factor', 'Max DD (abs)']
    genetic_90_metrics = [results_90['win_rate']*100, results_90['profit_factor'], abs(results_90['max_drawdown'])*100]
    genetic_full_metrics = [results_full['win_rate']*100, results_full['profit_factor'], abs(results_full['max_drawdown'])*100]
    default_metrics = [results_default['win_rate']*100, results_default['profit_factor'], abs(results_default['max_drawdown'])*100]
    
    x = range(len(metrics))
    width = 0.25
    ax.bar([i - width for i in x], genetic_90_metrics, width, label='Genetic (90d)', color='green', alpha=0.7)
    ax.bar(x, genetic_full_metrics, width, label='Genetic (8m)', color='blue', alpha=0.7)
    ax.bar([i + width for i in x], default_metrics, width, label='Default (8m)', color='orange', alpha=0.7)
    
    ax.set_title('Key Metrics Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('results/genetic_params_analysis.png', dpi=150)
    print(f"\n{'='*80}")
    print("Chart saved to: results/genetic_params_analysis.png")
    print(f"{'='*80}")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
