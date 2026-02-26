"""
Test M1 strategy with different hold durations
Current: Buy at RSI<35, Exit at RSI>65
Test: Hold longer by adjusting exit thresholds
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

def backtest_with_exit_threshold(df, config, long_exit_rsi, short_exit_rsi):
    """Test with custom exit RSI thresholds"""
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
                # Use custom exit threshold
                if row['RSI'] > long_exit_rsi or price >= position['take_profit'] or price <= position['stop_loss']:
                    should_exit = True
            else:
                # Use custom exit threshold
                if row['RSI'] < short_exit_rsi or price <= position['take_profit'] or price >= position['stop_loss']:
                    should_exit = True
            
            if should_exit:
                balance += pnl
                trades.append({'pnl': pnl, 'return_pct': price_change_pct * 100})
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
    
    print("="*100)
    print("TESTING DIFFERENT HOLD DURATIONS (Exit RSI Thresholds)")
    print("="*100)
    print(f"Entry: LONG at RSI < {config['rsi_buy']}, SHORT at RSI > {config['rsi_sell']}")
    print()
    
    # Test different exit thresholds
    test_configs = [
        # (long_exit_rsi, short_exit_rsi, description)
        (65, 35, "Current (Quick exit)"),
        (70, 30, "Hold slightly longer"),
        (75, 25, "Hold longer"),
        (80, 20, "Hold much longer"),
        (85, 15, "Hold very long"),
    ]
    
    results = []
    
    for long_exit, short_exit, desc in test_configs:
        balance, trades, max_dd = backtest_with_exit_threshold(df, config, long_exit, short_exit)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            return_pct = (balance / 1000 - 1) * 100
            
            results.append({
                'desc': desc,
                'long_exit': long_exit,
                'short_exit': short_exit,
                'return': return_pct,
                'max_dd': max_dd,
                'trades': len(trades),
                'win_rate': len(winning)/len(trades)*100,
                'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
                'avg_loss': trades_df[trades_df['pnl'] < 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0,
                'avg_return': trades_df['return_pct'].mean()
            })
    
    print(f"{'Exit Thresholds':<25} | {'Return':>8} | {'Max DD':>7} | {'Trades':>6} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9}")
    print("="*100)
    
    for r in results:
        print(f"{r['desc']:<25} | {r['return']:>7.2f}% | {r['max_dd']:>6.2f}% | {r['trades']:>6} | {r['win_rate']:>5.1f} | ${r['avg_win']:>7.2f} | ${r['avg_loss']:>8.2f}")
    
    print("="*100)
    
    # Find best by return
    best_return = max(results, key=lambda x: x['return'])
    print(f"\n✓ BEST RETURN: {best_return['desc']}")
    print(f"  Exit at RSI > {best_return['long_exit']} (long) / RSI < {best_return['short_exit']} (short)")
    print(f"  Return: {best_return['return']:.2f}%")
    print(f"  Max DD: {best_return['max_dd']:.2f}%")
    print(f"  Trades: {best_return['trades']}")
    print(f"  Win Rate: {best_return['win_rate']:.1f}%")
    
    # Find best risk-adjusted (return/DD ratio)
    for r in results:
        r['risk_adj'] = r['return'] / r['max_dd'] if r['max_dd'] > 0 else 0
    
    best_risk_adj = max(results, key=lambda x: x['risk_adj'])
    print(f"\n✓ BEST RISK-ADJUSTED: {best_risk_adj['desc']}")
    print(f"  Exit at RSI > {best_risk_adj['long_exit']} (long) / RSI < {best_risk_adj['short_exit']} (short)")
    print(f"  Return: {best_risk_adj['return']:.2f}%")
    print(f"  Max DD: {best_risk_adj['max_dd']:.2f}%")
    print(f"  Risk-Adjusted Score: {best_risk_adj['risk_adj']:.2f}")
    
    if best_return['desc'] != "Current (Quick exit)":
        print(f"\n💡 RECOMMENDATION: Consider switching to '{best_return['desc']}'")
        print(f"   Improvement: +{best_return['return'] - results[0]['return']:.2f}% return")
        print(f"   Drawdown change: {best_return['max_dd'] - results[0]['max_dd']:+.2f}%")
    else:
        print(f"\n✓ Current exit thresholds are optimal")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
