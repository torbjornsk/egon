"""
Establish baseline performance for current M5 and M1 configurations
Save results to JSON for future comparison
"""
import json
from datetime import datetime
from test_suite import TestSuite

def save_baseline(results, config, filename):
    """Save baseline results to JSON"""
    baseline = {
        'timestamp': datetime.now().isoformat(),
        'config': config,
        'results': results
    }
    
    with open(filename, 'w') as f:
        json.dump(baseline, f, indent=2)
    
    print(f"Baseline saved to: {filename}")

def load_baseline(filename):
    """Load baseline results from JSON"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def print_results_table(results, config_name):
    """Print results in a formatted table"""
    print(f"\n{config_name} RESULTS:")
    print("="*90)
    print(f"{'Period':<15} {'Return':<12} {'Trades':<8} {'Win Rate':<10} {'PF':<8} {'Max DD':<10} {'Sharpe':<8}")
    print("-"*90)
    
    for period, metrics in results.items():
        print(f"{period:<15} {metrics['total_return']:>10.1f}% {metrics['total_trades']:>7} "
              f"{metrics['win_rate']:>8.1f}% {metrics['profit_factor']:>6.2f} "
              f"{metrics['max_drawdown']:>8.1f}% {metrics['sharpe']:>6.2f}")
    
    # Calculate averages
    avg_return = sum(m['total_return'] for m in results.values()) / len(results)
    avg_trades = sum(m['total_trades'] for m in results.values()) / len(results)
    avg_wr = sum(m['win_rate'] for m in results.values()) / len(results)
    avg_pf = sum(m['profit_factor'] for m in results.values()) / len(results)
    avg_dd = sum(m['max_drawdown'] for m in results.values()) / len(results)
    avg_sharpe = sum(m['sharpe'] for m in results.values()) / len(results)
    
    print("-"*90)
    print(f"{'AVERAGE':<15} {avg_return:>10.1f}% {avg_trades:>7.0f} "
          f"{avg_wr:>8.1f}% {avg_pf:>6.2f} {avg_dd:>8.1f}% {avg_sharpe:>6.2f}")
    print("="*90)

def main():
    print("="*90)
    print("ESTABLISHING BASELINE PERFORMANCE")
    print("="*90)
    
    # Initialize test suite
    suite = TestSuite()
    
    # Fetch and cache data
    print("\nFetching and caching data...")
    suite.fetch_and_cache_data(force_refresh=False)
    
    # Load current configurations
    print("\nLoading configurations...")
    with open('config/m5_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_params.json', 'r') as f:
        m1_config = json.load(f)
    
    print(f"\nM5 Config: RSI {m5_config['rsi_buy']}/{m5_config['rsi_sell']}, "
          f"Exit {m5_config['rsi_exit_long']}/{m5_config['rsi_exit_short']}, "
          f"TP {m5_config['profit_target_pct']*100:.1f}%")
    
    print(f"M1 Config: RSI {m1_config['rsi_buy']}/{m1_config['rsi_sell']}, "
          f"Exit {m1_config['rsi_exit_long']}/{m1_config['rsi_exit_short']}, "
          f"TP {m1_config['profit_target_pct']*100:.1f}%")
    
    # Test M5
    print("\n" + "="*90)
    print("TESTING M5 CONFIGURATION")
    print("="*90)
    m5_results = suite.test_config('M5 Baseline', m5_config, timeframe='M5')
    print_results_table(m5_results, 'M5')
    
    # Save M5 baseline
    save_baseline(m5_results, m5_config, 'tests/baseline_m5.json')
    
    # Test M1
    print("\n" + "="*90)
    print("TESTING M1 CONFIGURATION")
    print("="*90)
    m1_results = suite.test_config('M1 Baseline', m1_config, timeframe='M1')
    print_results_table(m1_results, 'M1')
    
    # Save M1 baseline
    save_baseline(m1_results, m1_config, 'tests/baseline_m1.json')
    
    # Summary
    print("\n" + "="*90)
    print("BASELINE ESTABLISHED")
    print("="*90)
    print("\nBaseline files created:")
    print("  - tests/baseline_m5.json")
    print("  - tests/baseline_m1.json")
    print("\nYou can now:")
    print("  1. Modify parameters in config files")
    print("  2. Run tests/compare_to_baseline.py to see improvements/regressions")
    print("  3. Commit baseline files to git for version control")

if __name__ == '__main__':
    main()
