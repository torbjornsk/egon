"""
Profile performance to identify bottlenecks
Shows exactly where time is spent
"""
import json
import time
import cProfile
import pstats
from io import StringIO
from test_suite_monte_carlo import MonteCarloTestSuite

def profile_single_test():
    """Profile a single Monte Carlo test with detailed timing"""
    print("="*80)
    print("PERFORMANCE PROFILING")
    print("="*80)
    
    suite = MonteCarloTestSuite()
    
    # Load config
    with open('config/m5_params.json', 'r') as f:
        config = json.load(f)
    
    print("\nTesting with 10 samples, 14-day windows, 120-day period")
    print("\nDetailed timing breakdown:\n")
    
    # Time each step
    timings = {}
    
    # 1. Load cached data
    start = time.time()
    cache_key = suite._get_cache_key('XAUUSD', 'M5', 120)
    df_full = suite._load_cached_data(cache_key)
    timings['load_cache'] = time.time() - start
    print(f"1. Load cached data: {timings['load_cache']*1000:.2f}ms")
    
    # 2. Prepare indicators
    start = time.time()
    df_full = suite.prepare_indicators(df_full, config['fast_ema'], 
                                       config['slow_ema'], config['rsi_period'])
    timings['prepare_indicators'] = time.time() - start
    print(f"2. Prepare indicators (column references): {timings['prepare_indicators']*1000:.2f}ms")
    
    # 3. Generate windows
    start = time.time()
    windows = suite.generate_time_windows(df_full, window_days=14, n_samples=10)
    timings['generate_windows'] = time.time() - start
    print(f"3. Generate 10 windows: {timings['generate_windows']*1000:.2f}ms")
    print(f"   - Full dataset: {len(df_full)} candles")
    print(f"   - Window size: {len(windows[0])} candles each")
    
    # 4. Simulate strategy on each window
    print(f"\n4. Simulate strategy on each window:")
    window_times = []
    total_trades = 0
    
    for i, window in enumerate(windows):
        start = time.time()
        trades = suite.simulate_strategy(window, config)
        elapsed = time.time() - start
        window_times.append(elapsed)
        total_trades += len(trades) if trades else 0
        print(f"   Window {i+1}: {elapsed*1000:.2f}ms ({len(trades) if trades else 0} trades)")
    
    timings['simulate_avg'] = sum(window_times) / len(window_times)
    timings['simulate_total'] = sum(window_times)
    print(f"   Average per window: {timings['simulate_avg']*1000:.2f}ms")
    print(f"   Total simulation: {timings['simulate_total']*1000:.2f}ms")
    print(f"   Total trades: {total_trades}")
    
    # 5. Analyze results
    start = time.time()
    sample_results = []
    for window in windows:
        trades = suite.simulate_strategy(window, config)
        metrics = suite.analyze_results(trades)
        if metrics:
            sample_results.append(metrics)
    timings['analyze'] = time.time() - start
    print(f"\n5. Analyze results: {timings['analyze']*1000:.2f}ms")
    
    # Total
    total_time = sum(timings.values())
    print(f"\n" + "="*80)
    print("TIMING BREAKDOWN")
    print("="*80)
    print(f"{'Operation':<30} {'Time (ms)':<15} {'% of Total':<15}")
    print("-"*80)
    
    for op, t in timings.items():
        pct = (t / total_time) * 100
        print(f"{op:<30} {t*1000:>12.2f}ms {pct:>12.1f}%")
    
    print("-"*80)
    print(f"{'TOTAL':<30} {total_time*1000:>12.2f}ms {100.0:>12.1f}%")
    
    # Extrapolate to full optimization
    print(f"\n" + "="*80)
    print("EXTRAPOLATION TO FULL OPTIMIZATION")
    print("="*80)
    print(f"\nTime per config (10 samples): {total_time:.3f}s")
    print(f"Time for 400 configs: {total_time * 400 / 60:.1f} minutes")
    print(f"Time for 400 configs (30 samples): {total_time * 400 * 3 / 60:.1f} minutes")
    
    # Identify bottleneck
    bottleneck = max(timings.items(), key=lambda x: x[1])
    print(f"\nBottleneck: {bottleneck[0]} ({bottleneck[1]*1000:.2f}ms, {bottleneck[1]/total_time*100:.1f}%)")
    
    return timings

def profile_simulate_strategy():
    """Deep profile of the simulate_strategy function"""
    print("\n" + "="*80)
    print("DEEP PROFILING: simulate_strategy()")
    print("="*80)
    
    suite = MonteCarloTestSuite()
    
    with open('config/m5_params.json', 'r') as f:
        config = json.load(f)
    
    cache_key = suite._get_cache_key('XAUUSD', 'M5', 120)
    df_full = suite._load_cached_data(cache_key)
    df_full = suite.prepare_indicators(df_full, config['fast_ema'], 
                                       config['slow_ema'], config['rsi_period'])
    windows = suite.generate_time_windows(df_full, window_days=14, n_samples=1)
    window = windows[0]
    
    print(f"\nProfiling simulation on {len(window)} candles...")
    
    # Profile with cProfile
    profiler = cProfile.Profile()
    profiler.enable()
    
    trades = suite.simulate_strategy(window, config)
    
    profiler.disable()
    
    # Print stats
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)  # Top 20 functions
    
    print(s.getvalue())
    print(f"\nTotal trades: {len(trades) if trades else 0}")
    
    # Manual timing of key operations
    print("\n" + "="*80)
    print("MANUAL TIMING OF KEY OPERATIONS")
    print("="*80)
    
    # Time DataFrame iteration
    start = time.time()
    for idx in range(len(window)):
        row = window.iloc[idx]
    elapsed = time.time() - start
    print(f"DataFrame iteration ({len(window)} rows): {elapsed*1000:.2f}ms")
    
    # Time RSI comparison
    start = time.time()
    for idx in range(len(window)):
        row = window.iloc[idx]
        check = row['RSI'] < config['rsi_buy']
    elapsed = time.time() - start
    print(f"RSI comparisons ({len(window)} checks): {elapsed*1000:.2f}ms")
    
    # Time position checks (simulate 2 positions)
    positions = [
        {'type': 'LONG', 'entry': 2000, 'tp': 2050, 'sl': 1950},
        {'type': 'SHORT', 'entry': 2000, 'tp': 1950, 'sl': 2050}
    ]
    start = time.time()
    for idx in range(len(window)):
        row = window.iloc[idx]
        for pos in positions:
            if pos['type'] == 'LONG':
                check1 = row['close'] >= pos['tp']
                check2 = row['close'] <= pos['sl']
                check3 = row['RSI'] >= config['rsi_exit_long']
    elapsed = time.time() - start
    print(f"Position exit checks ({len(window)} × 2 positions): {elapsed*1000:.2f}ms")

if __name__ == '__main__':
    timings = profile_single_test()
    profile_simulate_strategy()
    
    print("\n" + "="*80)
    print("OPTIMIZATION SUGGESTIONS")
    print("="*80)
    
    if timings['simulate_total'] / sum(timings.values()) > 0.8:
        print("\n✓ Simulation is the bottleneck (expected)")
        print("  This is the actual strategy logic - hard to optimize further")
        print("  Current performance is already good for Python/pandas")
        print("\nPossible improvements:")
        print("  1. Use NumPy arrays instead of pandas (2-3x faster)")
        print("  2. Compile with Numba JIT (5-10x faster)")
        print("  3. Rewrite in Cython/Rust (10-50x faster)")
        print("  4. Parallel processing (use all 8 cores)")
    else:
        print("\n⚠ Unexpected bottleneck found - see timing breakdown above")
