"""
Test SIGNAL-BASED adaptive exits for M1 bot
Based on real trade analysis: exit when signal fades or reverses

Strategies:
1. Baseline - Current strategy (10min time-based)
2. Trend Reversal - Exit if trend reverses while losing
3. Signal Fade + Sideways - Exit if signal fades AND price sideways
4. Combined (BEST) - Trend reversal OR (signal fade + sideways) OR 10min fallback
"""

import sys
import pandas as pd
import numpy as np
import random
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

def strategy_baseline(df):
    """Time-based adaptive exit (10 minutes)"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 35:
                entry = row['close']
                lev_pos = balance * 0.15 * 25
                sl = entry - (row['ATR'] * 4.0)
                tp = entry + (entry * 0.008)
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                lev_pos = balance * 0.15 * 25
                sl = entry + (row['ATR'] * 4.0)
                tp = entry - (entry * 0.008)
                
                position = {
                    'type': 'short',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            bars_held = i - position['entry_bar']
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            if position['type'] == 'short':
                current_pnl_pct = -current_pnl_pct
            
            # Time-based adaptive exit
            if current_pnl_pct < 0 and bars_held >= 10:
                exit_price = row['close']
                exit_reason = "ADAPTIVE_TIME"
            elif position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:  # short
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < 25:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0,
                    'bars_held': bars_held
                })
                
                position = None
    
    return balance, trades

def strategy_signal_based(df):
    """Signal-based adaptive exits: trend reversal + signal fade"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1] if i > 0 else row
        
        if position is None:
            if row['RSI'] < 35:
                entry = row['close']
                lev_pos = balance * 0.15 * 25
                sl = entry - (row['ATR'] * 4.0)
                tp = entry + (entry * 0.008)
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i,
                    'entry_atr': row['ATR']
                }
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                lev_pos = balance * 0.15 * 25
                sl = entry + (row['ATR'] * 4.0)
                tp = entry - (entry * 0.008)
                
                position = {
                    'type': 'short',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i,
                    'entry_atr': row['ATR']
                }
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            bars_held = i - position['entry_bar']
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            if position['type'] == 'short':
                current_pnl_pct = -current_pnl_pct
            
            price_change = abs(row['close'] - position['entry'])
            is_sideways = price_change < position['entry_atr'] * 0.3
            
            # ADAPTIVE EXITS
            if position['type'] == 'long':
                # Trend reversal while losing
                if row['downtrend'] and current_pnl_pct < 0:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
                # Signal fade + sideways
                elif row['RSI'] > 50 and current_pnl_pct < 0 and bars_held >= 3 and is_sideways:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_FADE"
                # Time fallback
                elif current_pnl_pct < 0 and bars_held >= 10:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TIME"
                # Normal exits
                elif row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            else:  # short
                # Trend reversal while losing
                if row['uptrend'] and current_pnl_pct < 0:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
                # Signal fade + sideways
                elif row['RSI'] < 50 and current_pnl_pct < 0 and bars_held >= 3 and is_sideways:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_FADE"
                # Time fallback
                elif current_pnl_pct < 0 and bars_held >= 10:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TIME"
                # Normal exits
                elif row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < 25:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0,
                    'bars_held': bars_held
                })
                
                position = None
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("SIGNAL-BASED ADAPTIVE EXITS TEST")
    print("=" * 100)
    print()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M1 data...")
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Total bars: {len(df)}")
    print()
    
    strategies = {
        'Baseline (Time-based)': strategy_baseline,
        'Signal-Based (Trend + Fade)': strategy_signal_based
    }
    
    results = {name: [] for name in strategies}
    
    # Test on 30-day periods
    print("Testing on 30-day periods (15 samples)...")
    bars_30d = 30 * 24 * 60
    max_start = len(df) - bars_30d - 200
    
    for sample in range(15):
        start_idx = random.randint(200, max_start)
        end_idx = start_idx + bars_30d
        
        df_sample = df.iloc[start_idx:end_idx].copy()
        df_sample = df_sample.reset_index(drop=True)
        
        for name, strategy_func in strategies.items():
            balance, trades = strategy_func(df_sample)
            
            if trades:
                return_pct = (balance / 1000 - 1) * 100
                win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
                adaptive_exits = sum(1 for t in trades if 'ADAPTIVE' in t['reason'])
                adaptive_pct = (adaptive_exits / len(trades)) * 100 if trades else 0
                
                # Count exit types
                trend_exits = sum(1 for t in trades if t['reason'] == 'ADAPTIVE_TREND')
                fade_exits = sum(1 for t in trades if t['reason'] == 'ADAPTIVE_FADE')
                time_exits = sum(1 for t in trades if t['reason'] == 'ADAPTIVE_TIME')
                
                results[name].append({
                    'return': return_pct,
                    'trades': len(trades),
                    'win_rate': win_rate,
                    'adaptive_pct': adaptive_pct,
                    'trend_exits': trend_exits,
                    'fade_exits': fade_exits,
                    'time_exits': time_exits
                })
    
    print()
    print("=" * 100)
    print("RESULTS (30-day periods, 15 samples)")
    print("=" * 100)
    print(f"{'Strategy':<30} | {'Avg Return':>11} | {'Win Rate':>9} | {'Adaptive %':>11} | {'Improvement':>12}")
    print("=" * 100)
    
    baseline_return = np.mean([r['return'] for r in results['Baseline (Time-based)']])
    
    for name in strategies.keys():
        if results[name]:
            avg_return = np.mean([r['return'] for r in results[name]])
            avg_win_rate = np.mean([r['win_rate'] for r in results[name]])
            avg_adaptive = np.mean([r['adaptive_pct'] for r in results[name]])
            
            improvement = ((avg_return - baseline_return) / abs(baseline_return)) * 100 if baseline_return != 0 else 0
            
            print(f"{name:<30} | {avg_return:>10.1f}% | {avg_win_rate:>8.1f}% | {avg_adaptive:>10.1f}% | {improvement:>11.1f}%")
    
    print("=" * 100)
    print()
    
    # Show exit breakdown for signal-based strategy
    signal_results = results['Signal-Based (Trend + Fade)']
    if signal_results:
        avg_trend = np.mean([r['trend_exits'] for r in signal_results])
        avg_fade = np.mean([r['fade_exits'] for r in signal_results])
        avg_time = np.mean([r['time_exits'] for r in signal_results])
        
        print("ADAPTIVE EXIT BREAKDOWN (Signal-Based):")
        print(f"  Trend Reversals: {avg_trend:.1f} per period")
        print(f"  Signal Fading: {avg_fade:.1f} per period")
        print(f"  Time Fallback: {avg_time:.1f} per period")
        print()
    
    # Recommendation
    signal_return = np.mean([r['return'] for r in results['Signal-Based (Trend + Fade)']])
    signal_win_rate = np.mean([r['win_rate'] for r in results['Signal-Based (Trend + Fade)']])
    
    print("=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)
    
    if signal_return > baseline_return * 1.05:
        print(f"✅ IMPLEMENT: Signal-Based Adaptive Exits")
        print(f"   Return: {signal_return:.1f}% (vs {baseline_return:.1f}% baseline)")
        print(f"   Win Rate: {signal_win_rate:.1f}%")
        print(f"   Improvement: {((signal_return - baseline_return) / abs(baseline_return)) * 100:+.1f}%")
        print()
        print("   This strategy exits faster when:")
        print("   1. Trend reverses against position while losing")
        print("   2. Signal fades + price goes sideways (after 3 min)")
        print("   3. Still losing after 10 minutes (fallback)")
    else:
        print(f"⚠ KEEP BASELINE: Signal-based not significantly better")
        print(f"   Signal-based: {signal_return:.1f}%")
        print(f"   Baseline: {baseline_return:.1f}%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
