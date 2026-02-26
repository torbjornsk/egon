"""
Analyze losing streak patterns to set realistic consecutive loss limits
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, timeframe='M5'):
    df = df.copy()
    
    if timeframe == 'M5':
        fast_span = 12
        slow_span = 26
        rsi_period = 14
    else:
        fast_span = 5
        slow_span = 12
        rsi_period = 5
    
    df['ema_fast'] = df['close'].ewm(span=fast_span).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_span).mean()
    
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

def backtest_with_streak_tracking(df, config, timeframe='M5'):
    """Backtest and track losing streaks"""
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    trades = []
    current_streak = 0
    max_losing_streak = 0
    losing_streaks = []
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            elif row['RSI'] > config['rsi_sell'] and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * config['profit_target_pct'])
                
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
                elif row['RSI'] > config.get('rsi_exit_long', 75):
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < config.get('rsi_exit_short', 25):
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                
                # Track streaks
                if pnl < 0:
                    current_streak += 1
                    if current_streak > max_losing_streak:
                        max_losing_streak = current_streak
                else:
                    if current_streak > 0:
                        losing_streaks.append(current_streak)
                    current_streak = 0
                
                trades.append({'pnl': pnl, 'reason': exit_reason})
                position = None
    
    # Add final streak if ended on losses
    if current_streak > 0:
        losing_streaks.append(current_streak)
    
    return balance, trades, max_losing_streak, losing_streaks

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("LOSING STREAK ANALYSIS")
    print("="*100)
    print()
    
    # Load configs
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    print(f"M5 bars: {len(df_m5)}")
    print(f"M1 bars: {len(df_m1)}")
    print()
    
    # Analyze M5
    print("Analyzing M5 bot...")
    balance_m5, trades_m5, max_streak_m5, streaks_m5 = backtest_with_streak_tracking(df_m5, m5_config, 'M5')
    
    print(f"  Total trades: {len(trades_m5)}")
    print(f"  Max losing streak: {max_streak_m5}")
    print(f"  Number of losing streaks: {len(streaks_m5)}")
    if streaks_m5:
        print(f"  Avg losing streak: {np.mean(streaks_m5):.1f}")
        print(f"  95th percentile: {np.percentile(streaks_m5, 95):.0f}")
        print(f"  99th percentile: {np.percentile(streaks_m5, 99):.0f}")
    print()
    
    # Analyze M1
    print("Analyzing M1 bot...")
    balance_m1, trades_m1, max_streak_m1, streaks_m1 = backtest_with_streak_tracking(df_m1, m1_config, 'M1')
    
    print(f"  Total trades: {len(trades_m1)}")
    print(f"  Max losing streak: {max_streak_m1}")
    print(f"  Number of losing streaks: {len(streaks_m1)}")
    if streaks_m1:
        print(f"  Avg losing streak: {np.mean(streaks_m1):.1f}")
        print(f"  95th percentile: {np.percentile(streaks_m1, 95):.0f}")
        print(f"  99th percentile: {np.percentile(streaks_m1, 99):.0f}")
    print()
    
    # Distribution analysis
    print("="*100)
    print("LOSING STREAK DISTRIBUTION")
    print("="*100)
    print()
    
    print("M5 Bot:")
    if streaks_m5:
        for streak_len in range(1, max_streak_m5 + 1):
            count = sum(1 for s in streaks_m5 if s == streak_len)
            pct = count / len(streaks_m5) * 100
            print(f"  {streak_len} losses: {count} times ({pct:.1f}%)")
    print()
    
    print("M1 Bot:")
    if streaks_m1:
        for streak_len in range(1, min(max_streak_m1 + 1, 15)):  # Cap at 15 for readability
            count = sum(1 for s in streaks_m1 if s == streak_len)
            pct = count / len(streaks_m1) * 100
            print(f"  {streak_len} losses: {count} times ({pct:.1f}%)")
        
        if max_streak_m1 > 15:
            count_15plus = sum(1 for s in streaks_m1 if s > 15)
            pct = count_15plus / len(streaks_m1) * 100
            print(f"  15+ losses: {count_15plus} times ({pct:.1f}%)")
    print()
    
    # Recommendations
    print("="*100)
    print("RECOMMENDATIONS")
    print("="*100)
    print()
    
    # M5 recommendation
    m5_99th = np.percentile(streaks_m5, 99) if streaks_m5 else 5
    m5_recommended = int(m5_99th) + 2  # Add buffer
    
    print(f"M5 Bot:")
    print(f"  Current limit: 5 consecutive losses")
    print(f"  99th percentile: {m5_99th:.0f} losses")
    print(f"  Recommended: {m5_recommended} consecutive losses")
    print(f"  Reasoning: Covers 99% of normal streaks + buffer")
    print()
    
    # M1 recommendation
    m1_99th = np.percentile(streaks_m1, 99) if streaks_m1 else 5
    m1_recommended = int(m1_99th) + 2
    
    print(f"M1 Bot:")
    print(f"  Current limit: 5 consecutive losses")
    print(f"  99th percentile: {m1_99th:.0f} losses")
    print(f"  Recommended: {m1_recommended} consecutive losses")
    print(f"  Reasoning: M1 is noisier, needs higher threshold")
    print()
    
    # Overall assessment
    print("ASSESSMENT:")
    if m5_recommended <= 5:
        print("  M5: Current limit (5) is appropriate")
    else:
        print(f"  M5: Increase limit to {m5_recommended} to avoid false triggers")
    
    if m1_recommended <= 5:
        print("  M1: Current limit (5) is appropriate")
    else:
        print(f"  M1: Increase limit to {m1_recommended} to avoid false triggers")
    
    print()
    print("ALTERNATIVE APPROACH:")
    print("  Instead of consecutive losses, consider:")
    print("  - Loss rate over last N trades (e.g., 70% losses in last 20 trades)")
    print("  - This is more robust to normal variance")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
