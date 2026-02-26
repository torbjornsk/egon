"""
Test profit maximization strategies:
1. Trailing stops - Lock in profits as price moves
2. Momentum exits - Exit when momentum weakens
3. Dynamic profit targets - Adjust based on volatility
4. No cooldown after wins - Re-enter faster
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
    
    # Momentum indicators
    df['momentum'] = df['close'] - df['close'].shift(3)
    df['momentum_strength'] = df['momentum'].rolling(5).mean()
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def strategy_current(df, config, timeframe='M5'):
    """Current strategy with cooldown"""
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
            # Cooldown check
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

def strategy_profit_max(df, config, timeframe='M5'):
    """
    Profit maximization:
    1. Trailing stops after hitting profit threshold
    2. Momentum-based exits (exit when momentum weakens)
    3. Dynamic profit targets based on volatility
    4. No cooldown after winning trades
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
    base_atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        bars_since_close += 1
        
        if position is None:
            # IMPROVEMENT 4: No cooldown after wins
            if not last_trade_profitable and bars_since_close < cooldown_bars:
                continue
            
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * base_atr_mult)
                
                # IMPROVEMENT 3: Dynamic profit target based on volatility
                # Higher volatility = bigger target
                avg_atr = df['ATR'].iloc[i-20:i].mean()
                volatility_ratio = row['ATR'] / avg_atr if avg_atr > 0 else 1.0
                dynamic_tp_pct = config['profit_target_pct'] * volatility_ratio
                tp = entry + (entry * dynamic_tp_pct)
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'peak_price': entry,
                    'trailing_active': False,
                    'entry_momentum': row['momentum']
                }
            
            elif row['RSI'] > config['rsi_sell'] and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * base_atr_mult)
                
                # Dynamic TP
                avg_atr = df['ATR'].iloc[i-20:i].mean()
                volatility_ratio = row['ATR'] / avg_atr if avg_atr > 0 else 1.0
                dynamic_tp_pct = config['profit_target_pct'] * volatility_ratio
                tp = entry - (entry * dynamic_tp_pct)
                
                position = {
                    'type': 'short',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'peak_price': entry,
                    'trailing_active': False,
                    'entry_momentum': row['momentum']
                }
        
        elif position is not None:
            # Track peak/trough for trailing
            if position['type'] == 'long' and row['close'] > position['peak_price']:
                position['peak_price'] = row['close']
            elif position['type'] == 'short' and row['close'] < position['peak_price']:
                position['peak_price'] = row['close']
            
            # Calculate profit
            if position['type'] == 'long':
                profit_pct = (row['close'] - position['entry']) / position['entry']
            else:
                profit_pct = (position['entry'] - row['close']) / position['entry']
            
            exit_price = None
            exit_reason = None
            
            # IMPROVEMENT 1: Trailing stops
            if profit_pct > 0.003:  # After 0.3% profit
                position['trailing_active'] = True
                
                if position['type'] == 'long':
                    # Trail at 0.25% below peak (tighter than before)
                    trail_sl = position['peak_price'] * 0.9975
                    if trail_sl > position['sl']:
                        position['sl'] = trail_sl
                else:
                    trail_sl = position['peak_price'] * 1.0025
                    if trail_sl < position['sl']:
                        position['sl'] = trail_sl
            
            # Check standard exits
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
            
            # IMPROVEMENT 2: Momentum-based exits (only if not hit SL/TP)
            if not exit_price:
                if position['type'] == 'long':
                    # Exit if momentum weakens significantly
                    if profit_pct > 0.002:  # Only for profitable trades
                        if row['momentum'] < 0 and row['momentum_strength'] < 0:
                            # Momentum turned negative
                            exit_price = row['close']
                            exit_reason = "Momentum_Weak"
                    
                    # Standard RSI exit
                    if not exit_price and row['RSI'] > config.get('rsi_exit_long', 75):
                        exit_price = row['close']
                        exit_reason = "RSI"
                
                else:  # SHORT
                    if profit_pct > 0.002:
                        if row['momentum'] > 0 and row['momentum_strength'] > 0:
                            exit_price = row['close']
                            exit_reason = "Momentum_Weak"
                    
                    if not exit_price and row['RSI'] < config.get('rsi_exit_short', 25):
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
    print("PROFIT MAXIMIZATION TEST")
    print("="*100)
    print()
    print("Focus: Maximize gains, not just avoid losses")
    print("  1. Trailing stops - Lock in profits")
    print("  2. Momentum exits - Exit when momentum weakens")
    print("  3. Dynamic profit targets - Adjust for volatility")
    print("  4. No cooldown after wins - Re-enter faster")
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
    balance_m5_profit, trades_m5_profit = strategy_profit_max(df_m5, m5_config, 'M5')
    
    print(f"\nCurrent: ${balance_m5_current:.2f} ({(balance_m5_current/1000-1)*100:+.1f}%), {len(trades_m5_current)} trades")
    
    if trades_m5_current:
        trades_df = pd.DataFrame(trades_m5_current)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        print(f"  Win rate: {len(winning)/len(trades_df)*100:.1f}%")
        print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "")
        print(f"  Avg loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "")
    
    print(f"\nProfit Max: ${balance_m5_profit:.2f} ({(balance_m5_profit/1000-1)*100:+.1f}%), {len(trades_m5_profit)} trades")
    
    if trades_m5_profit:
        trades_df = pd.DataFrame(trades_m5_profit)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        print(f"  Win rate: {len(winning)/len(trades_df)*100:.1f}%")
        print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "")
        print(f"  Avg loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "")
        
        print(f"\n  Exit breakdown:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"    {reason}: {count} ({count/len(trades_df)*100:.1f}%)")
    
    print(f"\nImprovement: {(balance_m5_profit/balance_m5_current-1)*100:+.1f}%")
    
    # Test M1
    print()
    print("="*100)
    print("M1 BOT")
    print("="*100)
    
    balance_m1_current, trades_m1_current = strategy_current(df_m1, m1_config, 'M1')
    balance_m1_profit, trades_m1_profit = strategy_profit_max(df_m1, m1_config, 'M1')
    
    print(f"\nCurrent: ${balance_m1_current:.2f} ({(balance_m1_current/1000-1)*100:+.1f}%), {len(trades_m1_current)} trades")
    
    if trades_m1_current:
        trades_df = pd.DataFrame(trades_m1_current)
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win rate: {len(winning)/len(trades_df)*100:.1f}%")
    
    print(f"\nProfit Max: ${balance_m1_profit:.2f} ({(balance_m1_profit/1000-1)*100:+.1f}%), {len(trades_m1_profit)} trades")
    
    if trades_m1_profit:
        trades_df = pd.DataFrame(trades_m1_profit)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        print(f"  Win rate: {len(winning)/len(trades_df)*100:.1f}%")
        print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "")
        print(f"  Avg loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "")
        
        print(f"\n  Exit breakdown:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"    {reason}: {count} ({count/len(trades_df)*100:.1f}%)")
    
    print(f"\nImprovement: {(balance_m1_profit/balance_m1_current-1)*100:+.1f}%")
    
    # Summary
    print()
    print("="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    m5_improvement = (balance_m5_profit / balance_m5_current - 1) * 100
    m1_improvement = (balance_m1_profit / balance_m1_current - 1) * 100
    
    print(f"\nM5: {m5_improvement:+.1f}% improvement")
    print(f"M1: {m1_improvement:+.1f}% improvement")
    print()
    
    if m5_improvement > 10 or m1_improvement > 10:
        print("✓ Implement profit maximization!")
        print("  Significant gains from:")
        if m5_improvement > 10:
            print(f"    - M5: {m5_improvement:+.1f}%")
        if m1_improvement > 10:
            print(f"    - M1: {m1_improvement:+.1f}%")
    elif m5_improvement > 5 or m1_improvement > 5:
        print("~ Consider profit maximization")
        print(f"  M5: {m5_improvement:+.1f}%")
        print(f"  M1: {m1_improvement:+.1f}%")
    else:
        print("✗ Current strategy better")
        print(f"  M5: {m5_improvement:+.1f}%")
        print(f"  M1: {m1_improvement:+.1f}%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
