"""
Test what the bot startup looks like
Simulates the initial data fetch and display
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

print("\n" + "="*80)
print("BOT STARTUP SIMULATION")
print("="*80)
print("Strategy: m5_scalping_balanced_aggressive")
print("Timeframe: M5 (5-minute candles)")
print("Checking every 1 second(s) for new candles")
print("="*80)

# Initialize MT5
if not mt5.initialize():
    print(f"Failed to connect to MT5: {mt5.last_error()}")
    sys.exit(1)

print("\nFetching initial data...")

# Fetch M5 data
symbol = 'XAUUSD.p'
m5_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 200)

if m5_rates is None or len(m5_rates) == 0:
    print(f"Failed to fetch data: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

# Convert to DataFrame
df = pd.DataFrame(m5_rates)
df['time'] = pd.to_datetime(df['time'], unit='s')

# Calculate indicators
df['ema_5'] = df['close'].ewm(span=5, adjust=False).mean()
df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()

delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=5).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=5).mean()
rs = gain / loss
df['rsi'] = 100 - (100 / (1 + rs))

high_low = df['high'] - df['low']
high_close = np.abs(df['high'] - df['close'].shift())
low_close = np.abs(df['low'] - df['close'].shift())
ranges = pd.concat([high_low, high_close, low_close], axis=1)
true_range = np.max(ranges, axis=1)
df['atr'] = true_range.rolling(14).mean()

# Get latest
latest = df.iloc[-1]

print(f"\nCurrent Market State:")
print(f"  Time: {latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Close: {latest['close']:.2f}")
print(f"  EMA 5: {latest['ema_5']:.2f}")
print(f"  EMA 12: {latest['ema_12']:.2f}")
print(f"  RSI: {latest['rsi']:.2f}")
print(f"  ATR: {latest['atr']:.2f}")

# Check if data is fresh
now = pd.Timestamp.now()
age_minutes = (now - latest['time']).total_seconds() / 60

if age_minutes > 10:
    print(f"\n  Market Status: CLOSED (last data {age_minutes:.0f} minutes ago)")
    print(f"  Waiting for market to open...")
else:
    print(f"\n  Market Status: OPEN")
    print(f"  Monitoring for signals...")

print("\n" + "="*80)

# Show what happens next
if age_minutes > 10:
    print("\nBot will now wait and print status every 60 seconds:")
    print(f"  Waiting for market to open... (last data: {latest['time'].strftime('%Y-%m-%d %H:%M')}, {age_minutes:.0f}min ago)")
    print(f"  Waiting for market to open... (last data: {latest['time'].strftime('%Y-%m-%d %H:%M')}, {age_minutes+1:.0f}min ago)")
    print("  ...")
else:
    print("\nBot will now monitor for new candles:")
    print(f"  Waiting for new candle... (current: {latest['time'].strftime('%H:%M')}, price: {latest['close']:.2f})")
    print("  ...")
    print("  NEW M5 CANDLE: 2026-03-03 14:40:00")
    print("  Analyzing candle...")

mt5.shutdown()
print("\n" + "="*80)
