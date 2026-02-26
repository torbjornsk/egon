"""
Test if M1 is holding winners too long
Compare different exit strategies:
1. Current: RSI 75 exit
2. Tighter: RSI 70 exit (sell sooner)
3. Trailing stop: Lock in profits after hitting certain threshold
4. Profit-based: Exit at 0.5% instead of waiting for RSI
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

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
    
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def strategy_current(df):
    """Current: Exit at RSI 75"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    missed_profits = []  # Track how much profit we gave back
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
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
                    'peak_profit_pct': 0
                }
            
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * 0.008)
                
                position = {
                    'type': 'short', 
                    'entry': entry, 
                    'lev_pos': lev_pos, 
                    'sl': sl, 
                    'tp': tp,
                    'peak_profit_pct': 0
                }
        
        elif position is not None:
            # Track peak profit
            if position['type'] == 'long':
                current_profit_pct = (row['close'] - position['entry']) / position['entry'] * 100
            else:
                current_profit_pct = (position['entry'] - row['close']) / position['entry'] * 100
            
            if current_profit_pct > position['peak_profit_pct']:
                position['peak_profit_pct'] = current_profit_pct
            
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
            else:
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
                
                # Calculate how much profit we gave back
                exit_profit_pct = pnl_pct * 100
                profit_given_back = position['peak_profit_pct'] - exit_profit_pct
                
                trades.append({
                    'pnl': pnl, 
                    'reason': exit_reason,
                    'peak_profit_pct': position['peak_profit_pct'],
                    'exit_profit_pct': exit_profit_pct,
                    'gave_back': profit_given_back
                })
                
                if profit_given_back > 0.2:  # Gave back more than 0.2%
                    missed_profits.append(profit_given_back)
                
                position = None
    
    return balance, trades, missed_profits

def strategy_tighter_exit(df, rsi_exit=70):
    """Exit at RSI 70 instead of 75"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 35:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * 0.008)
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * 0.008)
                position = {'type': 'short', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
        
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
                elif row['RSI'] > rsi_exit:  # Tighter exit
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < (100 - rsi_exit):
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                trades.append({'pnl': pnl, 'reason': exit_reason})
                position = None
    
    return balance, trades

def strategy_trailing_stop(df):
    """Lock in profits with trailing stop after hitting 0.4% profit"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
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
                    'trailing_active': False,
                    'peak_price': entry
                }
            
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * 0.008)
                position = {
                    'type': 'short', 
                    'entry': entry, 
                    'lev_pos': lev_pos, 
                    'sl': sl, 
                    'tp': tp,
                    'trailing_active': False,
                    'peak_price': entry
                }
        
        elif position is not None:
            # Update trailing stop
            if position['type'] == 'long':
                profit_pct = (row['close'] - position['entry']) / position['entry']
                
                # Activate trailing after 0.4% profit
                if profit_pct > 0.004:
                    position['trailing_active'] = True
                
                if position['trailing_active']:
                    if row['close'] > position['peak_price']:
                        position['peak_price'] = row['close']
                        # Trail stop at 0.2% below peak
                        position['sl'] = position['peak_price'] * 0.998
            else:
                profit_pct = (position['entry'] - row['close']) / position['entry']
                
                if profit_pct > 0.004:
                    position['trailing_active'] = True
                
                if position['trailing_active']:
                    if row['close'] < position['peak_price']:
                        position['peak_price'] = row['close']
                        position['sl'] = position['peak_price'] * 1.002
            
            exit_price = None
            exit_reason = None
            
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
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
                trades.append({'pnl': pnl, 'reason': exit_reason})
                position = None
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("M1 EXIT TIMING ANALYSIS")
    print("="*100)
    print()
    
    # Get last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print("Fetching 30 days of M1 data...")
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Bars: {len(df)}")
    print()
    
    # Test strategies
    print("Testing exit strategies...")
    print()
    
    balance_current, trades_current, missed = strategy_current(df)
    balance_rsi70, trades_rsi70 = strategy_tighter_exit(df, rsi_exit=70)
    balance_rsi65, trades_rsi65 = strategy_tighter_exit(df, rsi_exit=65)
    balance_trail, trades_trail = strategy_trailing_stop(df)
    
    # Analyze missed profits
    if missed:
        print("PROFIT GIVE-BACK ANALYSIS (Current Strategy):")
        print(f"  Trades that gave back >0.2%: {len(missed)}")
        print(f"  Avg profit given back: {np.mean(missed):.2f}%")
        print(f"  Max profit given back: {max(missed):.2f}%")
        print(f"  Total profit lost: {sum(missed):.2f}%")
        print()
    
    # Compare results
    results = [
        ("Current (RSI 75)", balance_current, trades_current),
        ("Tighter (RSI 70)", balance_rsi70, trades_rsi70),
        ("Tighter (RSI 65)", balance_rsi65, trades_rsi65),
        ("Trailing Stop", balance_trail, trades_trail),
    ]
    
    print("="*100)
    print("RESULTS COMPARISON")
    print("="*100)
    print(f"{'Strategy':<20} | {'Return':>8} | {'Trades':>6} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9}")
    print("="*100)
    
    for name, balance, trades in results:
        if not trades:
            continue
        
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        
        return_pct = (balance / 1000 - 1) * 100
        win_rate = len(winning) / len(trades) * 100
        avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
        avg_loss = losing['pnl'].mean() if len(losing) > 0 else 0
        
        print(f"{name:<20} | {return_pct:>7.1f}% | {len(trades):>6} | {win_rate:>5.1f} | ${avg_win:>7.2f} | ${avg_loss:>8.2f}")
    
    print("="*100)
    
    # Find best
    best = max(results, key=lambda x: x[1])
    print(f"\nBEST: {best[0]} with {(best[1]/1000-1)*100:.1f}% return")
    
    if best[0] != "Current (RSI 75)":
        improvement = (best[1] / balance_current - 1) * 100
        print(f"Improvement over current: +{improvement:.1f}%")
        print(f"\nRECOMMENDATION: Switch M1 to {best[0]}")
    else:
        print(f"\nRECOMMENDATION: Current exit timing is already optimal")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
