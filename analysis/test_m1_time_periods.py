"""
Test M1 strategy across multiple random time periods (Monte Carlo style)
to see if recent poor performance is an anomaly or consistent pattern
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import random

def compute_indicators(df):
    df = df.copy()
    
    # Fast EMAs for M1
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = -delta.clip(upper=0).rolling(5).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def backtest_m1_strategy(df):
    """Current M1 mean reversion strategy"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    atr_mult = 4.0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            # Buy dips
            if row['RSI'] < 35:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * 0.008)
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            # Sell peaks
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * 0.008)
                
                position = {'type': 'short', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
        
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
                elif row['RSI'] > 75:
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < 25:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                trades.append({'pnl': pnl, 'reason': exit_reason})
                position = None
    
    return balance, trades

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("M1 STRATEGY PERFORMANCE ACROSS MULTIPLE TIME PERIODS")
    print("="*100)
    print()
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching 60 days of M1 data...")
    df_full = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Total bars: {len(df_full)}")
    print()
    
    # Test different period lengths
    test_periods = [
        ('24 hours', 1440),   # 1440 M1 bars = 24 hours
        ('3 days', 4320),     # 3 days
        ('7 days', 10080),    # 1 week
        ('14 days', 20160),   # 2 weeks
    ]
    
    results_by_period = {}
    
    for period_name, bars in test_periods:
        print(f"Testing {period_name} periods ({bars} bars)...")
        
        # Sample 20 random periods of this length
        samples = []
        max_start = len(df_full) - bars - 200  # Need 200 bars for warmup
        
        if max_start < 0:
            print(f"  Not enough data for {period_name}")
            continue
        
        for _ in range(20):
            start_idx = random.randint(200, max_start)
            end_idx = start_idx + bars
            
            df_sample = df_full.iloc[start_idx:end_idx].copy()
            df_sample = df_sample.reset_index(drop=True)
            
            balance, trades = backtest_m1_strategy(df_sample)
            
            if trades:
                trades_df = pd.DataFrame(trades)
                winning = trades_df[trades_df['pnl'] > 0]
                losing = trades_df[trades_df['pnl'] < 0]
                sl_trades = trades_df[trades_df['reason'] == 'SL']
                
                return_pct = (balance / 1000 - 1) * 100
                win_rate = len(winning) / len(trades) * 100
                sl_rate = len(sl_trades) / len(trades) * 100
                avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
                avg_loss = losing['pnl'].mean() if len(losing) > 0 else 0
                risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
                
                samples.append({
                    'return': return_pct,
                    'trades': len(trades),
                    'win_rate': win_rate,
                    'sl_rate': sl_rate,
                    'risk_reward': risk_reward,
                    'profitable': return_pct > 0
                })
        
        if samples:
            results_by_period[period_name] = samples
            
            # Calculate statistics
            returns = [s['return'] for s in samples]
            win_rates = [s['win_rate'] for s in samples]
            sl_rates = [s['sl_rate'] for s in samples]
            rr_ratios = [s['risk_reward'] for s in samples]
            profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
            
            print(f"  Samples: {len(samples)}")
            print(f"  Avg Return: {np.mean(returns):.1f}% (±{np.std(returns):.1f}%)")
            print(f"  Profitable: {profitable_pct:.0f}% of periods")
            print(f"  Avg Win Rate: {np.mean(win_rates):.1f}%")
            print(f"  Avg SL Rate: {np.mean(sl_rates):.1f}%")
            print(f"  Avg R:R: 1:{np.mean(rr_ratios):.2f}")
            print()
    
    # Summary comparison
    print("="*100)
    print("SUMMARY COMPARISON")
    print("="*100)
    print(f"{'Period':<15} | {'Avg Return':>12} | {'Profitable':>11} | {'Win Rate':>9} | {'SL Rate':>8} | {'R:R':>8}")
    print("="*100)
    
    for period_name in ['24 hours', '3 days', '7 days', '14 days']:
        if period_name not in results_by_period:
            continue
        
        samples = results_by_period[period_name]
        returns = [s['return'] for s in samples]
        win_rates = [s['win_rate'] for s in samples]
        sl_rates = [s['sl_rate'] for s in samples]
        rr_ratios = [s['risk_reward'] for s in samples]
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        
        print(f"{period_name:<15} | {np.mean(returns):>11.1f}% | {profitable_pct:>10.0f}% | {np.mean(win_rates):>8.1f}% | {np.mean(sl_rates):>7.1f}% | 1:{np.mean(rr_ratios):>5.2f}")
    
    print("="*100)
    print()
    
    # Conclusions
    print("CONCLUSIONS:")
    print()
    
    # Check if performance degrades on shorter timeframes
    if '24 hours' in results_by_period and '14 days' in results_by_period:
        short_return = np.mean([s['return'] for s in results_by_period['24 hours']])
        long_return = np.mean([s['return'] for s in results_by_period['14 days']])
        
        short_profitable = sum(1 for s in results_by_period['24 hours'] if s['profitable']) / len(results_by_period['24 hours']) * 100
        long_profitable = sum(1 for s in results_by_period['14 days'] if s['profitable']) / len(results_by_period['14 days']) * 100
        
        print(f"24-hour periods: {short_return:.1f}% avg return, {short_profitable:.0f}% profitable")
        print(f"14-day periods: {long_return:.1f}% avg return, {long_profitable:.0f}% profitable")
        print()
        
        if short_profitable < 50:
            print("WARNING: Less than 50% of 24-hour periods are profitable")
            print("  This means M1 is coin-flip territory on daily timeframes")
            print("  Your recent loss is NOT an anomaly - it's expected variance")
        elif short_profitable > 60:
            print("GOOD: Most 24-hour periods are profitable")
            print("  Your recent loss is likely just bad luck")
        else:
            print("MARGINAL: About half of 24-hour periods are profitable")
            print("  M1 is break-even on short timeframes, profitable long-term")
        
        print()
        
        if long_return > short_return * 2:
            print("Strategy needs TIME to work - short-term variance is high")
            print("  Keep M1 running if you're patient for long-term gains")
        elif short_return < 0:
            print("Strategy is NEGATIVE on short timeframes")
            print("  Consider disabling M1 or switching strategies")
    
    print()
    print("RECOMMENDATION:")
    
    if '24 hours' in results_by_period:
        samples = results_by_period['24 hours']
        profitable_pct = sum(1 for s in samples if s['profitable']) / len(samples) * 100
        avg_return = np.mean([s['return'] for s in samples])
        
        if profitable_pct < 45:
            print("  M1 is unreliable on daily timeframes - consider disabling")
        elif profitable_pct > 60 and avg_return > 2:
            print("  M1 is solid - keep running, recent loss is just variance")
        else:
            print("  M1 is marginal - keep if you're patient, disable if you want consistency")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
