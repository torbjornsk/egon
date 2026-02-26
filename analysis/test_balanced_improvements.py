"""
Balanced approach: Keep what works, improve what doesn't
1. No cooldown after wins (more opportunities)
2. Wider trailing stops (lock profits but let winners breathe)
3. Keep standard exits (they work!)
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
    cooldown_bars = 2
    bars_since_close = 999
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        bars_since_close += 1
        
        if position is None:
            if bars_since_close < cooldown_bars:
                continue
            
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
                bars_since_close = 0
    
    return balance, trades

def strategy_balanced(df, config, timeframe='M5'):
    """
    Balanced improvements:
    1. No cooldown after wins - Jump back in faster
    2. Wide trailing stops - Lock big profits only (>1%)
    3. Keep standard exits - They work!
    """
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    trades = []
    cooldown_bars = 2
    bars_since_close = 999
    last_trade_profitable = False
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        bars_since_close += 1
        
        if position is None:
            # IMPROVEMENT 1: No cooldown after wins
            if not last_trade_profitable and bars_since_close < cooldown_bars:
                continue
            
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
            
            # IMPROVEMENT 2: Wide trailing stops (only for big winners)
            if profit_pct > 0.01:  # After 1% profit (not 0.3%)
                position['trailing_active'] = True
                
                if position['type'] == 'long':
                    # Trail at 0.5% below peak (wider than 0.25%)
                    trail_sl = position['peak_price'] * 0.995
                    if trail_sl > position['sl']:
                        position['sl'] = trail_sl
                else:
                    trail_sl = position['peak_price'] * 1.005
                    if trail_sl < position['sl']:
                        position['sl'] = trail_sl
            
            exit_price = None
            exit_reason = None
            
            # Standard exits (keep what works!)
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > config.get('rsi_exit_long', 75):
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
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
                last_trade_profitable = (pnl > 0)
                trades.append({'pnl': pnl, 'reason': exit_reason})
                position = None
                bars_since_close = 0
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("BALANCED IMPROVEMENTS TEST")
    print("="*100)
    print()
    print("Conservative profit maximization:")
    print("  1. No cooldown after wins - More opportunities")
    print("  2. Wide trailing stops - Lock BIG profits only (>1%)")
    print("  3. Keep standard exits - They work!")
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
    
    # Test both
    for bot_name, df, config, timeframe in [
        ('M5', df_m5, m5_config, 'M5'),
        ('M1', df_m1, m1_config, 'M1')
    ]:
        print("="*100)
        print(f"{bot_name} BOT")
        print("="*100)
        
        balance_current, trades_current = strategy_current(df, config, timeframe)
        balance_balanced, trades_balanced = strategy_balanced(df, config, timeframe)
        
        print(f"\nCurrent: ${balance_current:.2f} ({(balance_current/1000-1)*100:+.1f}%), {len(trades_current)} trades")
        print(f"Balanced: ${balance_balanced:.2f} ({(balance_balanced/1000-1)*100:+.1f}%), {len(trades_balanced)} trades")
        
        improvement = (balance_balanced / balance_current - 1) * 100
        print(f"Improvement: {improvement:+.1f}%")
        
        if trades_balanced:
            trades_df = pd.DataFrame(trades_balanced)
            winning = trades_df[trades_df['pnl'] > 0]
            losing = trades_df[trades_df['pnl'] < 0]
            
            print(f"\n  Win rate: {len(winning)/len(trades_df)*100:.1f}%")
            print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "")
            print(f"  Avg loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "")
            
            # Count trailing exits
            trail_exits = len(trades_df[trades_df['reason'] == 'Trail'])
            if trail_exits > 0:
                print(f"  Trailing exits: {trail_exits} ({trail_exits/len(trades_df)*100:.1f}%)")
        
        print()
    
    print("="*100)
    print("SUMMARY")
    print("="*100)
    print()
    print("Key insight: Simpler is often better!")
    print("  - No cooldown after wins = More opportunities")
    print("  - Wide trailing stops = Protect big winners only")
    print("  - Keep standard exits = They're already optimized")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
