"""
Test different stop loss widths for M1 strategy
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

def backtest_with_stop_width(df, config, atr_multiplier):
    """Test with specific ATR multiplier for stop loss"""
    df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    equity_curve = []
    peak = 1000
    max_dd = 0
    
    exit_long_rsi = config.get('rsi_exit_long', config['rsi_sell'])
    exit_short_rsi = config.get('rsi_exit_short', config['rsi_buy'])
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                base_position = balance * config['position_size_pct']
                leveraged_position = base_position * config['leverage']
                stop_distance = row['ATR'] * atr_multiplier  # Use custom multiplier
                
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
                stop_distance = row['ATR'] * atr_multiplier  # Use custom multiplier
                
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
                trades.append({'pnl': pnl, 'exit_reason': exit_reason})
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
    
    # Load M1 config
    with open('config/m1_scalping_params.json', 'r') as f:
        config = json.load(f)
    
    print("="*100)
    print("TESTING DIFFERENT STOP LOSS WIDTHS")
    print("="*100)
    print()
    
    # Test different ATR multipliers
    test_multipliers = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    
    results = []
    
    for mult in test_multipliers:
        balance, trades, max_dd = backtest_with_stop_width(df, config, mult)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            return_pct = (balance / 1000 - 1) * 100
            
            # Count exit reasons
            sl_count = len(trades_df[trades_df['exit_reason'] == 'SL'])
            tp_count = len(trades_df[trades_df['exit_reason'] == 'TP'])
            rsi_count = len(trades_df[trades_df['exit_reason'] == 'RSI'])
            
            sl_rate = sl_count / len(trades) * 100
            
            results.append({
                'multiplier': mult,
                'return': return_pct,
                'max_dd': max_dd,
                'trades': len(trades),
                'win_rate': len(winning)/len(trades)*100,
                'sl_rate': sl_rate,
                'sl_count': sl_count,
                'tp_count': tp_count,
                'rsi_count': rsi_count,
                'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
                'avg_loss': trades_df[trades_df['pnl'] < 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0
            })
    
    print(f"{'ATR Mult':>8} | {'Return':>8} | {'Max DD':>7} | {'Trades':>6} | {'Win%':>5} | {'SL Rate':>7} | {'SL/TP/RSI':<12}")
    print("="*100)
    
    for r in results:
        exit_str = f"{r['sl_count']}/{r['tp_count']}/{r['rsi_count']}"
        print(f"{r['multiplier']:>8.1f} | {r['return']:>7.1f}% | {r['max_dd']:>6.1f}% | {r['trades']:>6} | {r['win_rate']:>5.1f} | {r['sl_rate']:>6.1f}% | {exit_str:<12}")
    
    print("="*100)
    
    # Find best by return
    best_return = max(results, key=lambda x: x['return'])
    print(f"\n✓ BEST RETURN: {best_return['multiplier']}x ATR")
    print(f"  Return: {best_return['return']:.1f}%")
    print(f"  Max DD: {best_return['max_dd']:.1f}%")
    print(f"  Stop Loss Rate: {best_return['sl_rate']:.1f}%")
    print(f"  Win Rate: {best_return['win_rate']:.1f}%")
    
    # Find best risk-adjusted
    for r in results:
        r['risk_adj'] = r['return'] / r['max_dd'] if r['max_dd'] > 0 else 0
    
    best_risk = max(results, key=lambda x: x['risk_adj'])
    print(f"\n✓ BEST RISK-ADJUSTED: {best_risk['multiplier']}x ATR")
    print(f"  Return: {best_risk['return']:.1f}%")
    print(f"  Max DD: {best_risk['max_dd']:.1f}%")
    print(f"  Risk/Reward Ratio: {best_risk['risk_adj']:.2f}")
    print(f"  Stop Loss Rate: {best_risk['sl_rate']:.1f}%")
    
    # Find lowest SL rate with good returns
    good_returns = [r for r in results if r['return'] > 50]
    if good_returns:
        lowest_sl = min(good_returns, key=lambda x: x['sl_rate'])
        print(f"\n✓ LOWEST STOP LOSS RATE (with >50% return): {lowest_sl['multiplier']}x ATR")
        print(f"  Return: {lowest_sl['return']:.1f}%")
        print(f"  Stop Loss Rate: {lowest_sl['sl_rate']:.1f}%")
        print(f"  Max DD: {lowest_sl['max_dd']:.1f}%")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    current = results[1]  # 1.5x is current
    
    if best_return['multiplier'] == 1.5:
        print("✓ Current 1.5x ATR is optimal")
    else:
        print(f"💡 Switch to {best_return['multiplier']}x ATR")
        print(f"   Return improvement: {best_return['return'] - current['return']:+.1f}%")
        print(f"   Stop loss rate: {best_return['sl_rate']:.1f}% (was {current['sl_rate']:.1f}%)")
        print(f"   Drawdown change: {best_return['max_dd'] - current['max_dd']:+.1f}%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
