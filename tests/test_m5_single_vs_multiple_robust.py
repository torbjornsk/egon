"""
Robust test of M5 single vs multiple positions
Test on multiple time periods to see if result is consistent
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

def load_config(path):
    """Load config"""
    with open(path, 'r') as f:
        return json.load(f)

def calculate_indicators(df, config):
    """Calculate indicators"""
    df = df.copy()
    
    df['ema_fast'] = df['close'].ewm(span=config['fast_ema']).mean()
    df['ema_slow'] = df['close'].ewm(span=config['slow_ema']).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(config['rsi_period']).mean()
    loss = -delta.clip(upper=0).rolling(config['rsi_period']).mean()
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

def simulate_strategy(df, config, max_positions=1):
    """Simulate M5 strategy"""
    
    position_size_per_trade = config['position_size_pct'] / max_positions
    
    positions = []
    balance = 10000
    trades = []
    cooldown_until = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if pd.isna(row['RSI']) or pd.isna(row['ATR']):
            continue
        
        # Check exits
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            should_exit = False
            exit_price = None
            
            if pos['type'] == 'LONG':
                if row['RSI'] > config['rsi_exit_long']:
                    should_exit = True
                    exit_price = row['close']
            else:
                if row['RSI'] < config['rsi_exit_short']:
                    should_exit = True
                    exit_price = row['close']
            
            if not should_exit:
                if pos['type'] == 'LONG' and row['low'] <= pos['sl']:
                    should_exit = True
                    exit_price = pos['sl']
                elif pos['type'] == 'SHORT' and row['high'] >= pos['sl']:
                    should_exit = True
                    exit_price = pos['sl']
            
            if not should_exit:
                if pos['type'] == 'LONG' and row['high'] >= pos['tp']:
                    should_exit = True
                    exit_price = pos['tp']
                elif pos['type'] == 'SHORT' and row['low'] <= pos['tp']:
                    should_exit = True
                    exit_price = pos['tp']
            
            if should_exit:
                if pos['type'] == 'LONG':
                    profit = (exit_price - pos['entry_price']) * 100 * position_size_per_trade * config['leverage']
                else:
                    profit = (pos['entry_price'] - exit_price) * 100 * position_size_per_trade * config['leverage']
                
                balance += profit
                trades.append({'profit': profit})
                positions_to_remove.append(idx)
                cooldown_until = i + 2
        
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
        
        # Check entry
        if i >= cooldown_until and len(positions) < max_positions:
            if row['RSI'] < config['rsi_buy']:
                atr = row['ATR']
                entry_price = row['close']
                sl = entry_price - (atr * config['atr_multiplier'])
                tp = entry_price + (entry_price * config['profit_target_pct'])
                
                positions.append({
                    'type': 'LONG',
                    'entry_price': entry_price,
                    'entry_bar': i,
                    'sl': sl,
                    'tp': tp
                })
            
            elif config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                atr = row['ATR']
                entry_price = row['close']
                sl = entry_price + (atr * config['atr_multiplier'])
                tp = entry_price - (entry_price * config['profit_target_pct'])
                
                positions.append({
                    'type': 'SHORT',
                    'entry_price': entry_price,
                    'entry_bar': i,
                    'sl': sl,
                    'tp': tp
                })
    
    return_pct = (balance - 10000) / 10000 * 100
    win_rate = sum(1 for t in trades if t['profit'] > 0) / len(trades) * 100 if trades else 0
    
    return {
        'return_pct': return_pct,
        'trades': len(trades),
        'win_rate': win_rate,
        'balance': balance
    }

def main():
    """Run robust comparison"""
    print("="*100)
    print("M5 BOT: ROBUST SINGLE vs MULTIPLE POSITIONS TEST")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get full history (use available data)
    print(f"\nFetching M5 history...")
    bars = 120 * 24 * 12  # 120 days
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars)
    
    if rates is None or len(rates) == 0:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df_full = pd.DataFrame(rates)
    df_full['time'] = pd.to_datetime(df_full['time'], unit='s')
    
    mt5.shutdown()
    
    print(f"Loaded {len(df_full)} bars ({df_full.iloc[0]['time']} to {df_full.iloc[-1]['time']})")
    
    # Load config
    config = load_config('config/m5_params.json')
    
    # Calculate indicators on full dataset
    print(f"Calculating indicators...")
    df_full = calculate_indicators(df_full, config)
    
    # Test on multiple 30-day periods
    print(f"\nTesting on 30-day periods...")
    
    bars_30d = 30 * 24 * 12
    num_tests = 10
    
    single_results = []
    multiple_results = []
    
    for test_num in range(num_tests):
        # Get random 30-day period
        max_start = len(df_full) - bars_30d - 200
        start_idx = np.random.randint(200, max_start)
        end_idx = start_idx + bars_30d
        
        df_test = df_full.iloc[start_idx:end_idx].copy().reset_index(drop=True)
        
        # Test single position
        single_result = simulate_strategy(df_test, config, max_positions=1)
        single_results.append(single_result)
        
        # Test multiple positions
        multiple_result = simulate_strategy(df_test, config, max_positions=2)
        multiple_results.append(multiple_result)
        
        print(f"  Test {test_num+1}/{ num_tests}: Single={single_result['return_pct']:+.1f}%, Multiple={multiple_result['return_pct']:+.1f}%")
    
    # Calculate statistics
    print(f"\n" + "="*100)
    print("RESULTS ACROSS 10 RANDOM 30-DAY PERIODS")
    print("="*100)
    
    single_returns = [r['return_pct'] for r in single_results]
    multiple_returns = [r['return_pct'] for r in multiple_results]
    
    single_trades = [r['trades'] for r in single_results]
    multiple_trades = [r['trades'] for r in multiple_results]
    
    print(f"\n{'Metric':<30} | {'Single':>20} | {'Multiple':>20}")
    print("-"*100)
    print(f"{'Avg Return':<30} | {np.mean(single_returns):>19.1f}% | {np.mean(multiple_returns):>19.1f}%")
    print(f"{'Median Return':<30} | {np.median(single_returns):>19.1f}% | {np.median(multiple_returns):>19.1f}%")
    print(f"{'Std Dev':<30} | {np.std(single_returns):>19.1f}% | {np.std(multiple_returns):>19.1f}%")
    print(f"{'Min Return':<30} | {np.min(single_returns):>19.1f}% | {np.min(multiple_returns):>19.1f}%")
    print(f"{'Max Return':<30} | {np.max(single_returns):>19.1f}% | {np.max(multiple_returns):>19.1f}%")
    print(f"")
    print(f"{'Avg Trades':<30} | {np.mean(single_trades):>20.1f} | {np.mean(multiple_trades):>20.1f}")
    
    # Win rate
    single_wins = sum(1 for r in single_returns if r > 0)
    multiple_wins = sum(1 for r in multiple_returns if r > 0)
    
    print(f"{'Periods with Profit':<30} | {single_wins:>20}/10 | {multiple_wins:>20}/10")
    
    # Statistical significance
    print(f"\n" + "="*100)
    print("STATISTICAL ANALYSIS")
    print("="*100)
    
    avg_diff = np.mean(multiple_returns) - np.mean(single_returns)
    pct_diff = (avg_diff / abs(np.mean(single_returns))) * 100 if np.mean(single_returns) != 0 else 0
    
    # Count how many times multiple beat single
    multiple_wins_count = sum(1 for i in range(num_tests) if multiple_returns[i] > single_returns[i])
    
    print(f"\nAverage Difference: {avg_diff:+.1f}% ({pct_diff:+.1f}% relative)")
    print(f"Multiple beat Single: {multiple_wins_count}/{num_tests} times ({multiple_wins_count/num_tests*100:.0f}%)")
    
    # Recommendation
    print(f"\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    if multiple_wins_count >= 7 and avg_diff > 5:
        print(f"\n✓ KEEP MULTIPLE POSITIONS")
        print(f"  Multiple positions consistently outperform ({multiple_wins_count}/{num_tests} periods)")
        print(f"  Average improvement: {avg_diff:+.1f}%")
        print(f"\n  Why it works for M5:")
        print(f"    - More trades = more opportunities to profit")
        print(f"    - Risk spreading reduces impact of single bad trade")
        print(f"    - Win rate improves with multiple positions")
    elif single_wins_count >= 7 and avg_diff < -5:
        print(f"\n✓ SWITCH TO SINGLE POSITION")
        print(f"  Single position consistently outperforms ({single_wins_count}/{num_tests} periods)")
        print(f"  Average improvement: {-avg_diff:+.1f}%")
        print(f"\n  Why it works for M5:")
        print(f"    - Rare signals benefit from larger position size")
        print(f"    - Simpler management")
        print(f"    - Better profit per signal")
    else:
        print(f"\n→ NO CLEAR WINNER")
        print(f"  Multiple wins: {multiple_wins_count}/{num_tests}")
        print(f"  Single wins: {single_wins_count}/{num_tests}")
        print(f"  Average difference: {avg_diff:+.1f}%")
        print(f"\n  Both strategies work similarly well")
        print(f"  Current setup (multiple positions) is fine")
        print(f"  Choice depends on preference:")
        print(f"    - Multiple: More trades, risk spreading")
        print(f"    - Single: Simpler, larger per-trade profit")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
