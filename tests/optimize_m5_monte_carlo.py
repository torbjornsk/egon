"""
Fast M5 optimization using Monte Carlo sampling
Tests on 10-20 random 14-day windows instead of full dataset
~10x faster with 90% confidence
"""
import json
from test_suite_monte_carlo import MonteCarloTestSuite
from itertools import product
import time

def optimize_m5_monte_carlo():
    print("="*100)
    print("M5 PARAMETER OPTIMIZATION (Monte Carlo Sampling)")
    print("="*100)
    
    suite = MonteCarloTestSuite()
    suite.print_confidence_table()
    
    # Load base config
    with open('config/m5_params.json', 'r') as f:
        base_config = json.load(f)
    
    print(f"\nCurrent config: RSI {base_config['rsi_buy']}/{base_config['rsi_sell']}, "
          f"Exit {base_config['rsi_exit_long']}/{base_config['rsi_exit_short']}, "
          f"TP {base_config['profit_target_pct']*100:.1f}%")
    
    # Define parameter ranges
    rsi_buy_values = [20, 25, 30, 35, 40]
    rsi_sell_values = [60, 65, 70, 75, 80]
    rsi_exit_long_values = [60, 65, 70, 75]
    rsi_exit_short_values = [25, 30, 35, 40]
    profit_target_values = [0.015, 0.020, 0.025, 0.030]
    
    combinations = list(product(
        rsi_buy_values,
        rsi_sell_values,
        rsi_exit_long_values,
        rsi_exit_short_values,
        profit_target_values
    ))
    
    # Monte Carlo settings
    n_samples = 15  # 15 samples = ~85% confidence
    window_days = 14  # 2-week windows
    test_period = 120  # Sample from last 120 days
    
    print(f"\nMonte Carlo Settings:")
    print(f"  Testing {len(combinations)} parameter combinations")
    print(f"  Sampling {n_samples} random {window_days}-day windows from {test_period}-day period")
    print(f"  Confidence level: ~85%")
    print(f"  Expected speedup: ~8-10x vs full dataset\n")
    
    start_time = time.time()
    results = []
    
    for i, (rsi_buy, rsi_sell, rsi_exit_long, rsi_exit_short, profit_target) in enumerate(combinations, 1):
        if rsi_buy >= rsi_sell or rsi_exit_short >= rsi_exit_long:
            continue
        
        test_config = base_config.copy()
        test_config['rsi_buy'] = rsi_buy
        test_config['rsi_sell'] = rsi_sell
        test_config['rsi_exit_long'] = rsi_exit_long
        test_config['rsi_exit_short'] = rsi_exit_short
        test_config['profit_target_pct'] = profit_target
        
        if i % 50 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed
            remaining = (len(combinations) - i) / rate
            print(f"Progress: {i}/{len(combinations)} ({i/len(combinations)*100:.1f}%) - "
                  f"ETA: {remaining/60:.1f} min")
        
        mc_results = suite.test_config_monte_carlo(
            test_config,
            timeframe='M5',
            period_days=test_period,
            window_days=window_days,
            n_samples=n_samples
        )
        
        if not mc_results:
            continue
        
        config_name = f"RSI {rsi_buy}/{rsi_sell}, Exit {rsi_exit_long}/{rsi_exit_short}, TP {profit_target*100:.1f}%"
        
        results.append({
            'config': test_config,
            'config_name': config_name,
            'mean_return': mc_results['mean_return'],
            'std_return': mc_results['std_return'],
            'mean_wr': mc_results['mean_win_rate'],
            'mean_pf': mc_results['mean_profit_factor'],
            'mean_sharpe': mc_results['mean_sharpe'],
            'consistency': 1 / (mc_results['std_return'] + 0.1),  # Lower std = more consistent
            'risk_adjusted': mc_results['mean_return'] * mc_results['mean_sharpe']
        })
    
    elapsed = time.time() - start_time
    print(f"\nCompleted {len(results)} configurations in {elapsed/60:.1f} minutes")
    print(f"Average: {elapsed/len(results):.2f} seconds per config")
    
    # Sort by different metrics
    by_return = sorted(results, key=lambda x: x['mean_return'], reverse=True)
    by_consistency = sorted(results, key=lambda x: x['consistency'], reverse=True)
    by_risk_adjusted = sorted(results, key=lambda x: x['risk_adjusted'], reverse=True)
    
    # Print results
    print("\n" + "="*100)
    print("TOP 10 BY MEAN RETURN")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Mean Ret':<12} {'Std':<10} {'WR':<8} {'PF':<8} {'Sharpe':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_return[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['mean_return']:>10.1f}% {r['std_return']:>8.1f}% "
              f"{r['mean_wr']:>6.1f}% {r['mean_pf']:>6.2f} {r['mean_sharpe']:>6.2f}")
    
    print("\n" + "="*100)
    print("TOP 10 BY CONSISTENCY (low variance)")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Mean Ret':<12} {'Std':<10} {'WR':<8} {'PF':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_consistency[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['mean_return']:>10.1f}% {r['std_return']:>8.1f}% "
              f"{r['mean_wr']:>6.1f}% {r['mean_pf']:>6.2f}")
    
    print("\n" + "="*100)
    print("TOP 10 BY RISK-ADJUSTED RETURN (return × sharpe)")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Score':<12} {'Return':<10} {'Sharpe':<8} {'WR':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_risk_adjusted[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['risk_adjusted']:>10.1f} {r['mean_return']:>8.1f}% "
              f"{r['mean_sharpe']:>6.2f} {r['mean_wr']:>6.1f}%")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    best = by_risk_adjusted[0]
    
    print(f"\nBest Configuration (Risk-Adjusted):")
    print(f"  {best['config_name']}")
    print(f"\nPerformance (Monte Carlo - {n_samples} samples):")
    print(f"  Mean Return: {best['mean_return']:.1f}% ± {best['std_return']:.1f}%")
    print(f"  Win Rate: {best['mean_wr']:.1f}%")
    print(f"  Profit Factor: {best['mean_pf']:.2f}")
    print(f"  Sharpe Ratio: {best['mean_sharpe']:.2f}")
    print(f"  Risk-Adjusted Score: {best['risk_adjusted']:.1f}")
    
    # Compare to current
    with open('tests/baseline_m5.json', 'r') as f:
        baseline = json.load(f)
    
    baseline_avg = sum(r['total_return'] for r in baseline['results'].values()) / len(baseline['results'])
    improvement = best['mean_return'] - baseline_avg
    
    print(f"\nComparison to Current Config:")
    print(f"  Current Average Return: {baseline_avg:.1f}%")
    print(f"  Optimized Mean Return: {best['mean_return']:.1f}%")
    print(f"  Improvement: {improvement:+.1f}%")
    
    if improvement > 2:
        print(f"\n✓ Recommended: Update config/m5_params.json")
        print(f"  Note: Run full test (tests/optimize_m5.py) to validate before deploying")
    elif improvement > 0:
        print(f"\n≈ Marginal improvement - current config is good")
    else:
        print(f"\n✓ Current config is optimal")
    
    # Save results
    with open('tests/m5_monte_carlo_results.json', 'w') as f:
        json.dump({
            'settings': {
                'n_samples': n_samples,
                'window_days': window_days,
                'test_period': test_period,
                'confidence': '~85%'
            },
            'top_10': [
                {
                    'config': r['config'],
                    'metrics': {
                        'mean_return': r['mean_return'],
                        'std_return': r['std_return'],
                        'mean_wr': r['mean_wr'],
                        'mean_pf': r['mean_pf'],
                        'mean_sharpe': r['mean_sharpe']
                    }
                } for r in by_risk_adjusted[:10]
            ],
            'best_config': best['config']
        }, f, indent=2)
    
    print(f"\nResults saved to: tests/m5_monte_carlo_results.json")
    print(f"Total time: {elapsed/60:.1f} minutes")

if __name__ == '__main__':
    optimize_m5_monte_carlo()
