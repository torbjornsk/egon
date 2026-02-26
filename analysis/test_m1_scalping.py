"""
Test M1 (1-minute) scalping strategy
More action-packed with faster trades
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, fast_ema=10, slow_ema=20, rsi_period=7):
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

def backtest_m1(df, config):
    """M1 scalping backtest"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    peak_balance = 1000
    trades = []
    equity_curve = [balance]
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if balance > peak_balance:
            peak_balance = balance
        
        if position is None:
            # LONG ENTRY
            if row['RSI'] < config['rsi_buy']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'time': row['time'],
                    'leveraged_position': leveraged_position,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * config['profit_target_pct'])
                }
            
            # SHORT ENTRY
            elif config['enable_shorts'] and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'time': row['time'],
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
            exit_reason = ''
            
            if position['type'] == 'long':
                if row['RSI'] > config['rsi_sell']:
                    should_exit = True
                    exit_reason = 'RSI exit'
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Take profit'
                elif price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
            else:
                if row['RSI'] < config['rsi_buy']:
                    should_exit = True
                    exit_reason = 'RSI exit'
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Take profit'
                elif price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
            
            if should_exit:
                balance += pnl
                trades.append({
                    'type': position['type'],
                    'entry_time': position['time'],
                    'exit_time': row['time'],
                    'pnl': pnl,
                    'reason': exit_reason
                })
                position = None
        
        equity_curve.append(balance)
    
    return balance, trades, equity_curve

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching M1 data (this may take a moment)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)  # Test on 3 months for speed
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    if df is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"M1 data: {len(df)} bars from {df['time'].min()} to {df['time'].max()}")
    print()
    
    # Test different M1 configurations
    configs = [
        {
            'name': 'Conservative M1',
            'fast_ema': 10,
            'slow_ema': 20,
            'rsi_period': 7,
            'rsi_buy': 25,
            'rsi_sell': 75,
            'atr_multiplier': 2.5,
            'profit_target_pct': 0.015,  # 1.5%
            'position_size_pct': 0.10,
            'leverage': 25,
            'enable_shorts': True
        },
        {
            'name': 'Moderate M1',
            'fast_ema': 8,
            'slow_ema': 16,
            'rsi_period': 7,
            'rsi_buy': 30,
            'rsi_sell': 70,
            'atr_multiplier': 2.0,
            'profit_target_pct': 0.01,  # 1%
            'position_size_pct': 0.12,
            'leverage': 25,
            'enable_shorts': True
        },
        {
            'name': 'Aggressive M1',
            'fast_ema': 5,
            'slow_ema': 12,
            'rsi_period': 5,
            'rsi_buy': 35,
            'rsi_sell': 65,
            'atr_multiplier': 1.5,
            'profit_target_pct': 0.008,  # 0.8%
            'position_size_pct': 0.15,
            'leverage': 25,
            'enable_shorts': True
        }
    ]
    
    print("="*100)
    print(f"{'Strategy':<20} | {'Return':>8} | {'Trades':>6} | {'Win%':>5} | {'MaxDD':>6} | {'Avg Win':>8} | {'Avg Loss':>9} | {'Trades/Day':>10}")
    print("="*100)
    
    results = []
    for config in configs:
        balance, trades, equity = backtest_m1(df, config)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            
            equity_series = pd.Series(equity)
            running_max = equity_series.expanding().max()
            drawdown = (equity_series - running_max) / running_max
            max_dd = drawdown.min()
            
            return_pct = (balance / 1000 - 1) * 100
            
            # Calculate trades per day
            days = (df['time'].max() - df['time'].min()).days
            trades_per_day = len(trades) / days if days > 0 else 0
            
            result = {
                'name': config['name'],
                'balance': balance,
                'return': return_pct,
                'trades': len(trades),
                'win_rate': len(winning) / len(trades) * 100,
                'max_dd': abs(max_dd) * 100,
                'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
                'avg_loss': trades_df[trades_df['pnl'] < 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0,
                'trades_per_day': trades_per_day,
                'config': config
            }
            
            results.append(result)
            
            print(f"{result['name']:<20} | {result['return']:>7.2f}% | {result['trades']:>6} | "
                  f"{result['win_rate']:>5.1f} | {result['max_dd']:>5.1f}% | "
                  f"${result['avg_win']:>7.2f} | ${result['avg_loss']:>8.2f} | "
                  f"{result['trades_per_day']:>10.1f}")
    
    print("="*100)
    
    if results:
        # Find best by return
        best = max(results, key=lambda x: x['return'])
        print(f"\nBest Return: {best['name']} → {best['return']:.2f}%")
        print(f"  Trades: {best['trades']} ({best['trades_per_day']:.1f}/day)")
        print(f"  Win Rate: {best['win_rate']:.1f}%")
        print(f"  Max DD: {best['max_dd']:.2f}%")
        
        print(f"\nRecommended M1 Configuration:")
        print(f"  Fast EMA: {best['config']['fast_ema']}")
        print(f"  Slow EMA: {best['config']['slow_ema']}")
        print(f"  RSI Period: {best['config']['rsi_period']}")
        print(f"  RSI Buy: {best['config']['rsi_buy']}")
        print(f"  RSI Sell: {best['config']['rsi_sell']}")
        print(f"  ATR Multiplier: {best['config']['atr_multiplier']}")
        print(f"  Profit Target: {best['config']['profit_target_pct']*100}%")
        print(f"  Position Size: {best['config']['position_size_pct']*100}%")
        print(f"  Leverage: {best['config']['leverage']}x")
        
        # Save best config
        m1_config = {
            "strategy": "m1_scalping",
            "position_size_pct": best['config']['position_size_pct'],
            "leverage": best['config']['leverage'],
            "max_drawdown_limit": 0.35,
            "fast_ema": best['config']['fast_ema'],
            "slow_ema": best['config']['slow_ema'],
            "rsi_period": best['config']['rsi_period'],
            "rsi_buy": best['config']['rsi_buy'],
            "rsi_sell": best['config']['rsi_sell'],
            "atr_multiplier": best['config']['atr_multiplier'],
            "profit_target_pct": best['config']['profit_target_pct'],
            "enable_shorts": best['config']['enable_shorts']
        }
        
        with open('config/m1_scalping_params.json', 'w') as f:
            json.dump(m1_config, f, indent=2)
        
        print(f"\nConfiguration saved to: config/m1_scalping_params.json")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
