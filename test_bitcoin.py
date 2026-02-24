import MetaTrader5 as mt5
from datetime import datetime, timedelta

# Initialize MT5
if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

print("Searching for Bitcoin symbols...")
print()

# Common Bitcoin symbol names
btc_symbols = ['BTCUSD', 'BTCUSDT', 'BTC', 'BITCOIN', 'XBTUSD']

found_symbols = []

# Search for Bitcoin symbols
all_symbols = mt5.symbols_get()
for symbol in all_symbols:
    if any(btc in symbol.name.upper() for btc in ['BTC', 'BITCOIN']):
        found_symbols.append(symbol.name)

if found_symbols:
    print(f"Found {len(found_symbols)} Bitcoin symbols:")
    for sym in found_symbols:
        print(f"  - {sym}")
        
        # Try to get info
        info = mt5.symbol_info(sym)
        if info:
            print(f"    Visible: {info.visible}")
            print(f"    Trade allowed: {info.trade_mode != 0}")
            
            # Try to get recent data
            if not info.visible:
                mt5.symbol_select(sym, True)
            
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 100)
            if rates is not None and len(rates) > 0:
                import pandas as pd
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                latest_price = df['close'].iloc[-1]
                print(f"    Latest price: ${latest_price:,.2f}")
                print(f"    Data available: Yes ({len(rates)} bars)")
                
                # Calculate volatility
                returns = df['close'].pct_change()
                volatility = returns.std() * 100
                print(f"    Volatility: {volatility:.2f}% per 5min bar")
            else:
                print(f"    Data available: No")
        print()
else:
    print("No Bitcoin symbols found on this broker")
    print()
    print("Your broker may not offer Bitcoin trading.")
    print("Consider using a crypto-focused broker or exchange.")

mt5.shutdown()
