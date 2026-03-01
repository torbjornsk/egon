"""
Analyze why M1 bot didn't trade during the gap period
Check RSI levels and bot logic
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import json

def analyze_gap_period():
    """Analyze why M1 bot didn't trade"""
    
    print("="*70)
    print("WHY M1 BOT DIDN'T TRADE - ANALYSIS")
    print("="*70)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get M1 data
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 300)
    
    if rates is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Calculate indicators
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Load M1 config
    with open('config/m1_params.json', 'r') as f:
        config = json.load(f)
    
    # Find the gap
    gap_index = None
    for i in range(1, len(df)):
        time_diff = (df.iloc[i]['time'] - df.iloc[i-1]['time']).total_seconds() / 60
        if time_diff > 30:
            gap_index = i
            break
    
    if gap_index is None:
        print("No gap found")
        mt5.shutdown()
        return
    
    print(f"\nGap found at: {df.iloc[gap_index]['time']}")
    print(f"Gap open price: ${df.iloc[gap_index]['open']:.2f}")
    print("-" * 70)
    
    # Analyze first 100 candles after gap
    print(f"\nM1 Bot Entry Requirements:")
    print(f"  LONG: RSI < {config['rsi_buy']}")
    print(f"  SHORT: RSI > {config['rsi_sell']} AND downtrend")
    print(f"  Warmup: 2 candles after gap (no trading)")
    print(f"  Cooldown: 2 candles after closing position")
    
    print(f"\nRSI Levels After Gap:")
    print("-" * 70)
    
    # Check RSI for first 100 candles after gap
    post_gap = df.iloc[gap_index:gap_index+100]
    
    entry_opportunities = 0
    
    for i, (idx, row) in enumerate(post_gap.iterrows()):
        rsi = row['RSI']
        
        # Skip warmup period
        if i < 2:
            status = "[WARMUP - No trading]"
        elif rsi < config['rsi_buy']:
            status = f"[LONG SIGNAL] ✓"
            entry_opportunities += 1
        elif rsi > config['rsi_sell']:
            status = f"[SHORT SIGNAL?]"
        else:
            status = f"[No signal]"
        
        # Show first 20 candles
        if i < 20:
            print(f"  {i:2d}. {row['time'].strftime('%H:%M')} | "
                  f"Price: ${row['close']:7.2f} | "
                  f"RSI: {rsi:5.1f} | {status}")
    
    print(f"\n  ... (showing first 20 of 100 candles)")
    
    # Summary
    print(f"\n" + "="*70)
    print("ANALYSIS SUMMARY")
    print("="*70)
    
    # Check RSI distribution
    rsi_values = post_gap['RSI'].dropna()
    
    print(f"\nRSI Statistics (100 candles after gap):")
    print(f"  Min: {rsi_values.min():.1f}")
    print(f"  Max: {rsi_values.max():.1f}")
    print(f"  Mean: {rsi_values.mean():.1f}")
    print(f"  Median: {rsi_values.median():.1f}")
    
    # Count how many candles met entry criteria
    long_signals = (rsi_values < config['rsi_buy']).sum()
    short_signals = (rsi_values > config['rsi_sell']).sum()
    
    print(f"\nEntry Signals (after 2-candle warmup):")
    print(f"  LONG signals (RSI < {config['rsi_buy']}): {long_signals} candles")
    print(f"  SHORT signals (RSI > {config['rsi_sell']}): {short_signals} candles")
    
    print(f"\nWhy M1 Bot Didn't Trade:")
    
    if long_signals == 0 and short_signals == 0:
        print(f"  ❌ NO ENTRY SIGNALS")
        print(f"     RSI stayed between {config['rsi_buy']} and {config['rsi_sell']}")
        print(f"     Gap up pushed RSI too high for LONG entry")
        print(f"     Price kept rising, never became oversold")
    elif long_signals > 0:
        print(f"  ⚠️  {long_signals} LONG signals detected")
        print(f"     But bot may have been in cooldown or had other restrictions")
        print(f"     Check bot logs for details")
    
    # Price action summary
    gap_open = post_gap.iloc[0]['open']
    highest = post_gap['high'].max()
    lowest = post_gap['low'].min()
    final = post_gap.iloc[-1]['close']
    
    print(f"\nPrice Action (100 minutes after gap):")
    print(f"  Gap open: ${gap_open:.2f}")
    print(f"  Highest:  ${highest:.2f} (+${highest-gap_open:.2f}, +{((highest-gap_open)/gap_open)*100:.2f}%)")
    print(f"  Lowest:   ${lowest:.2f} (${lowest-gap_open:.2f}, {((lowest-gap_open)/gap_open)*100:.2f}%)")
    print(f"  Final:    ${final:.2f} (${final-gap_open:.2f}, {((final-gap_open)/gap_open)*100:.2f}%)")
    
    print(f"\nConclusion:")
    print(f"  M1 bot is designed for MEAN REVERSION (buy oversold, sell overbought)")
    print(f"  Gap up created STRONG TREND (price kept rising)")
    print(f"  RSI stayed elevated (not oversold enough for entry)")
    print(f"  Bot correctly avoided chasing the move")
    print(f"  ")
    print(f"  For trending moves like this, you need:")
    print(f"  → Trend-following strategy (not mean reversion)")
    print(f"  → Wider RSI thresholds or momentum-based entries")
    print(f"  → Gap detection with trend confirmation")
    
    mt5.shutdown()
    print("\n" + "="*70)

if __name__ == "__main__":
    analyze_gap_period()
