"""
Analyze the specific failed SHORT trade from 23:09 to 23:21
Goal: Determine when the bot should have recognized the signal was failing
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.append('.')
from src.mt5_connector import MT5Connector

def compute_indicators(df):
    df = df.copy()
    
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = -delta.clip(upper=0).rolling(5).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
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
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("ANALYZING FAILED SHORT TRADE: 23:09 - 23:21")
    print("=" * 100)
    print()
    
    # Get data around the trade time
    # Need historical data before 23:09 for indicators
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)  # Get 2 hours of data
    
    df = mt5.get_historical_data('XAUUSD', 'M1', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to get data")
        return
    
    # Compute indicators
    df = compute_indicators(df)
    
    # Find the trade window (23:09 to 23:21)
    # Note: MT5 time might be different from local time
    print(f"Data range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    print(f"Total bars: {len(df)}")
    print()
    
    # Get the last 30 minutes of data (should include our trade)
    recent_df = df.tail(30).copy()
    
    print("=" * 100)
    print("LAST 30 MINUTES - CANDLE BY CANDLE ANALYSIS")
    print("=" * 100)
    print()
    
    # Simulate the SHORT trade
    # Entry signal: RSI > 65 (for SHORT)
    entry_idx = None
    entry_price = None
    entry_rsi = None
    
    for i in range(len(recent_df)):
        row = recent_df.iloc[i]
        
        if entry_idx is None:
            # Look for SHORT entry signal
            if row['RSI'] > 65:
                entry_idx = i
                entry_price = row['close']
                entry_rsi = row['RSI']
                print(f"🔴 SHORT ENTRY at {row['time']}")
                print(f"   Price: ${entry_price:.2f}")
                print(f"   RSI: {entry_rsi:.2f}")
                print(f"   EMA Fast: {row['ema_fast']:.2f}, Slow: {row['ema_slow']:.2f}")
                print(f"   Trend: {'DOWN' if row['downtrend'] else 'UP'}")
                print()
                continue
        
        # Analyze each candle after entry
        if entry_idx is not None:
            minutes_held = i - entry_idx
            current_pnl = entry_price - row['close']  # SHORT: profit when price goes down
            pnl_pct = (current_pnl / entry_price) * 100
            
            # Check various exit signals
            signals = []
            
            # 1. RSI reversal (RSI drops below 35 = bullish)
            if row['RSI'] < 35:
                signals.append(f"RSI_REVERSAL({row['RSI']:.1f})")
            
            # 2. Trend reversal (EMA crossover to uptrend)
            prev_row = recent_df.iloc[i-1] if i > 0 else row
            if prev_row['downtrend'] and row['uptrend']:
                signals.append("TREND_REVERSAL")
            
            # 3. Signal fading (RSI moving back toward neutral)
            if entry_rsi > 65 and row['RSI'] < 60:
                signals.append(f"SIGNAL_FADING(RSI:{row['RSI']:.1f})")
            
            # 4. Sideways movement (price not moving much)
            price_change = abs(row['close'] - entry_price)
            if price_change < row['ATR'] * 0.2:  # Less than 20% of ATR movement
                signals.append(f"SIDEWAYS(Δ${price_change:.2f})")
            
            # 5. Price moving against us
            if current_pnl < 0:
                signals.append(f"LOSING(${current_pnl:.2f})")
            
            signal_str = ", ".join(signals) if signals else "NONE"
            
            print(f"Min {minutes_held}: {row['time']} | Price: ${row['close']:.2f} | P/L: ${current_pnl:+.2f} ({pnl_pct:+.3f}%)")
            print(f"       RSI: {row['RSI']:.1f} | Trend: {'DOWN' if row['downtrend'] else 'UP'} | Signals: {signal_str}")
            
            # Determine if we should exit
            should_exit = False
            exit_reason = None
            
            # Strategy 1: Signal fading + sideways
            if row['RSI'] < 60 and price_change < row['ATR'] * 0.3:
                should_exit = True
                exit_reason = "Signal faded + sideways movement"
            
            # Strategy 2: Trend reversal while losing
            if row['uptrend'] and current_pnl < 0:
                should_exit = True
                exit_reason = "Trend reversed to uptrend while losing"
            
            # Strategy 3: RSI reversal
            if row['RSI'] < 35:
                should_exit = True
                exit_reason = "RSI reversal (bullish signal)"
            
            if should_exit:
                print(f"       ⚠️  SHOULD EXIT: {exit_reason}")
                print()
                print("=" * 100)
                print("RECOMMENDATION")
                print("=" * 100)
                print(f"Exit at minute {minutes_held}: ${row['close']:.2f}")
                print(f"P/L: ${current_pnl:.2f} ({pnl_pct:+.3f}%)")
                print(f"Reason: {exit_reason}")
                print()
                print("ADAPTIVE EXIT RULE:")
                print("For M1 scalping, exit if:")
                print("  1. RSI signal fades (RSI < 60 for SHORT) AND")
                print("  2. Price is sideways (movement < 30% of ATR)")
                print("  OR")
                print("  3. Trend reverses against position while losing")
                break
            
            print()
    
    if entry_idx is None:
        print("No SHORT entry signal found in recent data")
        print("Showing last 10 candles for reference:")
        print()
        for i in range(max(0, len(recent_df)-10), len(recent_df)):
            row = recent_df.iloc[i]
            print(f"{row['time']} | Price: ${row['close']:.2f} | RSI: {row['RSI']:.1f} | Trend: {'DOWN' if row['downtrend'] else 'UP'}")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
