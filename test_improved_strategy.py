import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from strategies.improved_scalping import ImprovedScalpingStrategy
from backtesting.backtester import Backtester
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

def main():
    # Connect and get data
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data: {len(data)} bars from {data['time'].min()} to {data['time'].max()}")
    
    # Test different configurations
    configs = {
        "Your Original Approach": {
            'ema_period': 50,
            'rsi_period': 10,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'profit_target_pct': 0.03,
            'stop_loss_pct': 0.02,
            'require_uptrend': False,
            'use_atr_stops': False,
            'atr_period': 14,
            'atr_multiplier': 2.0
        },
        "With Trend Filter": {
            'ema_period': 50,
            'rsi_period': 10,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'profit_target_pct': 0.03,
            'stop_loss_pct': 0.02,
            'require_uptrend': True,  # Only buy in uptrend
            'use_atr_stops': False,
            'atr_period': 14,
            'atr_multiplier': 2.0
        },
        "With ATR Stops": {
            'ema_period': 50,
            'rsi_period': 10,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'profit_target_pct': 0.03,
            'stop_loss_pct': 0.02,
            'require_uptrend': True,
            'use_atr_stops': True,  # Dynamic stops based on volatility
            'atr_period': 14,
            'atr_multiplier': 2.0
        },
        "Conservative": {
            'ema_period': 50,
            'rsi_period': 14,
            'rsi_oversold': 25,  # More oversold
            'rsi_overbought': 75,  # More overbought
            'profit_target_pct': 0.025,
            'stop_loss_pct': 0.015,
            'require_uptrend': True,
            'use_atr_stops': True,
            'atr_period': 14,
            'atr_multiplier': 1.5
        }
    }
    
    results_all = {}
    
    for name, params in configs.items():
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"{'='*60}")
        
        strategy = ImprovedScalpingStrategy(params)
        backtester = Backtester(strategy, initial_balance=1000)  # Match your $1000 capital
        results = backtester.run(data, risk_per_trade=0.02)
        
        results_all[name] = results
        
        print(f"Total Trades: {results['total_trades']}")
        print(f"Win Rate: {results['win_rate']:.2%}")
        print(f"Total Profit: ${results['total_profit']:.2f}")
        print(f"Profit Factor: {results['profit_factor']:.2f}")
        print(f"Max Drawdown: {results['max_drawdown']:.2%}")
        print(f"Final Balance: ${results['final_balance']:.2f}")
        print(f"Return: {results['return_pct']:.2f}%")
    
    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curves
    ax = axes[0, 0]
    for name, results in results_all.items():
        ax.plot(results['equity_curve'], label=name, linewidth=2)
    ax.set_title('Equity Curves', fontsize=14, fontweight='bold')
    ax.set_xlabel('Trade Number')
    ax.set_ylabel('Balance ($)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Returns comparison
    ax = axes[0, 1]
    names = list(results_all.keys())
    returns = [results_all[name]['return_pct'] for name in names]
    colors = ['blue', 'green', 'orange', 'red']
    ax.bar(range(len(names)), returns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Return Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Win rate comparison
    ax = axes[1, 0]
    win_rates = [results_all[name]['win_rate'] * 100 for name in names]
    ax.bar(range(len(names)), win_rates, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Win Rate Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Win Rate (%)')
    ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50%')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # Max drawdown comparison
    ax = axes[1, 1]
    drawdowns = [abs(results_all[name]['max_drawdown']) * 100 for name in names]
    ax.bar(range(len(names)), drawdowns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Max Drawdown Comparison (Lower is Better)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Max Drawdown (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('results/improved_strategy_comparison.png', dpi=150)
    print(f"\n{'='*60}")
    print("Chart saved to: results/improved_strategy_comparison.png")
    print(f"{'='*60}")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
