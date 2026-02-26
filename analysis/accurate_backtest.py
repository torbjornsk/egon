"""
Accurate backtesting that matches live trading behavior
- Uses high/low for SL/TP detection (not just close)
- Properly handles intra-candle price movements
- Should match actual MT5 execution closely
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

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

def accurate_backtest(df, config):
    """
    Accurate backtest that checks high/low for SL/TP hits
    This should match actual MT5 execution
    """
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    exit_long_rsi = config.get('rsi_exit_long', config['rsi_sell'])
    exit_short_rsi = config.get('rsi_exit_short', config['rsi_buy'])
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # Check for entry signals using close price
            if row['RSI'] < config['rsi_buy']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                entry_price = row['close']
                
                position = {
                    'type': 'long',
                    'entry': entry_price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': entry_price - stop_distance,
                    'take_profit': entry_price + (entry_price * config['profit_target_pct'])
                }
            
            elif config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                entry_price = row['close']
                
                position = {
                    'type': 'short',
                    'entry': entry_price,
                    'leveraged_position': leveraged_position,
                    'stop_loss': entry_price + stop_distance,
                    'take_profit': entry_price - (entry_price * config['profit_target_pct'])
                }
        
        elif position is not None:
            entry = position['entry']
            exit_price = None
            exit_reason = None
            
            if position['type'] == 'long':
                # Check if SL was hit (using low of candle)
                if row['low'] <= position['stop_loss']:
                    exit_price = position['stop_loss']
                    exit_reason = "Stop Loss"
                # Check if TP was hit (using high of candle)
                elif row['high'] >= position['take_profit']:
                    exit_price = position['take_profit']
                    exit_reason = "Take Profit"
                # Check RSI exit (using close)
                elif row['RSI'] > exit_long_rsi:
                    exit_price = row['close']
                    exit_reason = "RSI Exit"
            
            else:  # short
                # Check if SL was hit (using high of candle)
                if row['high'] >= position['stop_loss']:
                    exit_price = position['stop_loss']
                    exit_reason = "Stop Loss"
                # Check if TP was hit (using low of candle)
                elif row['low'] <= position['take_profit']:
                    exit_price = position['take_profit']
                    exit_reason = "Take Profit"
                # Check RSI exit (using close)
                elif row['RSI'] < exit_short_rsi:
                    exit_price = row['close']
                    exit_reason = "RSI Exit"
            
            if exit_price is not None:
                if position['type'] == 'long':
                    price_change_pct = (exit_price - entry) / entry
                else:
                    price_change_pct = (entry - exit_price) / entry
                
                pnl = price_change_pct * position['leveraged_position']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'exit_reason': exit_reason,
                    'entry': entry,
                    'exit': exit_price,
                    'type': position['type']
                })
                position = None
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    hours = 10
    print("="*100)
    print(f"ACCURATE BACKTEST vs ACTUAL PERFORMANCE - Last {hours} Hours")
    print("="*100)
    print()
    
    # Get data
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=hours)
    
    print("Fetching M5 data...")
    m5_df = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    print("Fetching M1 data...")
    m1_df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    print(f"M5 data: {len(m5_df)} bars")
    print(f"M1 data: {len(m1_df)} bars")
    print()
    
    # Load configs
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    # Test M5 Bot
    print("="*100)
    print("M5 BOT")
    print("="*100)
    
    balance, trades = accurate_backtest(m5_df, m5_config)
    
    if trades:
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        total_pnl = trades_df['pnl'].sum()
        
        sl_count = len(trades_df[trades_df['exit_reason'] == 'Stop Loss'])
        tp_count = len(trades_df[trades_df['exit_reason'] == 'Take Profit'])
        rsi_count = len(trades_df[trades_df['exit_reason'] == 'RSI Exit'])
        
        print(f"\nSimulated Performance:")
        print(f"  Trades: {len(trades)}")
        print(f"  Total P/L: ${total_pnl:.2f}")
        print(f"  Win Rate: {len(winning)/len(trades)*100:.1f}%")
        print(f"  Avg Win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "  Avg Win: N/A")
        print(f"  Avg Loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "  Avg Loss: N/A")
        print(f"  Exit Reasons: {sl_count} SL, {tp_count} TP, {rsi_count} RSI")
        
        print(f"\nTrade Details:")
        for t in trades:
            print(f"  {t['type'].upper()}: ${t['entry']:.2f} -> ${t['exit']:.2f} = ${t['pnl']:+.2f} ({t['exit_reason']})")
    else:
        print("\nNo trades in simulation")
    
    print(f"\nActual Performance (from MT5):")
    print(f"  Trades: 5")
    print(f"  Total P/L: $96.32")
    
    # Test M1 Bot
    print()
    print("="*100)
    print("M1 BOT")
    print("="*100)
    
    balance, trades = accurate_backtest(m1_df, m1_config)
    
    if trades:
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        total_pnl = trades_df['pnl'].sum()
        
        sl_count = len(trades_df[trades_df['exit_reason'] == 'Stop Loss'])
        tp_count = len(trades_df[trades_df['exit_reason'] == 'Take Profit'])
        rsi_count = len(trades_df[trades_df['exit_reason'] == 'RSI Exit'])
        
        print(f"\nSimulated Performance:")
        print(f"  Trades: {len(trades)}")
        print(f"  Total P/L: ${total_pnl:.2f}")
        print(f"  Win Rate: {len(winning)/len(trades)*100:.1f}%")
        print(f"  Avg Win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "  Avg Win: N/A")
        print(f"  Avg Loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "  Avg Loss: N/A")
        print(f"  Exit Reasons: {sl_count} SL, {tp_count} TP, {rsi_count} RSI")
    else:
        print("\nNo trades in simulation")
    
    print(f"\nActual Performance (from MT5):")
    print(f"  Trades: 28")
    print(f"  Total P/L: $6.51")
    
    # Summary
    print()
    print("="*100)
    print("COMPARISON")
    print("="*100)
    print(f"Actual Total: $102.83 (M5: $96.32, M1: $6.51)")
    
    if trades:
        m1_sim = trades_df['pnl'].sum()
        print(f"Simulated M1: ${m1_sim:.2f}")
        print(f"Difference: ${m1_sim - 6.51:+.2f}")
    
    print("="*100)
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
