"""
Fix "Trade disabled" error (10017) in MT5
This script checks and enables trading for XAUUSD.p
"""

import MetaTrader5 as mt5
import sys

def check_and_fix_trading():
    """Check trading status and attempt to enable it"""
    
    print("="*60)
    print("MT5 Trading Status Checker")
    print("="*60)
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return False
    
    print("✓ MT5 initialized")
    
    # Check account info
    account_info = mt5.account_info()
    if account_info is None:
        print("❌ Failed to get account info")
        mt5.shutdown()
        return False
    
    print(f"\nAccount Information:")
    print(f"  Login: {account_info.login}")
    print(f"  Server: {account_info.server}")
    print(f"  Balance: ${account_info.balance:.2f}")
    print(f"  Trade Allowed: {account_info.trade_allowed}")
    print(f"  Trade Expert: {account_info.trade_expert}")
    
    if not account_info.trade_allowed:
        print("\n⚠️  WARNING: Trading is not allowed on this account!")
        print("   This is usually because:")
        print("   1. AutoTrading is disabled in MT5")
        print("   2. Account is read-only")
        print("   3. Account has trading restrictions")
    
    if not account_info.trade_expert:
        print("\n⚠️  WARNING: Expert Advisor trading is not allowed!")
        print("   Enable AutoTrading in MT5:")
        print("   - Click the 'AutoTrading' button in MT5 toolbar")
        print("   - Or press Ctrl+E")
    
    # Check symbol
    symbol = 'XAUUSD.p'
    print(f"\nSymbol Information: {symbol}")
    
    # Try to select symbol
    if not mt5.symbol_select(symbol, True):
        print(f"❌ Failed to select symbol {symbol}")
        print(f"   Error: {mt5.last_error()}")
        
        # Try alternative symbol
        alt_symbol = 'XAUUSD'
        print(f"\nTrying alternative symbol: {alt_symbol}")
        if mt5.symbol_select(alt_symbol, True):
            print(f"✓ Alternative symbol {alt_symbol} works!")
            print(f"  Update your bot to use '{alt_symbol}' instead of '{symbol}'")
            symbol = alt_symbol
        else:
            print(f"❌ Alternative symbol also failed")
            mt5.shutdown()
            return False
    else:
        print(f"✓ Symbol {symbol} selected")
    
    # Get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"❌ Failed to get symbol info")
        mt5.shutdown()
        return False
    
    print(f"\nSymbol Trading Status:")
    print(f"  Visible: {symbol_info.visible}")
    print(f"  Trade Mode: {symbol_info.trade_mode}")
    print(f"  Trade Allowed: {symbol_info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED}")
    
    # Trade mode meanings
    trade_modes = {
        0: "DISABLED - Trading disabled",
        1: "LONGONLY - Only long positions allowed",
        2: "SHORTONLY - Only short positions allowed", 
        3: "CLOSEONLY - Only closing positions allowed",
        4: "FULL - Full trading allowed"
    }
    
    mode_desc = trade_modes.get(symbol_info.trade_mode, "UNKNOWN")
    print(f"  Mode Description: {mode_desc}")
    
    if symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        print("\n❌ PROBLEM FOUND: Trading is DISABLED for this symbol!")
        print("   Possible solutions:")
        print("   1. This is a demo account - trading may be restricted")
        print("   2. Market is closed - wait for market to open")
        print("   3. Symbol is not available for trading on this account")
        print("   4. Contact your broker to enable trading")
    elif symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY:
        print("\n⚠️  WARNING: Only closing positions is allowed!")
        print("   This usually means market is about to close or has closed")
    elif symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
        print("\n✓ Full trading is allowed for this symbol")
    
    # Check market hours
    print(f"\nMarket Hours:")
    print(f"  Session Deals: {symbol_info.session_deals}")
    print(f"  Session Buy Orders: {symbol_info.session_buy_orders}")
    print(f"  Session Sell Orders: {symbol_info.session_sell_orders}")
    
    # Get current tick
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"\n⚠️  WARNING: No tick data available")
        print(f"   Market may be closed")
    else:
        print(f"\nCurrent Prices:")
        print(f"  Bid: {tick.bid}")
        print(f"  Ask: {tick.ask}")
        print(f"  Spread: {tick.ask - tick.bid:.2f}")
        
        if tick.bid == 0 or tick.ask == 0:
            print(f"\n⚠️  WARNING: Invalid prices (0)")
            print(f"   Market is likely closed")
    
    # Check terminal info
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"\nTerminal Status:")
        print(f"  Trade Allowed: {terminal_info.trade_allowed}")
        print(f"  Connected: {terminal_info.connected}")
        
        if not terminal_info.trade_allowed:
            print(f"\n❌ PROBLEM: AutoTrading is DISABLED in MT5!")
            print(f"   SOLUTION: Enable AutoTrading:")
            print(f"   1. Look for 'AutoTrading' button in MT5 toolbar")
            print(f"   2. Click it to enable (should turn green)")
            print(f"   3. Or press Ctrl+E")
            print(f"   4. Restart your bot")
    
    # Summary
    print("\n" + "="*60)
    print("DIAGNOSIS SUMMARY")
    print("="*60)
    
    issues = []
    
    if not account_info.trade_allowed:
        issues.append("❌ Account trading not allowed")
    
    if not account_info.trade_expert:
        issues.append("❌ Expert Advisor trading not allowed")
    
    if terminal_info and not terminal_info.trade_allowed:
        issues.append("❌ AutoTrading disabled in MT5 terminal")
    
    if symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        issues.append(f"❌ Trading disabled for {symbol}")
    
    if tick and (tick.bid == 0 or tick.ask == 0):
        issues.append("❌ Market appears to be closed")
    
    if issues:
        print("\nIssues Found:")
        for issue in issues:
            print(f"  {issue}")
        
        print("\nRECOMMENDED ACTIONS:")
        print("1. Enable AutoTrading in MT5 (Ctrl+E or toolbar button)")
        print("2. Verify market is open (gold trades 24/5, closed weekends)")
        print("3. Check if demo account has trading restrictions")
        print("4. Try placing a manual trade in MT5 to verify")
        print("5. Contact broker if issues persist")
    else:
        print("\n✓ No issues found - trading should work!")
        print("  If you still get errors, try:")
        print("  1. Restart MT5")
        print("  2. Restart your bot")
        print("  3. Check bot logs for other errors")
    
    mt5.shutdown()
    return len(issues) == 0

if __name__ == "__main__":
    success = check_and_fix_trading()
    sys.exit(0 if success else 1)
