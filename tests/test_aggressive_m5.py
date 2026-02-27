"""
Test Aggressive M5 Configurations
Explores higher-risk, higher-return settings while monitoring safety
"""
import json
from test_suite import TestSuite
import numpy as np

def test_aggressive_m5():
    print("="*100)
    print("AGGRESSIVE M5 CONFIGURATION TESTING")
    print("="*100)
    
    suite = TestSuite()
    
    # Load current config
    with open('config/m5_params.json', 'r') as f:
        base_config = json.load(f)
    
    print(f"\nCurrent M5 Config:")
    print(f"  RSI: {base_config['rsi_buy']}/{base_config['rsi_sell']}")
    print(f"  Exit: {base_config['rsi_exit_long']}/{base_config['rsi_exit_short']}")
    print(f"  TP: {base_config['profit_target_pct']*100:.1f}%")
    print(f"  Position Size: {base_config['position_size_pct']*100:.1f}%")
    print(f"  Leverage: {base_config['leverage']}x")
    
    # Define aggressive variations
    configs = {
        'Current (Baseline)': base_config.copy(),
        
        # More frequent trading (wider RSI bands)
        'More Trades (RSI 40/60)': {
            **base_config,
            'rsi_buy': 40,
            'rsi_sell': 60,
            'rsi_exit_long': 60,
            'rsi_exit_short': 40
        },
        
        # Higher position size
        'Larger Positions (20%)': {
            **base_config,
            'position_size_pct': 0.20
        },
        
        # Higher leverage
        'Higher Leverage (30x)': {
            **base_config,
            'leverage': 30
        },
        
        # Higher take profit
        'Higher TP (3.5%)': {
            **base_config,
            'profit_target_pct': 0.035
        },
        
        # Combination: More trades + larger positions
        'Aggressive Combo 1': {
            **base_config,
            'rsi_buy': 40,
            'rsi_sell': 60,
            'position_size_pct': 0.18,
            'profit_target_pct': 0.030
        },
        
        # Combination: More trades + higher leverage
        'Aggressive Combo 2': {
            **base_config,
            'rsi_buy': 40,
            'rsi_sell': 60,
            'leverage': 30,
            'profit_target_pct': 0.030
        },
        
        # Balanced aggressive
        'Balanced Aggressive': {
            **base_config,
            'rsi_buy': 38,
            'rsi_sell': 62,
            'position_size_pct': 0.18,
            'profit_target_pct': 0.028,
            'leverage': 27
        },
        
        # Maximum safe aggression
        'Max Safe Aggression': {
            **base_config,
            'rsi_buy': 40,
            'rsi_sell': 60,
            'position_size_pct': 0.20,
            'profit_target_pct': 0.030,
            'leverage': 30
        }
    }
    
    print(f"\nTesting {len(configs)} configurations across all periods...")
    print("This will take ~30 seconds with optimized code\n")
    
    results = {}
    
    for config_name, config in configs.items():
        print(f"Testing: {config_name}")
        
        period_results = {}
        
        # Test on all periods
        for period_name in ['recent_30d', 'recent_60d', 'recent_90d', 'recent_120d', 'full_history']:
            cache_key = suite._get_cache_key('XAUUSD', 'M5', suite.test_periods[period_name]['days'])
            df = suite._load_cached_data(cache_key)
            
            if df is None:
                continue
            
            df = suite.prepare_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
            trades = suite.simulate_strategy(df, config, max_positions=2)
            metrics = suite.analyze_results(trades)
            
            if metrics:
                period_results[period_name] = metrics
        
        if period_results:
            # Calculate aggregates
            avg_return = np.mean([r['total_return'] for r in period_results.values()])
            avg_sharpe = np.mean([r['sharpe'] for r in period_results.values()])
            max_dd = max([abs(r['max_drawdown']) for r in period_results.values()])
            avg_trades = np.mean([r['total_trades'] for r in period_results.values()])
            avg_wr = np.mean([r['win_rate'] for r in period_results.values()])
            
            # Calculate risk score (lower is better)
            risk_score = max_dd / avg_sharpe if avg_sharpe > 0 else 999
            
            # Calculate return per unit risk
            return_per_risk = avg_return / max_dd if max_dd > 0 else 0
            
            results[config_name] = {
                'config': config,
                'avg_return': avg_return,
                'avg_sharpe': avg_sharpe,
                'max_dd': max_dd,
                'avg_trades': avg_trades,
                'avg_wr': avg_wr,
                'risk_score': risk_score,
                'return_per_risk': return_per_risk,
                'period_results': period_results
            }
            
            print(f"  Avg Return: {avg_return:.1f}%, Sharpe: {avg_sharpe:.2f}, Max DD: {max_dd:.1f}%, Trades: {avg_trades:.0f}")
    
    # Analysis
    print("\n" + "="*100)
    print("RESULTS COMPARISON")
    print("="*100)
    
    print(f"\n{'Config':<25} {'Avg Ret':<12} {'Sharpe':<10} {'Max DD':<10} {'Trades':<10} {'WR':<8} {'Risk Score':<12}")
    print("-"*100)
    
    for name, r in results.items():
        print(f"{name:<25} {r['avg_return']:>10.1f}% {r['avg_sharpe']:>8.2f} {r['max_dd']:>8.1f}% "
              f"{r['avg_trades']:>9.0f} {r['avg_wr']:>6.1f}% {r['risk_score']:>10.2f}")
    
    # Find best by different metrics
    print("\n" + "="*100)
    print("BEST CONFIGURATIONS")
    print("="*100)
    
    best_return = max(results.items(), key=lambda x: x[1]['avg_return'])
    best_sharpe = max(results.items(), key=lambda x: x[1]['avg_sharpe'])
    best_return_per_risk = max(results.items(), key=lambda x: x[1]['return_per_risk'])
    
    print(f"\nBest by Total Return: {best_return[0]}")
    print(f"  Return: {best_return[1]['avg_return']:.1f}%")
    print(f"  Sharpe: {best_return[1]['avg_sharpe']:.2f}")
    print(f"  Max DD: {best_return[1]['max_dd']:.1f}%")
    print(f"  Trades: {best_return[1]['avg_trades']:.0f}")
    
    print(f"\nBest by Sharpe Ratio (risk-adjusted): {best_sharpe[0]}")
    print(f"  Return: {best_sharpe[1]['avg_return']:.1f}%")
    print(f"  Sharpe: {best_sharpe[1]['avg_sharpe']:.2f}")
    print(f"  Max DD: {best_sharpe[1]['max_dd']:.1f}%")
    print(f"  Trades: {best_sharpe[1]['avg_trades']:.0f}")
    
    print(f"\nBest by Return/Risk Ratio: {best_return_per_risk[0]}")
    print(f"  Return: {best_return_per_risk[1]['avg_return']:.1f}%")
    print(f"  Sharpe: {best_return_per_risk[1]['avg_sharpe']:.2f}")
    print(f"  Max DD: {best_return_per_risk[1]['max_dd']:.1f}%")
    print(f"  Return/Risk: {best_return_per_risk[1]['return_per_risk']:.2f}")
    
    # Safety check
    print("\n" + "="*100)
    print("SAFETY ANALYSIS")
    print("="*100)
    
    baseline = results['Current (Baseline)']
    
    print(f"\nCurrent Baseline:")
    print(f"  Return: {baseline['avg_return']:.1f}%")
    print(f"  Sharpe: {baseline['avg_sharpe']:.2f}")
    print(f"  Max DD: {baseline['max_dd']:.1f}%")
    
    print(f"\nSafe Aggressive Options (Max DD < 15%):")
    safe_options = [(name, r) for name, r in results.items() 
                    if r['max_dd'] < 15 and r['avg_return'] > baseline['avg_return']]
    
    if safe_options:
        safe_options.sort(key=lambda x: x[1]['avg_sharpe'], reverse=True)
        for name, r in safe_options[:3]:
            improvement = r['avg_return'] - baseline['avg_return']
            print(f"\n  {name}:")
            print(f"    Return: {r['avg_return']:.1f}% ({improvement:+.1f}%)")
            print(f"    Sharpe: {r['avg_sharpe']:.2f}")
            print(f"    Max DD: {r['max_dd']:.1f}%")
            print(f"    Trades: {r['avg_trades']:.0f}")
    else:
        print("  No configurations found that improve returns while staying under 15% DD")
    
    print(f"\nHigh Risk Options (Max DD 15-20%):")
    risky_options = [(name, r) for name, r in results.items() 
                     if 15 <= r['max_dd'] < 20 and r['avg_return'] > baseline['avg_return']]
    
    if risky_options:
        risky_options.sort(key=lambda x: x[1]['avg_return'], reverse=True)
        for name, r in risky_options[:3]:
            improvement = r['avg_return'] - baseline['avg_return']
            print(f"\n  {name}:")
            print(f"    Return: {r['avg_return']:.1f}% ({improvement:+.1f}%)")
            print(f"    Sharpe: {r['avg_sharpe']:.2f}")
            print(f"    Max DD: {r['max_dd']:.1f}%")
            print(f"    ⚠ Higher risk - monitor closely")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    # Find best safe option
    safe_configs = [(name, r) for name, r in results.items() 
                    if r['max_dd'] < 15 and r['avg_sharpe'] > baseline['avg_sharpe']]
    
    if safe_configs:
        best_safe = max(safe_configs, key=lambda x: x[1]['avg_return'])
        
        print(f"\nRecommended: {best_safe[0]}")
        print(f"\nConfiguration:")
        cfg = best_safe[1]['config']
        print(f"  RSI: {cfg['rsi_buy']}/{cfg['rsi_sell']}")
        print(f"  Exit: {cfg['rsi_exit_long']}/{cfg['rsi_exit_short']}")
        print(f"  TP: {cfg['profit_target_pct']*100:.1f}%")
        print(f"  Position Size: {cfg['position_size_pct']*100:.1f}%")
        print(f"  Leverage: {cfg['leverage']}x")
        
        print(f"\nExpected Performance:")
        print(f"  Return: {best_safe[1]['avg_return']:.1f}% (vs {baseline['avg_return']:.1f}% current)")
        print(f"  Sharpe: {best_safe[1]['avg_sharpe']:.2f} (vs {baseline['avg_sharpe']:.2f} current)")
        print(f"  Max DD: {best_safe[1]['max_dd']:.1f}% (vs {baseline['max_dd']:.1f}% current)")
        print(f"  Trades: {best_safe[1]['avg_trades']:.0f} (vs {baseline['avg_trades']:.0f} current)")
        
        improvement = best_safe[1]['avg_return'] - baseline['avg_return']
        print(f"\n✓ Improvement: {improvement:+.1f}% return with acceptable risk")
        
        # Save recommended config
        with open('tests/recommended_aggressive_m5.json', 'w') as f:
            json.dump({
                'name': best_safe[0],
                'config': cfg,
                'expected_performance': {
                    'avg_return': best_safe[1]['avg_return'],
                    'avg_sharpe': best_safe[1]['avg_sharpe'],
                    'max_dd': best_safe[1]['max_dd'],
                    'avg_trades': best_safe[1]['avg_trades']
                },
                'improvement_vs_baseline': {
                    'return': improvement,
                    'sharpe': best_safe[1]['avg_sharpe'] - baseline['avg_sharpe'],
                    'max_dd': best_safe[1]['max_dd'] - baseline['max_dd']
                }
            }, f, indent=2)
        
        print(f"\nRecommended config saved to: tests/recommended_aggressive_m5.json")
    else:
        print("\n⚠ Current configuration is already optimal for the risk level")
        print("  To increase returns, you would need to accept higher drawdowns (>15%)")

if __name__ == '__main__':
    test_aggressive_m5()
