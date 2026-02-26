"""
Optimize M1 exit thresholds across multiple time periods
Test various RSI exit levels to find most robust configuration
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json
import random

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

def backtest_period(df, config, long_exit_rsi, short_exit_rsi):
    """Backtest a single period with given exit thresholds"""
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
                if row['RSI'] > long_exit_rsi or price >= position['take_profit'] or price <= position['stop_loss']:
                    should_exit = True
            else:
                if row['RSI'] < short_exit_rsi or price <= position['take_profit'] or price >= position['stop_loss']:
                    should_exit = True
            
            if should_exit:
                balance += pnl
                trades.append({'pnl': pnl})
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
    
    if not trades:
        return None
    
    trades_df = pd.DataFrame(trades)
    winning = trades_df[trades_df['pnl'] > 0]
    
    return {
        'return': (balance / 1000 - 1) * 100,
        'max_dd': max_dd,
        'trades': len(trades),
        'win_rate': len(winning)/len(trades)*100 if len(trades) > 0 else 0
    }

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching M1 data (50 days)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=50)
    full_df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    if full_df is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"M1 data: {len(full_df)} bars\n")
    
    # Load current M1 config
    with open('config/m1_scalping_params.json', 'r') as f:
        config = json.load(f)
    
    # Generate 20 random time periods (7-14 days each)
    print("Generating 20 random time periods...")
    periods = []
    for _ in range(20):
        period_days = random.randint(7, 14)
        period_bars = period_days * 24 * 60  # M1 bars
        
        max_start = len(full_df) - period_bars - 200  # Need 200 bars for indicators
        if max_start < 200:
            continue
        
        start_idx = random.randint(200, max_start)
        end_idx = start_idx + period_bars
        
        period_df = full_df.iloc[start_idx:end_idx].copy()
        periods.append({
            'df': period_df,
            'days': period_days,
            'start': period_df.iloc[0]['time'],
            'end': period_df.iloc[-1]['time']
        })
    
    print(f"Created {len(periods)} test periods\n")
    
    # Test different exit threshold combinations
    print("="*100)
    print("OPTIMIZING EXIT THRESHOLDS ACROSS MULTIPLE TIME PERIODS")
    print("="*100)
    print()
    
    test_configs = [
        (65, 35, "Current (Quick)"),
        (68, 32, "Slightly longer"),
        (70, 30, "Moderate"),
        (72, 28, "Moderate+"),
        (75, 25, "Long"),
        (78, 22, "Long+"),
        (80, 20, "Very long"),
        (82, 18, "Very long+"),
        (85, 15, "Extreme"),
    ]
    
    results = []
    
    for long_exit, short_exit, desc in test_configs:
        period_results = []
        
        for period in periods:
            result = backtest_period(period['df'], config, long_exit, short_exit)
            if result:
                period_results.append(result)
        
        if period_results:
            returns = [r['return'] for r in period_results]
            dds = [r['max_dd'] for r in period_results]
            trades = [r['trades'] for r in period_results]
            win_rates = [r['win_rate'] for r in period_results]
            
            # Count winning periods
            winning_periods = sum(1 for r in returns if r > 0)
            
            results.append({
                'desc': desc,
                'long_exit': long_exit,
                'short_exit': short_exit,
                'avg_return': np.mean(returns),
                'median_return': np.median(returns),
                'avg_dd': np.mean(dds),
                'max_dd': np.max(dds),
                'win_period_pct': winning_periods / len(period_results) * 100,
                'avg_trades': np.mean(trades),
                'avg_win_rate': np.mean(win_rates),
                'worst_return': np.min(returns),
                'best_return': np.max(returns)
            })
    
    print(f"{'Exit Thresholds':<20} | {'Avg Ret':>8} | {'Med Ret':>8} | {'Win%':>5} | {'Avg DD':>7} | {'Max DD':>7} | {'Trades':>7}")
    print("="*100)
    
    for r in results:
        print(f"{r['desc']:<20} | {r['avg_return']:>7.1f}% | {r['median_return']:>7.1f}% | {r['win_period_pct']:>4.0f}% | {r['avg_dd']:>6.1f}% | {r['max_dd']:>6.1f}% | {r['avg_trades']:>7.0f}")
    
    print("="*100)
    
    # Find best by average return
    best_avg = max(results, key=lambda x: x['avg_return'])
    print(f"\n✓ BEST AVERAGE RETURN: {best_avg['desc']}")
    print(f"  Exit at RSI > {best_avg['long_exit']} (long) / RSI < {best_avg['short_exit']} (short)")
    print(f"  Avg Return: {best_avg['avg_return']:.1f}%")
    print(f"  Median Return: {best_avg['median_return']:.1f}%")
    print(f"  Winning Periods: {best_avg['win_period_pct']:.0f}%")
    print(f"  Avg Max DD: {best_avg['avg_dd']:.1f}%")
    print(f"  Worst Period: {best_avg['worst_return']:.1f}%")
    print(f"  Best Period: {best_avg['best_return']:.1f}%")
    
    # Find best by median (more robust)
    best_median = max(results, key=lambda x: x['median_return'])
    print(f"\n✓ BEST MEDIAN RETURN (Most Robust): {best_median['desc']}")
    print(f"  Exit at RSI > {best_median['long_exit']} (long) / RSI < {best_median['short_exit']} (short)")
    print(f"  Median Return: {best_median['median_return']:.1f}%")
    print(f"  Avg Return: {best_median['avg_return']:.1f}%")
    print(f"  Winning Periods: {best_median['win_period_pct']:.0f}%")
    
    # Find best risk-adjusted
    for r in results:
        r['risk_adj'] = r['avg_return'] / r['avg_dd'] if r['avg_dd'] > 0 else 0
    
    best_risk = max(results, key=lambda x: x['risk_adj'])
    print(f"\n✓ BEST RISK-ADJUSTED: {best_risk['desc']}")
    print(f"  Exit at RSI > {best_risk['long_exit']} (long) / RSI < {best_risk['short_exit']} (short)")
    print(f"  Return/DD Ratio: {best_risk['risk_adj']:.2f}")
    print(f"  Avg Return: {best_risk['avg_return']:.1f}%")
    print(f"  Avg DD: {best_risk['avg_dd']:.1f}%")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    if best_median['desc'] == "Current (Quick)":
        print("✓ Current exit thresholds (65/35) are optimal across different time periods")
    else:
        current = results[0]
        print(f"💡 Switch to '{best_median['desc']}' (RSI {best_median['long_exit']}/{best_median['short_exit']})")
        print(f"   Median return improvement: {best_median['median_return'] - current['median_return']:+.1f}%")
        print(f"   Average return improvement: {best_median['avg_return'] - current['avg_return']:+.1f}%")
        print(f"   Drawdown change: {best_median['avg_dd'] - current['avg_dd']:+.1f}%")
        print(f"   More consistent across different market conditions")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
