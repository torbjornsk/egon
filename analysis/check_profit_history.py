"""
Check the profit history of the M5 position to see peak and decline
"""

import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.append('.')
from src.mt5_connector import MT5Connector
from src.timezone_utils import mt5_to_local, format_time_local
import MetaTrader5 as mt5

def compute_indicators(df):
    df = df.copy()
    
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    
    return df

def main():
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("M5 POSITION PROFIT HISTORY ANALYSIS")
    print("=" * 100)
    print()
    
    # Get position
    positions = mt5.positions_get(symbol='XAUUSD')
    m5_position = None
    
    for pos in positions:
        if pos.magic == 234000:
            m5_position = pos
            break
    
    if m5_position is None:
        print("No M5 position found")
        connector.disconnect()
        return
    
    entry_price = m5_position.price_open
    # Convert MT5 timestamp to local timezone (handles DST automatically)
    entry_time = mt5_to_local(m5_position.time)
    current_profit = m5_position.profit
    
    print(f"Position Details:")
    print(f"  Entry: ${entry_price:.2f} at {entry_time}")
    print(f"  Current Profit: ${current_profit:.2f}")
    print()
    
    # Get M5 data since entry
    end_time = datetime.now()
    start_time = entry_time - timedelta(minutes=30)  # Get some data before entry
    
    df = connector.get_historical_data('XAUUSD', 'M5', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to get data")
        connector.disconnect()
        return
    
    df = compute_indicators(df)
    
    # Find entry candle
    entry_idx = None
    for i, row in df.iterrows():
        if abs((row['time'] - entry_time).total_seconds()) < 300:  # Within 5 minutes
            entry_idx = i
            break
    
    if entry_idx is None:
        print("Could not find entry candle in data")
        connector.disconnect()
        return
    
    print("=" * 100)
    print("PROFIT HISTORY SINCE ENTRY")
    print("=" * 100)
    print()
    
    # Calculate profit at each candle
    position_size_pct = 0.15
    leverage = 25
    lev_pos = 1000 * position_size_pct * leverage  # Assuming $1000 starting balance
    
    profit_history = []
    peak_profit = 0
    peak_time = None
    
    for i in range(entry_idx, len(df)):
        row = df.iloc[i]
        
        # Calculate profit
        price_change = row['close'] - entry_price
        pnl_pct = price_change / entry_price
        pnl = pnl_pct * lev_pos
        
        profit_history.append({
            'time': row['time'],
            'price': row['close'],
            'profit': pnl,
            'rsi': row['RSI'],
            'trend': 'UP' if row['uptrend'] else 'DOWN'
        })
        
        if pnl > peak_profit:
            peak_profit = pnl
            peak_time = row['time']
    
    # Show profit progression
    print(f"{'Time':<20} | {'Price':>10} | {'Profit':>10} | {'RSI':>6} | {'Trend':>5} | Notes")
    print("-" * 100)
    
    for record in profit_history:
        is_peak = (record['profit'] == peak_profit)
        is_current = (record == profit_history[-1])
        
        marker = ""
        if is_peak:
            marker = "← PEAK"
        elif is_current:
            marker = "← CURRENT"
        
        print(f"{record['time']} | ${record['price']:>9.2f} | ${record['profit']:>9.2f} | {record['rsi']:>5.1f} | {record['trend']:>5} | {marker}")
    
    print()
    print("=" * 100)
    print("ANALYSIS")
    print("=" * 100)
    print()
    
    current_profit_val = profit_history[-1]['profit']
    decline = peak_profit - current_profit_val
    decline_pct = (decline / peak_profit) * 100 if peak_profit > 0 else 0
    
    print(f"Peak Profit: ${peak_profit:.2f} at {peak_time}")
    print(f"Current Profit: ${current_profit_val:.2f}")
    print(f"Decline: ${decline:.2f} ({decline_pct:.1f}%)")
    print()
    
    print("Adaptive Exit Conditions:")
    print(f"  1. Profit > $100: {peak_profit > 100} (peak was ${peak_profit:.2f})")
    print(f"  2. Declined 30% from peak: {decline_pct > 30} (declined {decline_pct:.1f}%)")
    print()
    
    if peak_profit > 100 and decline_pct > 30:
        print("✅ SHOULD HAVE EXITED: Both conditions met!")
        print(f"   Bot should have exited when profit dropped below ${peak_profit * 0.7:.2f}")
        print()
        print("   Possible reasons it didn't:")
        print("   1. Bot was restarted and lost peak profit tracking")
        print("   2. Peak profit tracker not persisting across restarts")
        print("   3. Adaptive exit logic not checking correctly")
    elif peak_profit > 100:
        print(f"⚠ CLOSE TO EXIT: Peak > $100 but only declined {decline_pct:.1f}%")
        print(f"   Will exit if profit drops below ${peak_profit * 0.7:.2f}")
    else:
        print(f"❌ NOT READY TO EXIT: Peak profit ${peak_profit:.2f} < $100 threshold")
        print(f"   Adaptive exit only activates when profit exceeds $100")
    
    connector.disconnect()

if __name__ == "__main__":
    main()
