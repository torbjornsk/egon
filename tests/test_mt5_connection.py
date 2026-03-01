"""
Comprehensive MT5 Connection Test
Tests all MT5 API functions used by the bots
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

def test_initialization():
    """Test MT5 initialization"""
    print("\n" + "="*60)
    print("TEST 1: MT5 INITIALIZATION")
    print("="*60)
    
    if not mt5.initialize():
        error = mt5.last_error()
        print(f"✗ FAILED: {error}")
        return False
    
    print("✓ MT5 initialized successfully")
    return True

def test_account_info():
    """Test account information retrieval"""
    print("\n" + "="*60)
    print("TEST 2: ACCOUNT INFORMATION")
    print("="*60)
    
    try:
        account_info = mt5.account_info()
        if account_info is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        print(f"✓ Account info retrieved:")
        print(f"  Login: {account_info.login}")
        print(f"  Server: {account_info.server}")
        print(f"  Balance: ${account_info.balance:,.2f}")
        print(f"  Equity: ${account_info.equity:,.2f}")
        print(f"  Margin: ${account_info.margin:,.2f}")
        print(f"  Free Margin: ${account_info.margin_free:,.2f}")
        print(f"  Leverage: 1:{account_info.leverage}")
        print(f"  Currency: {account_info.currency}")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_symbol_info():
    """Test symbol information retrieval"""
    print("\n" + "="*60)
    print("TEST 3: SYMBOL INFORMATION (XAUUSD.p)")
    print("="*60)
    
    try:
        symbol = 'XAUUSD.p'
        
        # Check if symbol exists
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"✗ FAILED: Symbol {symbol} not found")
            print(f"  Error: {mt5.last_error()}")
            return False
        
        print(f"✓ Symbol info retrieved:")
        print(f"  Name: {symbol_info.name}")
        print(f"  Description: {symbol_info.description}")
        print(f"  Bid: {symbol_info.bid}")
        print(f"  Ask: {symbol_info.ask}")
        print(f"  Spread: {symbol_info.spread}")
        print(f"  Digits: {symbol_info.digits}")
        print(f"  Point: {symbol_info.point}")
        print(f"  Trade Mode: {symbol_info.trade_mode}")
        print(f"  Volume Min: {symbol_info.volume_min}")
        print(f"  Volume Max: {symbol_info.volume_max}")
        print(f"  Volume Step: {symbol_info.volume_step}")
        
        # Check if symbol is visible
        if not symbol_info.visible:
            print(f"\n⚠️  Symbol not visible, attempting to enable...")
            if not mt5.symbol_select(symbol, True):
                print(f"✗ FAILED to enable symbol")
                return False
            print(f"✓ Symbol enabled")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_historical_data():
    """Test historical data retrieval"""
    print("\n" + "="*60)
    print("TEST 4: HISTORICAL DATA RETRIEVAL")
    print("="*60)
    
    symbol = 'XAUUSD.p'
    timeframes = [
        ('M1', mt5.TIMEFRAME_M1, 100),
        ('M5', mt5.TIMEFRAME_M5, 100),
        ('H1', mt5.TIMEFRAME_H1, 100),
        ('H4', mt5.TIMEFRAME_H4, 50),
    ]
    
    all_passed = True
    
    for tf_name, tf_const, bars in timeframes:
        try:
            rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, bars)
            
            if rates is None or len(rates) == 0:
                print(f"✗ {tf_name}: FAILED - {mt5.last_error()}")
                all_passed = False
                continue
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            print(f"✓ {tf_name}: Retrieved {len(df)} bars")
            print(f"  Period: {df['time'].min()} to {df['time'].max()}")
            print(f"  Latest Close: {df['close'].iloc[-1]:.2f}")
            
        except Exception as e:
            print(f"✗ {tf_name}: FAILED - {e}")
            all_passed = False
    
    return all_passed

def test_tick_data():
    """Test tick data retrieval"""
    print("\n" + "="*60)
    print("TEST 5: TICK DATA")
    print("="*60)
    
    try:
        symbol = 'XAUUSD.p'
        ticks = mt5.copy_ticks_from(symbol, datetime.now() - timedelta(minutes=5), 100, mt5.COPY_TICKS_ALL)
        
        if ticks is None or len(ticks) == 0:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        df = pd.DataFrame(ticks)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        print(f"✓ Retrieved {len(df)} ticks")
        print(f"  Period: {df['time'].min()} to {df['time'].max()}")
        print(f"  Latest Bid: {df['bid'].iloc[-1]:.2f}")
        print(f"  Latest Ask: {df['ask'].iloc[-1]:.2f}")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_positions():
    """Test position retrieval"""
    print("\n" + "="*60)
    print("TEST 6: OPEN POSITIONS")
    print("="*60)
    
    try:
        positions = mt5.positions_get()
        
        if positions is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        if len(positions) == 0:
            print("✓ No open positions (expected for new account)")
        else:
            print(f"✓ Retrieved {len(positions)} open positions:")
            for pos in positions:
                print(f"  {pos.symbol} {pos.type} {pos.volume} lots @ {pos.price_open}")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_orders():
    """Test order retrieval"""
    print("\n" + "="*60)
    print("TEST 7: PENDING ORDERS")
    print("="*60)
    
    try:
        orders = mt5.orders_get()
        
        if orders is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        if len(orders) == 0:
            print("✓ No pending orders (expected for new account)")
        else:
            print(f"✓ Retrieved {len(orders)} pending orders:")
            for order in orders:
                print(f"  {order.symbol} {order.type} {order.volume} lots @ {order.price_open}")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_history():
    """Test trade history retrieval"""
    print("\n" + "="*60)
    print("TEST 8: TRADE HISTORY")
    print("="*60)
    
    try:
        # Get history from last 30 days
        from_date = datetime.now() - timedelta(days=30)
        to_date = datetime.now()
        
        deals = mt5.history_deals_get(from_date, to_date)
        
        if deals is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        if len(deals) == 0:
            print("✓ No trade history (expected for new account)")
        else:
            print(f"✓ Retrieved {len(deals)} deals from last 30 days")
            
            # Show recent deals
            for deal in deals[-5:]:
                deal_time = datetime.fromtimestamp(deal.time)
                print(f"  {deal_time}: {deal.symbol} {deal.type} {deal.volume} lots")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_order_check():
    """Test order validation (without sending)"""
    print("\n" + "="*60)
    print("TEST 9: ORDER VALIDATION")
    print("="*60)
    
    try:
        symbol = 'XAUUSD.p'
        symbol_info = mt5.symbol_info(symbol)
        
        if symbol_info is None:
            print(f"✗ FAILED: Symbol info not available")
            return False
        
        # Create a test order request (won't be sent)
        lot = symbol_info.volume_min
        price = symbol_info.ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "test order check",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Check order (doesn't send it)
        result = mt5.order_check(request)
        
        if result is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"⚠️  Order check returned: {result.retcode}")
            print(f"  Comment: {result.comment}")
            print(f"  This might be normal (market closed, etc.)")
        else:
            print(f"✓ Order validation passed")
            print(f"  Symbol: {symbol}")
            print(f"  Volume: {lot} lots")
            print(f"  Price: {price}")
            print(f"  Margin required: ${result.margin:.2f}")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_terminal_info():
    """Test terminal information"""
    print("\n" + "="*60)
    print("TEST 10: TERMINAL INFORMATION")
    print("="*60)
    
    try:
        terminal_info = mt5.terminal_info()
        
        if terminal_info is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        print(f"✓ Terminal info retrieved:")
        print(f"  Build: {terminal_info.build}")
        print(f"  Connected: {terminal_info.connected}")
        print(f"  Trade Allowed: {terminal_info.trade_allowed}")
        print(f"  Experts Enabled: {terminal_info.tradeapi_disabled}")
        print(f"  Company: {terminal_info.company}")
        print(f"  Name: {terminal_info.name}")
        print(f"  Path: {terminal_info.path}")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_symbols_total():
    """Test symbol enumeration"""
    print("\n" + "="*60)
    print("TEST 11: AVAILABLE SYMBOLS")
    print("="*60)
    
    try:
        symbols = mt5.symbols_get()
        
        if symbols is None:
            print(f"✗ FAILED: {mt5.last_error()}")
            return False
        
        print(f"✓ Total symbols available: {len(symbols)}")
        
        # Find gold symbols
        gold_symbols = [s for s in symbols if 'XAU' in s.name or 'GOLD' in s.name.upper()]
        
        if gold_symbols:
            print(f"\n  Gold symbols found:")
            for sym in gold_symbols:
                print(f"    {sym.name}: {sym.description}")
        else:
            print(f"\n  ⚠️  No gold symbols found")
        
        return True
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def run_all_tests():
    """Run all MT5 tests"""
    print("\n" + "="*60)
    print("MT5 CONNECTION TEST SUITE")
    print("Testing Dominion MetaTrader Installation")
    print("="*60)
    
    tests = [
        ("Initialization", test_initialization),
        ("Account Info", test_account_info),
        ("Symbol Info", test_symbol_info),
        ("Historical Data", test_historical_data),
        ("Tick Data", test_tick_data),
        ("Positions", test_positions),
        ("Orders", test_orders),
        ("History", test_history),
        ("Order Validation", test_order_check),
        ("Terminal Info", test_terminal_info),
        ("Symbols", test_symbols_total),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n✗ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - MT5 connection is working perfectly!")
    elif passed >= total * 0.8:
        print("\n⚠️  MOSTLY WORKING - Some minor issues detected")
    else:
        print("\n✗ ISSUES DETECTED - MT5 connection has problems")
    
    # Cleanup
    mt5.shutdown()
    print("\n✓ MT5 connection closed")
    
    return passed == total

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
