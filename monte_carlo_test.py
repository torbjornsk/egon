"""
Monte Carlo Walk-Forward Analysis
Tests strategy on 1000 random time periods of varying lengths
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
import random

# Import the safe leveraged backtest function
exec(open('safe_leveraged_strategy.py').read().split('def main()')[0])

def monte_carlo_test(data, config, num_tests=1000, min_days=14, max_days=90):
    """
    Test strategy on random time periods of varying lengths
    
    Args:
        data: Full dataset
        config: Strategy configuration
        num_tests: Number of random periods to test
        min_days: Minimum period length in days
        max_days: Maximum period length in days
    """
    
    results = []
    
    # Get date range
    start_date = data['time'].min()
    end_date = data['time'].max()
    total_days = (end_date - start_date).days
    
    print(f"Monte Carlo Testing: {num_tests} random periods")
    print(f"Period lengths: {min_days} to {max_days} days")
    print(f"Total data span: {total_days} days")
    print()
    
    for test_num in range(1, num_tests + 1):
        # Random period length
        period_days = random.randint(min_days, max_days)
        
        # Random start date (ensure we have enough data for the period)
        max_start_day = total_days - period_days
        if max_start_day <= 0:
            continue
            
        random_start_day = random.randint(0, max_start_day)
        period_start = start_date + timedelta(days=random_start_day)
        period_end = period_start + timedelta(days=period_days)
        
        # Filter data for this period
        period_data = data[(data['time'] >= period_start) & (data['time'] < period_end)].copy()
        
        if len(period_data) < 50:
            continue
        
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
                'test': test_num,
                'period_days': period_days,
                'start_date': period_start,
                'end_date': period_end,
                'balance': balance,
                'return': return_pct,
                'trades': len(trades),
                'win_rate': len(winning) / len(trades) * 100,
                'max_dd': max_dd * 100,
                'paused': paused
            }
            
            results.append(result)
            
            if test_num % 100 == 0:
                print(f"Completed {test_num}/{num_tests} tests...")
    
    return results

def analyze_monte_carlo_results(results):
    """Analyze Monte Carlo test results"""
    
    if not results:
        print("No results to analyze")
        return
    
    returns = [r['return'] for r in results]
    drawdowns = [abs(r['max_dd']) for r in results]
    win_rates = [r['win_rate'] for r in results]
    period_lengths = [r['period_days'] for r in results]
    
    print("\n" + "="*80)
    print("MONTE CARLO ANALYSIS SUMMARY")
    print("="*80)
    print(f"Total Tests Completed: {len(results)}")
    print()
    
    print("RETURNS:")
    print(f"  Average:     {np.mean(returns):>7.2f}%")
    print(f"  Median:      {np.median(returns):>7.2f}%")
    print(f"  Std Dev:     {np.std(returns):>7.2f}%")
    print(f"  Min:         {np.min(returns):>7.2f}%")
    print(f"  Max:         {np.max(returns):>7.2f}%")
    print(f"  25th %ile:   {np.percentile(returns, 25):>7.2f}%")
    print(f"  75th %ile:   {np.percentile(returns, 75):>7.2f}%")
    print(f"  Positive:    {sum(1 for r in returns if r > 0)}/{len(returns)} ({sum(1 for r in returns if r > 0)/len(returns)*100:.1f}%)")
    print()
    
    print("MAX DRAWDOWN:")
    print(f"  Average:     {np.mean(drawdowns):>7.2f}%")
    print(f"  Median:      {np.median(drawdowns):>7.2f}%")
    print(f"  Worst:       {np.max(drawdowns):>7.2f}%")
    print(f"  Best:        {np.min(drawdowns):>7.2f}%")
    print(f"  95th %ile:   {np.percentile(drawdowns, 95):>7.2f}%")
    print()
    
    print("WIN RATE:")
    print(f"  Average:     {np.mean(win_rates):>7.2f}%")
    print(f"  Median:      {np.median(win_rates):>7.2f}%")
    print(f"  Range:       {np.min(win_rates):.1f}% - {np.max(win_rates):.1f}%")
    print()
    
    print("PERIOD LENGTHS:")
    print(f"  Average:     {np.mean(period_lengths):>7.1f} days")
    print(f"  Median:      {np.median(period_lengths):>7.1f} days")
    print(f"  Range:       {np.min(period_lengths):.0f} - {np.max(period_lengths):.0f} days")
    print()
    
    # Consistency metrics
    positive_periods = sum(1 for r in returns if r > 0)
    consistency = positive_periods / len(results) * 100
    
    print("CONSISTENCY:")
    print(f"  Profitable Periods: {positive_periods}/{len(results)} ({consistency:.1f}%)")
    
    # Risk-adjusted return
    sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
    print(f"  Sharpe-like Ratio:  {sharpe:.2f}")
    
    # Analyze by period length
    print("\nRETURNS BY PERIOD LENGTH:")
    for days in [14, 30, 60, 90]:
        period_results = [r['return'] for r in results if abs(r['period_days'] - days) <= 3]
        if period_results:
            print(f"  ~{days} days: {np.mean(period_results):>6.2f}% avg, {np.median(period_results):>6.2f}% median ({len(period_results)} samples)")
    
    # Worst and best cases
    worst = min(results, key=lambda x: x['return'])
    best = max(results, key=lambda x: x['return'])
    
    print(f"\nWORST CASE:")
    print(f"  Period: {worst['period_days']} days ({worst['start_date'].strftime('%Y-%m-%d')} to {worst['end_date'].strftime('%Y-%m-%d')})")
    print(f"  Return: {worst['return']:.2f}%")
    print(f"  Max DD: {abs(worst['max_dd']):.2f}%")
    print(f"  Trades: {worst['trades']}")
    
    print(f"\nBEST CASE:")
    print(f"  Period: {best['period_days']} days ({best['start_date'].strftime('%Y-%m-%d')} to {best['end_date'].strftime('%Y-%m-%d')})")
    print(f"  Return: {best['return']:.2f}%")
    print(f"  Max DD: {abs(best['max_dd']):.2f}%")
    print(f"  Trades: {best['trades']}")

def plot_monte_carlo_results(results):
    """Plot Monte Carlo test results"""
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    
    returns = [r['return'] for r in results]
    drawdowns = [abs(r['max_dd']) for r in results]
    win_rates = [r['win_rate'] for r in results]
    period_lengths = [r['period_days'] for r in results]
    
    # Return distribution
    ax = axes[0, 0]
    ax.hist(returns, bins=50, alpha=0.7, color='blue', edgecolor='black')
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
    ax.axvline(x=np.mean(returns), color='green', linestyle='--', linewidth=2, label=f'Mean: {np.mean(returns):.1f}%')
    ax.axvline(x=np.median(returns), color='orange', linestyle='--', linewidth=2, label=f'Median: {np.median(returns):.1f}%')
    ax.set_title('Return Distribution', fontsize=14, fontweight='bold')
    ax.set_xlabel('Return (%)')
    ax.set_ylabel('Frequency')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Drawdown distribution
    ax = axes[0, 1]
    ax.hist(drawdowns, bins=50, alpha=0.7, color='red', edgecolor='black')
    ax.axvline(x=np.mean(drawdowns), color='blue', linestyle='--', linewidth=2, label=f'Mean: {np.mean(drawdowns):.1f}%')
    ax.axvline(x=np.median(drawdowns), color='green', linestyle='--', linewidth=2, label=f'Median: {np.median(drawdowns):.1f}%')
    ax.set_title('Max Drawdown Distribution', fontsize=14, fontweight='bold')
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('Frequency')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Win rate distribution
    ax = axes[0, 2]
    ax.hist(win_rates, bins=30, alpha=0.7, color='green', edgecolor='black')
    ax.axvline(x=np.mean(win_rates), color='blue', linestyle='--', linewidth=2, label=f'Mean: {np.mean(win_rates):.1f}%')
    ax.set_title('Win Rate Distribution', fontsize=14, fontweight='bold')
    ax.set_xlabel('Win Rate (%)')
    ax.set_ylabel('Frequency')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Return vs Period Length
    ax = axes[1, 0]
    scatter = ax.scatter(period_lengths, returns, c=returns, cmap='RdYlGn', s=20, alpha=0.5)
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax.set_title('Return vs Period Length', fontsize=14, fontweight='bold')
    ax.set_xlabel('Period Length (days)')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax, label='Return (%)')
    
    # Return vs Drawdown
    ax = axes[1, 1]
    scatter = ax.scatter(drawdowns, returns, c=win_rates, cmap='viridis', s=20, alpha=0.5)
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax.set_title('Return vs Drawdown', fontsize=14, fontweight='bold')
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax, label='Win Rate (%)')
    
    # Cumulative probability
    ax = axes[1, 2]
    sorted_returns = np.sort(returns)
    cumulative_prob = np.arange(1, len(sorted_returns) + 1) / len(sorted_returns) * 100
    ax.plot(sorted_returns, cumulative_prob, linewidth=2, color='blue')
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
    ax.axhline(y=50, color='green', linestyle='--', alpha=0.5)
    ax.set_title('Cumulative Probability', fontsize=14, fontweight='bold')
    ax.set_xlabel('Return (%)')
    ax.set_ylabel('Probability (%)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('results/monte_carlo_analysis.png', dpi=150)
    print(f"\nChart saved to: results/monte_carlo_analysis.png")

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
    
    # Run Monte Carlo test
    results = monte_carlo_test(data, config, num_tests=1000, min_days=14, max_days=90)
    
    # Analyze results
    analyze_monte_carlo_results(results)
    
    # Plot results
    plot_monte_carlo_results(results)
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
