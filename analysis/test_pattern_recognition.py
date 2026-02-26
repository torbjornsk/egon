"""
Test if looking at recent candle patterns improves exit decisions
Patterns to test:
1. RSI divergence (price up, RSI down = bearish)
2. Consecutive declining candles (momentum shift)
3. Volume/volatility changes (ATR expansion/contraction)
4. Support/resistance levels (price bouncing)
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
    
    df['ema_fast'] = df['close'].ewm(span=9).mean()
    df['ema_slow'] = df['close'].ewm(span=21).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    
    return df

def detect_patterns(df, idx):
    """Detect patterns in last 3-5 candles"""
    if idx < 5:
        return {}
    
    recent = df.iloc[idx-4:idx+1]  # Last 5 candles including current
    patterns = {}
    
    # 1. RSI Divergence (bearish for LONG)
    # Price making higher highs but RSI making lower highs
    if len(recent) >= 3:
        price_trend = recent['close'].iloc[-1] > recent['close'].iloc[-3]
        rsi_trend = recent['RSI'].iloc[-1] < recent['RSI'].iloc[-3]
        patterns['bearish_divergence'] = price_trend and rsi_trend
    
    # 2. Consecutive declining candles (momentum shift)
    declines = 0
    for i in range(len(recent) - 1):
        if recent['close'].iloc[i+1] < recent['close'].iloc[i]:
            declines += 1
    patterns['consecutive_declines'] = declines
    
    # 3. ATR expansion (volatility increasing = risk)
    if len(recent) >= 2:
        atr_change = (recent['ATR'].iloc[-1] - recent['ATR'].iloc[-2]) / recent['ATR'].iloc[-2]
        patterns['atr_expanding'] = atr_change > 0.1  # 10% increase
    
    # 4. Price rejection at resistance (failed to break higher)
    if len(recent) >= 3:
        recent_high = recent['high'].max()
        current_close = recent['close'].iloc[-1]
        rejection = (recent_high - current_close) / recent_high > 0.005  # 0.5% below high
        patterns['resistance_rejection'] = rejection
    
    return patterns

def strategy_baseline(df):
    """Current M5 strategy - only looks at latest candle"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    peak_profit = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 25:
                entry = row['close']
                lev_pos = balance * 0.15 * 25
                sl = entry - (row['ATR'] * 2.0)
                tp = entry + (entry * 0.01)
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
                peak_profit = 0
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            current_pnl = current_pnl_pct * position['lev_pos']
            peak_profit = max(peak_profit, current_pnl)
            
            bars_held = i - position['entry_bar']
            
            # Adaptive: profit decline
            if current_pnl > 100 and peak_profit > 100:
                decline_pct = ((peak_profit - current_pnl) / peak_profit) * 100
                if decline_pct > 30:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_DECLINE"
            
            # Adaptive: trend reversal
            if not exit_price and current_pnl > 50 and bars_held >= 3:
                if row['RSI'] > 60 and not row['uptrend']:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
            
            # Standard exits
            if not exit_price:
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 70:
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
                peak_profit = 0
    
    return balance, trades

def strategy_with_patterns(df):
    """M5 strategy with pattern recognition"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    peak_profit = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 25:
                entry = row['close']
                lev_pos = balance * 0.15 * 25
                sl = entry - (row['ATR'] * 2.0)
                tp = entry + (entry * 0.01)
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
                peak_profit = 0
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            current_pnl = current_pnl_pct * position['lev_pos']
            peak_profit = max(peak_profit, current_pnl)
            
            bars_held = i - position['entry_bar']
            
            # NEW: Pattern-based exits
            patterns = detect_patterns(df, i)
            
            # Exit if profitable and bearish patterns detected
            if current_pnl > 50 and bars_held >= 3:
                bearish_signals = 0
                
                if patterns.get('bearish_divergence'):
                    bearish_signals += 1
                
                if patterns.get('consecutive_declines', 0) >= 3:
                    bearish_signals += 1
                
                if patterns.get('resistance_rejection'):
                    bearish_signals += 1
                
                # Exit if 2+ bearish patterns
                if bearish_signals >= 2:
                    exit_price = row['close']
                    exit_reason = "PATTERN_BEARISH"
            
            # Adaptive: profit decline
            if not exit_price and current_pnl > 100 and peak_profit > 100:
                decline_pct = ((peak_profit - current_pnl) / peak_profit) * 100
                if decline_pct > 30:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_DECLINE"
            
            # Adaptive: trend reversal
            if not exit_price and current_pnl > 50 and bars_held >= 3:
                if row['RSI'] > 60 and not row['uptrend']:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
            
            # Standard exits
            if not exit_price:
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 70:
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
                peak_profit = 0
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("PATTERN RECOGNITION TEST - M5 STRATEGY")
    print("=" * 100)
    print()
    print("Testing if looking at recent candle patterns improves exits")
    print()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M5 data...")
    df = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    print(f"Total bars: {len(df)}")
    print()
    
    strategies = {
        'Baseline (Current)': strategy_baseline,
        'With Pattern Recognition': strategy_with_patterns
    }
    
    results = {name: [] for name in strategies}
    
    print("Testing on 30-day periods (15 samples)...")
    bars_30d = 30 * 24 * 12  # 30 days * 24 hours * 12 (5-min bars per hour)
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
                
                pattern_exits = sum(1 for t in trades if 'PATTERN' in t['reason'])
                pattern_pct = (pattern_exits / len(trades)) * 100 if trades else 0
                
                results[name].append({
                    'return': return_pct,
                    'trades': len(trades),
                    'win_rate': win_rate,
                    'pattern_exits': pattern_exits,
                    'pattern_pct': pattern_pct
                })
    
    print()
    print("=" * 100)
    print("RESULTS (30-day periods, 15 samples)")
    print("=" * 100)
    print(f"{'Strategy':<30} | {'Avg Return':>11} | {'Win Rate':>9} | {'Pattern Exits':>14} | {'Improvement':>12}")
    print("=" * 100)
    
    baseline_return = np.mean([r['return'] for r in results['Baseline (Current)']])
    
    for name in strategies.keys():
        if results[name]:
            avg_return = np.mean([r['return'] for r in results[name]])
            avg_win_rate = np.mean([r['win_rate'] for r in results[name]])
            avg_pattern_exits = np.mean([r['pattern_exits'] for r in results[name]])
            
            improvement = ((avg_return - baseline_return) / abs(baseline_return)) * 100 if baseline_return != 0 else 0
            
            print(f"{name:<30} | {avg_return:>10.1f}% | {avg_win_rate:>8.1f}% | {avg_pattern_exits:>13.1f} | {improvement:>11.1f}%")
    
    print("=" * 100)
    print()
    
    pattern_return = np.mean([r['return'] for r in results['With Pattern Recognition']])
    
    print("CONCLUSION:")
    print()
    
    if pattern_return > baseline_return * 1.05:
        print(f"✅ PATTERNS HELP: +{((pattern_return - baseline_return) / abs(baseline_return)) * 100:.1f}% improvement")
        print()
        print("Useful patterns:")
        print("  1. Bearish divergence (price up, RSI down)")
        print("  2. Consecutive declining candles (3+)")
        print("  3. Resistance rejection (failed breakout)")
        print()
        print("Recommendation: Add pattern recognition to M5 bot")
    else:
        print(f"⚠ PATTERNS DON'T HELP: Only {((pattern_return - baseline_return) / abs(baseline_return)) * 100:+.1f}% difference")
        print()
        print("Current single-candle approach is sufficient")
        print("Pattern recognition adds complexity without clear benefit")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
