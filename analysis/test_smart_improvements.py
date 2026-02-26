"""
Test smart improvements:
1. Trend filter - Only trade with the trend
2. Dynamic position sizing - Bigger positions on stronger signals
3. Smart exits - Trail stops, cut losses early, let winners run

Focus: Better position management while holding
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
    df['ema_200'] = df['close'].ewm(span=200).mean()
    
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
    
    # Trend indicators
    df['uptrend'] = (df['ema_fast'] > df['ema_slow']) & (df['close'] > df['ema_200'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow']) & (df['close'] < df['ema_200'])
    df['ranging'] = ~df['uptrend'] & ~df['downtrend']
    
    # Momentum for early exit detection
    df['momentum'] = df['close'] - df['close'].shift(3)
    df['momentum_weakening'] = df['momentum'].diff() < 0
    
    return df

def strategy_current(df, config, timeframe='M5'):
    """Current strategy (baseline)"""
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

def strategy_smart(df, config, timeframe='M5'):
    """
    Smart improvements:
    1. Trend filter - Only trade with trend
    2. Dynamic sizing - Bigger on stronger signals
    3. Smart exits - Trail stops, cut losses early, let winners run
    """
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    trades = []
    
    base_position_size = config['position_size_pct']
    leverage = config['leverage']
    base_atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # IMPROVEMENT 1: TREND FILTER
            # Only take longs in uptrend, shorts in downtrend
            
            # IMPROVEMENT 2: DYNAMIC POSITION SIZING
            # Stronger signals = bigger positions
            
            # LONG ENTRY (only in uptrend or ranging)
            if row['RSI'] < config['rsi_buy'] and not row['downtrend']:
                entry = row['close']
                
                # Dynamic sizing based on signal strength
                if row['RSI'] < 25:  # Very oversold
                    position_size = base_position_size * 1.3  # 30% bigger
                elif row['RSI'] < 30:  # Oversold
                    position_size = base_position_size * 1.15  # 15% bigger
                else:  # Slightly oversold
                    position_size = base_position_size * 0.85  # 15% smaller
                
                # Bonus: In strong uptrend, add 10%
                if row['uptrend']:
                    position_size *= 1.1
                
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * base_atr_mult)
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'peak_price': entry,
                    'trailing_active': False,
                    'bars_held': 0
                }
            
            # SHORT ENTRY (only in downtrend or ranging)
            elif row['RSI'] > config['rsi_sell'] and not row['uptrend']:
                entry = row['close']
                
                # Dynamic sizing
                if row['RSI'] > 75:  # Very overbought
                    position_size = base_position_size * 1.3
                elif row['RSI'] > 70:  # Overbought
                    position_size = base_position_size * 1.15
                else:
                    position_size = base_position_size * 0.85
                
                # Bonus in strong downtrend
                if row['downtrend']:
                    position_size *= 1.1
                
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * base_atr_mult)
                tp = entry - (entry * config['profit_target_pct'])
                
                position = {
                    'type': 'short',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'peak_price': entry,
                    'trailing_active': False,
                    'bars_held': 0
                }
        
        elif position is not None:
            # IMPROVEMENT 3: SMART EXITS WHILE HOLDING
            
            position['bars_held'] += 1
            
            # Track peak/trough for trailing
            if position['type'] == 'long':
                if row['close'] > position['peak_price']:
                    position['peak_price'] = row['close']
            else:
                if row['close'] < position['peak_price']:
                    position['peak_price'] = row['close']
            
            # Calculate current profit
            if position['type'] == 'long':
                profit_pct = (row['close'] - position['entry']) / position['entry']
            else:
                profit_pct = (position['entry'] - row['close']) / position['entry']
            
            # SMART EXIT LOGIC
            exit_price = None
            exit_reason = None
            
            # 1. EARLY EXIT: Cut losses if momentum reverses against us
            if profit_pct < -0.002 and position['bars_held'] > 3:  # Down 0.2% after 3 bars
                if position['type'] == 'long' and row['momentum'] < 0 and row['momentum_weakening']:
                    exit_price = row['close']
                    exit_reason = "Early_Cut"
                elif position['type'] == 'short' and row['momentum'] > 0 and row['momentum_weakening']:
                    exit_price = row['close']
                    exit_reason = "Early_Cut"
            
            # 2. TRAILING STOP: Lock in profits after hitting threshold
            if profit_pct > 0.003:  # After 0.3% profit
                position['trailing_active'] = True
                
                if position['type'] == 'long':
                    # Trail stop 0.15% below peak
                    trailing_sl = position['peak_price'] * 0.9985
                    if trailing_sl > position['sl']:
                        position['sl'] = trailing_sl
                else:
                    # Trail stop 0.15% above trough
                    trailing_sl = position['peak_price'] * 1.0015
                    if trailing_sl < position['sl']:
                        position['sl'] = trailing_sl
            
            # 3. EXTEND WINNERS: If in profit and momentum strong, ignore RSI exit
            strong_momentum = abs(row['momentum']) > row['ATR'] * 0.5
            in_profit = profit_pct > 0.005  # 0.5% profit
            
            # Check standard exits
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "Trail" if position['trailing_active'] else "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > config.get('rsi_exit_long', 75):
                    # Skip RSI exit if momentum strong and profitable
                    if not (strong_momentum and in_profit):
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
                    if not (strong_momentum and in_profit):
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
    print("SMART IMPROVEMENTS TEST")
    print("="*100)
    print()
    
    # Load configs
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print()
    
    # Test M5
    print("="*100)
    print("M5 BOT COMPARISON")
    print("="*100)
    print()
    
    print("Testing current strategy...")
    balance_m5_current, trades_m5_current = strategy_current(df_m5, m5_config, 'M5')
    
    print("Testing smart strategy...")
    balance_m5_smart, trades_m5_smart = strategy_smart(df_m5, m5_config, 'M5')
    
    # Analyze M5
    print(f"\nCurrent Strategy:")
    print(f"  Final balance: ${balance_m5_current:.2f}")
    print(f"  Return: {(balance_m5_current/1000-1)*100:+.1f}%")
    print(f"  Trades: {len(trades_m5_current)}")
    
    if trades_m5_current:
        trades_df = pd.DataFrame(trades_m5_current)
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win rate: {len(winning)/len(trades_m5_current)*100:.1f}%")
        print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "  Avg win: $0.00")
        print(f"  Avg loss: ${trades_df[trades_df['pnl'] < 0]['pnl'].mean():.2f}" if len(trades_df[trades_df['pnl'] < 0]) > 0 else "  Avg loss: $0.00")
    
    print(f"\nSmart Strategy:")
    print(f"  Final balance: ${balance_m5_smart:.2f}")
    print(f"  Return: {(balance_m5_smart/1000-1)*100:+.1f}%")
    print(f"  Trades: {len(trades_m5_smart)}")
    
    if trades_m5_smart:
        trades_df = pd.DataFrame(trades_m5_smart)
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win rate: {len(winning)/len(trades_m5_smart)*100:.1f}%")
        print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "  Avg win: $0.00")
        print(f"  Avg loss: ${trades_df[trades_df['pnl'] < 0]['pnl'].mean():.2f}" if len(trades_df[trades_df['pnl'] < 0]) > 0 else "  Avg loss: $0.00")
        
        # Exit reason breakdown
        print(f"\n  Exit reasons:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"    {reason}: {count} ({count/len(trades_df)*100:.1f}%)")
    
    improvement_m5 = (balance_m5_smart / balance_m5_current - 1) * 100
    print(f"\n  Improvement: {improvement_m5:+.1f}%")
    
    # Test M1
    print()
    print("="*100)
    print("M1 BOT COMPARISON")
    print("="*100)
    print()
    
    print("Testing current strategy...")
    balance_m1_current, trades_m1_current = strategy_current(df_m1, m1_config, 'M1')
    
    print("Testing smart strategy...")
    balance_m1_smart, trades_m1_smart = strategy_smart(df_m1, m1_config, 'M1')
    
    # Analyze M1
    print(f"\nCurrent Strategy:")
    print(f"  Final balance: ${balance_m1_current:.2f}")
    print(f"  Return: {(balance_m1_current/1000-1)*100:+.1f}%")
    print(f"  Trades: {len(trades_m1_current)}")
    
    if trades_m1_current:
        trades_df = pd.DataFrame(trades_m1_current)
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win rate: {len(winning)/len(trades_m1_current)*100:.1f}%")
    
    print(f"\nSmart Strategy:")
    print(f"  Final balance: ${balance_m1_smart:.2f}")
    print(f"  Return: {(balance_m1_smart/1000-1)*100:+.1f}%")
    print(f"  Trades: {len(trades_m1_smart)}")
    
    if trades_m1_smart:
        trades_df = pd.DataFrame(trades_m1_smart)
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win rate: {len(winning)/len(trades_m1_smart)*100:.1f}%")
        print(f"  Avg win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "  Avg win: $0.00")
        print(f"  Avg loss: ${trades_df[trades_df['pnl'] < 0]['pnl'].mean():.2f}" if len(trades_df[trades_df['pnl'] < 0]) > 0 else "  Avg loss: $0.00")
        
        print(f"\n  Exit reasons:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"    {reason}: {count} ({count/len(trades_df)*100:.1f}%)")
    
    improvement_m1 = (balance_m1_smart / balance_m1_current - 1) * 100
    print(f"\n  Improvement: {improvement_m1:+.1f}%")
    
    # Summary
    print()
    print("="*100)
    print("SUMMARY")
    print("="*100)
    print()
    
    print("Smart Improvements:")
    print("  1. Trend Filter - Only trade with trend")
    print("  2. Dynamic Sizing - 30% bigger on strong signals")
    print("  3. Smart Exits:")
    print("     - Cut losses early if momentum reverses")
    print("     - Trail stops after 0.3% profit")
    print("     - Let winners run if momentum strong")
    print()
    
    print(f"M5 Bot: {improvement_m5:+.1f}% improvement")
    print(f"M1 Bot: {improvement_m1:+.1f}% improvement")
    print()
    
    if improvement_m5 > 10 or improvement_m1 > 10:
        print("RECOMMENDATION: Implement smart improvements!")
        print("  Significant performance boost detected")
    elif improvement_m5 > 0 and improvement_m1 > 0:
        print("RECOMMENDATION: Consider implementing")
        print("  Modest improvements, worth testing live")
    else:
        print("RECOMMENDATION: Keep current strategy")
        print("  Smart improvements didn't help significantly")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
