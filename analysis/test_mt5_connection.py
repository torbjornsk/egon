import MetaTrader5 as mt5
from datetime import datetime, timedelta

# Initialize MT5
if not mt5.initialize():
    print(f"MT5 initialization failed: {mt5.last_error()}")
    quit()

print("MT5 initialized successfully!")
print(f"MT5 version: {mt5.version()}")
print(f"Terminal info: {mt5.terminal_info()}")

# Get account info
account_info = mt5.account_info()
if account_info:
    print(f"\nAccount info:")
    print(f"  Login: {account_info.login}")
    print(f"  Server: {account_info.server}")
    print(f"  Balance: {account_info.balance}")
else:
    print("\nNo account logged in")

# Try to find gold symbols
print("\nSearching for gold symbols...")
symbols = mt5.symbols_get()
gold_symbols = [s.name for s in symbols if 'XAU' in s.name or 'GOLD' in s.name.upper()]

if gold_symbols:
    print(f"Found {len(gold_symbols)} gold symbols:")
    for symbol in gold_symbols[:10]:  # Show first 10
        print(f"  - {symbol}")
else:
    print("No gold symbols found. Showing first 20 available symbols:")
    for symbol in symbols[:20]:
        print(f"  - {symbol.name}")

# Try to get data for XAUUSD
print("\nTrying to fetch XAUUSD data...")
end_date = datetime.now()
start_date = end_date - timedelta(days=7)

# Try different symbol variations
for symbol_name in ['XAUUSD.p', 'XAUUSD', 'XAUUSDm', 'GOLD', 'XAUUSD.']:
    print(f"\nTrying symbol: {symbol_name}")
    
    # Check if symbol exists
    symbol_info = mt5.symbol_info(symbol_name)
    if symbol_info is None:
        print(f"  Symbol not found")
        continue
    
    print(f"  Symbol found!")
    print(f"  Visible: {symbol_info.visible}")
    
    # Try to select it
    if not symbol_info.visible:
        if mt5.symbol_select(symbol_name, True):
            print(f"  Symbol selected successfully")
        else:
            print(f"  Failed to select symbol")
            continue
    
    # Try to get data
    rates = mt5.copy_rates_range(symbol_name, mt5.TIMEFRAME_M5, start_date, end_date)
    if rates is not None:
        print(f"  SUCCESS! Got {len(rates)} bars")
        print(f"  Latest price: {rates[-1]['close']}")
        break
    else:
        print(f"  Failed to get data: {mt5.last_error()}")

mt5.shutdown()
