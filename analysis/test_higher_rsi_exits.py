"""
Test higher RSI exit thresholds to improve risk/reward ratio
Current: M5 exits at 75/25, M1 exits at 75/25
Test: Higher thresholds to hold winners longer
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
                    'exit_reason': exit_reason,
                    'return_pct': price_change_pct * 100
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
    
    print("="*100)
    print("TESTING HIGHER RSI EXIT THRESHOLDS")
    print("="*100)
    print()
    
    # Test M5 Bot
    print("M5 BOT - Fetching 50 days of M5 data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=50)
    m5_df = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    print(f"M5 data: {len(m5_df)} bars")
    print(f"Current config: Entry RSI {m5_config['rsi_buy']}/{m5_config['rsi_sell']}, Exit RSI {m5_config.get('rsi_exit_long', m5_config['rsi_sell'])}/{m5_config.get('rsi_exit_short', m5_config['rsi_buy'])}")
    print()
    
    # Test different M5 exit thresholds
    m5_tests = [
        (75, 25, "Current"),
        (78, 22, "Slightly higher"),
        (80, 20, "Higher"),
        (82, 18, "Much higher"),
        (85, 15, "Very high"),
    ]
    
    m5_results = []
    
    for long_exit, short_exit, desc in m5_tests:
        balance, trades, max_dd = backtest_with_exits(m5_df, m5_config, long_exit, short_exit)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            losing = trades_df[trades_df['pnl'] < 0]
            return_pct = (balance / 1000 - 1) * 100
            
            sl_count = len(trades_df[trades_df['exit_reason'] == 'SL'])
            tp_count = len(trades_df[trades_df['exit_reason'] == 'TP'])
            rsi_count = len(trades_df[trades_df['exit_reason'] == 'RSI'])
            
            avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
            avg_loss = losing['pnl'].mean() if len(losing) > 0 else 0
            risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            
            m5_results.append({
                'desc': desc,
                'long_exit': long_exit,
                'short_exit': short_exit,
                'return': return_pct,
                'max_dd': max_dd,
                'trades': len(trades),
                'win_rate': len(winning)/len(trades)*100,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'risk_reward': risk_reward,
                'sl_rate': sl_count/len(trades)*100,
                'exits': f"{sl_count}/{tp_count}/{rsi_count}"
            })
    
    print("M5 BOT RESULTS:")
    print(f"{'Exit RSI':<18} | {'Return':>8} | {'Max DD':>7} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9} | {'R:R':>6} | {'SL%':>5} | {'SL/TP/RSI':<12}")
    print("="*100)
    
    for r in m5_results:
        print(f"{r['desc']:<18} | {r['return']:>7.1f}% | {r['max_dd']:>6.1f}% | {r['win_rate']:>5.1f} | ${r['avg_win']:>7.2f} | ${r['avg_loss']:>8.2f} | 1:{r['risk_reward']:>4.2f} | {r['sl_rate']:>4.1f}% | {r['exits']:<12}")
    
    print("="*100)
    
    # Find best risk/reward
    best_rr = max(m5_results, key=lambda x: x['risk_reward'])
    print(f"\n✓ BEST RISK/REWARD (M5): {best_rr['desc']} - Exit at RSI {best_rr['long_exit']}/{best_rr['short_exit']}")
    print(f"  Return: {best_rr['return']:.1f}%, R:R: 1:{best_rr['risk_reward']:.2f}, Win Rate: {best_rr['win_rate']:.1f}%")
    
    # Test M1 Bot
    print()
    print("="*100)
    print("M1 BOT - Fetching 50 days of M1 data...")
    m1_df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    print(f"M1 data: {len(m1_df)} bars")
    print(f"Current config: Entry RSI {m1_config['rsi_buy']}/{m1_config['rsi_sell']}, Exit RSI {m1_config.get('rsi_exit_long', m1_config['rsi_sell'])}/{m1_config.get('rsi_exit_short', m1_config['rsi_buy'])}")
    print()
    
    # Test different M1 exit thresholds
    m1_tests = [
        (75, 25, "Current"),
        (78, 22, "Slightly higher"),
        (80, 20, "Higher"),
        (82, 18, "Much higher"),
        (85, 15, "Very high"),
        (90, 10, "Extreme"),
    ]
    
    m1_results = []
    
    for long_exit, short_exit, desc in m1_tests:
        balance, trades, max_dd = backtest_with_exits(m1_df, m1_config, long_exit, short_exit)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            losing = trades_df[trades_df['pnl'] < 0]
            return_pct = (balance / 1000 - 1) * 100
            
            sl_count = len(trades_df[trades_df['exit_reason'] == 'SL'])
            tp_count = len(trades_df[trades_df['exit_reason'] == 'TP'])
            rsi_count = len(trades_df[trades_df['exit_reason'] == 'RSI'])
            
            avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
            avg_loss = losing['pnl'].mean() if len(losing) > 0 else 0
            risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            
            m1_results.append({
                'desc': desc,
                'long_exit': long_exit,
                'short_exit': short_exit,
                'return': return_pct,
                'max_dd': max_dd,
                'trades': len(trades),
                'win_rate': len(winning)/len(trades)*100,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'risk_reward': risk_reward,
                'sl_rate': sl_count/len(trades)*100,
                'exits': f"{sl_count}/{tp_count}/{rsi_count}"
            })
    
    print("M1 BOT RESULTS:")
    print(f"{'Exit RSI':<18} | {'Return':>8} | {'Max DD':>7} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9} | {'R:R':>6} | {'SL%':>5} | {'SL/TP/RSI':<12}")
    print("="*100)
    
    for r in m1_results:
        print(f"{r['desc']:<18} | {r['return']:>7.1f}% | {r['max_dd']:>6.1f}% | {r['win_rate']:>5.1f} | ${r['avg_win']:>7.2f} | ${r['avg_loss']:>8.2f} | 1:{r['risk_reward']:>4.2f} | {r['sl_rate']:>4.1f}% | {r['exits']:<12}")
    
    print("="*100)
    
    # Find best risk/reward
    best_rr = max(m1_results, key=lambda x: x['risk_reward'])
    print(f"\n✓ BEST RISK/REWARD (M1): {best_rr['desc']} - Exit at RSI {best_rr['long_exit']}/{best_rr['short_exit']}")
    print(f"  Return: {best_rr['return']:.1f}%, R:R: 1:{best_rr['risk_reward']:.2f}, Win Rate: {best_rr['win_rate']:.1f}%")
    
    # Overall recommendation
    print()
    print("="*100)
    print("RECOMMENDATIONS")
    print("="*100)
    
    m5_best = max(m5_results, key=lambda x: x['risk_reward'])
    m1_best = max(m1_results, key=lambda x: x['risk_reward'])
    
    if m5_best['desc'] != "Current":
        print(f"M5: Switch to RSI {m5_best['long_exit']}/{m5_best['short_exit']} exits")
        print(f"    Improves R:R from 1:{m5_results[0]['risk_reward']:.2f} to 1:{m5_best['risk_reward']:.2f}")
    else:
        print(f"M5: Current RSI exits are optimal")
    
    if m1_best['desc'] != "Current":
        print(f"M1: Switch to RSI {m1_best['long_exit']}/{m1_best['short_exit']} exits")
        print(f"    Improves R:R from 1:{m1_results[0]['risk_reward']:.2f} to 1:{m1_best['risk_reward']:.2f}")
    else:
        print(f"M1: Current RSI exits are optimal")
    
    print("="*100)
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
