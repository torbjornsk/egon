"""
Test script to verify refactored bots work correctly
Tests basic functionality without connecting to MT5
"""

import sys
import json
from pathlib import Path

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    try:
        from src.base_trading_bot import BaseTradingBot
        print("  ✓ BaseTradingBot imported")
        
        from src.strategies.m5_scalping import M5ScalpingStrategy
        print("  ✓ M5ScalpingStrategy imported")
        
        from src.strategies.m1_scalping import M1ScalpingStrategy
        print("  ✓ M1ScalpingStrategy imported")
        
        # Import refactored bots (but don't instantiate to avoid MT5 connection)
        import live_trading_bot_refactored
        print("  ✓ M5 refactored bot imported")
        
        import live_trading_bot_m1_refactored
        print("  ✓ M1 refactored bot imported")
        
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False

def test_config_files():
    """Test that config files exist and are valid"""
    print("\nTesting config files...")
    
    configs = [
        'config/m5_params.json',
        'config/m1_params.json'
    ]
    
    all_valid = True
    for config_path in configs:
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Check required fields
            required = ['strategy', 'position_size_pct', 'leverage', 'fast_ema', 
                       'slow_ema', 'rsi_period', 'rsi_buy', 'rsi_sell']
            
            missing = [field for field in required if field not in config]
            if missing:
                print(f"  ✗ {config_path}: Missing fields: {missing}")
                all_valid = False
            else:
                print(f"  ✓ {config_path}: Valid")
        except FileNotFoundError:
            print(f"  ✗ {config_path}: File not found")
            all_valid = False
        except json.JSONDecodeError as e:
            print(f"  ✗ {config_path}: Invalid JSON: {e}")
            all_valid = False
    
    return all_valid

def test_strategy_methods():
    """Test that strategy classes have required methods"""
    print("\nTesting strategy methods...")
    
    try:
        from src.strategies.m5_scalping import M5ScalpingStrategy
        from src.strategies.m1_scalping import M1ScalpingStrategy
        
        # Create dummy config
        config = {
            'fast_ema': 9,
            'slow_ema': 21,
            'rsi_period': 14,
            'rsi_buy': 30,
            'rsi_sell': 70,
            'atr_multiplier': 2.0,
            'profit_target_pct': 0.01,
            'enable_shorts': True
        }
        
        # Test M5 strategy
        m5_strategy = M5ScalpingStrategy(config)
        required_methods = ['get_timeframe', 'compute_indicators', 'print_indicators',
                          'check_entry_signal', 'check_exit_signal']
        
        for method in required_methods:
            if not hasattr(m5_strategy, method):
                print(f"  ✗ M5ScalpingStrategy missing method: {method}")
                return False
        print("  ✓ M5ScalpingStrategy has all required methods")
        
        # Test M1 strategy
        m1_strategy = M1ScalpingStrategy(config)
        for method in required_methods:
            if not hasattr(m1_strategy, method):
                print(f"  ✗ M1ScalpingStrategy missing method: {method}")
                return False
        print("  ✓ M1ScalpingStrategy has all required methods")
        
        return True
    except Exception as e:
        print(f"  ✗ Strategy method test failed: {e}")
        return False

def test_base_bot_methods():
    """Test that base bot has required methods"""
    print("\nTesting base bot methods...")
    
    try:
        from src.base_trading_bot import BaseTradingBot
        
        required_methods = [
            'load_config', 'connect_mt5', 'disconnect_mt5', 'get_account_info',
            'get_historical_data', 'get_open_positions', 'check_drawdown',
            'check_daily_loss_limit', 'check_consecutive_losses', 'run_safety_checks',
            'emergency_close_all', 'close_position', 'is_near_weekend_close',
            'has_new_candle', 'print_startup_state', 'run'
        ]
        
        for method in required_methods:
            if not hasattr(BaseTradingBot, method):
                print(f"  ✗ BaseTradingBot missing method: {method}")
                return False
        
        print("  ✓ BaseTradingBot has all required methods")
        return True
    except Exception as e:
        print(f"  ✗ Base bot method test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("="*60)
    print("REFACTORED BOTS TEST SUITE")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Config Files", test_config_files()))
    results.append(("Strategy Methods", test_strategy_methods()))
    results.append(("Base Bot Methods", test_base_bot_methods()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:.<40} {status}")
    
    print("="*60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Refactored bots are ready to use.")
        print("\nNext steps:")
        print("1. Test M5 bot: python live_trading_bot_refactored.py")
        print("2. Test M1 bot: python live_trading_bot_m1_refactored.py")
        print("3. Compare behavior with original bots")
        return 0
    else:
        print("\n✗ Some tests failed. Please fix issues before using refactored bots.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
