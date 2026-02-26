"""
Analyze recent M1 performance to understand why stops are being hit
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
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def backtest_recent(df, config):
    """Backtest recent period with detailed trade info"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    equity_curve = []
    peak = 1000
    max_dd = 0
    
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
                    'entry_time': row['time'],
                    'entry_rsi': row['RSI'],
                    'leveraged_position': leveraged_position,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * config['profit_target_pct']),
                    'atr': row['ATR']
                }
            
            elif config['enable_shorts'] and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * config['atr_multiplier']
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'entry_time': row['time'],
                    'entry_rsi': row['RSI'],
                    'leveraged_position': leveraged_position,
                    'stop_loss': price + stop_distance,
                    'take_profit': price - (price * config['profit_target_pct']),
                    'atr': row['ATR']
                }
        
        elif position is not None:
            entry = position['entry']
            
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            
            pnl = price_change_pct * position['leveraged_position']
            
            should_exit = False
            exit_reason = ""
            
            # Use new exit thresholds
            exit_long_rsi = config.get('rsi_exit_long', config['rsi_sell'])
            exit_short_rsi = config.get('rsi_exit_short', config['rsi_buy'])
            
            if position['type'] == 'long':
                if price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = "Stop Loss"
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = "Take Profit"
                elif row['RSI'] > exit_long_rsi:
                    should_exit = True
                    exit_reason = f"RSI Exit ({row['RSI']:.1f})"
            else:
                if price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = "Stop Loss"
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = "Take Profit"
                elif row['RSI'] < exit_short_rsi:
                    should_exit = True
                    exit_reason = f"RSI Exit ({row['RSI']:.1f})"
            
            if should_exit:
                balance += pnl
                duration_minutes = (row['time'] - position['entry_time']).total_seconds() / 60
                
                trades.append({
                    'type': position['type'],
                    'entry': entry,
                    'exit': price,
                    'entry_time': position['entry_time'],
                    'exit_time': row['time'],
                    'duration_min': duration_minutes,
                    'entry_rsi': position['entry_rsi'],
                    'exit_rsi': row['RSI'],
                    'pnl': pnl,
                    'exit_reason': exit_reason,
                    'atr': position['atr']
                })
                position = None
        
        # Track equity
        current_equity = balance
        if position is not None:
            entry = position['entry']
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            unrealized_pnl = price_change_pct * position['leveraged_position']
            current_equity = balance + unrealized_pnl
        
        equity_curve.append(current_equity)
        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return balance, trades, max_dd

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    # Get last 6 hours of M1 data
    print("Fetching recent M1 data (last 6 hours)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=6)
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    if df is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"M1 data: {len(df)} bars\n")
    
    # Load M1 config
    with open('config/m1_scalping_params.json', 'r') as f:
        config = json.load(f)
    
    print("="*100)
    print("RECENT M1 PERFORMANCE ANALYSIS (Last 6 Hours)")
    print("="*100)
    print(f"Configuration:")
    print(f"  Entry: RSI < {config['rsi_buy']} (long), RSI > {config['rsi_sell']} (short)")
    print(f"  Exit: RSI > {config.get('rsi_exit_long', config['rsi_sell'])} (long), RSI < {config.get('rsi_exit_short', config['rsi_buy'])} (short)")
    print(f"  Stop Loss: {config['atr_multiplier']}x ATR")
    print(f"  Take Profit: {config['profit_target_pct']*100}%")
    print()
    
    balance, trades, max_dd = backtest_recent(df, config)
    
    if not trades:
        print("No trades in this period")
        mt5.disconnect()
        return
    
    trades_df = pd.DataFrame(trades)
    
    # Overall stats
    return_pct = (balance / 1000 - 1) * 100
    winning = trades_df[trades_df['pnl'] > 0]
    losing = trades_df[trades_df['pnl'] < 0]
    
    print(f"OVERALL PERFORMANCE:")
    print(f"  Return: {return_pct:.2f}%")
    print(f"  Max Drawdown: {max_dd:.2f}%")
    print(f"  Total Trades: {len(trades)}")
    print(f"  Win Rate: {len(winning)/len(trades)*100:.1f}%")
    print(f"  Avg Win: ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "  Avg Win: N/A")
    print(f"  Avg Loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "  Avg Loss: N/A")
    print()
    
    # Exit reason breakdown
    print("EXIT REASONS:")
    exit_counts = trades_df['exit_reason'].value_counts()
    for reason, count in exit_counts.items():
        pct = count / len(trades) * 100
        reason_trades = trades_df[trades_df['exit_reason'] == reason]
        avg_pnl = reason_trades['pnl'].mean()
        print(f"  {reason}: {count} ({pct:.1f}%) - Avg P/L: ${avg_pnl:.2f}")
    print()
    
    # Stop loss analysis
    sl_trades = trades_df[trades_df['exit_reason'] == 'Stop Loss']
    if len(sl_trades) > 0:
        print(f"STOP LOSS ANALYSIS ({len(sl_trades)} trades):")
        print(f"  Avg Duration: {sl_trades['duration_min'].mean():.1f} minutes")
        print(f"  Avg Entry RSI: {sl_trades['entry_rsi'].mean():.1f}")
        print(f"  Avg ATR at entry: ${sl_trades['atr'].mean():.2f}")
        print(f"  Avg Loss: ${sl_trades['pnl'].mean():.2f}")
        
        # Show last 5 stop losses
        print(f"\n  Last {min(5, len(sl_trades))} Stop Losses:")
        for _, trade in sl_trades.tail(5).iterrows():
            print(f"    {trade['entry_time'].strftime('%H:%M')} - {trade['type'].upper()}: Entry ${trade['entry']:.2f} @ RSI {trade['entry_rsi']:.1f}, Exit ${trade['exit']:.2f}, Loss ${trade['pnl']:.2f}")
        print()
    
    # Recent trades (last 10)
    print("LAST 10 TRADES:")
    print(f"{'Time':<12} | {'Type':<5} | {'Entry':>8} | {'Exit':>8} | {'Duration':>8} | {'Exit Reason':<15} | {'P/L':>8}")
    print("="*100)
    
    for _, trade in trades_df.tail(10).iterrows():
        time_str = trade['entry_time'].strftime('%H:%M')
        type_str = trade['type'].upper()
        duration_str = f"{trade['duration_min']:.0f}m"
        pnl_str = f"${trade['pnl']:+.2f}"
        
        print(f"{time_str:<12} | {type_str:<5} | ${trade['entry']:>7.2f} | ${trade['exit']:>7.2f} | {duration_str:>8} | {trade['exit_reason']:<15} | {pnl_str:>8}")
    
    print("="*100)
    
    # Recommendations
    print("\nRECOMMENDATIONS:")
    
    sl_rate = len(sl_trades) / len(trades) * 100 if len(trades) > 0 else 0
    
    if sl_rate > 40:
        print(f"⚠ High stop loss rate ({sl_rate:.1f}%)")
        print(f"  Current: {config['atr_multiplier']}x ATR")
        print(f"  Consider: Widening stop to 2.0x or 2.5x ATR")
        print(f"  Or: Tightening entry conditions (RSI < 30 instead of < 35)")
    elif sl_rate > 25:
        print(f"⚠ Moderate stop loss rate ({sl_rate:.1f}%)")
        print(f"  Monitor closely - may need adjustment if continues")
    else:
        print(f"✓ Stop loss rate is acceptable ({sl_rate:.1f}%)")
    
    if return_pct < 0:
        print(f"⚠ Negative returns in recent period ({return_pct:.2f}%)")
        print(f"  This could be temporary market conditions")
        print(f"  Consider pausing M1 bot if losses continue")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
