"""
Compare actual performance vs what would have happened with higher RSI exits
Test against the exact same 10-hour period the bots just traded
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

def backtest_with_exits(df, config, exit_long_rsi, exit_short_rsi):
    """Backtest with specific RSI exit thresholds"""
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
            
            elif config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
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
            exit_reason = ""
            
            if position['type'] == 'long':
                if price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = "SL"
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = "TP"
                elif row['RSI'] > exit_long_rsi:
                    should_exit = True
                    exit_reason = "RSI"
            else:
                if price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = "SL"
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = "TP"
                elif row['RSI'] < exit_short_rsi:
                    should_exit = True
                    exit_reason = "RSI"
            
            if should_exit:
                balance += pnl
                trades.append({
                    'pnl': pnl,
                    'exit_reason': exit_reason
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
    print(f"COMPARING ACTUAL VS OPTIMIZED PERFORMANCE - Last {hours} Hours")
    print("="*100)
    print()
    
    # Get data for the same period
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
    print("M5 BOT COMPARISON")
    print("="*100)
    
    # Current settings
    current_exit_long = m5_config.get('rsi_exit_long', m5_config['rsi_sell'])
    current_exit_short = m5_config.get('rsi_exit_short', m5_config['rsi_buy'])
    
    balance_current, trades_current = backtest_with_exits(m5_df, m5_config, current_exit_long, current_exit_short)
    
    # Optimized settings (85/15)
    balance_opt, trades_opt = backtest_with_exits(m5_df, m5_config, 85, 15)
    
    # Calculate stats
    def calc_stats(trades):
        if not trades:
            return None
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        sl_count = len(trades_df[trades_df['exit_reason'] == 'SL'])
        
        return {
            'total_pnl': trades_df['pnl'].sum(),
            'trades': len(trades),
            'win_rate': len(winning)/len(trades)*100,
            'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
            'avg_loss': losing['pnl'].mean() if len(losing) > 0 else 0,
            'sl_rate': sl_count/len(trades)*100
        }
    
    current_stats = calc_stats(trades_current)
    opt_stats = calc_stats(trades_opt)
    
    print(f"\nCurrent (RSI {current_exit_long}/{current_exit_short}):")
    if current_stats:
        print(f"  Trades: {current_stats['trades']}")
        print(f"  Total P/L: ${current_stats['total_pnl']:.2f}")
        print(f"  Win Rate: {current_stats['win_rate']:.1f}%")
        print(f"  Avg Win: ${current_stats['avg_win']:.2f}")
        print(f"  Avg Loss: ${current_stats['avg_loss']:.2f}")
        print(f"  SL Rate: {current_stats['sl_rate']:.1f}%")
    
    print(f"\nOptimized (RSI 85/15):")
    if opt_stats:
        print(f"  Trades: {opt_stats['trades']}")
        print(f"  Total P/L: ${opt_stats['total_pnl']:.2f}")
        print(f"  Win Rate: {opt_stats['win_rate']:.1f}%")
        print(f"  Avg Win: ${opt_stats['avg_win']:.2f}")
        print(f"  Avg Loss: ${opt_stats['avg_loss']:.2f}")
        print(f"  SL Rate: {opt_stats['sl_rate']:.1f}%")
    
    if current_stats and opt_stats:
        diff = opt_stats['total_pnl'] - current_stats['total_pnl']
        print(f"\nDifference: ${diff:+.2f} ({diff/current_stats['total_pnl']*100:+.1f}%)")
    
    # Test M1 Bot
    print()
    print("="*100)
    print("M1 BOT COMPARISON")
    print("="*100)
    
    # Current settings
    current_exit_long = m1_config.get('rsi_exit_long', m1_config['rsi_sell'])
    current_exit_short = m1_config.get('rsi_exit_short', m1_config['rsi_buy'])
    
    balance_current, trades_current = backtest_with_exits(m1_df, m1_config, current_exit_long, current_exit_short)
    
    # Test a few options
    balance_80, trades_80 = backtest_with_exits(m1_df, m1_config, 80, 20)
    balance_85, trades_85 = backtest_with_exits(m1_df, m1_config, 85, 15)
    
    current_stats = calc_stats(trades_current)
    stats_80 = calc_stats(trades_80)
    stats_85 = calc_stats(trades_85)
    
    print(f"\nCurrent (RSI {current_exit_long}/{current_exit_short}):")
    if current_stats:
        print(f"  Trades: {current_stats['trades']}")
        print(f"  Total P/L: ${current_stats['total_pnl']:.2f}")
        print(f"  Win Rate: {current_stats['win_rate']:.1f}%")
        print(f"  Avg Win: ${current_stats['avg_win']:.2f}")
        print(f"  Avg Loss: ${current_stats['avg_loss']:.2f}")
    
    print(f"\nRSI 80/20:")
    if stats_80:
        print(f"  Trades: {stats_80['trades']}")
        print(f"  Total P/L: ${stats_80['total_pnl']:.2f}")
        print(f"  Win Rate: {stats_80['win_rate']:.1f}%")
        print(f"  Avg Win: ${stats_80['avg_win']:.2f}")
        print(f"  Avg Loss: ${stats_80['avg_loss']:.2f}")
        if current_stats:
            diff = stats_80['total_pnl'] - current_stats['total_pnl']
            print(f"  Difference: ${diff:+.2f}")
    
    print(f"\nRSI 85/15:")
    if stats_85:
        print(f"  Trades: {stats_85['trades']}")
        print(f"  Total P/L: ${stats_85['total_pnl']:.2f}")
        print(f"  Win Rate: {stats_85['win_rate']:.1f}%")
        print(f"  Avg Win: ${stats_85['avg_win']:.2f}")
        print(f"  Avg Loss: ${stats_85['avg_loss']:.2f}")
        if current_stats:
            diff = stats_85['total_pnl'] - current_stats['total_pnl']
            print(f"  Difference: ${diff:+.2f}")
    
    # Summary
    print()
    print("="*100)
    print("SUMMARY")
    print("="*100)
    print(f"Actual performance (last 10 hours): M5 $96.32, M1 $6.51, Total $102.83")
    
    if current_stats and opt_stats:
        m5_sim = current_stats['total_pnl']
        m5_opt = opt_stats['total_pnl']
        print(f"\nM5 Simulation: Current ${m5_sim:.2f} vs Optimized ${m5_opt:.2f}")
        print(f"  → Optimized would have made ${m5_opt - m5_sim:+.2f} more")
    
    if current_stats and stats_85:
        m1_sim = current_stats['total_pnl']
        m1_opt = stats_85['total_pnl']
        print(f"\nM1 Simulation: Current ${m1_sim:.2f} vs RSI 85/15 ${m1_opt:.2f}")
        print(f"  → RSI 85/15 would have made ${m1_opt - m1_sim:+.2f} difference")
    
    print("="*100)
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
