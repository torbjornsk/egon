"""
Benchmark Monte Carlo performance with different sample sizes
Run this to find the optimal balance between speed and confidence
"""
import json
import time
from test_suite_monte_carlo import MonteCarloTestSuite

def benchmark():
    print("="*80)
    print("MONTE CARLO PERFORMANCE BENCHMARK")
    print("="*80)
    
    suite = MonteCarloTestSuite()
    suite.print_confidence_table()
    
    # Load config
    with open('config/m5_params.json', 'r') as f:
        config = json.load(f)
    
    print(f"\nTesting M5 config: RSI {config['rsi_buy']}/{config['rsi_sell']}")
    print("\nBenchmarking different sample sizes...\n")
    
    sample_sizes = [5, 10, 15, 20, 30, 50]
    results = []
    
    for n_samples in sample_sizes:
        print(f"Testing {n_samples} samples...")
        start = time.time()
        
        mc_results = suite.test_config_monte_carlo(
            config,
            timeframe='M5',
            period_days=120,
            window_days=14,
            n_samples=n_samples
        )
        
        elapsed = time.time() - start
        
        if mc_results:
            results.append({
                'n_samples': n_samples,
                'time_seconds': elapsed,
                'mean_return': mc_results['mean_return'],
                'std_return': mc_results['std_return'],
                'confidence': mc_results['confidence']
            })
            
            print(f"  Time: {elapsed:.2f}s")
            print(f"  Mean return: {mc_results['mean_return']:.1f}% ± {mc_results['std_return']:.1f}%")
            print(f"  Confidence: {mc_results['confidence']*100:.0f}%\n")
    
    # Summary
    print("="*80)
    print("BENCHMARK SUMMARY")
    print("="*80)
    print(f"{'Samples':<10} {'Time':<12} {'Confidence':<15} {'Mean Return':<15} {'Std Dev':<10}")
    print("-"*80)
    
    for r in results:
        print(f"{r['n_samples']:<10} {r['time_seconds']:>8.2f}s    {r['confidence']*100:>6.0f}%         "
              f"{r['mean_return']:>10.1f}%      {r['std_return']:>6.1f}%")
    
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    # Calculate time per config for full optimization
    print("\nFor full optimization (~400 configs):")
    for r in results:
        total_time = r['time_seconds'] * 400
        print(f"  {r['n_samples']:>2} samples ({r['confidence']*100:.0f}% confidence): "
              f"{total_time/60:>5.1f} minutes")
    
    print("\nRecommended settings:")
    print("  - Quick test: 10 samples (~80% confidence, ~2-3 min)")
    print("  - Standard: 20 samples (~90% confidence, ~4-5 min)")
    print("  - Thorough: 30 samples (~95% confidence, ~6-8 min)")
    print("  - Exhaustive: 50 samples (~99% confidence, ~10-12 min)")
    
    # Find sweet spot (best confidence per second)
    efficiency = [(r['confidence'] / r['time_seconds'], r['n_samples']) for r in results]
    best_efficiency = max(efficiency)
    
    print(f"\nBest efficiency: {best_efficiency[1]} samples "
          f"({results[sample_sizes.index(best_efficiency[1])]['confidence']*100:.0f}% confidence)")

if __name__ == '__main__':
    benchmark()
