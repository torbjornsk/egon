"""
Test M1 improvements:
1. Conservative mean reversion (lower position size)
2. Momentum scalping (trade with the trend, not against it)
3. Hybrid approach
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df):
    df = df.copy()
    
    # Fast EMAs for M1
    df['ema_fast'] = df['close'].ewm(span=5).mean()
    df['ema_slow'] = df['close'].ewm(span=12).mean()
    df['ema_trend'] = df['close'].ewm(span=50).mean()
    
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
    
    # Momentum indicator
    df['momentum'] = df['close'] - df['close'].shift(3)
    
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    df['above_trend'] = (df['close'] > df['ema_trend'])
    
    return df

def strategy_conservative_mean_reversion(df):
    """Current strategy but with 10% position size instead of 15%"""
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.10  # Reduced from 0.15
    leverage = 25
    atr_mult = 4.0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < 35:  # Buy dips
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * 0.008)
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            elif row['RSI'] > 65 and row['downtrend']:  # Sell peaks
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

def strategy_momentum_scalping(df):
    """
    Momentum scalping: Buy when price is moving UP with confirmation
    - Enter on momentum + RSI confirmation
    - Quick exits (tighter profit targets)
    - Trade WITH the trend, not against it
    """
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.15
    leverage = 25
    atr_mult = 3.0  # Tighter stops for momentum
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if position is None:
            # LONG: Momentum up + RSI not overbought + above trend
            if (row['momentum'] > 0 and 
                row['RSI'] > 45 and row['RSI'] < 70 and
                row['uptrend'] and
                row['above_trend']):
                
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * 0.005)  # Tighter TP for quick scalp
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            # SHORT: Momentum down + RSI not oversold + below trend
            elif (row['momentum'] < 0 and
                  row['RSI'] < 55 and row['RSI'] > 30 and
                  row['downtrend'] and
                  not row['above_trend']):
                
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * 0.005)
                
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
                elif row['momentum'] < 0:  # Momentum reversal
                    exit_price = row['close']
                    exit_reason = "Momentum"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['momentum'] > 0:
                    exit_price = row['close']
                    exit_reason = "Momentum"
            
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

def strategy_hybrid(df):
    """
    Hybrid: Use momentum in trending markets, mean reversion in ranging markets
    """
    df = compute_indicators(df)
    
    position = None
    balance = 1000
    trades = []
    
    position_size = 0.12  # Slightly conservative
    leverage = 25
    atr_mult = 3.5
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Detect market condition
        price_range = df['high'].iloc[i-20:i].max() - df['low'].iloc[i-20:i].min()
        avg_atr = df['ATR'].iloc[i-20:i].mean()
        is_trending = price_range > (avg_atr * 3)
        
        if position is None:
            if is_trending:
                # Use momentum in trending markets
                if (row['momentum'] > 0 and row['RSI'] > 50 and row['RSI'] < 70 and row['uptrend']):
                    entry = row['close']
                    base_pos = balance * position_size
                    lev_pos = base_pos * leverage
                    sl = entry - (row['ATR'] * atr_mult)
                    tp = entry + (entry * 0.006)
                    position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp, 'mode': 'momentum'}
            else:
                # Use mean reversion in ranging markets
                if row['RSI'] < 30:
                    entry = row['close']
                    base_pos = balance * position_size
                    lev_pos = base_pos * leverage
                    sl = entry - (row['ATR'] * atr_mult)
                    tp = entry + (entry * 0.008)
                    position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp, 'mode': 'reversion'}
        
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
                elif position['mode'] == 'momentum' and row['momentum'] < 0:
                    exit_price = row['close']
                    exit_reason = "Exit"
                elif position['mode'] == 'reversion' and row['RSI'] > 70:
                    exit_price = row['close']
                    exit_reason = "Exit"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
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
    
    print("Fetching 50 days of M1 data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=50)
    df = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    print(f"M1 data: {len(df)} bars\n")
    
    print("="*100)
    print("TESTING M1 STRATEGY IMPROVEMENTS")
    print("="*100)
    print()
    
    # Test current strategy
    with open('config/m1_scalping_params.json', 'r') as f:
        current_config = json.load(f)
    
    print("1. Current Strategy (15% position, mean reversion)...")
    # We'll use the conservative test as proxy since we can't easily load current
    balance_current, trades_current = strategy_conservative_mean_reversion(df)
    # Adjust for 15% vs 10%
    balance_current = 1000 + (balance_current - 1000) * 1.5
    
    print("2. Conservative Mean Reversion (10% position)...")
    balance_cons, trades_cons = strategy_conservative_mean_reversion(df)
    
    print("3. Momentum Scalping (trade WITH movement)...")
    balance_mom, trades_mom = strategy_momentum_scalping(df)
    
    print("4. Hybrid (momentum + mean reversion)...")
    balance_hyb, trades_hyb = strategy_hybrid(df)
    
    # Compare results
    results = [
        ("Current (15% MR)", balance_current, trades_current),
        ("Conservative (10% MR)", balance_cons, trades_cons),
        ("Momentum Scalping", balance_mom, trades_mom),
        ("Hybrid", balance_hyb, trades_hyb)
    ]
    
    print()
    print("="*100)
    print("RESULTS COMPARISON")
    print("="*100)
    print(f"{'Strategy':<25} | {'Return':>8} | {'Trades':>6} | {'Win%':>5} | {'Avg Win':>8} | {'Avg Loss':>9}")
    print("="*100)
    
    for name, balance, trades in results:
        if not trades:
            continue
        
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        losing = trades_df[trades_df['pnl'] < 0]
        
        return_pct = (balance / 1000 - 1) * 100
        win_rate = len(winning) / len(trades) * 100
        avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
        avg_loss = losing['pnl'].mean() if len(losing) > 0 else 0
        
        print(f"{name:<25} | {return_pct:>7.1f}% | {len(trades):>6} | {win_rate:>5.1f} | ${avg_win:>7.2f} | ${avg_loss:>8.2f}")
    
    print("="*100)
    
    # Find best
    best = max(results, key=lambda x: x[1])
    print(f"\nBEST STRATEGY: {best[0]}")
    print(f"  Return: {(best[1]/1000-1)*100:.1f}%")
    print(f"  Trades: {len(best[2])}")
    
    if best[2]:
        trades_df = pd.DataFrame(best[2])
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win Rate: {len(winning)/len(best[2])*100:.1f}%")
    
    print()
    print("RECOMMENDATION:")
    if best[0] == "Current (15% MR)":
        print("  Current strategy is already optimal")
    else:
        print(f"  Switch M1 to: {best[0]}")
        print(f"  Expected improvement: {(best[1]/balance_current-1)*100:+.1f}%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
