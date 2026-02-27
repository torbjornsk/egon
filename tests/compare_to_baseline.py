"""
Compare current configuration performance against baseline
Shows improvements/regressions clearly
"""
import json
from datetime import datetime
from test_suite import TestSuite

def load_baseline(filename):
    """Load baseline results from JSON"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Baseline file not found: {filename}")
        print("Run tests/establish_baseline.py first to create baseline.")
        return None

def compare_metrics(current, baseline, metric_name):
    """Compare a metric and return difference with color coding"""
    curr_val = current[metric_name]
    base_val = baseline[metric_name]
    diff = curr_val - base_val
    
    # Determine if improvement (depends on metric)
    if metric_name == 'max_drawdown':
        # Lower is better for drawdown
        improved = diff > 0  # Less negative is better
    else:
        # Higher is better for other metrics
        improved = diff > 0
    
    symbol = "↑" if improved else "↓"
    return diff, symbol

def print_comparison(current_results, baseline_data, config_name):
    """Print detailed comparison"""
    baseline_results = baseline_data['results']
    baseline_config = baseline_data['config']
    baseline_time = baseline_data['timestamp']
    
    print(f"\n{config_name} COMPARISON")
    print("="*110)
    print(f"Baseline established: {baseline_time}")
    print(f"\nBaseline config: RSI {baseline_config['rsi_buy']}/{baseline_config['rsi_sell']}, "
          f"Exit {baseline_config['rsi_exit_long']}/{baseline_config['rsi_exit_short']}, "
          f"TP {baseline_config['profit_target_pct']*100:.1f}%")
    print("="*110)
    
    print(f"\n{'Period':<15} {'Metric':<12} {'Baseline':<12} {'Current':<12} {'Diff':<12} {'Status':<8}")
    print("-"*110)
    
    for period in baseline_results.keys():
        if period not in current_results:
            print(f"{period:<15} {'N/A':<12} {'N/A':<12} {'N/A':<12} {'N/A':<12} {'N/A':<8}")
            continue
        
        curr = current_results[period]
        base = baseline_results[period]
        
        # Return
        diff, symbol = compare_metrics(curr, base, 'total_return')
        print(f"{period:<15} {'Return':<12} {base['total_return']:>10.1f}% {curr['total_return']:>10.1f}% "
              f"{diff:>+9.1f}% {symbol:<8}")
        
        # Trades
        diff = curr['total_trades'] - base['total_trades']
        symbol = "↑" if diff > 0 else "↓"
        print(f"{'':15} {'Trades':<12} {base['total_trades']:>11} {curr['total_trades']:>11} "
              f"{diff:>+10} {symbol:<8}")
        
        # Win Rate
        diff, symbol = compare_metrics(curr, base, 'win_rate')
        print(f"{'':15} {'Win Rate':<12} {base['win_rate']:>10.1f}% {curr['win_rate']:>10.1f}% "
              f"{diff:>+9.1f}% {symbol:<8}")
        
        # Profit Factor
        diff, symbol = compare_metrics(curr, base, 'profit_factor')
        print(f"{'':15} {'Profit Factor':<12} {base['profit_factor']:>11.2f} {curr['profit_factor']:>11.2f} "
              f"{diff:>+10.2f} {symbol:<8}")
        
        # Max Drawdown
        diff, symbol = compare_metrics(curr, base, 'max_drawdown')
        print(f"{'':15} {'Max DD':<12} {base['max_drawdown']:>10.1f}% {curr['max_drawdown']:>10.1f}% "
              f"{diff:>+9.1f}% {symbol:<8}")
        
        # Sharpe
        diff, symbol = compare_metrics(curr, base, 'sharpe')
        print(f"{'':15} {'Sharpe':<12} {base['sharpe']:>11.2f} {curr['sharpe']:>11.2f} "
              f"{diff:>+10.2f} {symbol:<8}")
        
        print("-"*110)
    
    # Overall summary
    print("\nOVERALL SUMMARY:")
    
    # Calculate average improvements
    return_diffs = []
    trade_diffs = []
    wr_diffs = []
    
    for period in baseline_results.keys():
        if period in current_results:
            return_diffs.append(current_results[period]['total_return'] - baseline_results[period]['total_return'])
            trade_diffs.append(current_results[period]['total_trades'] - baseline_results[period]['total_trades'])
            wr_diffs.append(current_results[period]['win_rate'] - baseline_results[period]['win_rate'])
    
    avg_return_diff = sum(return_diffs) / len(return_diffs) if return_diffs else 0
    avg_trade_diff = sum(trade_diffs) / len(trade_diffs) if trade_diffs else 0
    avg_wr_diff = sum(wr_diffs) / len(wr_diffs) if wr_diffs else 0
    
    print(f"  Average Return Change: {avg_return_diff:+.1f}%")
    print(f"  Average Trade Count Change: {avg_trade_diff:+.0f}")
    print(f"  Average Win Rate Change: {avg_wr_diff:+.1f}%")
    
    if avg_return_diff > 0:
        print(f"\n✓ Configuration shows improvement over baseline!")
    elif avg_return_diff < -5:
        print(f"\n✗ Configuration shows significant regression from baseline")
    else:
        print(f"\n≈ Configuration shows similar performance to baseline")
    
    print("="*110)

def main():
    print("="*110)
    print("COMPARING CURRENT CONFIGURATION TO BASELINE")
    print("="*110)
    
    # Initialize test suite
    suite = TestSuite()
    
    # Load current configurations
    print("\nLoading current configurations...")
    with open('config/m5_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_params.json', 'r') as f:
        m1_config = json.load(f)
    
    print(f"\nCurrent M5: RSI {m5_config['rsi_buy']}/{m5_config['rsi_sell']}, "
          f"Exit {m5_config['rsi_exit_long']}/{m5_config['rsi_exit_short']}, "
          f"TP {m5_config['profit_target_pct']*100:.1f}%")
    
    print(f"Current M1: RSI {m1_config['rsi_buy']}/{m1_config['rsi_sell']}, "
          f"Exit {m1_config['rsi_exit_long']}/{m1_config['rsi_exit_short']}, "
          f"TP {m1_config['profit_target_pct']*100:.1f}%")
    
    # Test M5
    print("\n" + "="*110)
    print("TESTING M5")
    print("="*110)
    
    baseline_m5 = load_baseline('tests/baseline_m5.json')
    if baseline_m5:
        m5_results = suite.test_config('Current M5', m5_config, timeframe='M5')
        print_comparison(m5_results, baseline_m5, 'M5')
    
    # Test M1
    print("\n" + "="*110)
    print("TESTING M1")
    print("="*110)
    
    baseline_m1 = load_baseline('tests/baseline_m1.json')
    if baseline_m1:
        m1_results = suite.test_config('Current M1', m1_config, timeframe='M1')
        print_comparison(m1_results, baseline_m1, 'M1')

if __name__ == '__main__':
    main()
