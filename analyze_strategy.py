import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from strategies.scalping import ScalpingStrategy
from backtesting.backtester import Backtester
from datetime import datetime, timedelta
import json
import matplotlib.pyplot as plt

def analyze_strategy(params, data, label="Strategy"):
    """Run backtest and return detailed analysis"""
    strategy = ScalpingStrategy(params)
    backtester = Backtester(strategy, initial_balance=10000)
    results = backtester.run(data, risk_per_trade=0.02)
    
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"Parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")
    
    print(f"\nResults:")
    print(f"  Total Trades: {results['total_trades']}")
    print(f"  Winning Trades: {results['winning_trades']}")
    print(f"  Losing Trades: {results['losing_trades']}")
    print(f"  Win Rate: {results['win_rate']:.2%}")
    print(f"  Total Profit: ${results['total_profit']:.2f}")
    print(f"  Gross Profit: ${results['gross_profit']:.2f}")
    print(f"  Gross Loss: ${results['gross_loss']:.2f}")
    print(f"  Profit Factor: {results['profit_factor']:.2f}")
    print(f"  Max Drawdown: {results['max_drawdown']:.2%}")
    print(f"  Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"  Final Balance: ${results['final_balance']:.2f}")
    print(f"  Return: {results['return_pct']:.2f}%")
    
    if results['total_trades'] > 0:
        avg_win = results['gross_profit'] / results['winning_trades'] if results['winning_trades'] > 0 else 0
        avg_loss = results['gross_loss'] / results['losing_trades'] if results['losing_trades'] > 0 else 0
        print(f"  Avg Win: ${avg_win:.2f}")
        print(f"  Avg Loss: ${avg_loss:.2f}")
        print(f"  Risk/Reward Ratio: {avg_win/avg_loss:.2f}" if avg_loss > 0 else "  Risk/Reward Ratio: N/A")
    
    return results

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
    print(f"Time span: {days_span} days")
    
    # Load configurations
    with open('config/trading_params.json', 'r') as f:
        default_config = json.load(f)
    
    try:
        with open('config/trading_params_optimized.json', 'r') as f:
            optimized_config = json.load(f)
    except:
        optimized_config = None
    
    # Test default parameters
    results_default = analyze_strategy(default_config['scalping'], data, "DEFAULT PARAMETERS")
    
    # Test optimized parameters if available
    if optimized_config:
        results_optimized = analyze_strategy(optimized_config['scalping'], data, "OPTIMIZED PARAMETERS")
    
    # Test some alternative strategies
    print(f"\n{'='*60}")
    print("TESTING ALTERNATIVE STRATEGIES")
    print(f"{'='*60}")
    
    # Conservative strategy (tighter stops, smaller targets)
    conservative = {
        'fast_ema': 8,
        'slow_ema': 21,
        'rsi_period': 14,
        'rsi_overbought': 70,
        'rsi_oversold': 30,
        'atr_period': 14,
        'atr_multiplier': 1.5,
        'take_profit_pips': 40,
        'stop_loss_pips': 25
    }
    results_conservative = analyze_strategy(conservative, data, "CONSERVATIVE STRATEGY")
    
    # Aggressive strategy (wider stops, bigger targets)
    aggressive = {
        'fast_ema': 5,
        'slow_ema': 34,
        'rsi_period': 14,
        'rsi_overbought': 70,
        'rsi_oversold': 30,
        'atr_period': 14,
        'atr_multiplier': 2.5,
        'take_profit_pips': 80,
        'stop_loss_pips': 35
    }
    results_aggressive = analyze_strategy(aggressive, data, "AGGRESSIVE STRATEGY")
    
    # Plot equity curves comparison
    plt.figure(figsize=(14, 8))
    
    plt.subplot(2, 1, 1)
    plt.plot(results_default['equity_curve'], label='Default', linewidth=2)
    if optimized_config:
        plt.plot(results_optimized['equity_curve'], label='Optimized', linewidth=2)
    plt.plot(results_conservative['equity_curve'], label='Conservative', linewidth=2)
    plt.plot(results_aggressive['equity_curve'], label='Aggressive', linewidth=2)
    plt.title('Equity Curves Comparison', fontsize=14, fontweight='bold')
    plt.xlabel('Trade Number')
    plt.ylabel('Balance ($)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Summary comparison
    plt.subplot(2, 1, 2)
    strategies = ['Default', 'Conservative', 'Aggressive']
    returns = [results_default['return_pct'], results_conservative['return_pct'], results_aggressive['return_pct']]
    if optimized_config:
        strategies.insert(1, 'Optimized')
        returns.insert(1, results_optimized['return_pct'])
    
    colors = ['blue', 'green', 'orange', 'red'][:len(strategies)]
    plt.bar(strategies, returns, color=colors, alpha=0.7)
    plt.title('Return Comparison', fontsize=14, fontweight='bold')
    plt.ylabel('Return (%)')
    plt.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('results/strategy_comparison.png', dpi=150)
    print(f"\n{'='*60}")
    print("Chart saved to: results/strategy_comparison.png")
    print(f"{'='*60}")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
