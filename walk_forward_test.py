"""
Walk-Forward Analysis
Tests the strategy on multiple time periods to validate robustness
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

# Import the safe leveraged backtest function
exec(open('safe_leveraged_strategy.py').read().split('def main()')[0])

def test_multiple_periods(data, config, period_days=90, step_days=30):
    """
    Test strategy on multiple rolling periods
    
    Args:
        data: Full dataset
        config: Strategy configuration
        period_days: Length of each test period
        step_days: Days to step forward between tests
    """
    
    results = []
    
    # Get date range
    start_date = data['time'].min()
    end_date = data['time'].max()
    total_days = (end_date - start_date).days
    
    print(f"Testing strategy on rolling {period_days}-day periods")
    print(f"Total data span: {total_days} days")
    print(f"Step size: {step_days} days")
    print()
    
    current_start = start_date
    period_num = 1
    
    while current_start + timedelta(days=period_days) <= end_date:
        current_end = current_start + timedelta(days=period_days)
        
        # Filter data for this period
        period_data = data[(data['time'] >= current_start) & (data['time'] < current_end)].copy()
        
        if len(period_data) < 100:
            current_start += timedelta(days=step_days)
            continue
        
        print(f"Period {period_num}: {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")
        
        # Run backtest
        balance, trades, equity, paused = run_safe_leveraged_backtest(
            period_data,
            capital=1000,
            position_size_pct=config['position_size_pct'],
            leverage=config['leverage'],
            fast_ema=config['fast_ema'],
            slow_ema=config['slow_ema'],
            rsi_period=config['rsi_period'],
            rsi_buy=config['rsi_buy'],
            rsi_sell=config['rsi_sell'],
            atr_multiplier=config['atr_multiplier'],
            profit_target_pct=config['profit_target_pct'],
            max_drawdown_limit=config['max_drawdown_limit'],
            enable_shorts=config['enable_shorts']
        )
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            
            equity_series = pd.Series(equity)
            running_max = equity_series.expanding().max()
            drawdown = (equity_series - running_max) / running_max
            max_dd = drawdown.min()
            
            return_pct = (balance / 1000 - 1) * 100
            
            result = {
                'period': period_num,
                'start_date': current_start,
                'end_date': current_end,
                'balance': balance,
                'return': return_pct,
                'trades': len(trades),
                'win_rate': len(winning) / len(trades) * 100,
                'max_dd': max_dd * 100,
                'paused': paused,
                'equity': equity
            }
            
            results.append(result)
            
            print(f"  Return: {return_pct:>7.2f}%  |  Trades: {len(trades):>4}  |  Win Rate: {result['win_rate']:>5.1f}%  |  Max DD: {abs(max_dd)*100:>5.1f}%  |  Paused: {'Yes' if paused else 'No'}")
        else:
            print(f"  No trades")
        
        current_start += timedelta(days=step_days)
        period_num += 1
    
    return results

def analyze_results(results):
    """Analyze walk-forward test results"""
    
    if not results:
        print("No results to analyze")
        return
    
    returns = [r['return'] for r in results]
    drawdowns = [abs(r['max_dd']) for r in results]
    win_rates = [r['win_rate'] for r in results]
    trade_counts = [r['trades'] for r in results]
    
    print("\n" + "="*80)
    print("WALK-FORWARD ANALYSIS SUMMARY")
    print("="*80)
    print(f"Total Periods Tested: {len(results)}")
    print()
    
    print("RETURNS:")
    print(f"  Average:  {np.mean(returns):>7.2f}%")
    print(f"  Median:   {np.median(returns):>7.2f}%")
    print(f"  Std Dev:  {np.std(returns):>7.2f}%")
    print(f"  Min:      {np.min(returns):>7.2f}%")
    print(f"  Max:      {np.max(returns):>7.2f}%")
    print(f"  Positive: {sum(1 for r in returns if r > 0)}/{len(returns)} ({sum(1 for r in returns if r > 0)/len(returns)*100:.1f}%)")
    print()
    
    print("MAX DRAWDOWN:")
    print(f"  Average:  {np.mean(drawdowns):>7.2f}%")
    print(f"  Median:   {np.median(drawdowns):>7.2f}%")
    print(f"  Worst:    {np.max(drawdowns):>7.2f}%")
    print(f"  Best:     {np.min(drawdowns):>7.2f}%")
    print()
    
    print("WIN RATE:")
    print(f"  Average:  {np.mean(win_rates):>7.2f}%")
    print(f"  Median:   {np.median(win_rates):>7.2f}%")
    print(f"  Range:    {np.min(win_rates):.1f}% - {np.max(win_rates):.1f}%")
    print()
    
    print("TRADES PER PERIOD:")
    print(f"  Average:  {np.mean(trade_counts):>7.0f}")
    print(f"  Median:   {np.median(trade_counts):>7.0f}")
    print(f"  Range:    {np.min(trade_counts):.0f} - {np.max(trade_counts):.0f}")
    print()
    
    # Consistency metrics
    positive_periods = sum(1 for r in returns if r > 0)
    consistency = positive_periods / len(results) * 100
    
    print("CONSISTENCY:")
    print(f"  Profitable Periods: {positive_periods}/{len(results)} ({consistency:.1f}%)")
    
    # Risk-adjusted return
    sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
    print(f"  Sharpe-like Ratio:  {sharpe:.2f}")
    
    # Worst case scenario
    worst_period = min(results, key=lambda x: x['return'])
    print(f"\nWORST PERIOD:")
    print(f"  Date: {worst_period['start_date'].strftime('%Y-%m-%d')} to {worst_period['end_date'].strftime('%Y-%m-%d')}")
    print(f"  Return: {worst_period['return']:.2f}%")
    print(f"  Max DD: {abs(worst_period['max_dd']):.2f}%")
    
    # Best case scenario
    best_period = max(results, key=lambda x: x['return'])
    print(f"\nBEST PERIOD:")
    print(f"  Date: {best_period['start_date'].strftime('%Y-%m-%d')} to {best_period['end_date'].strftime('%Y-%m-%d')}")
    print(f"  Return: {best_period['return']:.2f}%")
    print(f"  Max DD: {abs(best_period['max_dd']):.2f}%")

def plot_results(results):
    """Plot walk-forward test results"""
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Returns over time
    ax = axes[0, 0]
    dates = [r['start_date'] for r in results]
    returns = [r['return'] for r in results]
    colors = ['green' if r > 0 else 'red' for r in returns]
    ax.bar(range(len(returns)), returns, color=colors, alpha=0.7)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_title('Returns by Period', fontsize=14, fontweight='bold')
    ax.set_xlabel('Period Number')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Cumulative returns
    ax = axes[0, 1]
    cumulative = np.cumprod([1 + r/100 for r in returns]) * 1000 - 1000
    ax.plot(cumulative, linewidth=2, color='blue')
    ax.set_title('Cumulative Profit', fontsize=14, fontweight='bold')
    ax.set_xlabel('Period Number')
    ax.set_ylabel('Cumulative Profit ($)')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    
    # Return distribution
    ax = axes[1, 0]
    ax.hist(returns, bins=20, alpha=0.7, color='blue', edgecolor='black')
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
    ax.axvline(x=np.mean(returns), color='green', linestyle='--', linewidth=2, label=f'Mean: {np.mean(returns):.1f}%')
    ax.set_title('Return Distribution', fontsize=14, fontweight='bold')
    ax.set_xlabel('Return (%)')
    ax.set_ylabel('Frequency')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Win rate vs Return scatter
    ax = axes[1, 1]
    win_rates = [r['win_rate'] for r in results]
    scatter = ax.scatter(win_rates, returns, c=returns, cmap='RdYlGn', s=100, alpha=0.6, edgecolors='black')
    ax.set_title('Win Rate vs Return', fontsize=14, fontweight='bold')
    ax.set_xlabel('Win Rate (%)')
    ax.set_ylabel('Return (%)')
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax, label='Return (%)')
    
    plt.tight_layout()
    plt.savefig('results/walk_forward_analysis.png', dpi=150)
    print(f"\nChart saved to: results/walk_forward_analysis.png")

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
    
    # Load configuration
    with open('config/safe_leveraged_params.json', 'r') as f:
        config = json.load(f)
    
    print("Testing configuration:")
    print(f"  Position Size: {config['position_size_pct']*100}%")
    print(f"  Leverage: {config['leverage']}x")
    print(f"  Effective: {config['position_size_pct']*config['leverage']*100}%")
    print()
    
    # Run walk-forward test
    results = test_multiple_periods(data, config, period_days=30, step_days=7)
    
    # Analyze results
    analyze_results(results)
    
    # Plot results
    plot_results(results)
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
