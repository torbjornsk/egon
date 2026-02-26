"""
Focused improvement: Adaptive exits while holding
- Cut losses faster when price action turns against us
- Let winners run longer when momentum is strong
- No trend filter, no dynamic sizing - just smarter exits
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, timeframe='M5'):
    df = df.copy()
    
    if timeframe == 'M5':
        fast_span = 12
        slow_span = 26
        rsi_period = 14
    else:
        fast_span = 5
        slow_span = 12
        rsi_period = 5
    
    df['ema_fast'] = df['close'].ewm(span=fast_span).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_span).mean()
    
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

def strategy_current(df, config, timeframe='M5'):
    """Current strategy"""
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            elif row['RSI'] > config['rsi_sell'] and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * config['profit_target_pct'])
                
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
                elif row['RSI'] > config.get('rsi_exit_long', 75):
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < config.get('rsi_exit_short', 25):
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

def strategy_adaptive_exits(df, config, timeframe='M5'):
    """
    Adaptive exits: Monitor each candle while holding
    - If losing and RSI reverses against us: exit early
    - If winning and RSI pushes further: delay exit
    """
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_rsi': row['RSI'],
                    'peak_price': entry,
                    'trailing_active': False
                }
            
            elif row['RSI'] > config['rsi_sell'] and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * config['profit_target_pct'])
                
                position = {
                    'type': 'short',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_rsi': row['RSI'],
                    'peak_price': entry,
                    'trailing_active': False
                }
        
        elif position is not None:
            # Track peak for trailing
            if position['type'] == 'long' and row['close'] > position['peak_price']:
                position['peak_price'] = row['close']
            elif position['type'] == 'short' and row['close'] < position['peak_price']:
                position['peak_price'] = row['close']
            
            # Calculate profit
            if position['type'] == 'long':
                profit_pct = (row['close'] - position['entry']) / position['entry']
            else:
                profit_pct = (position['entry'] - row['close']) / position['entry']
            
            # ADAPTIVE EXIT LOGIC
            exit_price = None
            exit_reason = None
            
            # Standard exits first
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
            
            # If not hit SL/TP, check adaptive exits
            if not exit_price:
                if position['type'] == 'long':
                    # ADAPTIVE: If losing and RSI turning down, exit early
                    if profit_pct < 0 and row['RSI'] > position['entry_rsi'] + 10:
                        # RSI moved up but price didn't follow - weak bounce
                        exit_price = row['close']
                        exit_reason = "Adaptive_Cut"
                    
                    # ADAPTIVE: If winning big, activate trailing stop
                    elif profit_pct > 0.005:  # 0.5% profit
                        if not position['trailing_active']:
                            position['trailing_active'] = True
                        
                        # Trail at 0.2% below peak
                        trail_sl = position['peak_price'] * 0.998
                        if trail_sl > position['sl']:
                            position['sl'] = trail_sl
                    
                    # Standard RSI exit, but delay if still strong
                    elif row['RSI'] > config.get('rsi_exit_long', 75):
                        # If profitable and RSI still climbing, wait
                        if profit_pct > 0.002 and row['RSI'] < 90:
                            pass  # Hold longer
                        else:
                            exit_price = row['close']
                            exit_reason = "RSI"
                
                else:  # SHORT
                    # ADAPTIVE: If losing and RSI turning up, exit early
                    if profit_pct < 0 and row['RSI'] < position['entry_rsi'] - 10:
                        exit_price = row['close']
                        exit_reason = "Adaptive_Cut"
                    
                    # ADAPTIVE: Trailing stop for winners
                    elif profit_pct > 0.005:
                        if not position['trailing_active']:
                            position['trailing_active'] = True
                        
                        trail_sl = position['peak_price'] * 1.002
                        if trail_sl < position['sl']:
                            position['sl'] = trail_sl
                    
                    # Standard RSI exit with delay
                    elif row['RSI'] < config.get('rsi_exit_short', 25):
                        if profit_pct > 0.002 and row['RSI'] > 10:
                            pass  # Hold longer
                        else:
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
    print("ADAPTIVE EXITS TEST")
    print("="*100)
    print()
    print("Focus: Better position management while holding")
    print("  - Cut losses when RSI reverses against us")
    print("  - Trail stops on big winners")
    print("  - Delay exits when momentum still strong")
    print()
    
    # Load configs
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    # Get data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print()
    
    # Test M5
    print("="*100)
    print("M5 BOT")
    print("="*100)
    
    balance_m5_current, trades_m5_current = strategy_current(df_m5, m5_config, 'M5')
    balance_m5_adaptive, trades_m5_adaptive = strategy_adaptive_exits(df_m5, m5_config, 'M5')
    
    print(f"\nCurrent: ${balance_m5_current:.2f} ({(balance_m5_current/1000-1)*100:+.1f}%), {len(trades_m5_current)} trades")
    print(f"Adaptive: ${balance_m5_adaptive:.2f} ({(balance_m5_adaptive/1000-1)*100:+.1f}%), {len(trades_m5_adaptive)} trades")
    print(f"Improvement: {(balance_m5_adaptive/balance_m5_current-1)*100:+.1f}%")
    
    if trades_m5_adaptive:
        trades_df = pd.DataFrame(trades_m5_adaptive)
        print(f"\nExit breakdown:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"  {reason}: {count} ({count/len(trades_df)*100:.1f}%)")
    
    # Test M1
    print()
    print("="*100)
    print("M1 BOT")
    print("="*100)
    
    balance_m1_current, trades_m1_current = strategy_current(df_m1, m1_config, 'M1')
    balance_m1_adaptive, trades_m1_adaptive = strategy_adaptive_exits(df_m1, m1_config, 'M1')
    
    print(f"\nCurrent: ${balance_m1_current:.2f} ({(balance_m1_current/1000-1)*100:+.1f}%), {len(trades_m1_current)} trades")
    print(f"Adaptive: ${balance_m1_adaptive:.2f} ({(balance_m1_adaptive/1000-1)*100:+.1f}%), {len(trades_m1_adaptive)} trades")
    print(f"Improvement: {(balance_m1_adaptive/balance_m1_current-1)*100:+.1f}%")
    
    if trades_m1_adaptive:
        trades_df = pd.DataFrame(trades_m1_adaptive)
        print(f"\nExit breakdown:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"  {reason}: {count} ({count/len(trades_df)*100:.1f}%)")
    
    # Summary
    print()
    print("="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    m5_improvement = (balance_m5_adaptive / balance_m5_current - 1) * 100
    m1_improvement = (balance_m1_adaptive / balance_m1_current - 1) * 100
    
    if m5_improvement > 5 or m1_improvement > 5:
        print("\n✓ Implement adaptive exits!")
        print(f"  M5: {m5_improvement:+.1f}% improvement")
        print(f"  M1: {m1_improvement:+.1f}% improvement")
    elif m5_improvement > 0 and m1_improvement > 0:
        print("\n~ Consider adaptive exits")
        print(f"  M5: {m5_improvement:+.1f}% improvement")
        print(f"  M1: {m1_improvement:+.1f}% improvement")
        print("  Modest gains, test live first")
    else:
        print("\n✗ Keep current strategy")
        print(f"  M5: {m5_improvement:+.1f}%")
        print(f"  M1: {m1_improvement:+.1f}%")
        print("  Current strategy is already optimal")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
