"""
Analyze M5 LONG trade from 23:00 (MT5 time)
Currently at +$151, previously hit +$150, dropped to +$100
Why isn't it taking profit?
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.append('.')
from src.mt5_connector import MT5Connector
import MetaTrader5 as mt5

def compute_indicators(df):
    df = df.copy()
    
    # M5 uses different EMAs: 9/21
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    
    # RSI (14 period for M5)
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR (14 period)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Trends
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def main():
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("ANALYZING M5 LONG TRADE FROM 23:00")
    print("=" * 100)
    print()
    
    # Get M5 data from 23:00 MT5 time until now
    # MT5 time is typically UTC+2 or UTC+3
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=3)  # Get 3 hours to be safe
    
    print("Fetching M5 data...")
    df = connector.get_historical_data('XAUUSD', 'M5', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to get data")
        return
    
    print(f"Data range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    print(f"Total bars: {len(df)}")
    print()
    
    # Compute indicators
    df = compute_indicators(df)
    
    # Find entry around 23:00
    print("Looking for LONG entry signal around 23:00...")
    print()
    
    # M5 config: RSI < 25 for entry, RSI > 70 for exit
    entry_idx = None
    for i in range(20, len(df)):
        row = df.iloc[i]
        # Look for entry around 23:00 (hour == 23, minute == 0)
        if row['time'].hour == 23 and row['time'].minute == 0:
            print(f"Found 23:00 candle at index {i}: {row['time']}")
            print(f"  RSI: {row['RSI']:.2f}, Price: ${row['close']:.2f}")
            print(f"  Trend: {'UP' if row['uptrend'] else 'DOWN'}")
            
            # Check if this was an entry signal (RSI < 25)
            if row['RSI'] < 25:
                entry_idx = i
                print(f"  ✓ LONG ENTRY SIGNAL (RSI < 25)")
            else:
                print(f"  ✗ Not an entry signal (RSI not < 25)")
                # Look nearby for actual entry
                for j in range(max(0, i-5), min(len(df), i+5)):
                    nearby = df.iloc[j]
                    if nearby['RSI'] < 25:
                        entry_idx = j
                        print(f"  Found nearby entry at {nearby['time']}: RSI {nearby['RSI']:.2f}")
                        break
            break
    
    if entry_idx is None:
        print("No LONG entry found around 23:00")
        print()
        print("Showing all M5 candles from recent data:")
        for i in range(max(0, len(df)-20), len(df)):
            row = df.iloc[i]
            print(f"{row['time']} | Price: ${row['close']:.2f} | RSI: {row['RSI']:.1f} | Trend: {'UP' if row['uptrend'] else 'DOWN'}")
        connector.disconnect()
        return
    
    # Simulate the trade
    entry_row = df.iloc[entry_idx]
    entry_price = entry_row['close']
    entry_rsi = entry_row['RSI']
    entry_atr = entry_row['ATR']
    
    # M5 config
    position_size_pct = 0.15
    leverage = 25
    lev_pos = 1000 * position_size_pct * leverage  # $3,750
    
    sl = entry_price - (entry_atr * 2.0)  # LONG: SL below entry
    tp = entry_price + (entry_price * 0.01)  # LONG: TP 1% above entry
    
    print()
    print("=" * 100)
    print("TRADE SIMULATION")
    print("=" * 100)
    print(f"Entry: ${entry_price:.2f} at {entry_row['time']}")
    print(f"RSI: {entry_rsi:.2f}, ATR: ${entry_atr:.2f}")
    print(f"SL: ${sl:.2f}, TP: ${tp:.2f}")
    print(f"Position: ${lev_pos:.0f} (15% @ 25x)")
    print()
    
    max_profit = 0
    max_profit_time = None
    
    for i in range(entry_idx + 1, len(df)):
        row = df.iloc[i]
        candles_held = i - entry_idx
        minutes_held = candles_held * 5
        
        # Calculate P/L (LONG: profit when price goes up)
        price_change = row['close'] - entry_price
        pnl_pct = price_change / entry_price
        pnl = pnl_pct * lev_pos
        
        # Track max profit
        if pnl > max_profit:
            max_profit = pnl
            max_profit_time = row['time']
        
        # Check exit conditions
        exit_triggered = False
        exit_reason = None
        exit_price = None
        
        # SL hit
        if row['low'] <= sl:
            exit_triggered = True
            exit_reason = "Stop Loss"
            exit_price = sl
            pnl = ((sl - entry_price) / entry_price) * lev_pos
        # TP hit
        elif row['high'] >= tp:
            exit_triggered = True
            exit_reason = "Take Profit"
            exit_price = tp
            pnl = ((tp - entry_price) / entry_price) * lev_pos
        # RSI exit (RSI > 70 for LONG)
        elif row['RSI'] > 70:
            exit_triggered = True
            exit_reason = "RSI Exit (RSI > 70)"
            exit_price = row['close']
        
        # Show key moments
        if pnl >= 100 or exit_triggered or i == len(df) - 1:
            print(f"{row['time']} ({minutes_held} min) | Price: ${row['close']:.2f} | P/L: ${pnl:+.2f}")
            print(f"  RSI: {row['RSI']:.1f} | Trend: {'UP' if row['uptrend'] else 'DOWN'}")
            
            if exit_triggered:
                print(f"  ✓ EXIT: {exit_reason} at ${exit_price:.2f}")
                print(f"  Final P/L: ${pnl:.2f}")
                break
            elif i == len(df) - 1:
                print(f"  ⚠ STILL OPEN - No exit signal triggered")
                print()
                print("=" * 100)
                print("WHY NO EXIT?")
                print("=" * 100)
                print(f"Current RSI: {row['RSI']:.1f} (needs > 70 to exit)")
                print(f"Current Price: ${row['close']:.2f}")
                print(f"Take Profit: ${tp:.2f} (needs to reach ${tp:.2f})")
                print(f"Stop Loss: ${sl:.2f}")
                print()
                print("The position is still open because:")
                print(f"  1. RSI ({row['RSI']:.1f}) has not exceeded 70")
                print(f"  2. Price (${row['close']:.2f}) has not reached TP (${tp:.2f})")
                print(f"  3. Price has not hit SL (${sl:.2f})")
                print()
                print(f"Max profit reached: ${max_profit:.2f} at {max_profit_time}")
                print(f"Current profit: ${pnl:.2f}")
                print(f"Profit given back: ${max_profit - pnl:.2f}")
    
    print()
    print("=" * 100)
    print("ANALYSIS")
    print("=" * 100)
    print()
    print("The M5 bot uses:")
    print("  Entry: RSI < 25")
    print("  Exit: RSI > 70 OR TP (1%) OR SL (2x ATR)")
    print()
    print("The issue: RSI-based exit is too conservative for M5")
    print("  - Profit swings from +$150 to +$100 to +$151")
    print("  - RSI hasn't reached 70 to trigger exit")
    print("  - TP at 1% might be too high for current volatility")
    print()
    print("Potential solutions:")
    print("  1. Lower RSI exit threshold (e.g., 65 instead of 70)")
    print("  2. Add trailing stop to lock in profits")
    print("  3. Add time-based profit taking (e.g., take profit if +$100 after 30 min)")
    print("  4. Add adaptive exits like M1 (trend reversal while profitable)")
    
    connector.disconnect()

if __name__ == "__main__":
    main()
