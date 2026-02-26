"""
Test alternative M1 signals:
1. Pure RSI (current)
2. RSI + Bollinger Bands (more signals)
3. MACD (trend following)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, fast_ema=5, slow_ema=12, rsi_period=5):
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
    
    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(20).mean()
    df['bb_std'] = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * 2)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * 2)
    
    # MACD
    df['macd'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def backtest_pure_rsi(df, config):
    """Strategy 1: Pure RSI (current)"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * config['profit_target_pct'])
                }
            
            elif config['enable_shorts'] and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price + stop_distance,
                    'take_profit': price - (price * config['profit_target_pct'])
                }
        
        elif position is not None:
            entry = position['entry']
            
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            
            pnl = price_change_pct * position['leveraged_position']
            
            should_exit = False
            
            if position['type'] == 'long':
                if row['RSI'] > config['rsi_sell'] or price >= position['take_profit'] or price <= position['stop_loss']:
                    should_exit = True
            else:
                if row['RSI'] < config['rsi_buy'] or price <= position['take_profit'] or price >= position['stop_loss']:
                    should_exit = True
            
            if should_exit:
                balance += pnl
                trades.append({'pnl': pnl})
                position = None
    
    return balance, trades

def backtest_rsi_plus_bb(df, config):
    """Strategy 2: RSI OR Bollinger Bands (more signals)"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            # LONG: RSI oversold OR price below lower BB
            if row['RSI'] < config['rsi_buy'] or price < row['bb_lower']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * config['profit_target_pct'])
                }
            
            # SHORT: RSI overbought OR price above upper BB (with downtrend)
            elif config['enable_shorts'] and row['downtrend'] and (row['RSI'] > config['rsi_sell'] or price > row['bb_upper']):
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price + stop_distance,
                    'take_profit': price - (price * config['profit_target_pct'])
                }
        
        elif position is not None:
            entry = position['entry']
            
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            
            pnl = price_change_pct * position['leveraged_position']
            
            should_exit = False
            
            if position['type'] == 'long':
                # Exit if RSI overbought OR price above upper BB
                if row['RSI'] > config['rsi_sell'] or price > row['bb_upper'] or price >= position['take_profit'] or price <= position['stop_loss']:
                    should_exit = True
            else:
                # Exit if RSI oversold OR price below lower BB
                if row['RSI'] < config['rsi_buy'] or price < row['bb_lower'] or price <= position['take_profit'] or price >= position['stop_loss']:
                    should_exit = True
            
            if should_exit:
                balance += pnl
                trades.append({'pnl': pnl})
                position = None
    
    return balance, trades

def backtest_macd(df, config):
    """Strategy 3: MACD crossovers (trend following)"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        price = row['close']
        
        if position is None:
            # LONG: MACD crosses above signal
            if row['macd'] > row['macd_signal'] and prev_row['macd'] <= prev_row['macd_signal']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * config['profit_target_pct'])
                }
            
            # SHORT: MACD crosses below signal
            elif config['enable_shorts'] and row['macd'] < row['macd_signal'] and prev_row['macd'] >= prev_row['macd_signal']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price + stop_distance,
                    'take_profit': price - (price * config['profit_target_pct'])
                }
        
        elif position is not None:
            entry = position['entry']
            
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            
            pnl = price_change_pct * position['leveraged_position']
            
            should_exit = False
            
            if position['type'] == 'long':
                # Exit on opposite MACD cross or stops
                if (row['macd'] < row['macd_signal'] and prev_row['macd'] >= prev_row['macd_signal']) or price >= position['take_profit'] or price <= position['stop_loss']:
                    should_exit = True
            else:
                if (row['macd'] > row['macd_signal'] and prev_row['macd'] <= prev_row['macd_signal']) or price <= position['take_profit'] or price >= position['stop_loss']:
                    should_exit = True
            
            if should_exit:
                balance += pnl
                trades.append({'pnl': pnl})
                position = None
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching M1 data (50 days)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=50)
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    if df is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"M1 data: {len(df)} bars\n")
    
    # Load current M1 config
    with open('config/m1_scalping_params.json', 'r') as f:
        config = json.load(f)
    
    print("="*90)
    print("TESTING ALTERNATIVE SIGNAL STRATEGIES")
    print("="*90)
    print()
    
    results = []
    
    # Test 1: Pure RSI
    print("1. Pure RSI (current strategy)...")
    balance1, trades1 = backtest_pure_rsi(df, config)
    if trades1:
        trades_df1 = pd.DataFrame(trades1)
        winning1 = trades_df1[trades_df1['pnl'] > 0]
        return1 = (balance1 / 1000 - 1) * 100
        results.append({
            'name': 'Pure RSI',
            'return': return1,
            'trades': len(trades1),
            'win_rate': len(winning1)/len(trades1)*100,
            'avg_win': winning1['pnl'].mean(),
            'avg_loss': trades_df1[trades_df1['pnl'] < 0]['pnl'].mean()
        })
        print(f"   Return: {return1:.2f}%, Trades: {len(trades1)}, Win Rate: {len(winning1)/len(trades1)*100:.1f}%")
    
    # Test 2: RSI + Bollinger Bands
    print("2. RSI + Bollinger Bands (more signals)...")
    balance2, trades2 = backtest_rsi_plus_bb(df, config)
    if trades2:
        trades_df2 = pd.DataFrame(trades2)
        winning2 = trades_df2[trades_df2['pnl'] > 0]
        return2 = (balance2 / 1000 - 1) * 100
        results.append({
            'name': 'RSI + BB',
            'return': return2,
            'trades': len(trades2),
            'win_rate': len(winning2)/len(trades2)*100,
            'avg_win': winning2['pnl'].mean(),
            'avg_loss': trades_df2[trades_df2['pnl'] < 0]['pnl'].mean()
        })
        print(f"   Return: {return2:.2f}%, Trades: {len(trades2)}, Win Rate: {len(winning2)/len(trades2)*100:.1f}%")
    
    # Test 3: MACD
    print("3. MACD Crossovers (trend following)...")
    balance3, trades3 = backtest_macd(df, config)
    if trades3:
        trades_df3 = pd.DataFrame(trades3)
        winning3 = trades_df3[trades_df3['pnl'] > 0]
        return3 = (balance3 / 1000 - 1) * 100
        results.append({
            'name': 'MACD',
            'return': return3,
            'trades': len(trades3),
            'win_rate': len(winning3)/len(trades3)*100,
            'avg_win': winning3['pnl'].mean(),
            'avg_loss': trades_df3[trades_df3['pnl'] < 0]['pnl'].mean()
        })
        print(f"   Return: {return3:.2f}%, Trades: {len(trades3)}, Win Rate: {len(winning3)/len(trades3)*100:.1f}%")
    
    print()
    print("="*90)
    print("COMPARISON")
    print("="*90)
    print(f"{'Strategy':<20} | {'Return':>8} | {'Trades':>6} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9}")
    print("="*90)
    
    for r in results:
        print(f"{r['name']:<20} | {r['return']:>7.2f}% | {r['trades']:>6} | {r['win_rate']:>5.1f} | ${r['avg_win']:>7.2f} | ${r['avg_loss']:>8.2f}")
    
    print("="*90)
    
    # Find best
    best = max(results, key=lambda x: x['return'])
    print(f"\n✓ BEST STRATEGY: {best['name']}")
    print(f"  Return: {best['return']:.2f}%")
    print(f"  Trades: {best['trades']}")
    print(f"  Win Rate: {best['win_rate']:.1f}%")
    
    if best['name'] != 'Pure RSI':
        print(f"\n  Recommendation: Switch to {best['name']}")
    else:
        print(f"\n  Recommendation: Keep current Pure RSI strategy")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
