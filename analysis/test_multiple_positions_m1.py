"""
Test multiple simultaneous positions for M1 bot
M1 already trades frequently, but might still benefit from multiple positions
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
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def strategy_single_position(df):
    """Current M1 strategy - one position at a time with adaptive exits"""
    config = {
        'fast_ema': 5,
        'slow_ema': 12,
        'rsi_period': 5,
        'rsi_buy': 35,
        'rsi_sell': 75,
        'atr_multiplier': 4.0,
        'profit_target_pct': 0.008,
        'position_size': 0.15
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
                    'entry_bar': i,
                    'entry_atr': row['ATR']
                }
        
        elif position is not None:
            exit_price = None
            bars_held = i - position['entry_bar']
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            current_pnl = current_pnl_pct * position['lev_pos']
            
            # Adaptive exits
            if current_pnl < 0 and bars_held >= 3:
                price_movement = abs(row['close'] - position['entry'])
                is_sideways = price_movement < position['entry_atr'] * 0.3
                
                if row['downtrend']:
                    exit_price = row['close']
                elif row['RSI'] > 50 and is_sideways:
                    exit_price = row['close']
            
            if not exit_price and current_pnl < 0 and bars_held >= 10:
                exit_price = row['close']
            
            if not exit_price:
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
    """Multiple M1 positions with reduced size"""
    config = {
        'fast_ema': 5,
        'slow_ema': 12,
        'rsi_period': 5,
        'rsi_buy': 35,
        'rsi_sell': 75,
        'atr_multiplier': 4.0,
        'profit_target_pct': 0.008,
        'position_size': 0.15 / max_positions
    }
    
    df = compute_indicators(df, config)
    
    positions = []
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check for new entry
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
                    'entry_bar': i,
                    'entry_atr': row['ATR']
                })
        
        # Check exits for all positions
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            exit_price = None
            bars_held = i - pos['entry_bar']
            
            current_pnl_pct = (row['close'] - pos['entry']) / pos['entry']
            current_pnl = current_pnl_pct * pos['lev_pos']
            
            # Adaptive exits
            if current_pnl < 0 and bars_held >= 3:
                price_movement = abs(row['close'] - pos['entry'])
                is_sideways = price_movement < pos['entry_atr'] * 0.3
                
                if row['downtrend']:
                    exit_price = row['close']
                elif row['RSI'] > 50 and is_sideways:
                    exit_price = row['close']
            
            if not exit_price and current_pnl < 0 and bars_held >= 10:
                exit_price = row['close']
            
            if not exit_price:
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

def strategy_multiple_conditional(df, max_positions=2):
    """Multiple M1 positions - only add if first is profitable"""
    config = {
        'fast_ema': 5,
        'slow_ema': 12,
        'rsi_period': 5,
        'rsi_buy': 35,
        'rsi_sell': 75,
        'atr_multiplier': 4.0,
        'profit_target_pct': 0.008,
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
            # Only add if first position profitable
            first_pos_pnl = (row['close'] - positions[0]['entry']) / positions[0]['entry'] * positions[0]['lev_pos']
            if first_pos_pnl > 20:  # $20+ profit (lower threshold for M1)
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
                'entry_bar': i,
                'entry_atr': row['ATR']
            })
        
        # Check exits
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            exit_price = None
            bars_held = i - pos['entry_bar']
            
            current_pnl_pct = (row['close'] - pos['entry']) / pos['entry']
            current_pnl = current_pnl_pct * pos['lev_pos']
            
            # Adaptive exits
            if current_pnl < 0 and bars_held >= 3:
                price_movement = abs(row['close'] - pos['entry'])
                is_sideways = price_movement < pos['entry_atr'] * 0.3
                
                if row['downtrend']:
                    exit_price = row['close']
                elif row['RSI'] > 50 and is_sideways:
                    exit_price = row['close']
            
            if not exit_price and current_pnl < 0 and bars_held >= 10:
                exit_price = row['close']
            
            if not exit_price:
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
    print("MULTIPLE POSITIONS TEST - M1 STRATEGY")
    print("=" * 100)
    print()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M1 data...")
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Total bars: {len(df)}")
    print()
    
    strategies = {
        'Single Position (Current)': strategy_single_position,
        'Multiple (2) - Reduced Size': lambda df: strategy_multiple_reduced_size(df, 2),
        'Multiple (2) - Conditional': lambda df: strategy_multiple_conditional(df, 2),
        'Multiple (3) - Reduced Size': lambda df: strategy_multiple_reduced_size(df, 3),
    }
    
    results = {name: [] for name in strategies}
    
    print("Testing on 30-day periods (15 samples)...")
    bars_30d = 30 * 24 * 60  # M1 bars
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
        print()
        print("   M1 benefits from multiple positions despite high trade frequency")
    else:
        print(f"⚠ KEEP SINGLE POSITION: Multiple positions don't significantly improve M1")
        print(f"   Best: {best_name} at {best_return:.1f}%")
        print(f"   Baseline: {baseline_return:.1f}%")
        print(f"   M1 already trades frequently enough with single position")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
