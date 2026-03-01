"""
Test if bot can fetch and process data correctly
Simulates what the M1 bot does
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

print("\n" + "="*60)
print("BOT DATA FETCH TEST")
print("="*60)

# Initialize MT5
if not mt5.initialize():
    print(f"✗ Failed to initialize MT5: {mt5.last_error()}")
    sys.exit(1)

print("✓ MT5 initialized")

# Test symbol
symbol = 'XAUUSD.p'

# Check symbol info
print(f"\nChecking symbol: {symbol}")
symbol_info = mt5.symbol_info(symbol)

if symbol_info is None:
    print(f"✗ Symbol not found: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

print(f"✓ Symbol found: {symbol_info.description}")
print(f"  Bid: {symbol_info.bid}")
print(f"  Ask: {symbol_info.ask}")
print(f"  Visible: {symbol_info.visible}")

# Enable symbol if not visible
if not symbol_info.visible:
    print(f"\n  Enabling symbol...")
    if mt5.symbol_select(symbol, True):
        print(f"  ✓ Symbol enabled")
    else:
        print(f"  ✗ Failed to enable: {mt5.last_error()}")

# Test M1 data fetch (what the bot does)
print(f"\nFetching M1 data (200 bars)...")
m1_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 200)

if m1_rates is None or len(m1_rates) == 0:
    print(f"✗ Failed to fetch M1 data: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

print(f"✓ Fetched {len(m1_rates)} M1 bars")

# Convert to DataFrame (what the bot does)
m1_data = pd.DataFrame(m1_rates)
m1_data['time'] = pd.to_datetime(m1_data['time'], unit='s')

print(f"\nM1 Data Summary:")
print(f"  Period: {m1_data['time'].min()} to {m1_data['time'].max()}")
print(f"  Latest time: {m1_data['time'].iloc[-1]}")
print(f"  Latest close: {m1_data['close'].iloc[-1]:.2f}")
print(f"  Latest volume: {m1_data['tick_volume'].iloc[-1]}")

# Check if data is recent
latest_time = m1_data['time'].iloc[-1]
now = pd.Timestamp.now()
age_minutes = (now - latest_time).total_seconds() / 60

print(f"\nData Freshness:")
print(f"  Current time: {now}")
print(f"  Latest bar: {latest_time}")
print(f"  Age: {age_minutes:.1f} minutes")

if age_minutes > 5:
    print(f"  ⚠️  Data is {age_minutes:.1f} minutes old (market might be closed)")
else:
    print(f"  ✓ Data is fresh")

# Test M5 data fetch
print(f"\nFetching M5 data (200 bars)...")
m5_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 200)

if m5_rates is None or len(m5_rates) == 0:
    print(f"✗ Failed to fetch M5 data: {mt5.last_error()}")
else:
    m5_data = pd.DataFrame(m5_rates)
    m5_data['time'] = pd.to_datetime(m5_data['time'], unit='s')
    print(f"✓ Fetched {len(m5_data)} M5 bars")
    print(f"  Period: {m5_data['time'].min()} to {m5_data['time'].max()}")
    print(f"  Latest close: {m5_data['close'].iloc[-1]:.2f}")

# Test indicator calculation (what the bot does)
print(f"\nTesting indicator calculation...")

try:
    # Calculate EMAs
    m1_data['ema_5'] = m1_data['close'].ewm(span=5, adjust=False).mean()
    m1_data['ema_12'] = m1_data['close'].ewm(span=12, adjust=False).mean()
    
    # Calculate RSI
    delta = m1_data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=5).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=5).mean()
    rs = gain / loss
    m1_data['rsi'] = 100 - (100 / (1 + rs))
    
    # Calculate ATR
    high_low = m1_data['high'] - m1_data['low']
    high_close = np.abs(m1_data['high'] - m1_data['close'].shift())
    low_close = np.abs(m1_data['low'] - m1_data['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    m1_data['atr'] = true_range.rolling(14).mean()
    
    print(f"✓ Indicators calculated successfully")
    
    # Show latest values
    latest = m1_data.iloc[-1]
    print(f"\nLatest Indicator Values:")
    print(f"  Close: {latest['close']:.2f}")
    print(f"  EMA 5: {latest['ema_5']:.2f}")
    print(f"  EMA 12: {latest['ema_12']:.2f}")
    print(f"  RSI: {latest['rsi']:.2f}")
    print(f"  ATR: {latest['atr']:.2f}")
    
    # Check for NaN values
    nan_count = m1_data[['ema_5', 'ema_12', 'rsi', 'atr']].isna().sum().sum()
    if nan_count > 0:
        print(f"\n  ⚠️  {nan_count} NaN values in indicators (normal for first few bars)")
    else:
        print(f"\n  ✓ No NaN values in indicators")
    
except Exception as e:
    print(f"✗ Failed to calculate indicators: {e}")

# Test signal generation (simplified)
print(f"\nTesting signal generation...")

try:
    # Remove NaN rows
    clean_data = m1_data.dropna()
    
    if len(clean_data) < 10:
        print(f"✗ Not enough clean data ({len(clean_data)} bars)")
    else:
        latest = clean_data.iloc[-1]
        prev = clean_data.iloc[-2]
        
        # Check for bullish signal
        ema_cross_up = (latest['ema_5'] > latest['ema_12']) and (prev['ema_5'] <= prev['ema_12'])
        rsi_ok = 30 < latest['rsi'] < 70
        
        print(f"✓ Signal check complete")
        print(f"  EMA 5 > EMA 12: {latest['ema_5'] > latest['ema_12']}")
        print(f"  EMA Cross Up: {ema_cross_up}")
        print(f"  RSI OK (30-70): {rsi_ok} (RSI: {latest['rsi']:.1f})")
        
        if ema_cross_up and rsi_ok:
            print(f"\n  🔔 BULLISH SIGNAL DETECTED!")
        else:
            print(f"\n  No signal at this time")
        
except Exception as e:
    print(f"✗ Failed signal generation: {e}")

# Check account info
print(f"\nChecking account info...")
account_info = mt5.account_info()

if account_info is None:
    print(f"✗ Failed to get account info: {mt5.last_error()}")
else:
    print(f"✓ Account info retrieved")
    print(f"  Balance: ${account_info.balance:,.2f}")
    print(f"  Equity: ${account_info.equity:,.2f}")
    print(f"  Free Margin: ${account_info.margin_free:,.2f}")
    print(f"  Leverage: 1:{account_info.leverage}")

# Check if trading is allowed
print(f"\nChecking trading status...")
terminal_info = mt5.terminal_info()

if terminal_info is None:
    print(f"✗ Failed to get terminal info: {mt5.last_error()}")
else:
    print(f"  Connected: {terminal_info.connected}")
    print(f"  Trade Allowed: {terminal_info.trade_allowed}")
    
    if not terminal_info.trade_allowed:
        print(f"  ⚠️  Trading is not allowed (might be weekend/market closed)")
    else:
        print(f"  ✓ Trading is allowed")

# Summary
print(f"\n" + "="*60)
print("SUMMARY")
print("="*60)

issues = []

if m1_rates is None or len(m1_rates) == 0:
    issues.append("Cannot fetch M1 data")

if age_minutes > 5:
    issues.append(f"Data is {age_minutes:.1f} minutes old (market closed?)")

if not terminal_info.trade_allowed:
    issues.append("Trading not allowed (weekend/market closed)")

if issues:
    print("\n⚠️  Issues detected:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("\n✓ Everything looks good!")
    print("  Bot should be able to fetch data and generate signals")

mt5.shutdown()
print("\n✓ Test complete")
