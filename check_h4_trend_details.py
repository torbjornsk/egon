"""
Check H4 trend details to understand why trend bot didn't trade
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime

def calculate_indicators(df):
    """Calculate indicators"""
    df = df.copy()
    
    # EMAs
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()
    
    # ADX
    high_diff = df['high'].diff()
    low_diff = -df['low'].diff()
    
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
    
    plus_di = 100 * (plus_dm.rolling(14).mean() / df['atr'])
    minus_di = 100 * (minus_dm.rolling(14).mean() / df['atr'])
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(14).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    
    return df

def main():
    """Check H4 trend"""
    print("="*80)
    print("H4 TREND ANALYSIS")
    print("="*80)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get H4 data
    print(f"\nFetching H4 data...")
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 250)
    
    if rates is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    mt5.shutdown()
    
    # Calculate indicators
    df = calculate_indicators(df)
    
    # Show last 10 H4 candles
    print(f"\nLast 10 H4 Candles:")
    print("-"*80)
    print(f"{'Time':<20} {'Close':>8} {'EMA50':>8} {'EMA200':>8} {'ADX':>6} {'Trend':<15}")
    print("-"*80)
    
    for i in range(-10, 0):
        row = df.iloc[i]
        
        ema_uptrend = row['ema_50'] > row['ema_200']
        strong_trend = row['adx'] > 25
        
        if ema_uptrend and strong_trend:
            trend = "UPTREND ✓"
        elif not ema_uptrend and strong_trend:
            trend = "DOWNTREND ✓"
        elif ema_uptrend:
            trend = "Up (weak)"
        else:
            trend = "Down (weak)"
        
        print(f"{row['time'].strftime('%Y-%m-%d %H:%M'):<20} "
              f"${row['close']:7.2f} "
              f"${row['ema_50']:7.2f} "
              f"${row['ema_200']:7.2f} "
              f"{row['adx']:6.1f} "
              f"{trend:<15}")
    
    # Current state
    last = df.iloc[-1]
    
    print(f"\n" + "="*80)
    print("CURRENT H4 STATE")
    print("="*80)
    
    print(f"\nTime: {last['time'].strftime('%Y-%m-%d %H:%M')}")
    print(f"Close: ${last['close']:.2f}")
    
    print(f"\nEMAs:")
    print(f"  EMA 20:  ${last['ema_20']:.2f}")
    print(f"  EMA 50:  ${last['ema_50']:.2f}")
    print(f"  EMA 200: ${last['ema_200']:.2f}")
    
    ema_alignment = "EMA 50 > EMA 200" if last['ema_50'] > last['ema_200'] else "EMA 50 < EMA 200"
    print(f"  Alignment: {ema_alignment}")
    
    print(f"\nTrend Strength:")
    print(f"  ADX: {last['adx']:.1f}")
    print(f"  +DI: {last['plus_di']:.1f}")
    print(f"  -DI: {last['minus_di']:.1f}")
    
    if last['adx'] < 25:
        print(f"  → ADX < 25: NO STRONG TREND")
    else:
        print(f"  → ADX > 25: STRONG TREND")
    
    print(f"\nTrend Bot Requirements:")
    print(f"  1. EMA 50 > EMA 200 (for uptrend): {last['ema_50'] > last['ema_200']}")
    print(f"  2. ADX > 25 (strong trend): {last['adx'] > 25}")
    
    if last['ema_50'] > last['ema_200'] and last['adx'] > 25:
        print(f"\n✓ UPTREND CONFIRMED - Bot would look for LONG entries")
    elif last['ema_50'] < last['ema_200'] and last['adx'] > 25:
        print(f"\n✓ DOWNTREND CONFIRMED - Bot would look for SHORT entries")
    else:
        print(f"\n❌ NO CLEAR TREND - Bot will not trade")
        
        if last['adx'] < 25:
            print(f"\nReason: ADX too low ({last['adx']:.1f} < 25)")
            print(f"  Market is ranging/choppy, not trending")
            print(f"  Trend bot requires strong directional movement")
        
        if abs(last['ema_50'] - last['ema_200']) < 5:
            print(f"\nReason: EMAs too close (${abs(last['ema_50'] - last['ema_200']):.2f} apart)")
            print(f"  No clear directional bias")
    
    print(f"\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    
    print(f"\nThe gap opening created:")
    print(f"  ✓ Strong price move (+$91, +1.7%)")
    print(f"  ✓ High RSI (overbought)")
    
    print(f"\nBut on H4 timeframe:")
    if last['adx'] < 25:
        print(f"  ❌ ADX = {last['adx']:.1f} (not strong enough)")
        print(f"  → Gap was too recent to establish H4 trend")
        print(f"  → Need sustained movement over multiple H4 candles")
    
    print(f"\nTrend bot is designed for:")
    print(f"  - Multi-day trends (not 2-hour gaps)")
    print(f"  - H4 timeframe confirmation (4-hour candles)")
    print(f"  - ADX > 25 (strong sustained trend)")
    
    print(f"\nFor gap moves like this, you need:")
    print(f"  - Lower timeframe strategy (M1, M5, M15)")
    print(f"  - Momentum-based entries (not pullbacks)")
    print(f"  - Faster reaction time")
    
    print(f"\n" + "="*80)

if __name__ == "__main__":
    main()
