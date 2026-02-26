"""
Compare CURRENT single position strategies vs multiple position versions
Uses exact same dataset and strategy logic for fair comparison
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
    
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
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

# ============================================================================
# M5 STRATEGIES
# ============================================================================

def m5_single(df):
    """Current M5 strategy - single position with adaptive exits"""
    df = compute_indicators(df, 9, 21, 14)
    
    position = None
    balance = 1000
    trades = []
    position_open_time = None
    peak_profit = 0
    
    position_size = 0.15
    leverage = 25
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 25:
                entry = row['close']
                lev_pos = balance * position_size * leverage
                sl = entry - (row['ATR'] * 2.0)
                tp = entry + (entry * 0.01)
                
                position = {
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
                position_open_time = i
                peak_profit = 0
        
        elif position is not None:
            exit_price = None
            bars_held = i - position['entry_bar']
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            current_pnl = current_pnl_pct * position['lev_pos']
            
            # Track peak profit
            if current_pnl > peak_profit:
                peak_profit = current_pnl
            
            # Adaptive profit taking
            if peak_profit > 100:
                decline_pct = (peak_profit - current_pnl) / peak_profit
                if decline_pct > 0.30:
                    exit_price = row['close']
            
            if not exit_price and current_pnl > 50 and bars_held >= 15:
                if row['RSI'] > 60 and row['downtrend']:
                    exit_price = row['close']
            
            # Standard exits
            if not exit_price:
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                elif row['RSI'] > 70:
                    exit_price = row['close']
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({'pnl': pnl, 'profitable': pnl > 0})
                position = None
                position_open_time = None
                peak_profit = 0
    
    return balance, trades

def m5_multiple(df, max_positions=2):
    """M5 with multiple positions - reduced size"""
    df = compute_indicators(df, 9, 21, 14)
    
    positions = []
    balance = 1000
    trades = []
    position_open_times = {}
    peak_profits = {}
    
    position_size = 0.15 / max_positions
    leverage = 25
    next_ticket = 1
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check for new entry
        if len(positions) < max_positions:
            if row['RSI'] < 25:
                entry = row['close']
                lev_pos = balance * position_size * leverage
                sl = entry - (row['ATR'] * 2.0)
                tp = entry + (entry * 0.01)
                
                ticket = next_ticket
                next_ticket += 1
                
                positions.append({
                    'ticket': ticket,
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                })
                position_open_times[ticket] = i
                peak_profits[ticket] = 0
        
        # Check exits for all positions
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            exit_price = None
            bars_held = i - pos['entry_bar']
            ticket = pos['ticket']
            
            current_pnl_pct = (row['close'] - pos['entry']) / pos['entry']
            current_pnl = current_pnl_pct * pos['lev_pos']
            
            # Track peak profit
            if current_pnl > peak_profits[ticket]:
                peak_profits[ticket] = current_pnl
            
            # Adaptive profit taking
            if peak_profits[ticket] > 100:
                decline_pct = (peak_profits[ticket] - current_pnl) / peak_profits[ticket]
                if decline_pct > 0.30:
                    exit_price = row['close']
            
            if not exit_price and current_pnl > 50 and bars_held >= 15:
                if row['RSI'] > 60 and row['downtrend']:
                    exit_price = row['close']
            
            # Standard exits
            if not exit_price:
                if row['low'] <= pos['sl']:
                    exit_price = pos['sl']
                elif row['high'] >= pos['tp']:
                    exit_price = pos['tp']
                elif row['RSI'] > 70:
                    exit_price = row['close']
            
            if exit_price:
                pnl_pct = (exit_price - pos['entry']) / pos['entry']
                pnl = pnl_pct * pos['lev_pos']
                balance += pnl
                
                trades.append({'pnl': pnl, 'profitable': pnl > 0})
                positions_to_remove.append(idx)
                
                del position_open_times[ticket]
                del peak_profits[ticket]
        
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
    
    return balance, trades

# ============================================================================
# M1 STRATEGIES
# ============================================================================

def m1_single(df):
    """Current M1 strategy - single position with adaptive exits"""
    df = compute_indicators(df, 5, 12, 5)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 35:
                entry = row['close']
                lev_pos = balance * position_size * leverage
                sl = entry - (row['ATR'] * 4.0)
                tp = entry + (entry * 0.008)
                
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
            
            # Adaptive exits (signal-based)
            if current_pnl < 0 and bars_held >= 3:
                price_movement = abs(row['close'] - position['entry'])
                is_sideways = price_movement < position['entry_atr'] * 0.3
                
                if row['downtrend']:
                    exit_price = row['close']
                elif row['RSI'] > 50 and is_sideways:
                    exit_price = row['close']
            
            # Time-based fallback
            if not exit_price and current_pnl < 0 and bars_held >= 10:
                exit_price = row['close']
            
            # Standard exits
            if not exit_price:
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                elif row['RSI'] > 75:
                    exit_price = row['close']
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({'pnl': pnl, 'profitable': pnl > 0})
                position = None
    
    return balance, trades

def m1_multiple(df, max_positions=2):
    """M1 with multiple positions - reduced size"""
    df = compute_indicators(df, 5, 12, 5)
    
    positions = []
    balance = 1000
    trades = []
    
    position_size = 0.15 / max_positions
    leverage = 25
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check for new entry
        if len(positions) < max_positions:
            if row['RSI'] < 35:
                entry = row['close']
                lev_pos = balance * position_size * leverage
                sl = entry - (row['ATR'] * 4.0)
                tp = entry + (entry * 0.008)
                
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
            
            # Standard exits
            if not exit_price:
                if row['low'] <= pos['sl']:
                    exit_price = pos['sl']
                elif row['high'] >= pos['tp']:
                    exit_price = pos['tp']
                elif row['RSI'] > 75:
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

# ============================================================================
# MAIN TEST
# ============================================================================

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("SINGLE vs MULTIPLE POSITIONS - FAIR COMPARISON")
    print("=" * 100)
    print()
    print("Testing CURRENT strategies with and without multiple positions")
    print("Same dataset, same logic, only difference is position count")
    print()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"M5 bars: {len(df_m5)}")
    print(f"M1 bars: {len(df_m1)}")
    print()
    
    # Test on 30-day periods
    print("Testing 30-day periods (15 samples)...")
    print()
    
    m5_bars = 30 * 24 * 12
    m1_bars = 30 * 24 * 60
    
    m5_single_results = []
    m5_multiple_results = []
    m1_single_results = []
    m1_multiple_results = []
    
    # M5 tests
    max_start_m5 = len(df_m5) - m5_bars - 200
    for _ in range(15):
        start_idx = random.randint(200, max_start_m5)
        end_idx = start_idx + m5_bars
        
        df_sample = df_m5.iloc[start_idx:end_idx].copy().reset_index(drop=True)
        
        # Single
        balance, trades = m5_single(df_sample)
        if trades:
            return_pct = (balance / 1000 - 1) * 100
            win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
            m5_single_results.append({'return': return_pct, 'trades': len(trades), 'win_rate': win_rate})
        
        # Multiple
        balance, trades = m5_multiple(df_sample, 2)
        if trades:
            return_pct = (balance / 1000 - 1) * 100
            win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
            m5_multiple_results.append({'return': return_pct, 'trades': len(trades), 'win_rate': win_rate})
    
    # M1 tests
    max_start_m1 = len(df_m1) - m1_bars - 200
    for _ in range(15):
        start_idx = random.randint(200, max_start_m1)
        end_idx = start_idx + m1_bars
        
        df_sample = df_m1.iloc[start_idx:end_idx].copy().reset_index(drop=True)
        
        # Single
        balance, trades = m1_single(df_sample)
        if trades:
            return_pct = (balance / 1000 - 1) * 100
            win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
            m1_single_results.append({'return': return_pct, 'trades': len(trades), 'win_rate': win_rate})
        
        # Multiple
        balance, trades = m1_multiple(df_sample, 2)
        if trades:
            return_pct = (balance / 1000 - 1) * 100
            win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
            m1_multiple_results.append({'return': return_pct, 'trades': len(trades), 'win_rate': win_rate})
    
    # Results
    print("=" * 100)
    print("RESULTS")
    print("=" * 100)
    print()
    
    print("M5 STRATEGY:")
    m5_single_avg = np.mean([r['return'] for r in m5_single_results])
    m5_single_trades = np.mean([r['trades'] for r in m5_single_results])
    m5_single_wr = np.mean([r['win_rate'] for r in m5_single_results])
    
    m5_multiple_avg = np.mean([r['return'] for r in m5_multiple_results])
    m5_multiple_trades = np.mean([r['trades'] for r in m5_multiple_results])
    m5_multiple_wr = np.mean([r['win_rate'] for r in m5_multiple_results])
    
    m5_improvement = ((m5_multiple_avg - m5_single_avg) / abs(m5_single_avg)) * 100
    
    print(f"  Single Position:   {m5_single_avg:>6.1f}% return, {m5_single_trades:>5.0f} trades, {m5_single_wr:>5.1f}% win rate")
    print(f"  Multiple (2):      {m5_multiple_avg:>6.1f}% return, {m5_multiple_trades:>5.0f} trades, {m5_multiple_wr:>5.1f}% win rate")
    print(f"  Improvement:       {m5_improvement:>+6.1f}%")
    print()
    
    print("M1 STRATEGY:")
    m1_single_avg = np.mean([r['return'] for r in m1_single_results])
    m1_single_trades = np.mean([r['trades'] for r in m1_single_results])
    m1_single_wr = np.mean([r['win_rate'] for r in m1_single_results])
    
    m1_multiple_avg = np.mean([r['return'] for r in m1_multiple_results])
    m1_multiple_trades = np.mean([r['trades'] for r in m1_multiple_results])
    m1_multiple_wr = np.mean([r['win_rate'] for r in m1_multiple_results])
    
    m1_improvement = ((m1_multiple_avg - m1_single_avg) / abs(m1_single_avg)) * 100
    
    print(f"  Single Position:   {m1_single_avg:>6.1f}% return, {m1_single_trades:>5.0f} trades, {m1_single_wr:>5.1f}% win rate")
    print(f"  Multiple (2):      {m1_multiple_avg:>6.1f}% return, {m1_multiple_trades:>5.0f} trades, {m1_multiple_wr:>5.1f}% win rate")
    print(f"  Improvement:       {m1_improvement:>+6.1f}%")
    print()
    
    print("=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)
    print()
    
    # Current combined
    current_combined = m5_single_avg + m1_single_avg
    multiple_combined = m5_multiple_avg + m1_multiple_avg
    combined_improvement = ((multiple_combined - current_combined) / current_combined) * 100
    
    print(f"Current (single):   M5 {m5_single_avg:.1f}% + M1 {m1_single_avg:.1f}% = {current_combined:.1f}% monthly")
    print(f"Multiple (2 each):  M5 {m5_multiple_avg:.1f}% + M1 {m1_multiple_avg:.1f}% = {multiple_combined:.1f}% monthly")
    print(f"Combined improvement: {combined_improvement:+.1f}%")
    print()
    
    if combined_improvement > 10:
        print("✅ IMPLEMENT MULTIPLE POSITIONS FOR BOTH BOTS")
        print(f"   Significant improvement: {combined_improvement:+.1f}%")
    elif m5_improvement > 15 and m1_improvement < 5:
        print("✅ IMPLEMENT MULTIPLE POSITIONS FOR M5 ONLY")
        print(f"   M5 improves {m5_improvement:+.1f}%, M1 only {m1_improvement:+.1f}%")
    elif m1_improvement > 15 and m5_improvement < 5:
        print("✅ IMPLEMENT MULTIPLE POSITIONS FOR M1 ONLY")
        print(f"   M1 improves {m1_improvement:+.1f}%, M5 only {m5_improvement:+.1f}%")
    else:
        print("⚠ KEEP SINGLE POSITIONS")
        print("   Multiple positions don't provide significant improvement")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
