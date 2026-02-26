"""
Find the SHORT trade that matches the actual -$54.80 loss
Look for trades around 23:09 that would result in ~$55 loss
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.append('.')
from src.mt5_connector import MT5Connector

def compute_indicators(df):
    df = df.copy()
    
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = -delta.clip(upper=0).rolling(5).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def simulate_trade(df, entry_idx, max_minutes=15):
    """Simulate a SHORT trade and return P/L"""
    entry_row = df.iloc[entry_idx]
    entry_price = entry_row['close']
    entry_atr = entry_row['ATR']
    
    position_size_pct = 0.15
    leverage = 25
    lev_pos = 1000 * position_size_pct * leverage
    
    sl = entry_price + (entry_atr * 4.0)
    tp = entry_price - (entry_price * 0.008)
    
    for i in range(entry_idx + 1, min(entry_idx + max_minutes + 1, len(df))):
        row = df.iloc[i]
        minutes_held = i - entry_idx
        
        # Check if SL hit
        if row['high'] >= sl:
            pnl = ((entry_price - sl) / entry_price) * lev_pos
            return pnl, minutes_held, "SL", entry_price, sl
        
        # Check if TP hit
        if row['low'] <= tp:
            pnl = ((entry_price - tp) / entry_price) * lev_pos
            return pnl, minutes_held, "TP", entry_price, tp
        
        # Check RSI exit
        if row['RSI'] < 25:
            pnl = ((entry_price - row['close']) / entry_price) * lev_pos
            return pnl, minutes_held, "RSI", entry_price, row['close']
    
    # Still open
    final_row = df.iloc[min(entry_idx + max_minutes, len(df) - 1)]
    pnl = ((entry_price - final_row['close']) / entry_price) * lev_pos
    return pnl, max_minutes, "OPEN", entry_price, final_row['close']

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("FINDING TRADE THAT MATCHES -$54.80 LOSS")
    print("=" * 100)
    print()
    
    # Get last 2 hours of data
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)
    
    df = mt5.get_historical_data('XAUUSD', 'M1', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to get data")
        return
    
    print(f"Data range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    print(f"Total bars: {len(df)}")
    print()
    
    df = compute_indicators(df)
    
    # Look for all potential SHORT entries
    print("Searching for SHORT entries that could result in ~$55 loss...")
    print()
    
    candidates = []
    
    for i in range(50, len(df) - 15):
        row = df.iloc[i]
        
        # SHORT entry conditions: RSI > 65 OR RSI > 60 with downtrend
        if row['RSI'] > 60:
            pnl, minutes, reason, entry, exit = simulate_trade(df, i, max_minutes=15)
            
            # Look for losses between $40 and $70
            if -70 < pnl < -40:
                candidates.append({
                    'time': row['time'],
                    'entry_price': entry,
                    'exit_price': exit,
                    'pnl': pnl,
                    'minutes': minutes,
                    'reason': reason,
                    'entry_rsi': row['RSI'],
                    'entry_trend': 'DOWN' if row['downtrend'] else 'UP',
                    'index': i
                })
    
    if not candidates:
        print("No trades found matching the loss profile")
        print()
        print("Showing all SHORT signals in recent data:")
        for i in range(max(0, len(df) - 30), len(df)):
            row = df.iloc[i]
            if row['RSI'] > 60:
                print(f"{row['time']} | RSI: {row['RSI']:.1f} | Price: ${row['close']:.2f} | Trend: {'DOWN' if row['downtrend'] else 'UP'}")
    else:
        print(f"Found {len(candidates)} potential matches:")
        print()
        
        for idx, trade in enumerate(candidates, 1):
            print(f"{idx}. Entry: {trade['time']} at ${trade['entry_price']:.2f}")
            print(f"   RSI: {trade['entry_rsi']:.1f}, Trend: {trade['entry_trend']}")
            print(f"   Exit: ${trade['exit_price']:.2f} after {trade['minutes']} min ({trade['reason']})")
            print(f"   P/L: ${trade['pnl']:.2f}")
            print()
        
        # Test the closest match with new logic
        closest = min(candidates, key=lambda x: abs(x['pnl'] + 54.80))
        print("=" * 100)
        print(f"CLOSEST MATCH: {closest['time']} (P/L: ${closest['pnl']:.2f})")
        print("=" * 100)
        print()
        
        # Now simulate with new adaptive logic
        entry_idx = closest['index']
        entry_row = df.iloc[entry_idx]
        entry_price = entry_row['close']
        entry_atr = entry_row['ATR']
        
        position_size_pct = 0.15
        leverage = 25
        lev_pos = 1000 * position_size_pct * leverage
        
        sl = entry_price + (entry_atr * 4.0)
        tp = entry_price - (entry_price * 0.008)
        
        print("Testing with NEW ADAPTIVE LOGIC:")
        print(f"Entry: ${entry_price:.2f}, SL: ${sl:.2f}, TP: ${tp:.2f}")
        print()
        
        for i in range(entry_idx + 1, min(entry_idx + 16, len(df))):
            row = df.iloc[i]
            minutes_held = i - entry_idx
            
            price_change = entry_price - row['close']
            pnl_pct = price_change / entry_price
            pnl = pnl_pct * lev_pos
            
            exit_triggered = False
            exit_reason = None
            
            # Adaptive exits (losing + 3+ minutes)
            if pnl < 0 and minutes_held >= 3:
                price_movement = abs(row['close'] - entry_price)
                is_sideways = price_movement < entry_atr * 0.3
                
                if row['uptrend']:
                    exit_triggered = True
                    exit_reason = "ADAPTIVE: Trend Reversal"
                elif row['RSI'] < 50 and is_sideways:
                    exit_triggered = True
                    exit_reason = "ADAPTIVE: Signal Fade"
            
            # Time fallback
            if not exit_triggered and pnl < 0 and minutes_held >= 10:
                exit_triggered = True
                exit_reason = "ADAPTIVE: Time Fallback"
            
            # Normal exits
            if not exit_triggered:
                if row['high'] >= sl:
                    exit_triggered = True
                    exit_reason = "Stop Loss"
                    pnl = ((entry_price - sl) / entry_price) * lev_pos
                elif row['low'] <= tp:
                    exit_triggered = True
                    exit_reason = "Take Profit"
                    pnl = ((entry_price - tp) / entry_price) * lev_pos
                elif row['RSI'] < 25:
                    exit_triggered = True
                    exit_reason = "RSI Exit"
            
            print(f"Min {minutes_held}: ${row['close']:.2f} | P/L: ${pnl:+.2f} | RSI: {row['RSI']:.1f} | {'UP' if row['uptrend'] else 'DOWN'}")
            
            if exit_triggered:
                print(f"   ✓ EXIT: {exit_reason}")
                print()
                print("=" * 100)
                print("RESULT")
                print("=" * 100)
                print(f"Old Logic: ${closest['pnl']:.2f} after {closest['minutes']} min")
                print(f"New Logic: ${pnl:.2f} after {minutes_held} min")
                
                if pnl > closest['pnl']:
                    saved = closest['pnl'] - pnl
                    print(f"✅ SAVED: ${saved:.2f} ({abs(saved/closest['pnl']*100):.1f}% reduction)")
                    print(f"   Exited {closest['minutes'] - minutes_held} minutes earlier")
                else:
                    print("⚠ No improvement on this specific trade")
                
                break
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
