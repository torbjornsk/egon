"""
Test bot performance across different market conditions:
- Strong uptrend
- Strong downtrend
- Crash (rapid decline)
- Ranging/choppy market
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
    else:  # M1
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

def backtest_m5(df):
    """M5 bot strategy"""
    df = compute_indicators(df, 'M5')
    
    with open('config/safe_leveraged_params.json', 'r') as f:
        config = json.load(f)
    
    position = None
    balance = 1000
    trades = []
    
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
                elif row['RSI'] > config['rsi_exit_long']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < config['rsi_exit_short']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                trades.append({'pnl': pnl, 'reason': exit_reason, 'type': position['type']})
                position = None
    
    return balance, trades

def backtest_m1(df):
    """M1 bot strategy"""
    df = compute_indicators(df, 'M1')
    
    with open('config/m1_scalping_params.json', 'r') as f:
        config = json.load(f)
    
    position = None
    balance = 1000
    trades = []
    
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
                elif row['RSI'] > config['rsi_exit_long']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < config['rsi_exit_short']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                trades.append({'pnl': pnl, 'reason': exit_reason, 'type': position['type']})
                position = None
    
    return balance, trades

def identify_market_conditions(df_full):
    """Identify different market condition periods in the data"""
    
    # Calculate trend strength over rolling windows
    window = 1440  # 1 day for M1, or adjust based on timeframe
    
    conditions = []
    
    for i in range(window, len(df_full) - window, window // 2):
        segment = df_full.iloc[i:i+window].copy()
        
        start_price = segment['close'].iloc[0]
        end_price = segment['close'].iloc[-1]
        price_change_pct = (end_price - start_price) / start_price * 100
        
        # Volatility
        returns = segment['close'].pct_change()
        volatility = returns.std() * 100
        
        # Range
        price_range = (segment['high'].max() - segment['low'].min()) / start_price * 100
        
        # Classify
        if price_change_pct > 2 and volatility < 0.5:
            condition = "Strong Uptrend"
        elif price_change_pct < -2 and volatility < 0.5:
            condition = "Strong Downtrend"
        elif price_change_pct < -3 and volatility > 0.8:
            condition = "Crash"
        elif abs(price_change_pct) < 1 and price_range < 3:
            condition = "Ranging"
        else:
            condition = "Mixed"
        
        conditions.append({
            'start_idx': i,
            'end_idx': i + window,
            'condition': condition,
            'price_change': price_change_pct,
            'volatility': volatility,
            'start_date': segment.index[0] if hasattr(segment.index[0], 'strftime') else None
        })
    
    return conditions

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("MARKET CONDITION STRESS TEST")
    print("="*100)
    print()
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    
    print(f"M5 bars: {len(df_m5)}")
    print(f"M1 bars: {len(df_m1)}")
    print()
    
    # Identify market conditions in M5 data
    print("Identifying market conditions...")
    conditions = identify_market_conditions(df_m5)
    
    # Group by condition type
    condition_groups = {}
    for c in conditions:
        cond_type = c['condition']
        if cond_type not in condition_groups:
            condition_groups[cond_type] = []
        condition_groups[cond_type].append(c)
    
    print(f"Found conditions: {list(condition_groups.keys())}")
    print()
    
    # Test each condition
    results = []
    
    for condition_type, periods in condition_groups.items():
        if condition_type == "Mixed":
            continue
        
        print(f"Testing {condition_type} ({len(periods)} periods)...")
        
        m5_returns = []
        m1_returns = []
        
        for period in periods[:3]:  # Test first 3 periods of each type
            # M5 test
            df_segment = df_m5.iloc[period['start_idx']:period['end_idx']].copy()
            if len(df_segment) > 200:
                balance_m5, trades_m5 = backtest_m5(df_segment)
                m5_returns.append((balance_m5 / 1000 - 1) * 100)
            
            # M1 test - find corresponding indices
            m5_start_time = df_m5.iloc[period['start_idx']].name
            m5_end_time = df_m5.iloc[period['end_idx']].name
            
            m1_segment = df_m1[(df_m1.index >= m5_start_time) & (df_m1.index <= m5_end_time)].copy()
            if len(m1_segment) > 200:
                balance_m1, trades_m1 = backtest_m1(m1_segment)
                m1_returns.append((balance_m1 / 1000 - 1) * 100)
        
        if m5_returns and m1_returns:
            results.append({
                'condition': condition_type,
                'm5_avg': np.mean(m5_returns),
                'm5_worst': min(m5_returns),
                'm1_avg': np.mean(m1_returns),
                'm1_worst': min(m1_returns),
                'periods_tested': min(len(m5_returns), len(m1_returns))
            })
    
    # Display results
    print()
    print("="*100)
    print("RESULTS BY MARKET CONDITION")
    print("="*100)
    print(f"{'Condition':<20} | {'M5 Avg':>9} | {'M5 Worst':>10} | {'M1 Avg':>9} | {'M1 Worst':>10} | {'Periods':>7}")
    print("="*100)
    
    for r in results:
        print(f"{r['condition']:<20} | {r['m5_avg']:>8.1f}% | {r['m5_worst']:>9.1f}% | {r['m1_avg']:>8.1f}% | {r['m1_worst']:>9.1f}% | {r['periods_tested']:>7}")
    
    print("="*100)
    print()
    
    # Analysis
    print("ANALYSIS:")
    print()
    
    for r in results:
        if r['condition'] in ['Strong Downtrend', 'Crash']:
            if r['m5_worst'] < -20 or r['m1_worst'] < -20:
                print(f"WARNING: {r['condition']} can cause significant losses")
                print(f"  M5 worst case: {r['m5_worst']:.1f}%")
                print(f"  M1 worst case: {r['m1_worst']:.1f}%")
                print()
    
    # Overall assessment
    worst_m5 = min([r['m5_worst'] for r in results])
    worst_m1 = min([r['m1_worst'] for r in results])
    
    print("WORST CASE SCENARIOS:")
    print(f"  M5 bot: {worst_m5:.1f}% loss in single period")
    print(f"  M1 bot: {worst_m1:.1f}% loss in single period")
    print()
    
    if worst_m5 < -30 or worst_m1 < -30:
        print("RISK ALERT: Bots can lose >30% in adverse conditions")
        print("  Consider: Lower leverage or tighter drawdown limits")
    elif worst_m5 < -20 or worst_m1 < -20:
        print("MODERATE RISK: Bots can lose 20-30% in adverse conditions")
        print("  Current drawdown limits (35% M5, 40% M1) should protect you")
    else:
        print("LOW RISK: Bots handle different market conditions well")
        print("  Mean reversion + shorts provide good protection")
    
    print()
    print("PROTECTION MECHANISMS:")
    print("  1. Both bots trade shorts (profit from downtrends)")
    print("  2. Mean reversion (buy dips, sell peaks)")
    print("  3. Drawdown limits (35% M5, 40% M1)")
    print("  4. Wide stops (3x ATR M5, 4x ATR M1)")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
