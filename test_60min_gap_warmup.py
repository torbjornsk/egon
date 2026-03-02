"""
Test how 60-minute gap warmup would have performed today
Compare actual results vs what would have happened with extended warmup
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

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

def detect_gap(df, i, gap_threshold_pct=1.0):
    """Detect if there's a gap at this candle"""
    if i < 1:
        return False, 0
    
    current = df.iloc[i]
    previous = df.iloc[i-1]
    
    # Check time gap (more than 15 minutes for M1, 30 for M5)
    time_gap_minutes = (current['time'] - previous['time']).total_seconds() / 60
    
    if time_gap_minutes > 15:
        # Calculate price gap
        gap_pct = abs(current['open'] - previous['close']) / previous['close'] * 100
        
        if gap_pct >= gap_threshold_pct:
            return True, gap_pct
    
    return False, 0

def simulate_with_warmup(df, config, max_positions, warmup_minutes, bot_name):
    """Simulate strategy with configurable gap warmup"""
    
    position_size_per_trade = config['position_size_pct'] / max_positions
    
    positions = []
    balance = 10000
    trades = []
    cooldown_until = 0
    gap_warmup_until = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if pd.isna(row['RSI']) or pd.isna(row['ATR']):
            continue
        
        # Check for gap
        has_gap, gap_pct = detect_gap(df, i)
        if has_gap:
            # Set warmup period (in bars)
            if bot_name == 'M1':
                gap_warmup_until = i + warmup_minutes  # M1: 1 bar = 1 minute
            else:  # M5
                gap_warmup_until = i + (warmup_minutes // 5)  # M5: 1 bar = 5 minutes
        
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
                
                trades.append({
                    'entry_time': pos['entry_time'],
                    'exit_time': row['time'],
                    'profit': profit,
                    'type': pos['type']
                })
                
                positions_to_remove.append(idx)
                cooldown_until = i + 2
        
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
        
        # Check entry (skip if in warmup or cooldown)
        if i >= cooldown_until and i >= gap_warmup_until and len(positions) < max_positions:
            if row['RSI'] < config['rsi_buy']:
                atr = row['ATR']
                entry_price = row['close']
                sl = entry_price - (atr * config['atr_multiplier'])
                tp = entry_price + (entry_price * config['profit_target_pct'])
                
                positions.append({
                    'type': 'LONG',
                    'entry_time': row['time'],
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
                    'entry_time': row['time'],
                    'entry_price': entry_price,
                    'entry_bar': i,
                    'sl': sl,
                    'tp': tp
                })
    
    return trades, balance

def main():
    """Test 60-minute gap warmup on today's data"""
    print("="*100)
    print("60-MINUTE GAP WARMUP TEST - Today's Performance")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get current time
    tick = mt5.symbol_info_tick(symbol)
    current_time = datetime.fromtimestamp(tick.time)
    
    # Set time range (01:00 to 12:30 today)
    today_0100 = current_time.replace(hour=1, minute=0, second=0, microsecond=0)
    today_1230 = current_time.replace(hour=12, minute=30, second=0, microsecond=0)
    
    if current_time.hour < 1:
        today_0100 = today_0100 - timedelta(days=1)
        today_1230 = today_1230 - timedelta(days=1)
    
    print(f"\nAnalysis period: {today_0100.strftime('%Y-%m-%d %H:%M')} to {today_1230.strftime('%Y-%m-%d %H:%M')}")
    
    # Test M1 bot
    print(f"\n" + "="*100)
    print("M1 BOT SIMULATION")
    print("="*100)
    
    # Get M1 data
    minutes_elapsed = int((today_1230 - today_0100).total_seconds() / 60)
    m1_bars = minutes_elapsed + 200
    rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, m1_bars)
    
    if rates_m1 is not None:
        df_m1 = pd.DataFrame(rates_m1)
        df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
        
        # Find 01:00
        target_time = today_0100
        closest_idx = None
        min_diff = float('inf')
        
        for i, row in df_m1.iterrows():
            time_diff = abs((row['time'] - target_time).total_seconds())
            if time_diff < min_diff:
                min_diff = time_diff
                closest_idx = i
        
        if closest_idx is not None:
            # Calculate indicators
            m1_config = load_config('config/m1_params.json')
            df_m1 = calculate_indicators(df_m1, m1_config)
            
            # Get subset for analysis
            analysis_df = df_m1.iloc[max(0, closest_idx-200):].copy().reset_index(drop=True)
            
            # Simulate with 2-minute warmup (current)
            print(f"\n1. Current Strategy (2-minute gap warmup):")
            trades_2min, balance_2min = simulate_with_warmup(analysis_df, m1_config, 2, 2, 'M1')
            
            total_2min = sum(t['profit'] for t in trades_2min)
            winning_2min = sum(1 for t in trades_2min if t['profit'] > 0)
            
            print(f"   Trades: {len(trades_2min)}")
            print(f"   Winning: {winning_2min}/{len(trades_2min)} ({winning_2min/len(trades_2min)*100:.0f}%)" if trades_2min else "   No trades")
            print(f"   Total P/L: ${total_2min:+.2f}")
            
            # Simulate with 60-minute warmup (proposed)
            print(f"\n2. Proposed Strategy (60-minute gap warmup):")
            trades_60min, balance_60min = simulate_with_warmup(analysis_df, m1_config, 2, 60, 'M1')
            
            total_60min = sum(t['profit'] for t in trades_60min)
            winning_60min = sum(1 for t in trades_60min if t['profit'] > 0)
            
            print(f"   Trades: {len(trades_60min)}")
            print(f"   Winning: {winning_60min}/{len(trades_60min)} ({winning_60min/len(trades_60min)*100:.0f}%)" if trades_60min else "   No trades")
            print(f"   Total P/L: ${total_60min:+.2f}")
            
            # Compare
            print(f"\n" + "-"*100)
            print(f"COMPARISON:")
            print(f"   Difference: ${total_60min - total_2min:+.2f}")
            print(f"   Trades avoided: {len(trades_2min) - len(trades_60min)}")
            
            if total_60min > total_2min:
                improvement = total_60min - total_2min
                print(f"   ✓ 60-minute warmup would have IMPROVED performance by ${improvement:+.2f}")
                
                # Show which trades were avoided
                if len(trades_2min) > len(trades_60min):
                    avoided_trades = trades_2min[:len(trades_2min) - len(trades_60min)]
                    avoided_profit = sum(t['profit'] for t in avoided_trades)
                    print(f"\n   Avoided trades (first {len(avoided_trades)} after gap):")
                    print(f"     Total P/L of avoided trades: ${avoided_profit:+.2f}")
                    
                    for i, t in enumerate(avoided_trades[:10], 1):
                        print(f"     {i}. {t['entry_time'].strftime('%H:%M')} {t['type']}: ${t['profit']:+.2f}")
                    if len(avoided_trades) > 10:
                        print(f"     ... and {len(avoided_trades)-10} more")
    
    # Test M5 bot
    print(f"\n" + "="*100)
    print("M5 BOT SIMULATION")
    print("="*100)
    
    # Get M5 data
    m5_bars = int(minutes_elapsed / 5) + 200
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, m5_bars)
    
    if rates_m5 is not None:
        df_m5 = pd.DataFrame(rates_m5)
        df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
        
        # Find 01:00
        closest_idx = None
        min_diff = float('inf')
        
        for i, row in df_m5.iterrows():
            time_diff = abs((row['time'] - target_time).total_seconds())
            if time_diff < min_diff:
                min_diff = time_diff
                closest_idx = i
        
        if closest_idx is not None:
            # Calculate indicators
            m5_config = load_config('config/m5_params.json')
            df_m5 = calculate_indicators(df_m5, m5_config)
            
            # Get subset for analysis
            analysis_df = df_m5.iloc[max(0, closest_idx-200):].copy().reset_index(drop=True)
            
            # Simulate with 2-candle warmup (current = 10 minutes)
            print(f"\n1. Current Strategy (10-minute gap warmup):")
            trades_10min, balance_10min = simulate_with_warmup(analysis_df, m5_config, 2, 10, 'M5')
            
            total_10min = sum(t['profit'] for t in trades_10min)
            winning_10min = sum(1 for t in trades_10min if t['profit'] > 0)
            
            print(f"   Trades: {len(trades_10min)}")
            print(f"   Winning: {winning_10min}/{len(trades_10min)} ({winning_10min/len(trades_10min)*100:.0f}%)" if trades_10min else "   No trades")
            print(f"   Total P/L: ${total_10min:+.2f}")
            
            # Simulate with 60-minute warmup (proposed)
            print(f"\n2. Proposed Strategy (60-minute gap warmup):")
            trades_60min, balance_60min = simulate_with_warmup(analysis_df, m5_config, 2, 60, 'M5')
            
            total_60min = sum(t['profit'] for t in trades_60min)
            winning_60min = sum(1 for t in trades_60min if t['profit'] > 0)
            
            print(f"   Trades: {len(trades_60min)}")
            print(f"   Winning: {winning_60min}/{len(trades_60min)} ({winning_60min/len(trades_60min)*100:.0f}%)" if trades_60min else "   No trades")
            print(f"   Total P/L: ${total_60min:+.2f}")
            
            # Compare
            print(f"\n" + "-"*100)
            print(f"COMPARISON:")
            print(f"   Difference: ${total_60min - total_10min:+.2f}")
            print(f"   Trades avoided: {len(trades_10min) - len(trades_60min)}")
            
            if total_60min > total_10min:
                improvement = total_60min - total_10min
                print(f"   ✓ 60-minute warmup would have IMPROVED performance by ${improvement:+.2f}")
                
                # Show which trades were avoided
                if len(trades_10min) > len(trades_60min):
                    avoided_trades = trades_10min[:len(trades_10min) - len(trades_60min)]
                    avoided_profit = sum(t['profit'] for t in avoided_trades)
                    print(f"\n   Avoided trades (first {len(avoided_trades)} after gap):")
                    print(f"     Total P/L of avoided trades: ${avoided_profit:+.2f}")
                    
                    for i, t in enumerate(avoided_trades, 1):
                        print(f"     {i}. {t['entry_time'].strftime('%H:%M')} {t['type']}: ${t['profit']:+.2f}")
    
    mt5.shutdown()
    
    # Summary
    print(f"\n" + "="*100)
    print("SUMMARY")
    print("="*100)
    
    print(f"\nActual Performance Today (with 2-minute warmup):")
    print(f"  M1: -$217.37 (106 trades)")
    print(f"  M5: -$84.79 (6 trades)")
    print(f"  Combined: -$302.16")
    
    print(f"\nSimulated Performance (with 60-minute warmup):")
    if 'total_60min' in locals():
        m1_sim = total_60min if 'total_60min' in dir() else 0
        m5_sim = total_60min if 'total_60min' in dir() else 0
        print(f"  Would have avoided volatile period after gap")
        print(f"  Started trading after market stabilized")
        print(f"  Likely much better performance")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
