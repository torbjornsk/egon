"""
Example usage of the comprehensive test suite
Run this to establish baselines and compare configurations
"""
import json
from test_suite import TestSuite

def load_config(path):
    """Load configuration from JSON file"""
    with open(path, 'r') as f:
        return json.load(f)

def main():
    # Initialize test suite
    suite = TestSuite()
    
    # Step 1: Fetch and cache data (only needed once per day)
    print("Step 1: Fetching and caching data...")
    print("This may take a few minutes on first run, but will be fast afterwards.\n")
    suite.fetch_and_cache_data(force_refresh=False)
    
    # Step 2: Load current configurations
    m5_config = load_config('config/m5_params.json')
    m1_config = load_config('config/m1_params.json')
    
    # Step 3: Test M5 configuration
    print("\n" + "="*80)
    print("TESTING M5 CONFIGURATION")
    print("="*80)
    m5_results = suite.test_config('Current M5', m5_config, timeframe='M5')
    
    # Step 4: Test M1 configuration
    print("\n" + "="*80)
    print("TESTING M1 CONFIGURATION")
    print("="*80)
    m1_results = suite.test_config('Current M1', m1_config, timeframe='M1')
    
    # Step 5: Compare multiple configurations (example)
    print("\n" + "="*80)
    print("EXAMPLE: COMPARING DIFFERENT M5 CONFIGURATIONS")
    print("="*80)
    
    # Create variations to test
    m5_conservative = m5_config.copy()
    m5_conservative['rsi_buy'] = 30
    m5_conservative['rsi_sell'] = 70
    m5_conservative['profit_target_pct'] = 0.015
    
    m5_aggressive = m5_config.copy()
    m5_aggressive['rsi_buy'] = 40
    m5_aggressive['rsi_sell'] = 60
    m5_aggressive['profit_target_pct'] = 0.03
    
    configs_to_compare = {
        'Current M5': m5_config,
        'Conservative': m5_conservative,
        'Aggressive': m5_aggressive
    }
    
    comparison_results = suite.compare_configs(configs_to_compare, timeframe='M5')
    
    print("\n" + "="*80)
    print("TEST SUITE COMPLETE")
    print("="*80)
    print("\nBaseline established! You can now:")
    print("1. Modify parameters in config files")
    print("2. Re-run this script to compare results")
    print("3. Use the test suite in your own scripts for parameter optimization")
    print("\nData is cached in: tests/data_cache/")
    print("Results are repeatable as long as you use the same cached data.")

if __name__ == '__main__':
    main()
