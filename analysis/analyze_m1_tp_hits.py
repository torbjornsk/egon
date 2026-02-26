"""
Analyze how often M1 actually hits its take profit target
and test lower TP values that might be more realistic
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def compute_indicators(df):
    df = df.copy()
    
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(5).mean()
    loss = -delta.clip(upper=0).rolling(5).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def backtest_with_tp(df, tp_pct):
    """Backtest with specific TP percentage"""
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
            if row['RSI'] < 35:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * tp_pct)
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            elif row['RSI'] > 65 and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * tp_pct)
                
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
    print("M1 TAKE PROFIT ANALYSIS")
    print("="*100)
    print()
    
    # Get last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print("Fetching 30 days of M1 data...")
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print(f"Bars: {len(df)}")
    print()
    
    # Test current TP
    print("Analyzing current TP (0.8%)...")
    balance_current, trades_current = backtest_with_tp(df, 0.008)
    
    trades_df = pd.DataFrame(trades_current)
    tp_hits = len(trades_df[trades_df['reason'] == 'TP'])
    rsi_exits = len(trades_df[trades_df['reason'] == 'RSI'])
    sl_hits = len(trades_df[trades_df['reason'] == 'SL'])
    
    print(f"\nCurrent TP (0.8%) Exit Breakdown:")
    print(f"  Take Profit hits: {tp_hits} ({tp_hits/len(trades_current)*100:.1f}%)")
    print(f"  RSI exits: {rsi_exits} ({rsi_exits/len(trades_current)*100:.1f}%)")
    print(f"  Stop Loss hits: {sl_hits} ({sl_hits/len(trades_current)*100:.1f}%)")
    print(f"  Total trades: {len(trades_current)}")
    print()
    
    if tp_hits / len(trades_current) < 0.15:
        print("WARNING: TP is hit less than 15% of the time - it's too far away!")
        print("Most trades exit via RSI, meaning TP is unrealistic for M1 timeframe")
        print()
    
    # Test different TP values
    print("Testing different TP values...")
    print()
    
    tp_values = [
        ("0.3%", 0.003),
        ("0.4%", 0.004),
        ("0.5%", 0.005),
        ("0.6%", 0.006),
        ("0.8% (current)", 0.008),
    ]
    
    results = []
    for name, tp_pct in tp_values:
        balance, trades = backtest_with_tp(df, tp_pct)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            losing = trades_df[trades_df['pnl'] < 0]
            tp_hits = len(trades_df[trades_df['reason'] == 'TP'])
            
            results.append({
                'name': name,
                'balance': balance,
                'trades': trades,
                'tp_hit_rate': tp_hits / len(trades) * 100,
                'return': (balance / 1000 - 1) * 100,
                'win_rate': len(winning) / len(trades) * 100,
                'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
                'avg_loss': losing['pnl'].mean() if len(losing) > 0 else 0,
            })
    
    print("="*100)
    print("RESULTS COMPARISON")
    print("="*100)
    print(f"{'TP Target':<18} | {'Return':>8} | {'TP Hit%':>7} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9}")
    print("="*100)
    
    for r in results:
        print(f"{r['name']:<18} | {r['return']:>7.1f}% | {r['tp_hit_rate']:>6.1f}% | {r['win_rate']:>5.1f} | ${r['avg_win']:>7.2f} | ${r['avg_loss']:>8.2f}")
    
    print("="*100)
    
    # Find best
    best = max(results, key=lambda x: x['balance'])
    print(f"\nBEST: {best['name']} with {best['return']:.1f}% return")
    print(f"  TP hit rate: {best['tp_hit_rate']:.1f}%")
    
    # Find most realistic (TP hit rate 20-40%)
    realistic = [r for r in results if 20 <= r['tp_hit_rate'] <= 40]
    if realistic:
        best_realistic = max(realistic, key=lambda x: x['balance'])
        print(f"\nMOST REALISTIC: {best_realistic['name']} with {best_realistic['return']:.1f}% return")
        print(f"  TP hit rate: {best_realistic['tp_hit_rate']:.1f}% (balanced between TP and RSI exits)")
        
        if best_realistic['name'] != best['name']:
            print(f"\nRECOMMENDATION: Switch to {best_realistic['name']}")
            print(f"  More consistent exits (TP actually gets hit)")
            print(f"  Better captures intra-candle moves")
        else:
            print(f"\nRECOMMENDATION: Keep current TP")
    
    print()
    print("EXPLANATION:")
    print("  Lower TP = More TP hits = Captures moves between candles")
    print("  Higher TP = More RSI exits = Waits for full reversal")
    print("  Sweet spot: TP hit rate around 25-35%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
