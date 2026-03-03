"""
Check M5 bot signals over last 24 hours
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def compute_indicators(df, fast_ema, slow_ema, rsi_period):
    """Compute technical indicators"""
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=fast_ema, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema, adjust=False).mean()
    
    # Trend
    df['uptrend'] = df['ema_fast'] > df['ema_slow']
    df['downtrend'] = df['ema_fast'] < df['ema_slow']
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['ATR'] = df['tr'].rolling(window=14).mean()
    
    return df

def check_entry_conditions(row, config):
    """Check if entry conditions are met"""
    signals = []
    
    # LONG conditions
    if row['RSI'] < config['rsi_buy'] and row['uptrend']:
        signals.append({
            'type': 'LONG',
            'time': row['time'],
            'price': row['close'],
            'rsi': row['RSI'],
            'ema_fast': row['ema_fast'],
            'ema_slow': row['ema_slow'],
            'atr': row['ATR']
        })
    
    # SHORT conditions
    if config.get('enable_shorts', True):
        if row['RSI'] > config['rsi_sell'] and row['downtrend']:
            signals.append({
                'type': 'SHORT',
                'time': row['time'],
                'price': row['close'],
                'rsi': row['RSI'],
                'ema_fast': row['ema_fast'],
                'ema_slow': row['ema_slow'],
                'atr': row['ATR']
            })
    
    return signals

def main():
    # Initialize MT5
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return
    
    print("Connected to MT5")
    
    # Load M5 config
    with open('config/m5_params.json', 'r') as f:
        config = json.load(f)
    
    print(f"\nM5 Bot Configuration:")
    print(f"  Fast EMA: {config['fast_ema']}")
    print(f"  Slow EMA: {config['slow_ema']}")
    print(f"  RSI Period: {config['rsi_period']}")
    print(f"  RSI Buy: {config['rsi_buy']}")
    print(f"  RSI Sell: {config['rsi_sell']}")
    print(f"  Enable Shorts: {config.get('enable_shorts', True)}")
    
    # Get last 24 hours of M5 data
    symbol = 'XAUUSD.p'
    timeframe = mt5.TIMEFRAME_M5
    
    # Get enough bars to calculate indicators properly
    bars_24h = 24 * 60 // 5  # 288 bars in 24 hours
    bars_needed = bars_24h + 100  # Extra for indicator warmup
    
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars_needed)
    
    if rates is None or len(rates) == 0:
        print("Failed to get market data")
        mt5.shutdown()
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"\nFetched {len(df)} M5 bars")
    print(f"From: {df['time'].iloc[0]}")
    print(f"To: {df['time'].iloc[-1]}")
    
    # Compute indicators
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    # Only analyze last 24 hours
    cutoff_time = datetime.now() - timedelta(hours=24)
    df_24h = df[df['time'] >= cutoff_time].copy()
    
    print(f"\nAnalyzing last 24 hours: {len(df_24h)} bars")
    
    # Check for signals
    all_signals = []
    for idx, row in df_24h.iterrows():
        signals = check_entry_conditions(row, config)
        all_signals.extend(signals)
    
    print(f"\n{'='*80}")
    print(f"SIGNALS FOUND: {len(all_signals)}")
    print(f"{'='*80}")
    
    if len(all_signals) == 0:
        print("\nNo entry signals found in the last 24 hours!")
        print("\nPossible reasons:")
        print("  1. RSI thresholds too strict (buy < 25, sell > 75)")
        print("  2. Trend filter too restrictive (requires EMA alignment)")
        print("  3. Market conditions not meeting criteria")
        
        # Show RSI distribution
        print(f"\nRSI Statistics (last 24h):")
        print(f"  Min: {df_24h['RSI'].min():.1f}")
        print(f"  Max: {df_24h['RSI'].max():.1f}")
        print(f"  Mean: {df_24h['RSI'].mean():.1f}")
        print(f"  Median: {df_24h['RSI'].median():.1f}")
        print(f"  Times RSI < {config['rsi_buy']}: {(df_24h['RSI'] < config['rsi_buy']).sum()}")
        print(f"  Times RSI > {config['rsi_sell']}: {(df_24h['RSI'] > config['rsi_sell']).sum()}")
        
        # Show trend distribution
        print(f"\nTrend Statistics (last 24h):")
        print(f"  Uptrend bars: {df_24h['uptrend'].sum()} ({df_24h['uptrend'].sum()/len(df_24h)*100:.1f}%)")
        print(f"  Downtrend bars: {df_24h['downtrend'].sum()} ({df_24h['downtrend'].sum()/len(df_24h)*100:.1f}%)")
        print(f"  Sideways bars: {(~df_24h['uptrend'] & ~df_24h['downtrend']).sum()}")
        
    else:
        print(f"\nSignals by type:")
        long_signals = [s for s in all_signals if s['type'] == 'LONG']
        short_signals = [s for s in all_signals if s['type'] == 'SHORT']
        print(f"  LONG: {len(long_signals)}")
        print(f"  SHORT: {len(short_signals)}")
        
        print(f"\nDetailed signals:")
        for i, signal in enumerate(all_signals, 1):
            print(f"\n{i}. {signal['type']} Signal")
            print(f"   Time: {signal['time']}")
            print(f"   Price: ${signal['price']:.2f}")
            print(f"   RSI: {signal['rsi']:.1f}")
            print(f"   EMA Fast: ${signal['ema_fast']:.2f}")
            print(f"   EMA Slow: ${signal['ema_slow']:.2f}")
            print(f"   ATR: ${signal['atr']:.2f}")
    
    # Check current conditions
    print(f"\n{'='*80}")
    print("CURRENT CONDITIONS")
    print(f"{'='*80}")
    current = df.iloc[-1]
    print(f"Time: {current['time']}")
    print(f"Price: ${current['close']:.2f}")
    print(f"RSI: {current['RSI']:.1f} (Buy < {config['rsi_buy']}, Sell > {config['rsi_sell']})")
    print(f"Trend: {'UP' if current['uptrend'] else 'DOWN' if current['downtrend'] else 'SIDEWAYS'}")
    print(f"EMA Fast: ${current['ema_fast']:.2f}")
    print(f"EMA Slow: ${current['ema_slow']:.2f}")
    print(f"ATR: ${current['ATR']:.2f}")
    
    # Check what's preventing entry
    print(f"\nEntry Check:")
    if current['RSI'] < config['rsi_buy']:
        print(f"  ✓ RSI oversold ({current['RSI']:.1f} < {config['rsi_buy']})")
    else:
        print(f"  ✗ RSI not oversold ({current['RSI']:.1f} >= {config['rsi_buy']})")
    
    if current['uptrend']:
        print(f"  ✓ Uptrend (EMA {current['ema_fast']:.2f} > {current['ema_slow']:.2f})")
    else:
        print(f"  ✗ Not uptrend (EMA {current['ema_fast']:.2f} <= {current['ema_slow']:.2f})")
    
    if current['RSI'] > config['rsi_sell']:
        print(f"  ✓ RSI overbought ({current['RSI']:.1f} > {config['rsi_sell']})")
    else:
        print(f"  ✗ RSI not overbought ({current['RSI']:.1f} <= {config['rsi_sell']})")
    
    if current['downtrend']:
        print(f"  ✓ Downtrend (EMA {current['ema_fast']:.2f} < {current['ema_slow']:.2f})")
    else:
        print(f"  ✗ Not downtrend (EMA {current['ema_fast']:.2f} >= {current['ema_slow']:.2f})")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
