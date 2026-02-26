"""
Test M1 strategy with EMA trend filter
Compare: Pure RSI vs RSI + Trend Filter
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
    
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def backtest_pure_rsi(df, config):
    """Original: Pure RSI strategy"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            # LONG: RSI oversold
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
            
            # SHORT: RSI overbought + downtrend
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
                trades.append({'pnl': pnl, 'type': position['type']})
                position = None
    
    return balance, trades

def backtest_with_trend_filter(df, config):
    """New: RSI + EMA Trend Filter"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            # LONG: RSI oversold AND uptrend
            if row['RSI'] < config['rsi_buy'] and row['uptrend']:
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
            
            # SHORT: RSI overbought AND downtrend
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
                trades.append({'pnl': pnl, 'type': position['type']})
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
    
    print("="*80)
    print("TESTING: PURE RSI vs RSI + TREND FILTER")
    print("="*80)
    print()
    
    # Test pure RSI
    print("Testing Pure RSI strategy...")
    balance1, trades1 = backtest_pure_rsi(df, config)
    
    if trades1:
        trades_df1 = pd.DataFrame(trades1)
        winning1 = trades_df1[trades_df1['pnl'] > 0]
        return1 = (balance1 / 1000 - 1) * 100
        
        print(f"  Return: {return1:.2f}%")
        print(f"  Trades: {len(trades1)}")
        print(f"  Win Rate: {len(winning1)/len(trades1)*100:.1f}%")
        print(f"  Avg Win: ${winning1['pnl'].mean():.2f}")
        print(f"  Avg Loss: ${trades_df1[trades_df1['pnl'] < 0]['pnl'].mean():.2f}")
    
    print()
    
    # Test with trend filter
    print("Testing RSI + Trend Filter strategy...")
    balance2, trades2 = backtest_with_trend_filter(df, config)
    
    if trades2:
        trades_df2 = pd.DataFrame(trades2)
        winning2 = trades_df2[trades_df2['pnl'] > 0]
        return2 = (balance2 / 1000 - 1) * 100
        
        print(f"  Return: {return2:.2f}%")
        print(f"  Trades: {len(trades2)}")
        print(f"  Win Rate: {len(winning2)/len(trades2)*100:.1f}%")
        print(f"  Avg Win: ${winning2['pnl'].mean():.2f}")
        print(f"  Avg Loss: ${trades_df2[trades_df2['pnl'] < 0]['pnl'].mean():.2f}")
    
    print()
    print("="*80)
    print("COMPARISON")
    print("="*80)
    
    if trades1 and trades2:
        print(f"Return:    {return1:.2f}% → {return2:.2f}% ({return2-return1:+.2f}%)")
        print(f"Trades:    {len(trades1)} → {len(trades2)} ({len(trades2)-len(trades1):+d})")
        print(f"Win Rate:  {len(winning1)/len(trades1)*100:.1f}% → {len(winning2)/len(trades2)*100:.1f}% ({(len(winning2)/len(trades2) - len(winning1)/len(trades1))*100:+.1f}%)")
        
        print()
        if return2 > return1:
            print(f"✓ TREND FILTER IS BETTER by {return2-return1:.2f}%")
            print(f"  Recommendation: Add trend filter to M1 bot")
        else:
            print(f"✗ PURE RSI IS BETTER by {return1-return2:.2f}%")
            print(f"  Recommendation: Keep current strategy")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
