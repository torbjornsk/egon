"""
Test multi-timeframe strategy (M5 entries + M1 exits) vs M5-only
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, fast_ema=20, slow_ema=30, rsi_period=10):
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

def backtest_m5_only(df_m5, config):
    """Original M5-only strategy"""
    df_m5 = compute_indicators(df_m5, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    peak_balance = 1000
    trades = []
    equity_curve = [balance]
    
    for i in range(200, len(df_m5)):
        row = df_m5.iloc[i]
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
                    exit_reason = 'M5 RSI exit'
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Take profit'
                elif price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
            else:
                if row['RSI'] < config['rsi_buy']:
                    should_exit = True
                    exit_reason = 'M5 RSI exit'
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

def backtest_multi_timeframe(df_m5, df_m1, config):
    """M5 entries + M1 exits"""
    df_m5 = compute_indicators(df_m5, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    df_m1 = compute_indicators(df_m1, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    # Create time index for M1 data
    df_m1 = df_m1.set_index('time')
    
    position = None
    balance = 1000
    peak_balance = 1000
    trades = []
    equity_curve = [balance]
    
    for i in range(200, len(df_m5)):
        row_m5 = df_m5.iloc[i]
        price_m5 = row_m5['close']
        time_m5 = row_m5['time']
        
        if balance > peak_balance:
            peak_balance = balance
        
        # Check M1 exits if in position
        if position is not None:
            # Get M1 candles between last M5 and current M5
            if i > 0:
                prev_time_m5 = df_m5.iloc[i-1]['time']
                m1_candles = df_m1[(df_m1.index > prev_time_m5) & (df_m1.index <= time_m5)]
                
                for m1_time, row_m1 in m1_candles.iterrows():
                    price_m1 = row_m1['close']
                    
                    # Check M1 exit conditions
                    should_exit_m1 = False
                    exit_reason = ''
                    
                    if position['type'] == 'long':
                        if row_m1['RSI'] > 80:  # Extreme overbought on M1
                            should_exit_m1 = True
                            exit_reason = 'M1 RSI extreme'
                        elif price_m1 >= position['take_profit']:
                            should_exit_m1 = True
                            exit_reason = 'Take profit'
                        elif price_m1 <= position['stop_loss']:
                            should_exit_m1 = True
                            exit_reason = 'Stop loss'
                    else:
                        if row_m1['RSI'] < 20:  # Extreme oversold on M1
                            should_exit_m1 = True
                            exit_reason = 'M1 RSI extreme'
                        elif price_m1 <= position['take_profit']:
                            should_exit_m1 = True
                            exit_reason = 'Take profit'
                        elif price_m1 >= position['stop_loss']:
                            should_exit_m1 = True
                            exit_reason = 'Stop loss'
                    
                    if should_exit_m1:
                        entry = position['entry']
                        if position['type'] == 'long':
                            price_change_pct = (price_m1 - entry) / entry
                        else:
                            price_change_pct = (entry - price_m1) / entry
                        
                        pnl = price_change_pct * position['leveraged_position']
                        balance += pnl
                        
                        trades.append({
                            'type': position['type'],
                            'entry_time': position['time'],
                            'exit_time': m1_time,
                            'pnl': pnl,
                            'reason': exit_reason
                        })
                        position = None
                        break
        
        # M5 entry logic (only if no position)
        if position is None:
            # LONG ENTRY
            if row_m5['RSI'] < config['rsi_buy']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row_m5['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'long',
                    'entry': price_m5,
                    'time': time_m5,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price_m5 - stop_distance,
                    'take_profit': price_m5 + (price_m5 * config['profit_target_pct'])
                }
            
            # SHORT ENTRY
            elif config['enable_shorts'] and row_m5['RSI'] > config['rsi_sell'] and row_m5['downtrend']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row_m5['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'short',
                    'entry': price_m5,
                    'time': time_m5,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price_m5 + stop_distance,
                    'take_profit': price_m5 - (price_m5 * config['profit_target_pct'])
                }
        
        # M5 exit logic (if still in position after M1 checks)
        elif position is not None:
            entry = position['entry']
            
            if position['type'] == 'long':
                price_change_pct = (price_m5 - entry) / entry
            else:
                price_change_pct = (entry - price_m5) / entry
            
            pnl = price_change_pct * position['leveraged_position']
            
            should_exit = False
            exit_reason = ''
            
            if position['type'] == 'long':
                if row_m5['RSI'] > config['rsi_sell']:
                    should_exit = True
                    exit_reason = 'M5 RSI exit'
            else:
                if row_m5['RSI'] < config['rsi_buy']:
                    should_exit = True
                    exit_reason = 'M5 RSI exit'
            
            if should_exit:
                balance += pnl
                trades.append({
                    'type': position['type'],
                    'entry_time': position['time'],
                    'exit_time': time_m5,
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
    
    print("Fetching M5 data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    print("Fetching M1 data...")
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    if df_m5 is None or df_m1 is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"M5 data: {len(df_m5)} bars")
    print(f"M1 data: {len(df_m1)} bars")
    print()
    
    # Load configuration
    with open('config/safe_leveraged_params.json', 'r') as f:
        config = json.load(f)
    
    print("="*80)
    print("TESTING M5-ONLY STRATEGY")
    print("="*80)
    balance_m5, trades_m5, equity_m5 = backtest_m5_only(df_m5, config)
    
    if trades_m5:
        trades_df_m5 = pd.DataFrame(trades_m5)
        winning_m5 = trades_df_m5[trades_df_m5['pnl'] > 0]
        
        equity_series_m5 = pd.Series(equity_m5)
        running_max_m5 = equity_series_m5.expanding().max()
        drawdown_m5 = (equity_series_m5 - running_max_m5) / running_max_m5
        max_dd_m5 = drawdown_m5.min()
        
        return_m5 = (balance_m5 / 1000 - 1) * 100
        
        print(f"Final Balance: ${balance_m5:.2f}")
        print(f"Return: {return_m5:.2f}%")
        print(f"Total Trades: {len(trades_m5)}")
        print(f"Win Rate: {len(winning_m5)/len(trades_m5)*100:.1f}%")
        print(f"Max Drawdown: {abs(max_dd_m5)*100:.2f}%")
        print(f"Avg Win: ${winning_m5['pnl'].mean():.2f}")
        print(f"Avg Loss: ${trades_df_m5[trades_df_m5['pnl'] < 0]['pnl'].mean():.2f}")
    
    print()
    print("="*80)
    print("TESTING MULTI-TIMEFRAME STRATEGY (M5 entries + M1 exits)")
    print("="*80)
    balance_mtf, trades_mtf, equity_mtf = backtest_multi_timeframe(df_m5, df_m1, config)
    
    if trades_mtf:
        trades_df_mtf = pd.DataFrame(trades_mtf)
        winning_mtf = trades_df_mtf[trades_df_mtf['pnl'] > 0]
        
        equity_series_mtf = pd.Series(equity_mtf)
        running_max_mtf = equity_series_mtf.expanding().max()
        drawdown_mtf = (equity_series_mtf - running_max_mtf) / running_max_mtf
        max_dd_mtf = drawdown_mtf.min()
        
        return_mtf = (balance_mtf / 1000 - 1) * 100
        
        print(f"Final Balance: ${balance_mtf:.2f}")
        print(f"Return: {return_mtf:.2f}%")
        print(f"Total Trades: {len(trades_mtf)}")
        print(f"Win Rate: {len(winning_mtf)/len(trades_mtf)*100:.1f}%")
        print(f"Max Drawdown: {abs(max_dd_mtf)*100:.2f}%")
        print(f"Avg Win: ${winning_mtf['pnl'].mean():.2f}")
        print(f"Avg Loss: ${trades_df_mtf[trades_df_mtf['pnl'] < 0]['pnl'].mean():.2f}")
        
        # Count M1 exits
        m1_exits = len(trades_df_mtf[trades_df_mtf['reason'] == 'M1 RSI extreme'])
        print(f"M1 Early Exits: {m1_exits} ({m1_exits/len(trades_mtf)*100:.1f}%)")
    
    print()
    print("="*80)
    print("COMPARISON")
    print("="*80)
    if trades_m5 and trades_mtf:
        print(f"Return Difference: {return_mtf - return_m5:+.2f}%")
        print(f"Drawdown Difference: {(abs(max_dd_mtf) - abs(max_dd_m5))*100:+.2f}%")
        print(f"Trade Count Difference: {len(trades_mtf) - len(trades_m5):+d}")
        
        if return_mtf > return_m5:
            print(f"\n✓ Multi-timeframe is BETTER by {return_mtf - return_m5:.2f}%")
        else:
            print(f"\n✗ M5-only is BETTER by {return_m5 - return_mtf:.2f}%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
