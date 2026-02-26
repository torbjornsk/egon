"""
Analyze M1 noise vs M5 to understand why M1 is failing live
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def analyze_noise(df, timeframe_name):
    """Analyze price noise and volatility"""
    
    # Calculate various noise metrics
    df['price_range'] = df['high'] - df['low']
    df['body'] = abs(df['close'] - df['open'])
    df['wick_ratio'] = (df['price_range'] - df['body']) / df['price_range']
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Price movement
    df['price_change'] = df['close'].diff()
    df['price_change_pct'] = df['close'].pct_change() * 100
    
    # Directional consistency
    df['direction'] = np.sign(df['price_change'])
    df['direction_consistency'] = df['direction'].rolling(5).apply(lambda x: abs(x.sum()) / len(x))
    
    print(f"\n{timeframe_name} NOISE ANALYSIS:")
    print(f"  Avg ATR: ${df['ATR'].mean():.2f}")
    print(f"  Avg Range: ${df['price_range'].mean():.2f}")
    print(f"  Avg Body: ${df['body'].mean():.2f}")
    print(f"  Avg Wick Ratio: {df['wick_ratio'].mean():.2%}")
    print(f"  Avg Price Change: ${abs(df['price_change']).mean():.2f}")
    print(f"  Directional Consistency: {df['direction_consistency'].mean():.2%}")
    
    # Calculate signal-to-noise ratio
    signal = abs(df['close'].iloc[-1] - df['close'].iloc[0])
    noise = df['price_range'].sum()
    snr = signal / noise
    
    print(f"  Signal-to-Noise Ratio: {snr:.4f}")
    
    return df

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("M1 vs M5 NOISE COMPARISON")
    print("="*100)
    
    # Get last 24 hours
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=24)
    
    print(f"\nAnalyzing last 24 hours...")
    
    # Get M1 data
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"M1 bars: {len(df_m1)}")
    
    # Get M5 data
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    print(f"M5 bars: {len(df_m5)}")
    
    # Analyze both
    df_m1 = analyze_noise(df_m1, "M1")
    df_m5 = analyze_noise(df_m5, "M5")
    
    # Compare
    print("\n" + "="*100)
    print("COMPARISON:")
    print("="*100)
    
    m1_atr = df_m1['ATR'].mean()
    m5_atr = df_m5['ATR'].mean()
    
    print(f"\nATR Comparison:")
    print(f"  M1: ${m1_atr:.2f}")
    print(f"  M5: ${m5_atr:.2f}")
    print(f"  Ratio: {m5_atr/m1_atr:.2f}x")
    
    m1_consistency = df_m1['direction_consistency'].mean()
    m5_consistency = df_m5['direction_consistency'].mean()
    
    print(f"\nDirectional Consistency:")
    print(f"  M1: {m1_consistency:.2%} (more noise = lower)")
    print(f"  M5: {m5_consistency:.2%}")
    print(f"  M5 is {(m5_consistency/m1_consistency-1)*100:.1f}% more consistent")
    
    # Calculate whipsaw potential
    m1_whipsaws = len(df_m1[df_m1['wick_ratio'] > 0.7])
    m5_whipsaws = len(df_m5[df_m5['wick_ratio'] > 0.7])
    
    print(f"\nWhipsaw Candles (wick > 70% of range):")
    print(f"  M1: {m1_whipsaws} ({m1_whipsaws/len(df_m1)*100:.1f}%)")
    print(f"  M5: {m5_whipsaws} ({m5_whipsaws/len(df_m5)*100:.1f}%)")
    
    print("\n" + "="*100)
    print("CONCLUSION:")
    print("="*100)
    
    if m1_consistency < 0.5:
        print("\nM1 has LOW directional consistency - price is choppy and noisy")
        print("Mean reversion on M1 is fighting random noise, not real reversals")
    
    if m1_whipsaws / len(df_m1) > 0.3:
        print("\nM1 has HIGH whipsaw rate - many false signals")
        print("Stop losses are getting hit by noise, not real moves")
    
    print("\nRECOMMENDATION:")
    print("  The M1 timeframe is too noisy for reliable trading")
    print("  Options:")
    print("    1. Disable M1 bot entirely (M5 alone made $305 in 24h)")
    print("    2. Use M1 only for very specific setups (e.g., breakouts)")
    print("    3. Increase M1 position size threshold (only trade clearest signals)")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
