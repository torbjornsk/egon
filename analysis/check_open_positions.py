"""
Check actual open positions in MT5 and analyze them
"""

import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.append('.')
from src.mt5_connector import MT5Connector
import MetaTrader5 as mt5

def compute_indicators(df):
    df = df.copy()
    
    # M5 EMAs
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    
    # RSI (14 period)
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
    print("CHECKING OPEN POSITIONS")
    print("=" * 100)
    print()
    
    # Get all open positions
    positions = mt5.positions_get(symbol='XAUUSD')
    
    if positions is None or len(positions) == 0:
        print("No open positions found")
        connector.disconnect()
        return
    
    print(f"Found {len(positions)} open position(s):")
    print()
    
    for pos in positions:
        pos_type = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        time_open = datetime.fromtimestamp(pos.time)
        time_held = datetime.now() - time_open
        minutes_held = time_held.total_seconds() / 60
        
        print(f"Position: {pos_type}")
        print(f"  Ticket: {pos.ticket}")
        print(f"  Entry Price: ${pos.price_open:.2f}")
        print(f"  Current Price: ${pos.price_current:.2f}")
        print(f"  SL: ${pos.sl:.2f}, TP: ${pos.tp:.2f}")
        print(f"  Volume: {pos.volume} lots")
        print(f"  Profit: ${pos.profit:.2f}")
        print(f"  Opened: {time_open} ({minutes_held:.0f} minutes ago)")
        print(f"  Magic: {pos.magic}")
        print()
        
        # Determine which bot (M1 = 234001, M5 = 234000)
        bot_type = "M1" if pos.magic == 234001 else "M5" if pos.magic == 234000 else "Unknown"
        print(f"  Bot: {bot_type}")
        print()
        
        # Get current market data
        if bot_type == "M5":
            timeframe = 'M5'
            print("  Analyzing M5 position...")
            print()
            
            # Get M5 data
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=4)
            df = connector.get_historical_data('XAUUSD', 'M5', start_time, end_time)
            
            if df is not None and len(df) > 0:
                df = compute_indicators(df)
                latest = df.iloc[-1]
                
                print(f"  Current Market Conditions:")
                print(f"    RSI: {latest['RSI']:.1f}")
                print(f"    Trend: {'UP' if latest['uptrend'] else 'DOWN'}")
                print(f"    EMA Fast: ${latest['ema_fast']:.2f}")
                print(f"    EMA Slow: ${latest['ema_slow']:.2f}")
                print()
                
                # M5 exit conditions
                print(f"  M5 Exit Conditions:")
                print(f"    RSI > 70: {latest['RSI']:.1f} > 70 = {latest['RSI'] > 70}")
                print(f"    Price >= TP: ${latest['close']:.2f} >= ${pos.tp:.2f} = {latest['close'] >= pos.tp}")
                print(f"    Price <= SL: ${latest['close']:.2f} <= ${pos.sl:.2f} = {latest['close'] <= pos.sl}")
                print()
                
                if pos_type == "LONG":
                    if latest['RSI'] < 70:
                        print(f"  ⚠ Position NOT exiting: RSI ({latest['RSI']:.1f}) below exit threshold (70)")
                        print(f"     RSI needs to rise {70 - latest['RSI']:.1f} more points")
                    
                    if latest['close'] < pos.tp:
                        tp_distance = pos.tp - latest['close']
                        tp_pct = (tp_distance / latest['close']) * 100
                        print(f"  ⚠ Position NOT exiting: Price ${tp_distance:.2f} ({tp_pct:.2f}%) below TP")
                    
                    print()
                    print(f"  Profit History:")
                    print(f"    Current: ${pos.profit:.2f}")
                    print(f"    You mentioned: +$150 peak, dropped to +$100, now +$151")
                    print()
                    print(f"  ISSUE: M5 bot waiting for RSI > 70 or TP hit")
                    print(f"         RSI is only {latest['RSI']:.1f}, so position stays open")
                    print(f"         Profit is fluctuating but no exit signal triggered")
        
        elif bot_type == "M1":
            print("  This is an M1 position (not the M5 one you mentioned)")
    
    print()
    print("=" * 100)
    print("RECOMMENDATION FOR M5")
    print("=" * 100)
    print()
    print("The M5 bot is holding because RSI hasn't reached 70.")
    print("This is causing profit to fluctuate without locking in gains.")
    print()
    print("Options:")
    print("  1. Lower RSI exit threshold (65 instead of 70)")
    print("  2. Add trailing stop to protect profits")
    print("  3. Add profit-taking rule: exit if profit > $100 and RSI > 60")
    print("  4. Add time-based exit: take profit after X minutes if profitable")
    
    connector.disconnect()

if __name__ == "__main__":
    main()
