"""
Check current M1 signals and why bot isn't trading
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, fast_ema=5, slow_ema=12, rsi_period=5):
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    # Load M1 config
    with open('config/m1_scalping_params.json', 'r') as f:
        config = json.load(f)
    
    print("="*80)
    print("M1 BOT SIGNAL DIAGNOSTIC")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  RSI Buy Threshold: {config['rsi_buy']}")
    print(f"  RSI Sell Threshold: {config['rsi_sell']}")
    print(f"  Fast EMA: {config['fast_ema']}")
    print(f"  Slow EMA: {config['slow_ema']}")
    print(f"  RSI Period: {config['rsi_period']}")
    print()
    
    # Get specific time period (adjust for MT5 timezone - add 1 hour)
    print("Fetching M1 data from 01:28 to 01:42 (MT5 time)...")
    start_time = datetime.now().replace(hour=1, minute=28, second=0, microsecond=0)
    end_time = datetime.now().replace(hour=1, minute=43, second=0, microsecond=0)
    df = mt5.get_historical_data('XAUUSD', 'M1', start_time, end_time)
    
    if df is None or len(df) == 0:
        print("Failed to fetch data or no data available")
        mt5.disconnect()
        return
    
    print(f"Got {len(df)} M1 candles")
    print()
    
    # Compute indicators
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    # Show all candles in this period
    print("="*80)
    print(f"ALL CANDLES FROM 00:28 TO 00:42 ({len(df)} candles)")
    print("="*80)
    print(f"{'Time':<20} | {'Close':>8} | {'RSI':>6} | {'EMA Fast':>9} | {'EMA Slow':>9} | {'Trend':<10} | {'Signal':<15}")
    print("="*80)
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Check signals
        signal = ""
        if row['RSI'] < config['rsi_buy']:
            signal = "LONG"
        elif row['RSI'] > config['rsi_sell'] and row['downtrend']:
            signal = "SHORT"
        else:
            signal = "No signal"
        
        trend = "Uptrend" if row['uptrend'] else "Downtrend" if row['downtrend'] else "Neutral"
        
        print(f"{row['time'].strftime('%Y-%m-%d %H:%M'):<20} | {row['close']:>8.2f} | {row['RSI']:>6.1f} | {row['ema_fast']:>9.2f} | {row['ema_slow']:>9.2f} | {trend:<10} | {signal:<15}")
    
    print("="*80)
    
    # Current state
    latest = df.iloc[-1]
    print(f"\nCURRENT STATE (as of {latest['time'].strftime('%Y-%m-%d %H:%M:%S')}):")
    print(f"  Price: ${latest['close']:.2f}")
    print(f"  RSI: {latest['RSI']:.2f}")
    print(f"  Fast EMA: {latest['ema_fast']:.2f}")
    print(f"  Slow EMA: {latest['ema_slow']:.2f}")
    print(f"  Trend: {'Uptrend' if latest['uptrend'] else 'Downtrend' if latest['downtrend'] else 'Neutral'}")
    print(f"  ATR: {latest['ATR']:.2f}")
    print()
    
    # Check entry conditions
    print("ENTRY CONDITIONS:")
    print(f"  LONG Entry: RSI < {config['rsi_buy']}")
    print(f"    Current RSI: {latest['RSI']:.2f} → {'✓ SIGNAL' if latest['RSI'] < config['rsi_buy'] else '✗ No signal'}")
    print()
    print(f"  SHORT Entry: RSI > {config['rsi_sell']} AND Downtrend")
    print(f"    Current RSI: {latest['RSI']:.2f} → {'✓' if latest['RSI'] > config['rsi_sell'] else '✗'}")
    print(f"    Downtrend: {'✓' if latest['downtrend'] else '✗'}")
    print(f"    → {'✓ SIGNAL' if (latest['RSI'] > config['rsi_sell'] and latest['downtrend']) else '✗ No signal'}")
    print()
    
    # Check for open positions
    print(f"\nOPEN POSITIONS:")
    try:
        import MetaTrader5 as mt5_direct
        positions = mt5_direct.positions_get(symbol='XAUUSD')
        if positions:
            print(f"  Found {len(positions)} position(s)")
            for pos in positions:
                print(f"    Magic: {pos.magic}, Type: {'LONG' if pos.type == 0 else 'SHORT'}, Volume: {pos.volume}, Profit: ${pos.profit:.2f}")
        else:
            print("  None")
    except Exception as e:
        print(f"  Could not check: {e}")
    
    print()
    
    # Summary
    if latest['RSI'] < config['rsi_buy']:
        print("✓ BOT SHOULD BE BUYING (LONG)")
        print(f"  Entry: ${latest['close']:.2f}")
        stop_distance = latest['ATR'] * config['atr_multiplier']
        print(f"  Stop Loss: ${latest['close'] - stop_distance:.2f}")
        print(f"  Take Profit: ${latest['close'] + (latest['close'] * config['profit_target_pct']):.2f}")
    elif latest['RSI'] > config['rsi_sell'] and latest['downtrend']:
        print("✓ BOT SHOULD BE SELLING (SHORT)")
        print(f"  Entry: ${latest['close']:.2f}")
        stop_distance = latest['ATR'] * config['atr_multiplier']
        print(f"  Stop Loss: ${latest['close'] + stop_distance:.2f}")
        print(f"  Take Profit: ${latest['close'] - (latest['close'] * config['profit_target_pct']):.2f}")
    else:
        print("✗ NO ENTRY SIGNAL")
        print(f"  RSI is {latest['RSI']:.2f}, needs to be < {config['rsi_buy']} for LONG or > {config['rsi_sell']} for SHORT")
        if latest['RSI'] > config['rsi_sell']:
            print(f"  RSI is high enough for SHORT, but trend is {'uptrend' if latest['uptrend'] else 'neutral'} (needs downtrend)")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
