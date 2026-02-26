"""
Test SMART adaptive exit strategies for M1 bot
Goal: Cut real losers faster without hurting win rate

Strategies to test:
1. Baseline (current) - No adaptive exits
2. Time + Loss - Exit if losing after 10+ minutes
3. Trend Reversal - Exit if losing AND EMA crossed against us
4. ATR Loss Limit - Exit if loss exceeds 0.5x ATR
5. Multi-Signal - Require 2+ confirmations
6. Hybrid - Combine best elements
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
    """Current M1 strategy - no adaptive exits"""
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
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0,
                    'bars_held': i - position['entry_bar']
                })
                
                position = None
    
    return balance, trades

def strategy_time_loss(df, min_bars=10):
    """Exit if losing after X bars (10 bars = 10 minutes on M1)"""
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
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            bars_held = i - position['entry_bar']
            
            # Calculate current P&L
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            
            if position['type'] == 'long':
                # ADAPTIVE: Exit if losing after min_bars
                if current_pnl_pct < 0 and bars_held >= min_bars:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TIME"
                elif row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
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

def strategy_trend_reversal(df):
    """Exit if losing AND trend reversed (EMA crossover)"""
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
                    'entry_uptrend': row['uptrend']
                }
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            
            # Check for EMA crossover (trend reversal)
            ema_crossed = (prev_row['uptrend'] and not row['uptrend'])
            
            if position['type'] == 'long':
                # ADAPTIVE: Exit if losing AND trend reversed
                if current_pnl_pct < 0 and ema_crossed:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
                elif row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0,
                    'bars_held': i - position['entry_bar']
                })
                
                position = None
    
    return balance, trades

def strategy_atr_loss_limit(df, atr_loss_mult=0.5):
    """Exit if loss exceeds 0.5x ATR (before hitting full SL at 4.0x)"""
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
                    'entry_bar': i,
                    'entry_atr': row['ATR']
                }
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            loss_amount = position['entry'] - row['close']
            atr_loss_threshold = position['entry_atr'] * atr_loss_mult
            
            if position['type'] == 'long':
                # ADAPTIVE: Exit if loss exceeds ATR threshold
                if loss_amount > atr_loss_threshold:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_ATR"
                elif row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0,
                    'bars_held': i - position['entry_bar']
                })
                
                position = None
    
    return balance, trades

def strategy_multi_signal(df):
    """Require 2+ signals: losing + (time OR trend OR ATR)"""
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
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            bars_held = i - position['entry_bar']
            loss_amount = position['entry'] - row['close']
            ema_crossed = (prev_row['uptrend'] and not row['uptrend'])
            
            if position['type'] == 'long':
                # Count signals
                signals = 0
                signal_reasons = []
                
                if current_pnl_pct < 0:
                    if bars_held >= 10:
                        signals += 1
                        signal_reasons.append("time")
                    if ema_crossed:
                        signals += 1
                        signal_reasons.append("trend")
                    if loss_amount > position['entry_atr'] * 0.5:
                        signals += 1
                        signal_reasons.append("atr")
                    
                    # ADAPTIVE: Exit if 2+ signals
                    if signals >= 2:
                        exit_price = row['close']
                        exit_reason = f"ADAPTIVE_MULTI_{'+'.join(signal_reasons)}"
                
                if not exit_price:
                    if row['low'] <= position['sl']:
                        exit_price = position['sl']
                        exit_reason = "SL"
                    elif row['high'] >= position['tp']:
                        exit_price = position['tp']
                        exit_reason = "TP"
                    elif row['RSI'] > 75:
                        exit_price = row['close']
                        exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
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
    print("SMART ADAPTIVE EXITS - M1 STRATEGY TEST")
    print("=" * 100)
    print()
    
    # Get 90 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M1 data...")
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Total bars: {len(df)}")
    print()
    
    # Test on 30-day period (most relevant)
    print("Testing strategies on 30-day periods (15 samples)...")
    print()
    
    strategies = {
        'Baseline (Current)': strategy_baseline,
        'Time + Loss (10min)': strategy_time_loss,
        'Trend Reversal': strategy_trend_reversal,
        'ATR Loss Limit (0.5x)': strategy_atr_loss_limit,
        'Multi-Signal (2+)': strategy_multi_signal
    }
    
    results = {name: [] for name in strategies}
    
    # Sample 15 random 30-day periods
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
                
                results[name].append({
                    'return': return_pct,
                    'trades': len(trades),
                    'win_rate': win_rate,
                    'adaptive_pct': adaptive_pct
                })
    
    # Display results
    print("=" * 100)
    print("RESULTS (30-day periods, 15 samples)")
    print("=" * 100)
    print(f"{'Strategy':<25} | {'Avg Return':>11} | {'Win Rate':>9} | {'Adaptive %':>11} | {'vs Baseline':>12}")
    print("=" * 100)
    
    baseline_return = np.mean([r['return'] for r in results['Baseline (Current)']])
    
    for name in strategies.keys():
        if results[name]:
            avg_return = np.mean([r['return'] for r in results[name]])
            avg_win_rate = np.mean([r['win_rate'] for r in results[name]])
            avg_adaptive = np.mean([r['adaptive_pct'] for r in results[name]])
            
            improvement = ((avg_return - baseline_return) / abs(baseline_return)) * 100 if baseline_return != 0 else 0
            
            print(f"{name:<25} | {avg_return:>10.1f}% | {avg_win_rate:>8.1f}% | {avg_adaptive:>10.1f}% | {improvement:>11.1f}%")
    
    print("=" * 100)
    print()
    
    # Find best strategy
    best_name = max(strategies.keys(), key=lambda n: np.mean([r['return'] for r in results[n]]))
    best_return = np.mean([r['return'] for r in results[best_name]])
    best_win_rate = np.mean([r['win_rate'] for r in results[best_name]])
    
    print("RECOMMENDATION:")
    print()
    
    if best_return > baseline_return * 1.1:  # At least 10% better
        print(f"✅ IMPLEMENT: {best_name}")
        print(f"   Return: {best_return:.1f}% (vs {baseline_return:.1f}% baseline)")
        print(f"   Win Rate: {best_win_rate:.1f}%")
        print(f"   Improvement: {((best_return - baseline_return) / abs(baseline_return)) * 100:+.1f}%")
    else:
        print("⚠ KEEP BASELINE: No strategy significantly outperforms")
        print(f"   Best alternative: {best_name} at {best_return:.1f}%")
        print(f"   Baseline: {baseline_return:.1f}%")
        print(f"   Difference too small to justify complexity")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
