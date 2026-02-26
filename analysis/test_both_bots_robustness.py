"""
Test BOTH M5 and M1 strategies across multiple time periods
Compare their performance side-by-side
"""

import sys
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

sys.path.append('.')
from src.mt5_connector import MT5Connector

def compute_indicators(df, fast_ema, slow_ema, rsi_period):
    df = df.copy()
    
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def backtest_m5(df):
    """M5 strategy - using OPTIMIZED config"""
    df = compute_indicators(df, 9, 21, 14)  # Optimized: 9/21 EMAs, RSI period 14
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    atr_mult = 2.0  # Optimized
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # Buy dips - OPTIMIZED: RSI < 25
            if row['RSI'] < 25:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * 0.01)  # Optimized: 1% profit target
                
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
                elif row['RSI'] > 70:  # Optimized: RSI exit at 70
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

def backtest_m1(df):
    """M1 strategy with fast re-entry"""
    df = compute_indicators(df, 5, 12, 5)
    
    position = None
    balance = 1000
    trades = []
    last_trade_profitable = False
    cooldown_candles = 2
    last_close_bar = None
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # Check cooldown (skip if last trade was profitable)
            if last_close_bar is not None:
                bars_since_close = i - last_close_bar
                if not last_trade_profitable and bars_since_close < cooldown_candles:
                    continue
            
            # Buy dips
            if row['RSI'] < 35:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
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
                
                is_profitable = pnl > 0
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': is_profitable,
                    'bars_held': i - position['entry_bar']
                })
                
                last_trade_profitable = is_profitable
                last_close_bar = i
                position = None
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("M5 vs M1 STRATEGY COMPARISON - ROBUSTNESS TEST")
    print("=" * 100)
    print()
    print("M5 Strategy: RSI<25 entry, RSI>70 exit, 2.0x ATR stops, 1.0% TP, 15% @ 25x (OPTIMIZED)")
    print("M1 Strategy: RSI<35 entry, RSI>75 exit, 4.0x ATR stops, 0.8% TP, 15% @ 25x, fast re-entry")
    print()
    
    # Get 90 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"M5 bars: {len(df_m5)}")
    print(f"M1 bars: {len(df_m1)}")
    print()
    
    # Test periods (in calendar days, not bars)
    test_periods = [
        ('1 day', 1, 50),
        ('3 days', 3, 40),
        ('7 days', 7, 30),
        ('14 days', 14, 25),
        ('30 days', 30, 15),
    ]
    
    m5_results = {}
    m1_results = {}
    
    for period_name, days, num_samples in test_periods:
        print(f"Testing {period_name} periods ({num_samples} samples)...")
        
        # Calculate bars needed for each timeframe
        m5_bars = days * 24 * 12  # 12 M5 bars per hour
        m1_bars = days * 24 * 60  # 60 M1 bars per hour
        
        m5_samples = []
        m1_samples = []
        
        # M5 samples
        max_start_m5 = len(df_m5) - m5_bars - 200
        if max_start_m5 > 0:
            for _ in range(num_samples):
                start_idx = random.randint(200, max_start_m5)
                end_idx = start_idx + m5_bars
                
                df_sample = df_m5.iloc[start_idx:end_idx].copy()
                df_sample = df_sample.reset_index(drop=True)
                
                balance, trades = backtest_m5(df_sample)
                
                if trades:
                    return_pct = (balance / 1000 - 1) * 100
                    win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
                    
                    m5_samples.append({
                        'return': return_pct,
                        'trades': len(trades),
                        'win_rate': win_rate,
                        'profitable': return_pct > 0
                    })
        
        # M1 samples
        max_start_m1 = len(df_m1) - m1_bars - 200
        if max_start_m1 > 0:
            for _ in range(num_samples):
                start_idx = random.randint(200, max_start_m1)
                end_idx = start_idx + m1_bars
                
                df_sample = df_m1.iloc[start_idx:end_idx].copy()
                df_sample = df_sample.reset_index(drop=True)
                
                balance, trades = backtest_m1(df_sample)
                
                if trades:
                    return_pct = (balance / 1000 - 1) * 100
                    win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
                    
                    m1_samples.append({
                        'return': return_pct,
                        'trades': len(trades),
                        'win_rate': win_rate,
                        'profitable': return_pct > 0
                    })
        
        if m5_samples:
            m5_results[period_name] = m5_samples
            m5_returns = [s['return'] for s in m5_samples]
            m5_profitable = sum(1 for s in m5_samples if s['profitable']) / len(m5_samples) * 100
            
            print(f"  M5: {np.mean(m5_returns):.1f}% avg (median {np.median(m5_returns):.1f}%), {m5_profitable:.0f}% profitable")
        
        if m1_samples:
            m1_results[period_name] = m1_samples
            m1_returns = [s['return'] for s in m1_samples]
            m1_profitable = sum(1 for s in m1_samples if s['profitable']) / len(m1_samples) * 100
            
            print(f"  M1: {np.mean(m1_returns):.1f}% avg (median {np.median(m1_returns):.1f}%), {m1_profitable:.0f}% profitable")
        
        print()
    
    # Comparison table
    print("=" * 120)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 120)
    print(f"{'Period':<10} | {'M5 Avg':>9} | {'M5 Median':>10} | {'M5 Profit%':>11} | {'M1 Avg':>9} | {'M1 Median':>10} | {'M1 Profit%':>11} | {'Winner':>8}")
    print("=" * 120)
    
    for period_name in ['1 day', '3 days', '7 days', '14 days', '30 days']:
        if period_name in m5_results and period_name in m1_results:
            m5_avg = np.mean([s['return'] for s in m5_results[period_name]])
            m5_med = np.median([s['return'] for s in m5_results[period_name]])
            m5_prof = sum(1 for s in m5_results[period_name] if s['profitable']) / len(m5_results[period_name]) * 100
            
            m1_avg = np.mean([s['return'] for s in m1_results[period_name]])
            m1_med = np.median([s['return'] for s in m1_results[period_name]])
            m1_prof = sum(1 for s in m1_results[period_name] if s['profitable']) / len(m1_results[period_name]) * 100
            
            winner = "M5" if m5_avg > m1_avg else "M1" if m1_avg > m5_avg else "TIE"
            
            print(f"{period_name:<10} | {m5_avg:>8.1f}% | {m5_med:>9.1f}% | {m5_prof:>10.0f}% | {m1_avg:>8.1f}% | {m1_med:>9.1f}% | {m1_prof:>10.0f}% | {winner:>8}")
    
    print("=" * 120)
    print()
    
    # Analysis
    print("ANALYSIS:")
    print()
    
    # Compare 30-day performance
    if '30 days' in m5_results and '30 days' in m1_results:
        m5_month = np.mean([s['return'] for s in m5_results['30 days']])
        m1_month = np.mean([s['return'] for s in m1_results['30 days']])
        
        m5_month_prof = sum(1 for s in m5_results['30 days'] if s['profitable']) / len(m5_results['30 days']) * 100
        m1_month_prof = sum(1 for s in m1_results['30 days'] if s['profitable']) / len(m1_results['30 days']) * 100
        
        print("30-Day Performance:")
        print(f"  M5: {m5_month:.1f}% avg return, {m5_month_prof:.0f}% profitable")
        print(f"  M1: {m1_month:.1f}% avg return, {m1_month_prof:.0f}% profitable")
        print()
        
        if m5_month > m1_month * 1.2:
            print("  ✅ M5 WINS: Significantly better returns")
        elif m1_month > m5_month * 1.2:
            print("  ✅ M1 WINS: Significantly better returns")
        else:
            print("  ⚖ CLOSE: Both strategies perform similarly")
        print()
    
    # Compare consistency
    if '1 day' in m5_results and '1 day' in m1_results:
        m5_day_prof = sum(1 for s in m5_results['1 day'] if s['profitable']) / len(m5_results['1 day']) * 100
        m1_day_prof = sum(1 for s in m1_results['1 day'] if s['profitable']) / len(m1_results['1 day']) * 100
        
        print("Daily Consistency:")
        print(f"  M5: {m5_day_prof:.0f}% of days are profitable")
        print(f"  M1: {m1_day_prof:.0f}% of days are profitable")
        print()
        
        if m5_day_prof > m1_day_prof + 10:
            print("  ✅ M5 is more consistent on daily timeframes")
        elif m1_day_prof > m5_day_prof + 10:
            print("  ✅ M1 is more consistent on daily timeframes")
        else:
            print("  ⚖ Both have similar daily consistency")
        print()
    
    # Overall recommendation
    print("=" * 120)
    print("RECOMMENDATION:")
    print("=" * 120)
    print()
    
    if '30 days' in m5_results and '30 days' in m1_results:
        m5_month = np.mean([s['return'] for s in m5_results['30 days']])
        m1_month = np.mean([s['return'] for s in m1_results['30 days']])
        
        m5_month_prof = sum(1 for s in m5_results['30 days'] if s['profitable']) / len(m5_results['30 days']) * 100
        m1_month_prof = sum(1 for s in m1_results['30 days'] if s['profitable']) / len(m1_results['30 days']) * 100
        
        if m5_month_prof >= 90 and m1_month_prof >= 90:
            print("✅ RUN BOTH: Both strategies are excellent over monthly timeframes")
            print(f"   M5: {m5_month:.1f}% monthly, M1: {m1_month:.1f}% monthly")
            print("   Running both provides diversification")
        elif m5_month_prof >= 80 and m1_month_prof >= 80:
            print("✓ RUN BOTH: Both strategies are solid")
            print(f"   M5: {m5_month:.1f}% monthly, M1: {m1_month:.1f}% monthly")
        elif m5_month_prof > m1_month_prof + 20:
            print("⚠ PREFER M5: Much more reliable than M1")
            print(f"   M5: {m5_month_prof:.0f}% profitable vs M1: {m1_month_prof:.0f}%")
        elif m1_month_prof > m5_month_prof + 20:
            print("⚠ PREFER M1: Much more reliable than M5")
            print(f"   M1: {m1_month_prof:.0f}% profitable vs M5: {m5_month_prof:.0f}%")
        else:
            print("✓ RUN BOTH: Complementary strategies")
            print("   Different timeframes provide diversification")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
