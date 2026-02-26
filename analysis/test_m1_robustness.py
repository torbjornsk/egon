"""
Test M1 baseline strategy robustness across multiple time periods
with larger sample sizes to get more accurate statistics
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
    
    # Fast EMAs for M1
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = -delta.clip(upper=0).rolling(5).mean()
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

def backtest_m1(df):
    """Current M1 baseline strategy"""
    df = compute_indicators(df)
    
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
    print("M1 BASELINE STRATEGY - ROBUSTNESS TEST")
    print("=" * 100)
    print()
    print("Strategy:")
    print("  - RSI < 35: Buy dips")
    print("  - RSI > 75: Exit")
    print("  - ATR 4.0x: Wide stops")
    print("  - 0.8% profit target")
    print("  - Fast re-entry after wins")
    print()
    
    # Get 90 days of data for more variety
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M1 data...")
    df_full = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Total bars: {len(df_full)}")
    print(f"Date range: {df_full.iloc[0]['time']} to {df_full.iloc[-1]['time']}")
    print()
    
    # Test different period lengths with MORE samples
    test_periods = [
        ('24 hours', 1440, 50),
        ('3 days', 4320, 40),
        ('7 days', 10080, 30),
        ('14 days', 20160, 25),
        ('30 days', 43200, 15),
    ]
    
    results_by_period = {}
    
    for period_name, bars, num_samples in test_periods:
        print(f"Testing {period_name} periods ({bars} bars, {num_samples} samples)...")
        
        samples = []
        max_start = len(df_full) - bars - 200
        
        if max_start < 0:
            print(f"  Not enough data for {period_name}")
            continue
        
        for _ in range(num_samples):
            start_idx = random.randint(200, max_start)
            end_idx = start_idx + bars
            
            df_sample = df_full.iloc[start_idx:end_idx].copy()
            df_sample = df_sample.reset_index(drop=True)
            
            balance, trades = backtest_m1(df_sample)
            
            if trades:
                return_pct = (balance / 1000 - 1) * 100
                win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
                sl_rate = sum(1 for t in trades if t['reason'] == 'SL') / len(trades) * 100
                
                samples.append({
                    'return': return_pct,
                    'trades': len(trades),
                    'win_rate': win_rate,
                    'sl_rate': sl_rate,
                    'profitable': return_pct > 0
                })
        
        if samples:
            results_by_period[period_name] = samples
            
            # Calculate statistics
            returns = [s['return'] for s in samples]
            win_rates = [s['win_rate'] for s in samples]
            sl_rates = [s['sl_rate'] for s in samples]
            profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
            
            print(f"  Samples: {len(samples)}")
            print(f"  Avg Return: {np.mean(returns):.1f}% (±{np.std(returns):.1f}%)")
            print(f"  Median Return: {np.median(returns):.1f}%")
            print(f"  Min/Max: {np.min(returns):.1f}% / {np.max(returns):.1f}%")
            print(f"  Profitable: {profitable_pct:.0f}% of periods")
            print(f"  Avg Win Rate: {np.mean(win_rates):.1f}%")
            print(f"  Avg SL Rate: {np.mean(sl_rates):.1f}%")
            print()
    
    # Summary table
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"{'Period':<12} | {'Samples':>7} | {'Avg Return':>11} | {'Median':>8} | {'Profitable':>11} | {'Win Rate':>9} | {'SL Rate':>8}")
    print("=" * 100)
    
    for period_name in ['24 hours', '3 days', '7 days', '14 days', '30 days']:
        if period_name not in results_by_period:
            continue
        
        samples = results_by_period[period_name]
        returns = [s['return'] for s in samples]
        win_rates = [s['win_rate'] for s in samples]
        sl_rates = [s['sl_rate'] for s in samples]
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        
        print(f"{period_name:<12} | {len(samples):>7} | {np.mean(returns):>10.1f}% | {np.median(returns):>7.1f}% | {profitable_pct:>10.0f}% | {np.mean(win_rates):>8.1f}% | {np.mean(sl_rates):>7.1f}%")
    
    print("=" * 100)
    print()
    
    # Analysis
    print("ANALYSIS:")
    print()
    
    # Check if longer periods are more profitable
    if '7 days' in results_by_period and '14 days' in results_by_period:
        week_return = np.mean([s['return'] for s in results_by_period['7 days']])
        two_week_return = np.mean([s['return'] for s in results_by_period['14 days']])
        
        week_median = np.median([s['return'] for s in results_by_period['7 days']])
        two_week_median = np.median([s['return'] for s in results_by_period['14 days']])
        
        print(f"7-day periods:")
        print(f"  Average: {week_return:.1f}%")
        print(f"  Median: {week_median:.1f}%")
        print()
        print(f"14-day periods:")
        print(f"  Average: {two_week_return:.1f}%")
        print(f"  Median: {two_week_median:.1f}%")
        print()
        
        if two_week_return < week_return:
            print("⚠ OBSERVATION: 14-day periods underperform 7-day periods")
            print("  This suggests:")
            print("  - High variance in strategy performance")
            print("  - Possible mean reversion in returns")
            print("  - Or recent market conditions favor shorter periods")
            print()
            
            # Check if it's a median vs mean issue
            if two_week_median > week_median:
                print("  However, MEDIAN return is higher for 14 days")
                print("  This means: A few bad 14-day periods drag down the average")
                print("  Strategy is actually more consistent than average suggests")
            else:
                print("  Even MEDIAN return is lower for 14 days")
                print("  This is a real pattern, not just outliers")
        else:
            print("✓ EXPECTED: Longer periods have higher returns")
            print("  Strategy compounds well over time")
    
    print()
    
    # Check consistency
    if '24 hours' in results_by_period:
        samples = results_by_period['24 hours']
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        avg_return = np.mean([s['return'] for s in samples])
        median_return = np.median([s['return'] for s in samples])
        
        print("24-Hour Consistency:")
        print(f"  {profitable_pct:.0f}% of periods are profitable")
        print(f"  Average: {avg_return:.1f}%, Median: {median_return:.1f}%")
        print()
        
        if profitable_pct >= 70:
            print("  ✅ EXCELLENT: Strategy is reliable on daily timeframes")
        elif profitable_pct >= 60:
            print("  ✓ GOOD: Strategy is mostly reliable")
        elif profitable_pct >= 50:
            print("  ⚠ MARGINAL: Strategy is break-even on short timeframes")
        else:
            print("  ❌ POOR: Strategy is unreliable on daily timeframes")
    
    print()
    print("=" * 100)
    print("RECOMMENDATION:")
    print("=" * 100)
    print()
    
    if '14 days' in results_by_period and '30 days' in results_by_period:
        two_week_profitable = sum(1 for s in results_by_period['14 days'] if s['profitable']) / len(results_by_period['14 days']) * 100
        month_profitable = sum(1 for s in results_by_period['30 days'] if s['profitable']) / len(results_by_period['30 days']) * 100
        
        two_week_return = np.mean([s['return'] for s in results_by_period['14 days']])
        month_return = np.mean([s['return'] for s in results_by_period['30 days']])
        
        if month_profitable >= 80 and month_return > 10:
            print("✅ DEPLOY: Strategy is reliable and profitable over monthly timeframes")
            print(f"   30-day periods: {month_return:.1f}% avg return, {month_profitable:.0f}% profitable")
        elif two_week_profitable >= 70 and two_week_return > 5:
            print("✓ DEPLOY: Strategy is solid over 2-week timeframes")
            print(f"   14-day periods: {two_week_return:.1f}% avg return, {two_week_profitable:.0f}% profitable")
        else:
            print("⚠ CAUTION: Strategy has high variance")
            print("   Monitor closely and be patient through drawdowns")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
