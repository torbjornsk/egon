"""
Backtest different strategies on the recent gap opening period
Compare M1, M5, and Trend strategies on the last 45 minutes
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def load_config(path):
    """Load strategy config"""
    with open(path, 'r') as f:
        return json.load(f)

def calculate_m1_indicators(df, config):
    """Calculate M1 strategy indicators"""
    df = df.copy()
    
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=config['fast_ema']).mean()
    df['ema_slow'] = df['close'].ewm(span=config['slow_ema']).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(config['rsi_period']).mean()
    loss = -delta.clip(upper=0).rolling(config['rsi_period']).mean()
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

def calculate_m5_indicators(df, config):
    """Calculate M5 strategy indicators"""
    df = df.copy()
    
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=config['fast_ema']).mean()
    df['ema_slow'] = df['close'].ewm(span=config['slow_ema']).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(config['rsi_period']).mean()
    loss = -delta.clip(upper=0).rolling(config['rsi_period']).mean()
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

def calculate_trend_indicators(df):
    """Calculate trend strategy indicators"""
    df = df.copy()
    
    # EMAs for trend
    df['ema_20'] = df['close'].ewm(span=20).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Strong trend detection
    df['strong_uptrend'] = (df['ema_20'] > df['ema_50']) & (df['ema_50'] > df['ema_200']) & (df['close'] > df['ema_20'])
    df['strong_downtrend'] = (df['ema_20'] < df['ema_50']) & (df['ema_50'] < df['ema_200']) & (df['close'] < df['ema_20'])
    
    return df

def simulate_m1_strategy(df, config):
    """Simulate M1 scalping strategy"""
    trades = []
    position = None
    
    for i in range(200, len(df)):  # Start after warmup
        row = df.iloc[i]
        
        # Check exit first
        if position:
            should_exit = False
            
            # RSI exits
            if position['type'] == 'LONG':
                exit_threshold = config.get('rsi_exit_long', config['rsi_sell'])
                if row['RSI'] > exit_threshold:
                    should_exit = True
            else:
                exit_threshold = config.get('rsi_exit_short', config['rsi_buy'])
                if row['RSI'] < exit_threshold:
                    should_exit = True
            
            # Time-based exit (10 minutes for losing positions)
            if position['profit'] < 0:
                bars_held = i - position['entry_bar']
                if bars_held >= 10:
                    should_exit = True
            
            if should_exit:
                exit_price = row['close']
                if position['type'] == 'LONG':
                    profit = (exit_price - position['entry_price']) * 100 * config['position_size_pct'] * config['leverage']
                else:
                    profit = (position['entry_price'] - exit_price) * 100 * config['position_size_pct'] * config['leverage']
                
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': row['time'],
                    'type': position['type'],
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'profit': profit
                })
                position = None
        
        # Check entry
        if not position:
            # LONG entry
            if row['RSI'] < config['rsi_buy']:
                position = {
                    'type': 'LONG',
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i,
                    'profit': 0
                }
            # SHORT entry
            elif config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                position = {
                    'type': 'SHORT',
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i,
                    'profit': 0
                }
        
        # Update position profit
        if position:
            if position['type'] == 'LONG':
                position['profit'] = (row['close'] - position['entry_price']) * 100 * config['position_size_pct'] * config['leverage']
            else:
                position['profit'] = (position['entry_price'] - row['close']) * 100 * config['position_size_pct'] * config['leverage']
    
    return trades

def simulate_m5_strategy(df, config):
    """Simulate M5 scalping strategy"""
    trades = []
    position = None
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check exit first
        if position:
            should_exit = False
            
            # RSI exits
            if position['type'] == 'LONG':
                if row['RSI'] > config['rsi_sell']:
                    should_exit = True
            else:
                if row['RSI'] < config['rsi_buy']:
                    should_exit = True
            
            if should_exit:
                exit_price = row['close']
                if position['type'] == 'LONG':
                    profit = (exit_price - position['entry_price']) * 100 * config['position_size_pct'] * config['leverage']
                else:
                    profit = (position['entry_price'] - exit_price) * 100 * config['position_size_pct'] * config['leverage']
                
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': row['time'],
                    'type': position['type'],
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'profit': profit
                })
                position = None
        
        # Check entry
        if not position:
            # LONG entry
            if row['RSI'] < config['rsi_buy']:
                position = {
                    'type': 'LONG',
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i
                }
            # SHORT entry
            elif config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                position = {
                    'type': 'SHORT',
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i
                }
    
    return trades

def simulate_trend_strategy(df):
    """Simulate trend following strategy"""
    trades = []
    position = None
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Check exit first
        if position:
            should_exit = False
            
            # Trend reversal exit
            if position['type'] == 'LONG':
                if row['strong_downtrend']:
                    should_exit = True
                elif row['RSI'] > 80:
                    should_exit = True
            else:
                if row['strong_uptrend']:
                    should_exit = True
                elif row['RSI'] < 20:
                    should_exit = True
            
            if should_exit:
                exit_price = row['close']
                if position['type'] == 'LONG':
                    profit = (exit_price - position['entry_price']) * 100 * 0.10 * 10  # 10% @ 10x
                else:
                    profit = (position['entry_price'] - exit_price) * 100 * 0.10 * 10
                
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': row['time'],
                    'type': position['type'],
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'profit': profit
                })
                position = None
        
        # Check entry
        if not position:
            # LONG entry on strong uptrend
            if row['strong_uptrend'] and row['RSI'] > 50 and row['RSI'] < 75:
                position = {
                    'type': 'LONG',
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i
                }
            # SHORT entry on strong downtrend
            elif row['strong_downtrend'] and row['RSI'] < 50 and row['RSI'] > 25:
                position = {
                    'type': 'SHORT',
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i
                }
    
    return trades

def main():
    """Run backtest comparison"""
    print("="*80)
    print("GAP PERIOD BACKTEST - Strategy Comparison")
    print("="*80)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get M1 data for last 45 minutes (45 bars)
    print("\nFetching M1 data for last 45 minutes...")
    rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 250)  # Extra for indicators
    
    if rates_m1 is None:
        print("Failed to get M1 data")
        mt5.shutdown()
        return
    
    df_m1 = pd.DataFrame(rates_m1)
    df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
    
    # Get M5 data
    print("Fetching M5 data...")
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 250)
    df_m5 = pd.DataFrame(rates_m5)
    df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
    
    # Get M15 data for trend strategy
    print("Fetching M15 data...")
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 250)
    df_m15 = pd.DataFrame(rates_m15)
    df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s')
    
    mt5.shutdown()
    
    # Load configs
    config_m1 = load_config('config/m1_params.json')
    config_m5 = load_config('config/m5_params.json')
    
    # Calculate indicators
    print("\nCalculating indicators...")
    df_m1 = calculate_m1_indicators(df_m1, config_m1)
    df_m5 = calculate_m5_indicators(df_m5, config_m5)
    df_m15 = calculate_trend_indicators(df_m15)
    
    # Find the gap in M1 data
    print("\nFinding gap in data...")
    gap_index = None
    for i in range(1, len(df_m1)):
        time_diff = (df_m1.iloc[i]['time'] - df_m1.iloc[i-1]['time']).total_seconds() / 60
        if time_diff > 30:
            gap_index = i
            print(f"Gap found at index {i}, time: {df_m1.iloc[i]['time']}")
            break
    
    if gap_index is None:
        print("No gap found, using last 100 bars")
        gap_index = len(df_m1) - 100
    
    # Run simulations starting from gap
    print("\nRunning strategy simulations from gap opening...")
    print("-" * 80)
    
    # M1 Strategy - 100 minutes after gap
    print("\n1. M1 SCALPING STRATEGY")
    df_m1_test = df_m1.iloc[max(0, gap_index-200):min(len(df_m1), gap_index+100)]
    trades_m1 = simulate_m1_strategy(df_m1_test, config_m1)
    total_profit_m1 = sum(t['profit'] for t in trades_m1)
    winning_m1 = [t for t in trades_m1 if t['profit'] > 0]
    
    print(f"   Period: {df_m1_test.iloc[0]['time']} to {df_m1_test.iloc[-1]['time']}")
    print(f"   Bars: {len(df_m1_test)}")
    print(f"   Trades: {len(trades_m1)}")
    print(f"   Winning: {len(winning_m1)}/{len(trades_m1)} ({len(winning_m1)/len(trades_m1)*100:.0f}%)" if trades_m1 else "   No trades")
    print(f"   Total P/L: ${total_profit_m1:.2f}")
    
    if trades_m1:
        for t in trades_m1[:5]:  # Show first 5
            print(f"     {t['type']}: ${t['entry_price']:.2f} → ${t['exit_price']:.2f} = ${t['profit']:+.2f}")
        if len(trades_m1) > 5:
            print(f"     ... and {len(trades_m1)-5} more trades")
    
    # M5 Strategy - 100 minutes after gap
    print("\n2. M5 SCALPING STRATEGY")
    gap_index_m5 = None
    for i in range(1, len(df_m5)):
        time_diff = (df_m5.iloc[i]['time'] - df_m5.iloc[i-1]['time']).total_seconds() / 60
        if time_diff > 30:
            gap_index_m5 = i
            break
    if gap_index_m5 is None:
        gap_index_m5 = len(df_m5) - 20
    
    df_m5_test = df_m5.iloc[max(0, gap_index_m5-200):min(len(df_m5), gap_index_m5+20)]
    trades_m5 = simulate_m5_strategy(df_m5_test, config_m5)
    total_profit_m5 = sum(t['profit'] for t in trades_m5)
    winning_m5 = [t for t in trades_m5 if t['profit'] > 0]
    
    print(f"   Period: {df_m5_test.iloc[0]['time']} to {df_m5_test.iloc[-1]['time']}")
    print(f"   Bars: {len(df_m5_test)}")
    print(f"   Trades: {len(trades_m5)}")
    print(f"   Winning: {len(winning_m5)}/{len(trades_m5)} ({len(winning_m5)/len(trades_m5)*100:.0f}%)" if trades_m5 else "   No trades")
    print(f"   Total P/L: ${total_profit_m5:.2f}")
    
    if trades_m5:
        for t in trades_m5[:5]:
            print(f"     {t['type']}: ${t['entry_price']:.2f} → ${t['exit_price']:.2f} = ${t['profit']:+.2f}")
        if len(trades_m5) > 5:
            print(f"     ... and {len(trades_m5)-5} more trades")
    
    # Trend Strategy - 150 minutes after gap
    print("\n3. TREND FOLLOWING STRATEGY (M15)")
    gap_index_m15 = None
    for i in range(1, len(df_m15)):
        time_diff = (df_m15.iloc[i]['time'] - df_m15.iloc[i-1]['time']).total_seconds() / 60
        if time_diff > 30:
            gap_index_m15 = i
            break
    if gap_index_m15 is None:
        gap_index_m15 = len(df_m15) - 10
    
    df_m15_test = df_m15.iloc[max(0, gap_index_m15-200):min(len(df_m15), gap_index_m15+10)]
    trades_trend = simulate_trend_strategy(df_m15_test)
    total_profit_trend = sum(t['profit'] for t in trades_trend)
    winning_trend = [t for t in trades_trend if t['profit'] > 0]
    
    print(f"   Period: {df_m15_test.iloc[0]['time']} to {df_m15_test.iloc[-1]['time']}")
    print(f"   Bars: {len(df_m15_test)}")
    print(f"   Trades: {len(trades_trend)}")
    print(f"   Winning: {len(winning_trend)}/{len(trades_trend)} ({len(winning_trend)/len(trades_trend)*100:.0f}%)" if trades_trend else "   No trades")
    print(f"   Total P/L: ${total_profit_trend:.2f}")
    
    if trades_trend:
        for t in trades_trend[:5]:
            print(f"     {t['type']}: ${t['entry_price']:.2f} → ${t['exit_price']:.2f} = ${t['profit']:+.2f}")
        if len(trades_trend) > 5:
            print(f"     ... and {len(trades_trend)-5} more trades")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\nStrategy Performance (from gap opening ~100 minutes):")
    print(f"  M1 Scalping:  ${total_profit_m1:+8.2f}  ({len(trades_m1)} trades)")
    print(f"  M5 Scalping:  ${total_profit_m5:+8.2f}  ({len(trades_m5)} trades)")
    print(f"  Trend (M15):  ${total_profit_trend:+8.2f}  ({len(trades_trend)} trades)")
    
    print(f"\nBest performer: ", end="")
    best = max([(total_profit_m1, "M1 Scalping"), 
                (total_profit_m5, "M5 Scalping"), 
                (total_profit_trend, "Trend Following")], 
               key=lambda x: x[0])
    print(f"{best[1]} (${best[0]:+.2f})")
    
    print(f"\nConclusion:")
    if total_profit_trend > total_profit_m1 and total_profit_trend > total_profit_m5:
        print("  ✓ Trend following strategy captured the gap move best")
        print("  → Recommendation: Run trend bot alongside M1 bot")
    elif total_profit_m1 > total_profit_m5:
        print("  ✓ M1 scalping performed better than M5")
        print("  → M1 bot is working well for this market")
    else:
        print("  → Results vary by strategy and market conditions")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
