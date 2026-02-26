"""
Test the new adaptive exit strategy against the specific failed trade
Trade details: SHORT from 23:09, closed at -$54.80
Goal: Verify the new logic would have exited earlier with smaller loss
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.append('.')
from src.mt5_connector import MT5Connector

def compute_indicators(df):
    df = df.copy()
    
    # EMAs (5/12 for M1)
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    
    # RSI (5 period for M1)
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = -delta.clip(upper=0).rolling(5).mean()
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

def simulate_trade_old_logic(df, entry_idx):
    """Simulate with old logic (no adaptive exits)"""
    entry_row = df.iloc[entry_idx]
    entry_price = entry_row['close']
    entry_rsi = entry_row['RSI']
    
    # M1 config
    position_size_pct = 0.15
    leverage = 25
    lev_pos = 1000 * position_size_pct * leverage  # $3,750 leveraged position
    
    sl = entry_price + (entry_row['ATR'] * 4.0)  # SHORT: SL above entry
    tp = entry_price - (entry_price * 0.008)  # SHORT: TP below entry
    
    print("=" * 100)
    print("OLD LOGIC (No Adaptive Exits)")
    print("=" * 100)
    print(f"Entry: ${entry_price:.2f} at {entry_row['time']}")
    print(f"RSI: {entry_rsi:.2f}, Trend: {'DOWN' if entry_row['downtrend'] else 'UP'}")
    print(f"SL: ${sl:.2f}, TP: ${tp:.2f}")
    print()
    
    for i in range(entry_idx + 1, min(entry_idx + 20, len(df))):
        row = df.iloc[i]
        minutes_held = i - entry_idx
        
        # Calculate P/L (SHORT: profit when price goes down)
        price_change = entry_price - row['close']
        pnl_pct = price_change / entry_price
        pnl = pnl_pct * lev_pos
        
        # Check exit conditions (old logic)
        exit_triggered = False
        exit_reason = None
        exit_price = None
        
        # SL hit
        if row['high'] >= sl:
            exit_triggered = True
            exit_reason = "Stop Loss"
            exit_price = sl
            pnl = ((entry_price - sl) / entry_price) * lev_pos
        # TP hit
        elif row['low'] <= tp:
            exit_triggered = True
            exit_reason = "Take Profit"
            exit_price = tp
            pnl = ((entry_price - tp) / entry_price) * lev_pos
        # RSI exit (RSI < 25 for SHORT)
        elif row['RSI'] < 25:
            exit_triggered = True
            exit_reason = "RSI Exit"
            exit_price = row['close']
        
        print(f"Min {minutes_held}: {row['time']} | Price: ${row['close']:.2f} | P/L: ${pnl:+.2f}")
        print(f"       RSI: {row['RSI']:.1f} | Trend: {'DOWN' if row['downtrend'] else 'UP'}")
        
        if exit_triggered:
            print(f"       ✓ EXIT: {exit_reason} at ${exit_price:.2f}")
            print(f"       Final P/L: ${pnl:.2f}")
            print()
            return pnl, minutes_held, exit_reason
        
        print()
    
    # If we get here, position still open
    final_row = df.iloc[min(entry_idx + 19, len(df) - 1)]
    final_pnl = ((entry_price - final_row['close']) / entry_price) * lev_pos
    print(f"Position still open after 20 minutes, P/L: ${final_pnl:.2f}")
    print()
    return final_pnl, 20, "Still Open"

def simulate_trade_new_logic(df, entry_idx):
    """Simulate with new signal-based adaptive exits"""
    entry_row = df.iloc[entry_idx]
    entry_price = entry_row['close']
    entry_rsi = entry_row['RSI']
    entry_atr = entry_row['ATR']
    
    # M1 config
    position_size_pct = 0.15
    leverage = 25
    lev_pos = 1000 * position_size_pct * leverage  # $3,750 leveraged position
    
    sl = entry_price + (entry_row['ATR'] * 4.0)  # SHORT: SL above entry
    tp = entry_price - (entry_price * 0.008)  # SHORT: TP below entry
    
    print("=" * 100)
    print("NEW LOGIC (Signal-Based Adaptive Exits)")
    print("=" * 100)
    print(f"Entry: ${entry_price:.2f} at {entry_row['time']}")
    print(f"RSI: {entry_rsi:.2f}, Trend: {'DOWN' if entry_row['downtrend'] else 'UP'}")
    print(f"SL: ${sl:.2f}, TP: ${tp:.2f}")
    print()
    
    for i in range(entry_idx + 1, min(entry_idx + 20, len(df))):
        row = df.iloc[i]
        minutes_held = i - entry_idx
        
        # Calculate P/L (SHORT: profit when price goes down)
        price_change = entry_price - row['close']
        pnl_pct = price_change / entry_price
        pnl = pnl_pct * lev_pos
        
        # Check exit conditions (new logic)
        exit_triggered = False
        exit_reason = None
        exit_price = None
        
        # ADAPTIVE EXITS (only if losing and held 3+ minutes)
        if pnl < 0 and minutes_held >= 3:
            price_movement = abs(row['close'] - entry_price)
            is_sideways = price_movement < entry_atr * 0.3
            
            # Trend reversal (SHORT: uptrend is bad)
            if row['uptrend']:
                exit_triggered = True
                exit_reason = "ADAPTIVE: Trend Reversal"
                exit_price = row['close']
            # Signal fade + sideways (SHORT: RSI < 50 means signal faded)
            elif row['RSI'] < 50 and is_sideways:
                exit_triggered = True
                exit_reason = "ADAPTIVE: Signal Fade + Sideways"
                exit_price = row['close']
        
        # Time-based fallback (10 minutes)
        if not exit_triggered and pnl < 0 and minutes_held >= 10:
            exit_triggered = True
            exit_reason = "ADAPTIVE: Time Fallback"
            exit_price = row['close']
        
        # Normal exits
        if not exit_triggered:
            # SL hit
            if row['high'] >= sl:
                exit_triggered = True
                exit_reason = "Stop Loss"
                exit_price = sl
                pnl = ((entry_price - sl) / entry_price) * lev_pos
            # TP hit
            elif row['low'] <= tp:
                exit_triggered = True
                exit_reason = "Take Profit"
                exit_price = tp
                pnl = ((entry_price - tp) / entry_price) * lev_pos
            # RSI exit (RSI < 25 for SHORT)
            elif row['RSI'] < 25:
                exit_triggered = True
                exit_reason = "RSI Exit"
                exit_price = row['close']
        
        # Show signals
        signals = []
        if pnl < 0:
            signals.append(f"LOSING(${pnl:.2f})")
        if row['uptrend']:
            signals.append("UPTREND")
        if row['RSI'] < 50:
            signals.append(f"RSI_FADE({row['RSI']:.1f})")
        
        signal_str = ", ".join(signals) if signals else "NONE"
        
        print(f"Min {minutes_held}: {row['time']} | Price: ${row['close']:.2f} | P/L: ${pnl:+.2f}")
        print(f"       RSI: {row['RSI']:.1f} | Trend: {'DOWN' if row['downtrend'] else 'UP'} | Signals: {signal_str}")
        
        if exit_triggered:
            print(f"       ✓ EXIT: {exit_reason} at ${exit_price:.2f}")
            print(f"       Final P/L: ${pnl:.2f}")
            print()
            return pnl, minutes_held, exit_reason
        
        print()
    
    # If we get here, position still open
    final_row = df.iloc[min(entry_idx + 19, len(df) - 1)]
    final_pnl = ((entry_price - final_row['close']) / entry_price) * lev_pos
    print(f"Position still open after 20 minutes, P/L: ${final_pnl:.2f}")
    print()
    return final_pnl, 20, "Still Open"

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("TESTING NEW ADAPTIVE EXITS AGAINST SPECIFIC FAILED TRADE")
    print("=" * 100)
    print()
    print("Trade Details:")
    print("  Type: SHORT")
    print("  Entry Time: ~23:09 (MT5 time)")
    print("  Actual Loss: -$54.80")
    print()
    
    # Get recent M1 data (last 2 hours)
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)
    
    print("Fetching M1 data...")
    df = mt5.get_historical_data('XAUUSD', 'M1', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to get data")
        return
    
    print(f"Data range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    print(f"Total bars: {len(df)}")
    print()
    
    # Compute indicators
    df = compute_indicators(df)
    
    # Find SHORT entry signal in recent data
    # Look for RSI > 65 with downtrend
    entry_idx = None
    for i in range(50, len(df) - 20):  # Need room before and after
        row = df.iloc[i]
        if row['RSI'] > 65 and row['downtrend']:
            entry_idx = i
            print(f"Found SHORT entry signal at index {i}: {row['time']}")
            print(f"  RSI: {row['RSI']:.2f}, Price: ${row['close']:.2f}")
            print()
            break
    
    if entry_idx is None:
        print("No SHORT entry signal found in recent data")
        print("Showing last 10 candles:")
        for i in range(max(0, len(df)-10), len(df)):
            row = df.iloc[i]
            print(f"{row['time']} | Price: ${row['close']:.2f} | RSI: {row['RSI']:.1f} | Trend: {'DOWN' if row['downtrend'] else 'UP'}")
        mt5.disconnect()
        return
    
    # Simulate with old logic
    old_pnl, old_minutes, old_reason = simulate_trade_old_logic(df, entry_idx)
    
    # Simulate with new logic
    new_pnl, new_minutes, new_reason = simulate_trade_new_logic(df, entry_idx)
    
    # Compare results
    print("=" * 100)
    print("COMPARISON")
    print("=" * 100)
    print(f"Old Logic: ${old_pnl:.2f} loss after {old_minutes} minutes ({old_reason})")
    print(f"New Logic: ${new_pnl:.2f} {'loss' if new_pnl < 0 else 'profit'} after {new_minutes} minutes ({new_reason})")
    print()
    
    if new_pnl > old_pnl:
        improvement = old_pnl - new_pnl  # Both negative, so this gives positive improvement
        improvement_pct = (improvement / abs(old_pnl)) * 100 if old_pnl != 0 else 0
        print(f"✅ IMPROVEMENT: ${improvement:.2f} saved ({improvement_pct:.1f}% reduction in loss)")
        print(f"   Exited {old_minutes - new_minutes} minutes earlier")
    elif new_pnl == old_pnl:
        print("⚠ NO CHANGE: Same result with both strategies")
    else:
        print("❌ WORSE: New logic performed worse (unexpected)")
    
    print()
    print("CONCLUSION:")
    if new_pnl > old_pnl and new_minutes < old_minutes:
        print("✅ New adaptive exits would have prevented this loss!")
        print(f"   Exit reason: {new_reason}")
        print(f"   Time saved: {old_minutes - new_minutes} minutes")
    else:
        print("⚠ Results may vary - test on more data for validation")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
