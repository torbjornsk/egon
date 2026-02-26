import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

if not mt5.initialize():
    print("Failed to initialize")
    quit()

symbol = 'XAUUSD'
mt5.symbol_select(symbol, True)

print("Testing different methods to get maximum data...\n")

# Method 1: copy_rates_from_pos (get last N bars)
print("Method 1: copy_rates_from_pos")
for count in [10000, 50000, 100000]:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, count)
    if rates is not None:
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        print(f"  {count:6d} bars: Got {len(rates):6d} bars - {df['time'].min()} to {df['time'].max()}")
    else:
        print(f"  {count:6d} bars: FAILED - {mt5.last_error()}")

print("\nGetting maximum available data...")
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100000)
if rates is not None:
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    days_span = (df['time'].max() - df['time'].min()).days
    print(f"\nMaximum data available:")
    print(f"  Bars: {len(rates)}")
    print(f"  Date range: {df['time'].min()} to {df['time'].max()}")
    print(f"  Days span: {days_span}")
    print(f"  Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

mt5.shutdown()
