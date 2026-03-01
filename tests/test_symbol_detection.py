"""
Detect the correct gold symbol for this broker
"""

import MetaTrader5 as mt5

print("\n" + "="*60)
print("GOLD SYMBOL DETECTION")
print("="*60)

if not mt5.initialize():
    print(f"✗ Failed to initialize MT5: {mt5.last_error()}")
    exit(1)

print("\nSearching for gold symbols...")

# Get all symbols
symbols = mt5.symbols_get()

# Find gold symbols
gold_symbols = []
for sym in symbols:
    name_upper = sym.name.upper()
    desc_upper = sym.description.upper()
    
    if ('XAU' in name_upper or 'GOLD' in name_upper) and 'USD' in name_upper:
        gold_symbols.append(sym)

if not gold_symbols:
    print("\n✗ No gold/USD symbols found!")
    mt5.shutdown()
    exit(1)

print(f"\n✓ Found {len(gold_symbols)} gold/USD symbol(s):\n")

for sym in gold_symbols:
    print(f"Symbol: {sym.name}")
    print(f"  Description: {sym.description}")
    print(f"  Visible: {sym.visible}")
    print(f"  Bid: {sym.bid}")
    print(f"  Ask: {sym.ask}")
    print(f"  Spread: {sym.spread}")
    print(f"  Digits: {sym.digits}")
    print(f"  Volume Min: {sym.volume_min}")
    print(f"  Volume Max: {sym.volume_max}")
    print(f"  Trade Mode: {sym.trade_mode}")
    print()

# Recommend the best one
if len(gold_symbols) == 1:
    recommended = gold_symbols[0].name
else:
    # Prefer visible symbols
    visible = [s for s in gold_symbols if s.visible]
    if visible:
        recommended = visible[0].name
    else:
        recommended = gold_symbols[0].name

print("="*60)
print(f"RECOMMENDED SYMBOL: {recommended}")
print("="*60)

print(f"\nUpdate your bot configs to use: '{recommended}'")

# Test if we can enable it
print(f"\nTesting symbol activation...")
if mt5.symbol_select(recommended, True):
    print(f"✓ Symbol {recommended} activated successfully")
    
    # Test data retrieval
    print(f"\nTesting data retrieval...")
    rates = mt5.copy_rates_from_pos(recommended, mt5.TIMEFRAME_M1, 0, 10)
    if rates is not None and len(rates) > 0:
        print(f"✓ Successfully retrieved {len(rates)} M1 bars")
        print(f"  Latest close: {rates[-1]['close']:.2f}")
    else:
        print(f"✗ Failed to retrieve data: {mt5.last_error()}")
else:
    print(f"✗ Failed to activate symbol: {mt5.last_error()}")

mt5.shutdown()
