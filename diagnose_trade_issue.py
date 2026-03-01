"""
Advanced diagnostic for trade disabled issues
When AutoTrading is enabled but trading still fails
"""

import MetaTrader5 as mt5
import sys

def advanced_diagnosis():
    """Perform advanced diagnosis of trading issues"""
    
    print("="*70)
    print("ADVANCED TRADING DIAGNOSTIC")
    print("="*70)
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return False
    
    print("✓ MT5 initialized\n")
    
    # 1. Account Information
    print("1. ACCOUNT INFORMATION")
    print("-" * 70)
    account_info = mt5.account_info()
    if account_info:
        print(f"  Login: {account_info.login}")
        print(f"  Server: {account_info.server}")
        print(f"  Name: {account_info.name}")
        print(f"  Company: {account_info.company}")
        print(f"  Currency: {account_info.currency}")
        print(f"  Balance: ${account_info.balance:.2f}")
        print(f"  Leverage: 1:{account_info.leverage}")
        print(f"  Margin Free: ${account_info.margin_free:.2f}")
        print(f"  Margin Level: {account_info.margin_level:.2f}%")
        print(f"  Trade Allowed: {account_info.trade_allowed}")
        print(f"  Trade Expert: {account_info.trade_expert}")
        print(f"  Trade Mode: {account_info.trade_mode}")
        
        # Trade mode meanings
        trade_modes = {
            0: "DEMO",
            1: "CONTEST", 
            2: "REAL"
        }
        print(f"  Account Type: {trade_modes.get(account_info.trade_mode, 'UNKNOWN')}")
        
        if account_info.trade_mode == 0:
            print(f"  ⚠️  This is a DEMO account - may have restrictions")
    
    # 2. Terminal Information
    print(f"\n2. TERMINAL INFORMATION")
    print("-" * 70)
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"  Build: {terminal_info.build}")
        print(f"  Connected: {terminal_info.connected}")
        print(f"  Trade Allowed: {terminal_info.trade_allowed}")
        print(f"  Tradeapi Disabled: {terminal_info.tradeapi_disabled}")
        print(f"  Dlls Allowed: {terminal_info.dlls_allowed}")
        
        if terminal_info.tradeapi_disabled:
            print(f"  ❌ PROBLEM: Trade API is DISABLED!")
            print(f"     This prevents external programs from trading")
    
    # 3. Symbol Information
    print(f"\n3. SYMBOL INFORMATION")
    print("-" * 70)
    symbol = 'XAUUSD.p'
    
    # Try to select symbol
    if not mt5.symbol_select(symbol, True):
        print(f"❌ Failed to select {symbol}")
        error = mt5.last_error()
        print(f"   Error code: {error[0]}")
        print(f"   Error message: {error[1]}")
        
        # Try alternative
        alt_symbol = 'XAUUSD'
        print(f"\n   Trying alternative: {alt_symbol}")
        if mt5.symbol_select(alt_symbol, True):
            print(f"   ✓ {alt_symbol} works - use this instead!")
            symbol = alt_symbol
        else:
            print(f"   ❌ {alt_symbol} also failed")
            mt5.shutdown()
            return False
    
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info:
        print(f"  Symbol: {symbol}")
        print(f"  Description: {symbol_info.description}")
        print(f"  Visible: {symbol_info.visible}")
        print(f"  Trade Mode: {symbol_info.trade_mode}")
        
        trade_modes = {
            0: "DISABLED",
            1: "LONGONLY",
            2: "SHORTONLY",
            3: "CLOSEONLY",
            4: "FULL"
        }
        print(f"  Trade Mode Name: {trade_modes.get(symbol_info.trade_mode, 'UNKNOWN')}")
        
        print(f"  Volume Min: {symbol_info.volume_min}")
        print(f"  Volume Max: {symbol_info.volume_max}")
        print(f"  Volume Step: {symbol_info.volume_step}")
        print(f"  Contract Size: {symbol_info.trade_contract_size}")
        
        # Check if symbol allows trading
        if symbol_info.trade_mode == 0:
            print(f"  ❌ PROBLEM: Trading is DISABLED for this symbol!")
        elif symbol_info.trade_mode == 3:
            print(f"  ⚠️  WARNING: Only CLOSING positions allowed!")
    
    # 4. Current Market Data
    print(f"\n4. MARKET DATA")
    print("-" * 70)
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        print(f"  Bid: {tick.bid}")
        print(f"  Ask: {tick.ask}")
        print(f"  Spread: {tick.ask - tick.bid:.5f}")
        print(f"  Last: {tick.last}")
        print(f"  Volume: {tick.volume}")
        
        if tick.bid == 0 or tick.ask == 0:
            print(f"  ❌ PROBLEM: Invalid prices - market may be closed!")
    else:
        print(f"  ❌ No tick data available - market closed?")
    
    # 5. Try a Test Order (without sending)
    print(f"\n5. TEST ORDER VALIDATION")
    print("-" * 70)
    
    if tick and tick.ask > 0:
        # Create a test order request
        test_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": symbol_info.volume_min if symbol_info else 0.01,
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "sl": tick.ask - 10,
            "tp": tick.ask + 10,
            "deviation": 20,
            "magic": 234000,
            "comment": "test_order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        print(f"  Test order parameters:")
        print(f"    Symbol: {test_request['symbol']}")
        print(f"    Volume: {test_request['volume']}")
        print(f"    Type: BUY")
        print(f"    Price: {test_request['price']}")
        print(f"    SL: {test_request['sl']}")
        print(f"    TP: {test_request['tp']}")
        
        # Check the order (don't send it)
        result = mt5.order_check(test_request)
        
        if result is None:
            print(f"  ❌ order_check returned None")
            error = mt5.last_error()
            print(f"     Error: {error}")
        else:
            print(f"\n  Order Check Result:")
            print(f"    Retcode: {result.retcode}")
            print(f"    Comment: {result.comment}")
            
            # Retcode meanings
            retcodes = {
                10004: "REQUOTE - Requote",
                10006: "REJECT - Request rejected",
                10007: "CANCEL - Request canceled",
                10008: "PLACED - Order placed",
                10009: "DONE - Request completed",
                10010: "DONE_PARTIAL - Partial fill",
                10011: "ERROR - Request error",
                10012: "TIMEOUT - Request timeout",
                10013: "INVALID - Invalid request",
                10014: "INVALID_VOLUME - Invalid volume",
                10015: "INVALID_PRICE - Invalid price",
                10016: "INVALID_STOPS - Invalid stops",
                10017: "TRADE_DISABLED - Trade disabled",
                10018: "MARKET_CLOSED - Market closed",
                10019: "NO_MONEY - Not enough money",
                10020: "PRICE_CHANGED - Price changed",
                10021: "PRICE_OFF - No prices",
                10022: "INVALID_EXPIRATION - Invalid expiration",
                10023: "ORDER_CHANGED - Order changed",
                10024: "TOO_MANY_REQUESTS - Too many requests",
                10025: "NO_CHANGES - No changes",
                10026: "SERVER_DISABLES_AT - Server disabled",
                10027: "CLIENT_DISABLES_AT - Client disabled",
                10028: "LOCKED - Locked",
                10029: "FROZEN - Frozen",
                10030: "INVALID_FILL - Invalid fill",
            }
            
            retcode_name = retcodes.get(result.retcode, "UNKNOWN")
            print(f"    Retcode Name: {retcode_name}")
            
            if result.retcode == 10017:
                print(f"\n  ❌ CONFIRMED: Trade is disabled!")
                print(f"     Possible reasons:")
                print(f"     1. Account has trading restrictions")
                print(f"     2. Symbol is not tradeable on this account")
                print(f"     3. Demo account limitations")
                print(f"     4. Broker-side restrictions")
            elif result.retcode == 10009:
                print(f"\n  ✓ Order validation PASSED!")
                print(f"    Trading should work (order not actually sent)")
            else:
                print(f"\n  ⚠️  Order validation returned: {retcode_name}")
    
    # 6. Check Existing Positions
    print(f"\n6. EXISTING POSITIONS")
    print("-" * 70)
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        print(f"  Failed to get positions")
    elif len(positions) == 0:
        print(f"  No open positions")
    else:
        print(f"  Open positions: {len(positions)}")
        for pos in positions:
            print(f"    Ticket: {pos.ticket}, Type: {'BUY' if pos.type == 0 else 'SELL'}, "
                  f"Volume: {pos.volume}, Profit: ${pos.profit:.2f}")
    
    # 7. Summary and Recommendations
    print(f"\n" + "="*70)
    print("DIAGNOSIS SUMMARY")
    print("="*70)
    
    issues = []
    recommendations = []
    
    # Check all conditions
    if account_info and not account_info.trade_allowed:
        issues.append("Account trading not allowed")
        recommendations.append("This is the main issue - account-level restriction")
    
    if terminal_info and terminal_info.tradeapi_disabled:
        issues.append("Trade API is disabled")
        recommendations.append("Enable API trading in MT5 settings")
    
    if symbol_info and symbol_info.trade_mode == 0:
        issues.append(f"Trading disabled for {symbol}")
        recommendations.append(f"Symbol {symbol} cannot be traded on this account")
    
    if tick and (tick.bid == 0 or tick.ask == 0):
        issues.append("Market appears closed")
        recommendations.append("Wait for market to open")
    
    if issues:
        print("\n❌ ISSUES FOUND:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        
        print("\n💡 RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        
        print("\n🔧 SPECIFIC ACTIONS:")
        if "Account trading not allowed" in issues:
            print("  → This is a DEMO ACCOUNT restriction")
            print("  → Options:")
            print("     a) Create a new demo account (may have different settings)")
            print("     b) Contact Dominion Markets support")
            print("     c) Try with a live account (use caution!)")
            print("  → The account itself has trading disabled, not just AutoTrading")
    else:
        print("\n✓ No critical issues found!")
        print("  If trading still fails, try:")
        print("  1. Restart MT5 completely")
        print("  2. Reconnect to the server")
        print("  3. Try placing a manual trade first")
    
    mt5.shutdown()
    return len(issues) == 0

if __name__ == "__main__":
    success = advanced_diagnosis()
    sys.exit(0 if success else 1)
