"""
Test multiple simultaneous positions vs single position
Compare: 
1. Single position (current)
2. Multiple positions with reduced size
3. Multiple positions with conditions
"""

import sys
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

sys.path.append('.')
from src.mt5_connector import MT5Connector

def compute_indicators(df, config):
    df = df.copy()
    
    df['ema_fast'] = df['close'].ewm(span=config['fast_ema']).mean()
    df['ema_slow'] = df['close'].ewm(span=config['slow_ema']).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(config['rsi_period']).mean()
    loss = -delta.clip(upper=0).rolling(config['rsi_period']).mean()
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

def strategy_single_position(df):
    """Current strategy - one position at a time"""
    config = {
        'fast_ema': 9,
        'slow_ema': 21,
        'rsi_period': 14,
        'rsi_buy': 25,
        'rsi_sell': 70,
        'atr_multiplier': 2.0,
        'profit_target_pct': 0.01,
        'position_size': 0.15  # 15% @ 25x
    }
    
    df = compute_indicators(df, config)
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                lev_pos = balance * config['position_size'] * 25
                sl = entry - (row['ATR'] * config['atr_multiplier'])
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
        
        elif position is not None:
            exit_price = None
            
            if row['low'] <= position['sl']:
                exit_price = position['sl']
            elif row['high'] >= position['tp']:
                exit_price = position['tp']
            elif row['RSI'] > config['rsi_sell']:
                exit_price = row['close']
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({'pnl': pnl, 'profitable': pnl > 0})
                position = None
    
    return balance, trades

def strategy_multiple_reduced_size(df, max_positions=2):
    """Multiple positions with reduced size to maintain same total exposure"""
    config = {
        'fast_ema': 9,
        'slow_ema': 21,
        'rsi_period': 14,
        'rsi_buy': 25,
        'rsi_sell': 70,
        'atr_multiplier': 2.0,
        'profit_target_pct': 0.01,
        'position_size': 0.15 / max_positions  # Split position size
    }
    
    df = compute_indicators(df, config)
    
    positions = []
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check for new entry if not at max positions
        if len(positions) < max_positions:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                lev_pos = balance * config['position_size'] * 25
                sl = entry - (row['ATR'] * config['atr_multiplier'])
                tp = entry + (entry * config['profit_target_pct'])
                
                positions.append({
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                })
        
        # Check exits for all positions
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            exit_price = None
            
            if row['low'] <= pos['sl']:
                exit_price = pos['sl']
            elif row['high'] >= pos['tp']:
                exit_price = pos['tp']
            elif row['RSI'] > config['rsi_sell']:
                exit_price = row['close']
            
            if exit_price:
                pnl_pct = (exit_price - pos['entry']) / pos['entry']
                pnl = pnl_pct * pos['lev_pos']
                balance += pnl
                
                trades.append({'pnl': pnl, 'profitable': pnl > 0})
                positions_to_remove.append(idx)
        
        # Remove closed positions
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
    
    return balance, trades

def strategy_multiple_conditional(df, max_positions=2):
    """Multiple positions with conditions: only add if first is profitable"""
    config = {
        'fast_ema': 9,
        'slow_ema': 21,
        'rsi_period': 14,
        'rsi_buy': 25,
        'rsi_sell': 70,
        'atr_multiplier': 2.0,
        'profit_target_pct': 0.01,
        'position_size': 0.15 / max_positions
    }
    
    df = compute_indicators(df, config)
    
    positions = []
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check for new entry
        can_add_position = False
        if len(positions) == 0:
            can_add_position = True
        elif len(positions) < max_positions:
            # Only add second position if first is profitable
            first_pos_pnl = (row['close'] - positions[0]['entry']) / positions[0]['entry'] * positions[0]['lev_pos']
            if first_pos_pnl > 50:  # First position has $50+ profit
                can_add_position = True
        
        if can_add_position and row['RSI'] < config['rsi_buy']:
            entry = row['close']
            lev_pos = balance * config['position_size'] * 25
            sl = entry - (row['ATR'] * config['atr_multiplier'])
            tp = entry + (entry * config['profit_target_pct'])
            
            positions.append({
                'entry': entry,
                'lev_pos': lev_pos,
                'sl': sl,
                'tp': tp,
                'entry_bar': i
            })
        
        # Check exits
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            exit_price = None
            
            if row['low'] <= pos['sl']:
                exit_price = pos['sl']
            elif row['high'] >= pos['tp']:
                exit_price = pos['tp']
            elif row['RSI'] > config['rsi_sell']:
                exit_price = row['close']
            
            if exit_price:
                pnl_pct = (exit_price - pos['entry']) / pos['entry']
                pnl = pnl_pct * pos['lev_pos']
                balance += pnl
                
                trades.append({'pnl': pnl, 'profitable': pnl > 0})
                positions_to_remove.append(idx)
        
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("MULTIPLE POSITIONS TEST - M5 STRATEGY")
    print("=" * 100)
    print()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M5 data...")
    df = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    print(f"Total bars: {len(df)}")
    print()
    
    strategies = {
        'Single Position (Current)': strategy_single_position,
        'Multiple (2) - Reduced Size': lambda df: strategy_multiple_reduced_size(df, 2),
        'Multiple (2) - Conditional': lambda df: strategy_multiple_conditional(df, 2),
    }
    
    results = {name: [] for name in strategies}
    
    print("Testing on 30-day periods (15 samples)...")
    bars_30d = 30 * 24 * 12
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
                
                results[name].append({
                    'return': return_pct,
                    'trades': len(trades),
                    'win_rate': win_rate
                })
    
    print()
    print("=" * 100)
    print("RESULTS (30-day periods, 15 samples)")
    print("=" * 100)
    print(f"{'Strategy':<35} | {'Avg Return':>11} | {'Avg Trades':>11} | {'Win Rate':>9} | {'vs Single':>10}")
    print("=" * 100)
    
    baseline_return = np.mean([r['return'] for r in results['Single Position (Current)']])
    
    for name in strategies.keys():
        if results[name]:
            avg_return = np.mean([r['return'] for r in results[name]])
            avg_trades = np.mean([r['trades'] for r in results[name]])
            avg_win_rate = np.mean([r['win_rate'] for r in results[name]])
            
            improvement = ((avg_return - baseline_return) / abs(baseline_return)) * 100 if baseline_return != 0 else 0
            
            print(f"{name:<35} | {avg_return:>10.1f}% | {avg_trades:>10.1f} | {avg_win_rate:>8.1f}% | {improvement:>9.1f}%")
    
    print("=" * 100)
    print()
    
    # Recommendation
    best_name = max(strategies.keys(), key=lambda n: np.mean([r['return'] for r in results[n]]))
    best_return = np.mean([r['return'] for r in results[best_name]])
    
    print("RECOMMENDATION:")
    print()
    
    if best_return > baseline_return * 1.1:
        print(f"✅ IMPLEMENT: {best_name}")
        print(f"   Return: {best_return:.1f}% (vs {baseline_return:.1f}% baseline)")
        print(f"   Improvement: {((best_return - baseline_return) / abs(baseline_return)) * 100:+.1f}%")
    else:
        print(f"⚠ KEEP SINGLE POSITION: Multiple positions don't significantly improve performance")
        print(f"   Best: {best_name} at {best_return:.1f}%")
        print(f"   Baseline: {baseline_return:.1f}%")
        print(f"   Added complexity not worth small gain")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
