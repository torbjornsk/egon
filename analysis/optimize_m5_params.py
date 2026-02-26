"""
Optimize M5 parameters to find the best configuration
Test different combinations of RSI thresholds, profit targets, and ATR multipliers
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from itertools import product

sys.path.append('.')
from src.mt5_connector import MT5Connector

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

def backtest_m5(df, params):
    """Backtest M5 with given parameters"""
    df = compute_indicators(df, params['fast_ema'], params['slow_ema'], params['rsi_period'])
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < params['rsi_buy']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * params['atr_multiplier'])
                tp = entry + (entry * params['profit_target_pct'])
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > params['rsi_exit_long']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0
                })
                
                position = None
    
    if not trades:
        return None
    
    return_pct = (balance / 1000 - 1) * 100
    win_rate = sum(1 for t in trades if t['profitable']) / len(trades) * 100
    
    # Calculate max drawdown
    equity = 1000
    peak = 1000
    max_dd = 0
    for t in trades:
        equity += t['pnl']
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak
        if dd > max_dd:
            max_dd = dd
    
    return {
        'return': return_pct,
        'trades': len(trades),
        'win_rate': win_rate,
        'max_dd': max_dd * 100,
        'sharpe': return_pct / max_dd if max_dd > 0 else 0
    }

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("=" * 100)
    print("M5 PARAMETER OPTIMIZATION")
    print("=" * 100)
    print()
    
    # Get 90 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    print("Fetching 90 days of M5 data...")
    df = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    print(f"Total bars: {len(df)}")
    print()
    
    # Parameter grid to test
    param_grid = {
        'fast_ema': [9, 12, 20],
        'slow_ema': [21, 30],
        'rsi_period': [10, 14],
        'rsi_buy': [25, 30, 35],
        'rsi_exit_long': [70, 75, 80, 85],
        'atr_multiplier': [2.0, 2.5, 3.0],
        'profit_target_pct': [0.01, 0.015, 0.02, 0.03, 0.04]
    }
    
    print("Testing parameter combinations...")
    print(f"Total combinations: {np.prod([len(v) for v in param_grid.values()])}")
    print()
    
    results = []
    count = 0
    
    for fast_ema in param_grid['fast_ema']:
        for slow_ema in param_grid['slow_ema']:
            if fast_ema >= slow_ema:
                continue
            for rsi_period in param_grid['rsi_period']:
                for rsi_buy in param_grid['rsi_buy']:
                    for rsi_exit in param_grid['rsi_exit_long']:
                        if rsi_exit <= rsi_buy + 20:  # Exit must be significantly higher
                            continue
                        for atr_mult in param_grid['atr_multiplier']:
                            for profit_target in param_grid['profit_target_pct']:
                                count += 1
                                
                                params = {
                                    'fast_ema': fast_ema,
                                    'slow_ema': slow_ema,
                                    'rsi_period': rsi_period,
                                    'rsi_buy': rsi_buy,
                                    'rsi_exit_long': rsi_exit,
                                    'atr_multiplier': atr_mult,
                                    'profit_target_pct': profit_target
                                }
                                
                                result = backtest_m5(df, params)
                                
                                if result:
                                    result['params'] = params
                                    results.append(result)
                                
                                if count % 50 == 0:
                                    print(f"Tested {count} combinations...")
    
    print(f"\nCompleted {count} tests, {len(results)} valid results")
    print()
    
    # Sort by Sharpe ratio (return / drawdown)
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    
    # Show top 10
    print("=" * 100)
    print("TOP 10 CONFIGURATIONS (by Sharpe ratio)")
    print("=" * 100)
    print()
    
    for i, r in enumerate(results[:10], 1):
        p = r['params']
        print(f"{i}. Return: {r['return']:.1f}%, Win Rate: {r['win_rate']:.1f}%, Max DD: {r['max_dd']:.1f}%, Sharpe: {r['sharpe']:.2f}")
        print(f"   EMA: {p['fast_ema']}/{p['slow_ema']}, RSI Period: {p['rsi_period']}, RSI: {p['rsi_buy']}/{p['rsi_exit_long']}")
        print(f"   ATR: {p['atr_multiplier']}x, TP: {p['profit_target_pct']*100:.1f}%, Trades: {r['trades']}")
        print()
    
    # Show best by return
    results_by_return = sorted(results, key=lambda x: x['return'], reverse=True)
    
    print("=" * 100)
    print("TOP 5 BY RETURN")
    print("=" * 100)
    print()
    
    for i, r in enumerate(results_by_return[:5], 1):
        p = r['params']
        print(f"{i}. Return: {r['return']:.1f}%, Win Rate: {r['win_rate']:.1f}%, Max DD: {r['max_dd']:.1f}%, Sharpe: {r['sharpe']:.2f}")
        print(f"   EMA: {p['fast_ema']}/{p['slow_ema']}, RSI Period: {p['rsi_period']}, RSI: {p['rsi_buy']}/{p['rsi_exit_long']}")
        print(f"   ATR: {p['atr_multiplier']}x, TP: {p['profit_target_pct']*100:.1f}%, Trades: {r['trades']}")
        print()
    
    # Recommendation
    print("=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)
    print()
    
    best = results[0]
    p = best['params']
    
    print("Best balanced configuration (highest Sharpe ratio):")
    print()
    print(f"Performance:")
    print(f"  Return: {best['return']:.1f}%")
    print(f"  Win Rate: {best['win_rate']:.1f}%")
    print(f"  Max Drawdown: {best['max_dd']:.1f}%")
    print(f"  Sharpe Ratio: {best['sharpe']:.2f}")
    print(f"  Trades: {best['trades']}")
    print()
    print(f"Parameters:")
    print(f"  fast_ema: {p['fast_ema']}")
    print(f"  slow_ema: {p['slow_ema']}")
    print(f"  rsi_period: {p['rsi_period']}")
    print(f"  rsi_buy: {p['rsi_buy']}")
    print(f"  rsi_exit_long: {p['rsi_exit_long']}")
    print(f"  atr_multiplier: {p['atr_multiplier']}")
    print(f"  profit_target_pct: {p['profit_target_pct']}")
    print()
    
    # Compare to current config
    current_params = {
        'fast_ema': 20,
        'slow_ema': 30,
        'rsi_period': 10,
        'rsi_buy': 30,
        'rsi_exit_long': 85,
        'atr_multiplier': 3.0,
        'profit_target_pct': 0.04
    }
    
    current_result = backtest_m5(df, current_params)
    
    print("Current config performance:")
    print(f"  Return: {current_result['return']:.1f}%")
    print(f"  Win Rate: {current_result['win_rate']:.1f}%")
    print(f"  Max Drawdown: {current_result['max_dd']:.1f}%")
    print(f"  Sharpe Ratio: {current_result['sharpe']:.2f}")
    print()
    
    improvement = ((best['return'] - current_result['return']) / abs(current_result['return'])) * 100 if current_result['return'] != 0 else 0
    print(f"Improvement: {improvement:+.1f}%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
