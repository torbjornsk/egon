"""
Optimize M1 parameters using the test suite
Tests multiple parameter combinations and ranks by performance
"""
import json
from test_suite import TestSuite
from itertools import product

def optimize_m1():
    print("="*100)
    print("M1 PARAMETER OPTIMIZATION")
    print("="*100)
    
    # Initialize test suite
    suite = TestSuite()
    
    # Load base config
    with open('config/m1_params.json', 'r') as f:
        base_config = json.load(f)
    
    print(f"\nCurrent config: RSI {base_config['rsi_buy']}/{base_config['rsi_sell']}, "
          f"Exit {base_config['rsi_exit_long']}/{base_config['rsi_exit_short']}, "
          f"TP {base_config['profit_target_pct']*100:.1f}%")
    
    # Define parameter ranges to test (M1 typically uses tighter ranges)
    rsi_buy_values = [25, 30, 35, 40, 45]
    rsi_sell_values = [55, 60, 65, 70, 75]
    rsi_exit_long_values = [65, 70, 75, 80]
    rsi_exit_short_values = [20, 25, 30, 35]
    profit_target_values = [0.005, 0.006, 0.007, 0.008, 0.009, 0.010]
    
    # Generate all combinations
    combinations = list(product(
        rsi_buy_values,
        rsi_sell_values,
        rsi_exit_long_values,
        rsi_exit_short_values,
        profit_target_values
    ))
    
    print(f"\nTesting {len(combinations)} parameter combinations...")
    print("This will take several minutes (M1 has more data)...\n")
    
    results = []
    
    for i, (rsi_buy, rsi_sell, rsi_exit_long, rsi_exit_short, profit_target) in enumerate(combinations, 1):
        # Skip invalid combinations
        if rsi_buy >= rsi_sell:
            continue
        if rsi_exit_short >= rsi_exit_long:
            continue
        
        # Create test config
        test_config = base_config.copy()
        test_config['rsi_buy'] = rsi_buy
        test_config['rsi_sell'] = rsi_sell
        test_config['rsi_exit_long'] = rsi_exit_long
        test_config['rsi_exit_short'] = rsi_exit_short
        test_config['profit_target_pct'] = profit_target
        
        # Test configuration
        config_name = f"RSI {rsi_buy}/{rsi_sell}, Exit {rsi_exit_long}/{rsi_exit_short}, TP {profit_target*100:.1f}%"
        
        if i % 100 == 0:
            print(f"Progress: {i}/{len(combinations)} ({i/len(combinations)*100:.1f}%)")
        
        period_results = suite.test_config(config_name, test_config, timeframe='M1', use_cache=True)
        
        if not period_results:
            continue
        
        # Calculate aggregate metrics
        avg_return = sum(r['total_return'] for r in period_results.values()) / len(period_results)
        avg_trades = sum(r['total_trades'] for r in period_results.values()) / len(period_results)
        avg_wr = sum(r['win_rate'] for r in period_results.values()) / len(period_results)
        avg_pf = sum(r['profit_factor'] for r in period_results.values()) / len(period_results)
        avg_dd = sum(r['max_drawdown'] for r in period_results.values()) / len(period_results)
        avg_sharpe = sum(r['sharpe'] for r in period_results.values()) / len(period_results)
        
        # Focus on recent performance (weighted average)
        if 'recent_30d' in period_results and 'recent_60d' in period_results:
            recent_return = (period_results['recent_30d']['total_return'] * 2 + 
                           period_results['recent_60d']['total_return']) / 3
        else:
            recent_return = avg_return
        
        # Calculate risk-adjusted score (balance return with risk)
        risk_adjusted_score = avg_return * avg_sharpe / max(abs(avg_dd), 1)
        
        results.append({
            'config': test_config,
            'config_name': config_name,
            'avg_return': avg_return,
            'recent_return': recent_return,
            'avg_trades': avg_trades,
            'avg_wr': avg_wr,
            'avg_pf': avg_pf,
            'avg_dd': avg_dd,
            'avg_sharpe': avg_sharpe,
            'risk_adjusted_score': risk_adjusted_score,
            'period_results': period_results
        })
    
    print(f"\nCompleted testing {len(results)} valid configurations")
    
    # Sort by different metrics
    by_avg_return = sorted(results, key=lambda x: x['avg_return'], reverse=True)
    by_recent_return = sorted(results, key=lambda x: x['recent_return'], reverse=True)
    by_sharpe = sorted(results, key=lambda x: x['avg_sharpe'], reverse=True)
    by_risk_adjusted = sorted(results, key=lambda x: x['risk_adjusted_score'], reverse=True)
    
    # Print top results
    print("\n" + "="*100)
    print("TOP 10 BY AVERAGE RETURN")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Avg Ret':<10} {'Recent':<10} {'Trades':<8} {'WR':<8} {'PF':<8} {'Sharpe':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_avg_return[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['avg_return']:>8.1f}% {r['recent_return']:>8.1f}% "
              f"{r['avg_trades']:>7.0f} {r['avg_wr']:>6.1f}% {r['avg_pf']:>6.2f} {r['avg_sharpe']:>6.2f}")
    
    print("\n" + "="*100)
    print("TOP 10 BY RECENT PERFORMANCE (30d + 60d weighted)")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Recent':<10} {'Avg Ret':<10} {'Trades':<8} {'WR':<8} {'PF':<8} {'Sharpe':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_recent_return[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['recent_return']:>8.1f}% {r['avg_return']:>8.1f}% "
              f"{r['avg_trades']:>7.0f} {r['avg_wr']:>6.1f}% {r['avg_pf']:>6.2f} {r['avg_sharpe']:>6.2f}")
    
    print("\n" + "="*100)
    print("TOP 10 BY SHARPE RATIO (risk-adjusted return)")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Sharpe':<10} {'Avg Ret':<10} {'Trades':<8} {'WR':<8} {'PF':<8} {'Max DD':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_sharpe[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['avg_sharpe']:>8.2f} {r['avg_return']:>8.1f}% "
              f"{r['avg_trades']:>7.0f} {r['avg_wr']:>6.1f}% {r['avg_pf']:>6.2f} {r['avg_dd']:>6.1f}%")
    
    print("\n" + "="*100)
    print("TOP 10 BY RISK-ADJUSTED SCORE (return * sharpe / drawdown)")
    print("="*100)
    print(f"{'Rank':<6} {'Config':<45} {'Score':<10} {'Ret':<10} {'Sharpe':<8} {'DD':<8} {'WR':<8}")
    print("-"*100)
    
    for i, r in enumerate(by_risk_adjusted[:10], 1):
        print(f"{i:<6} {r['config_name']:<45} {r['risk_adjusted_score']:>8.1f} {r['avg_return']:>8.1f}% "
              f"{r['avg_sharpe']:>6.2f} {r['avg_dd']:>6.1f}% {r['avg_wr']:>6.1f}%")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    # Use risk-adjusted score for M1 (more important to manage risk with high-frequency trading)
    best = by_risk_adjusted[0]
    
    print(f"\nBest Overall Configuration (Risk-Adjusted):")
    print(f"  {best['config_name']}")
    print(f"\nPerformance:")
    print(f"  Average Return: {best['avg_return']:.1f}%")
    print(f"  Recent Return: {best['recent_return']:.1f}%")
    print(f"  Average Trades: {best['avg_trades']:.0f}")
    print(f"  Win Rate: {best['avg_wr']:.1f}%")
    print(f"  Profit Factor: {best['avg_pf']:.2f}")
    print(f"  Max Drawdown: {best['avg_dd']:.1f}%")
    print(f"  Sharpe Ratio: {best['avg_sharpe']:.2f}")
    print(f"  Risk-Adjusted Score: {best['risk_adjusted_score']:.1f}")
    
    print(f"\nPeriod Breakdown:")
    for period, metrics in best['period_results'].items():
        print(f"  {period:<15}: {metrics['total_return']:>6.1f}% ({metrics['total_trades']} trades, {metrics['win_rate']:.1f}% WR)")
    
    # Compare to current
    with open('tests/baseline_m1.json', 'r') as f:
        baseline = json.load(f)
    
    baseline_avg = sum(r['total_return'] for r in baseline['results'].values()) / len(baseline['results'])
    improvement = best['avg_return'] - baseline_avg
    
    print(f"\nComparison to Current Config:")
    print(f"  Current Average Return: {baseline_avg:.1f}%")
    print(f"  Optimized Average Return: {best['avg_return']:.1f}%")
    print(f"  Improvement: {improvement:+.1f}%")
    
    if improvement > 5:
        print(f"\n✓ Recommended: Update config/m1_params.json with optimized parameters")
    elif improvement > 0:
        print(f"\n≈ Marginal improvement - current config is already good")
    else:
        print(f"\n✓ Current config is optimal - no changes needed")
    
    # Save detailed results
    with open('tests/m1_optimization_results.json', 'w') as f:
        json.dump({
            'top_10_by_return': [
                {
                    'config': r['config'],
                    'metrics': {
                        'avg_return': r['avg_return'],
                        'recent_return': r['recent_return'],
                        'avg_trades': r['avg_trades'],
                        'avg_wr': r['avg_wr'],
                        'avg_pf': r['avg_pf'],
                        'avg_sharpe': r['avg_sharpe'],
                        'risk_adjusted_score': r['risk_adjusted_score']
                    }
                } for r in by_avg_return[:10]
            ],
            'top_10_by_risk_adjusted': [
                {
                    'config': r['config'],
                    'metrics': {
                        'avg_return': r['avg_return'],
                        'recent_return': r['recent_return'],
                        'avg_trades': r['avg_trades'],
                        'avg_wr': r['avg_wr'],
                        'avg_pf': r['avg_pf'],
                        'avg_sharpe': r['avg_sharpe'],
                        'risk_adjusted_score': r['risk_adjusted_score']
                    }
                } for r in by_risk_adjusted[:10]
            ],
            'best_config': best['config']
        }, f, indent=2)
    
    print(f"\nDetailed results saved to: tests/m1_optimization_results.json")

if __name__ == '__main__':
    optimize_m1()
