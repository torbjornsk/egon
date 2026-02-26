"""
Test IMPROVED M1 strategy (with limit orders, adaptive exits, fast re-entry)
across multiple random time periods to validate robustness
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

def backtest_baseline_m1(df):
    """Baseline M1 strategy (market orders, no adaptive exits)"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0  # Actual M1 config
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # Buy dips
            if row['RSI'] < 35:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * 0.008)  # Actual M1 config
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
        
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
                trades.append({'pnl': pnl, 'reason': exit_reason, 'profitable': pnl > 0})
                position = None
    
    return balance, trades

def backtest_improved_m1(df):
    """
    Improved M1 strategy with:
    1. Limit orders (0.015% offset)
    2. Adaptive exits
    3. Fast re-entry after wins
    """
    df = compute_indicators(df)
    
    position = None
    pending_order = None
    balance = 1000
    trades = []
    last_trade_profitable = False
    cooldown_candles = 2
    last_close_bar = None
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0  # Actual M1 config
    limit_offset_pct = 0.015
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None and pending_order is None:
            # Check cooldown (skip if last trade was profitable)
            if last_close_bar is not None:
                bars_since_close = i - last_close_bar
                if not last_trade_profitable and bars_since_close < cooldown_candles:
                    continue
            
            # LONG ENTRY - Place limit order below current price
            if row['RSI'] < 35:
                limit_price = row['close'] * (1 - limit_offset_pct / 100)
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = limit_price - (row['ATR'] * atr_mult)
                tp = limit_price + (limit_price * 0.008)  # Actual M1 config
                
                pending_order = {
                    'type': 'long',
                    'limit_price': limit_price,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_rsi': row['RSI'],
                    'placed_bar': i
                }
        
        elif pending_order is not None:
            # Check if limit order would be filled
            if row['low'] <= pending_order['limit_price']:
                # Order filled!
                position = {
                    'type': pending_order['type'],
                    'entry': pending_order['limit_price'],
                    'lev_pos': pending_order['lev_pos'],
                    'sl': pending_order['sl'],
                    'tp': pending_order['tp'],
                    'entry_rsi': pending_order['entry_rsi'],
                    'entry_bar': i
                }
                pending_order = None
            
            # Cancel if RSI moved away (signal invalidated)
            elif row['RSI'] > 40:
                pending_order = None
            
            # Update limit price if still in entry zone
            elif row['RSI'] < 35:
                new_limit = row['close'] * (1 - limit_offset_pct / 100)
                if new_limit < pending_order['limit_price']:
                    pending_order['limit_price'] = new_limit
                    pending_order['sl'] = new_limit - (row['ATR'] * atr_mult)
                    pending_order['tp'] = new_limit + (new_limit * 0.008)  # Actual M1 config
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            # Calculate current profit
            current_profit_pct = (row['close'] - position['entry']) / position['entry']
            
            if position['type'] == 'long':
                # ADAPTIVE EXIT: Early loss cutting
                if current_profit_pct < 0 and row['RSI'] > position['entry_rsi'] + 10:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_CUT"
                # Stop loss
                elif row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                # Take profit
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                # ADAPTIVE EXIT: Delayed exit for winners
                elif row['RSI'] > 75:
                    if current_profit_pct > 0.002 and row['RSI'] < 90:
                        # Hold longer - momentum still strong
                        pass
                    else:
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
    print("IMPROVED M1 STRATEGY - MULTI-PERIOD ROBUSTNESS TEST")
    print("=" * 100)
    print()
    print("Testing:")
    print("  ✓ Limit orders (0.015% offset)")
    print("  ✓ Adaptive exits (early cuts + delayed exits)")
    print("  ✓ Fast re-entry after wins")
    print()
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching 60 days of M1 data...")
    df_full = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Total bars: {len(df_full)}")
    print()
    
    # Test different period lengths
    test_periods = [
        ('24 hours', 1440),
        ('3 days', 4320),
        ('7 days', 10080),
        ('14 days', 20160),
    ]
    
    baseline_results = {}
    improved_results = {}
    
    for period_name, bars in test_periods:
        print(f"Testing {period_name} periods ({bars} bars)...")
        
        # Sample 20 random periods
        baseline_samples = []
        improved_samples = []
        max_start = len(df_full) - bars - 200
        
        if max_start < 0:
            print(f"  Not enough data for {period_name}")
            continue
        
        for _ in range(20):
            start_idx = random.randint(200, max_start)
            end_idx = start_idx + bars
            
            df_sample = df_full.iloc[start_idx:end_idx].copy()
            df_sample = df_sample.reset_index(drop=True)
            
            # Test baseline
            balance_base, trades_base = backtest_baseline_m1(df_sample)
            if trades_base:
                return_base = (balance_base / 1000 - 1) * 100
                win_rate_base = sum(1 for t in trades_base if t['profitable']) / len(trades_base) * 100
                sl_rate_base = sum(1 for t in trades_base if t['reason'] == 'SL') / len(trades_base) * 100
                
                baseline_samples.append({
                    'return': return_base,
                    'trades': len(trades_base),
                    'win_rate': win_rate_base,
                    'sl_rate': sl_rate_base,
                    'profitable': return_base > 0
                })
            
            # Test improved
            balance_imp, trades_imp = backtest_improved_m1(df_sample)
            if trades_imp:
                return_imp = (balance_imp / 1000 - 1) * 100
                win_rate_imp = sum(1 for t in trades_imp if t['profitable']) / len(trades_imp) * 100
                sl_rate_imp = sum(1 for t in trades_imp if t['reason'] == 'SL') / len(trades_imp) * 100
                adaptive_rate = sum(1 for t in trades_imp if t['reason'] == 'ADAPTIVE_CUT') / len(trades_imp) * 100
                
                improved_samples.append({
                    'return': return_imp,
                    'trades': len(trades_imp),
                    'win_rate': win_rate_imp,
                    'sl_rate': sl_rate_imp,
                    'adaptive_rate': adaptive_rate,
                    'profitable': return_imp > 0
                })
        
        if baseline_samples and improved_samples:
            baseline_results[period_name] = baseline_samples
            improved_results[period_name] = improved_samples
            
            # Calculate statistics
            base_returns = [s['return'] for s in baseline_samples]
            imp_returns = [s['return'] for s in improved_samples]
            
            base_profitable = sum(1 for s in baseline_samples if s['profitable']) / len(baseline_samples) * 100
            imp_profitable = sum(1 for s in improved_samples if s['profitable']) / len(improved_samples) * 100
            
            improvement = ((np.mean(imp_returns) - np.mean(base_returns)) / abs(np.mean(base_returns))) * 100 if np.mean(base_returns) != 0 else 0
            
            print(f"  BASELINE:")
            print(f"    Avg Return: {np.mean(base_returns):.1f}% (±{np.std(base_returns):.1f}%)")
            print(f"    Profitable: {base_profitable:.0f}% of periods")
            print(f"    Avg Win Rate: {np.mean([s['win_rate'] for s in baseline_samples]):.1f}%")
            print(f"  IMPROVED:")
            print(f"    Avg Return: {np.mean(imp_returns):.1f}% (±{np.std(imp_returns):.1f}%)")
            print(f"    Profitable: {imp_profitable:.0f}% of periods")
            print(f"    Avg Win Rate: {np.mean([s['win_rate'] for s in improved_samples]):.1f}%")
            print(f"    Adaptive Cuts: {np.mean([s['adaptive_rate'] for s in improved_samples]):.1f}%")
            print(f"  IMPROVEMENT: {improvement:+.1f}%")
            print()
    
    # Summary comparison
    print("=" * 100)
    print("SUMMARY COMPARISON")
    print("=" * 100)
    print(f"{'Period':<15} | {'Baseline Return':>15} | {'Improved Return':>15} | {'Improvement':>12} | {'Profitable':>11}")
    print("=" * 100)
    
    for period_name in ['24 hours', '3 days', '7 days', '14 days']:
        if period_name not in baseline_results or period_name not in improved_results:
            continue
        
        base_samples = baseline_results[period_name]
        imp_samples = improved_results[period_name]
        
        base_return = np.mean([s['return'] for s in base_samples])
        imp_return = np.mean([s['return'] for s in imp_samples])
        improvement = ((imp_return - base_return) / abs(base_return)) * 100 if base_return != 0 else 0
        imp_profitable = sum(1 for s in imp_samples if s['profitable']) / len(imp_samples) * 100
        
        print(f"{period_name:<15} | {base_return:>14.1f}% | {imp_return:>14.1f}% | {improvement:>11.1f}% | {imp_profitable:>10.0f}%")
    
    print("=" * 100)
    print()
    
    # Detailed analysis
    print("DETAILED ANALYSIS:")
    print()
    
    if '24 hours' in improved_results:
        samples = improved_results['24 hours']
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        avg_return = np.mean([s['return'] for s in samples])
        median_return = np.median([s['return'] for s in samples])
        
        print(f"24-Hour Performance:")
        print(f"  Average Return: {avg_return:.1f}%")
        print(f"  Median Return: {median_return:.1f}%")
        print(f"  Profitable Periods: {profitable_pct:.0f}%")
        print()
        
        if profitable_pct >= 60:
            print("  ✅ EXCELLENT: Most 24-hour periods are profitable")
            print("     Strategy is reliable on daily timeframes")
        elif profitable_pct >= 50:
            print("  ✓ GOOD: Majority of 24-hour periods are profitable")
            print("     Strategy is solid with acceptable variance")
        else:
            print("  ⚠ MARGINAL: Less than half of 24-hour periods are profitable")
            print("     Strategy needs longer timeframes to be reliable")
        print()
    
    if '14 days' in improved_results:
        samples = improved_results['14 days']
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        avg_return = np.mean([s['return'] for s in samples])
        
        print(f"14-Day Performance:")
        print(f"  Average Return: {avg_return:.1f}%")
        print(f"  Profitable Periods: {profitable_pct:.0f}%")
        print()
        
        if profitable_pct >= 80:
            print("  ✅ EXCELLENT: Strategy is very reliable over 2 weeks")
        elif profitable_pct >= 70:
            print("  ✓ GOOD: Strategy is reliable over 2 weeks")
        else:
            print("  ⚠ NEEDS IMPROVEMENT: Strategy still has high variance")
        print()
    
    # Overall improvement
    print("=" * 100)
    print("OVERALL IMPROVEMENT SUMMARY")
    print("=" * 100)
    print()
    
    total_improvement = []
    for period_name in ['24 hours', '3 days', '7 days', '14 days']:
        if period_name in baseline_results and period_name in improved_results:
            base_return = np.mean([s['return'] for s in baseline_results[period_name]])
            imp_return = np.mean([s['return'] for s in improved_results[period_name]])
            improvement = ((imp_return - base_return) / abs(base_return)) * 100 if base_return != 0 else 0
            total_improvement.append(improvement)
    
    if total_improvement:
        avg_improvement = np.mean(total_improvement)
        print(f"Average Improvement Across All Periods: {avg_improvement:+.1f}%")
        print()
        
        if avg_improvement > 50:
            print("✅ MAJOR IMPROVEMENT: New features significantly boost performance")
        elif avg_improvement > 25:
            print("✓ GOOD IMPROVEMENT: New features provide solid gains")
        elif avg_improvement > 0:
            print("⚠ MINOR IMPROVEMENT: New features help but gains are modest")
        else:
            print("❌ NO IMPROVEMENT: New features don't help (or hurt)")
    
    print()
    print("RECOMMENDATION:")
    print()
    
    if '24 hours' in improved_results:
        samples = improved_results['24 hours']
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        avg_return = np.mean([s['return'] for s in samples])
        
        if profitable_pct >= 60 and avg_return > 2:
            print("  ✅ DEPLOY: Improved M1 strategy is reliable and profitable")
            print("     Safe to run in live trading")
        elif profitable_pct >= 50:
            print("  ✓ DEPLOY WITH CAUTION: Strategy is profitable but has variance")
            print("     Monitor closely and be patient through drawdowns")
        else:
            print("  ⚠ NEEDS MORE WORK: Strategy still too unreliable on short timeframes")
            print("     Consider further optimizations or longer evaluation periods")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
