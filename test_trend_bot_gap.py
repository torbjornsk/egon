"""
Test Trend Following Bot on Gap Period
Simulate trend bot from 01:00 MT5 time onwards
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))

def load_config(path):
    """Load strategy config"""
    with open(path, 'r') as f:
        return json.load(f)

def calculate_indicators(df):
    """Calculate trend following indicators"""
    df = df.copy()
    
    # EMAs
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(14).mean()
    
    # ADX
    df = calculate_adx(df)
    
    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    return df

def calculate_adx(df, period=14):
    """Calculate ADX"""
    high_diff = df['high'].diff()
    low_diff = -df['low'].diff()
    
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
    
    atr = df['atr']
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(period).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    
    return df

def get_h4_trend(df_h4):
    """Determine H4 trend"""
    last = df_h4.iloc[-1]
    
    ema_uptrend = last['ema_50'] > last['ema_200']
    ema_downtrend = last['ema_50'] < last['ema_200']
    strong_trend = last['adx'] > 25
    
    if ema_uptrend and strong_trend:
        return 'UPTREND'
    elif ema_downtrend and strong_trend:
        return 'DOWNTREND'
    else:
        return 'NO_TREND'

def check_entry_signal(row, h4_trend, config):
    """Check if there's an entry signal"""
    if h4_trend == 'NO_TREND':
        return None
    
    if h4_trend == 'UPTREND':
        # Pullback to EMA 20
        pullback = row['close'] <= row['ema_20'] * 1.002
        
        # RSI in range
        rsi_ok = (row['rsi'] >= config.get('rsi_min', 40)) and \
                 (row['rsi'] <= config.get('rsi_max', 60))
        
        # Price above EMA 50
        h1_uptrend = row['close'] > row['ema_50']
        
        if pullback and rsi_ok and h1_uptrend:
            return 'LONG'
    
    elif h4_trend == 'DOWNTREND':
        # Pullback to EMA 20
        pullback = row['close'] >= row['ema_20'] * 0.998
        
        # RSI in range
        rsi_ok = (row['rsi'] >= config.get('rsi_min', 40)) and \
                 (row['rsi'] <= config.get('rsi_max', 60))
        
        # Price below EMA 50
        h1_downtrend = row['close'] < row['ema_50']
        
        if pullback and rsi_ok and h1_downtrend:
            return 'SHORT'
    
    return None

def simulate_trend_bot(df_h1, df_h4, config, start_idx=0):
    """Simulate trend bot trading"""
    trades = []
    position = None
    
    # Get H4 trend at start
    h4_trend = get_h4_trend(df_h4)
    
    print(f"\nH4 Trend at start: {h4_trend}")
    if h4_trend != 'NO_TREND':
        last_h4 = df_h4.iloc[-1]
        print(f"  EMA 50: ${last_h4['ema_50']:.2f}")
        print(f"  EMA 200: ${last_h4['ema_200']:.2f}")
        print(f"  ADX: {last_h4['adx']:.1f}")
    
    for i in range(start_idx, len(df_h1)):
        row = df_h1.iloc[i]
        
        # Skip if indicators not ready
        if pd.isna(row['rsi']) or pd.isna(row['atr']):
            continue
        
        # Check exit first
        if position:
            should_exit = False
            exit_reason = None
            
            # Calculate trailing stop
            atr = row['atr']
            trail_distance = atr * config.get('atr_multiplier', 2.0)
            
            if position['type'] == 'LONG':
                # Update trailing stop
                profit_pct = (row['close'] - position['entry_price']) / position['entry_price']
                
                if profit_pct >= 0.05:
                    # Lock in 50% of profit
                    min_profit_lock = position['entry_price'] + (row['close'] - position['entry_price']) * 0.5
                    trailing_stop = max(position['trailing_stop'], row['close'] - trail_distance, min_profit_lock)
                else:
                    trailing_stop = max(position['trailing_stop'], row['close'] - trail_distance)
                
                position['trailing_stop'] = trailing_stop
                
                # Check if stop hit
                if row['low'] <= trailing_stop:
                    should_exit = True
                    exit_reason = f"Trailing stop @ ${trailing_stop:.2f}"
                    exit_price = trailing_stop
                
            else:  # SHORT
                # Update trailing stop
                profit_pct = (position['entry_price'] - row['close']) / position['entry_price']
                
                if profit_pct >= 0.05:
                    # Lock in 50% of profit
                    min_profit_lock = position['entry_price'] - (position['entry_price'] - row['close']) * 0.5
                    trailing_stop = min(position['trailing_stop'], row['close'] + trail_distance, min_profit_lock)
                else:
                    trailing_stop = min(position['trailing_stop'], row['close'] + trail_distance)
                
                position['trailing_stop'] = trailing_stop
                
                # Check if stop hit
                if row['high'] >= trailing_stop:
                    should_exit = True
                    exit_reason = f"Trailing stop @ ${trailing_stop:.2f}"
                    exit_price = trailing_stop
            
            # Check trend reversal
            if not should_exit:
                if position['type'] == 'LONG' and h4_trend == 'DOWNTREND':
                    should_exit = True
                    exit_reason = "H4 trend reversed"
                    exit_price = row['close']
                elif position['type'] == 'SHORT' and h4_trend == 'UPTREND':
                    should_exit = True
                    exit_reason = "H4 trend reversed"
                    exit_price = row['close']
            
            if should_exit:
                # Calculate profit
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
                    'profit': profit,
                    'exit_reason': exit_reason,
                    'bars_held': i - position['entry_bar']
                })
                
                position = None
        
        # Check entry
        if not position:
            signal = check_entry_signal(row, h4_trend, config)
            
            if signal:
                atr = row['atr']
                sl_distance = atr * config.get('atr_multiplier', 2.0)
                
                if signal == 'LONG':
                    trailing_stop = row['close'] - sl_distance
                else:
                    trailing_stop = row['close'] + sl_distance
                
                position = {
                    'type': signal,
                    'entry_time': row['time'],
                    'entry_price': row['close'],
                    'entry_bar': i,
                    'trailing_stop': trailing_stop
                }
    
    return trades, position

def main():
    """Test trend bot on gap period"""
    print("="*80)
    print("TREND BOT BACKTEST - Gap Period (01:00 MT5 onwards)")
    print("="*80)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get current time
    server_time = datetime.fromtimestamp(mt5.symbol_info_tick(symbol).time)
    today_0100 = server_time.replace(hour=1, minute=0, second=0, microsecond=0)
    
    if server_time.hour < 1:
        today_0100 = today_0100 - timedelta(days=1)
    
    print(f"\nCurrent MT5 time: {server_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Analysis from: {today_0100.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Fetch H1 data (trend bot uses H1 for entries)
    print(f"\nFetching H1 data...")
    h1_bars = 300
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, h1_bars)
    
    if rates_h1 is None:
        print("Failed to get H1 data")
        mt5.shutdown()
        return
    
    df_h1 = pd.DataFrame(rates_h1)
    df_h1['time'] = pd.to_datetime(df_h1['time'], unit='s')
    
    # Fetch H4 data (for trend direction)
    print(f"Fetching H4 data...")
    rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 250)
    
    if rates_h4 is None:
        print("Failed to get H4 data")
        mt5.shutdown()
        return
    
    df_h4 = pd.DataFrame(rates_h4)
    df_h4['time'] = pd.to_datetime(df_h4['time'], unit='s')
    
    mt5.shutdown()
    
    # Load config
    config = load_config('config/trend_params.json')
    
    print(f"\nTrend Bot Settings:")
    print(f"  Position Size: {config['position_size_pct']*100}% @ {config['leverage']}x")
    print(f"  ATR Multiplier: {config['atr_multiplier']}x")
    print(f"  RSI Range: {config['rsi_min']}-{config['rsi_max']}")
    print(f"  ADX Threshold: {config['adx_threshold']}")
    
    # Calculate indicators
    print(f"\nCalculating indicators...")
    df_h1 = calculate_indicators(df_h1)
    df_h4 = calculate_indicators(df_h4)
    
    # Find 01:00 in H1 data
    target_time = today_0100
    closest_idx = None
    min_diff = float('inf')
    
    for i, row in df_h1.iterrows():
        time_diff = abs((row['time'] - target_time).total_seconds())
        if time_diff < min_diff:
            min_diff = time_diff
            closest_idx = i
    
    if closest_idx is None:
        print("Could not find 01:00 in data")
        return
    
    print(f"Found 01:00 at index {closest_idx}: {df_h1.iloc[closest_idx]['time']}")
    
    # Run simulation from 01:00
    print(f"\n" + "="*80)
    print("SIMULATION RESULTS")
    print("="*80)
    
    trades, open_position = simulate_trend_bot(df_h1, df_h4, config, start_idx=closest_idx)
    
    if len(trades) == 0 and not open_position:
        print(f"\n❌ NO TRADES")
        print(f"\nReasons:")
        
        # Check H4 trend
        h4_trend = get_h4_trend(df_h4)
        print(f"  H4 Trend: {h4_trend}")
        
        if h4_trend == 'NO_TREND':
            print(f"  → No clear H4 trend (ADX < 25 or EMAs not aligned)")
        else:
            # Check H1 conditions
            analysis_df = df_h1.iloc[closest_idx:].copy()
            
            # Count potential signals
            if h4_trend == 'UPTREND':
                pullbacks = (analysis_df['close'] <= analysis_df['ema_20'] * 1.002).sum()
                rsi_ok = ((analysis_df['rsi'] >= 40) & (analysis_df['rsi'] <= 60)).sum()
                h1_uptrend = (analysis_df['close'] > analysis_df['ema_50']).sum()
                
                print(f"  → Looking for LONG entries (H4 uptrend)")
                print(f"     Pullbacks to EMA20: {pullbacks}/{len(analysis_df)}")
                print(f"     RSI 40-60: {rsi_ok}/{len(analysis_df)}")
                print(f"     H1 uptrend: {h1_uptrend}/{len(analysis_df)}")
            else:
                pullbacks = (analysis_df['close'] >= analysis_df['ema_20'] * 0.998).sum()
                rsi_ok = ((analysis_df['rsi'] >= 40) & (analysis_df['rsi'] <= 60)).sum()
                h1_downtrend = (analysis_df['close'] < analysis_df['ema_50']).sum()
                
                print(f"  → Looking for SHORT entries (H4 downtrend)")
                print(f"     Pullbacks to EMA20: {pullbacks}/{len(analysis_df)}")
                print(f"     RSI 40-60: {rsi_ok}/{len(analysis_df)}")
                print(f"     H1 downtrend: {h1_downtrend}/{len(analysis_df)}")
    
    else:
        if trades:
            print(f"\n✓ Executed {len(trades)} trades")
            
            total_profit = 0
            winning = 0
            
            for i, t in enumerate(trades, 1):
                total_profit += t['profit']
                if t['profit'] > 0:
                    winning += 1
                
                print(f"\n{i}. {t['type']} Trade")
                print(f"   Entry:  {t['entry_time'].strftime('%Y-%m-%d %H:%M')} @ ${t['entry_price']:.2f}")
                print(f"   Exit:   {t['exit_time'].strftime('%Y-%m-%d %H:%M')} @ ${t['exit_price']:.2f}")
                print(f"   Duration: {t['bars_held']} hours")
                print(f"   Exit Reason: {t['exit_reason']}")
                print(f"   Profit: ${t['profit']:+.2f}")
            
            print(f"\n" + "-"*80)
            print(f"Summary:")
            print(f"  Total Trades: {len(trades)}")
            print(f"  Winning: {winning}/{len(trades)} ({winning/len(trades)*100:.0f}%)")
            print(f"  Total P/L: ${total_profit:+.2f}")
        
        if open_position:
            print(f"\n⚠️  OPEN POSITION:")
            print(f"   Type: {open_position['type']}")
            print(f"   Entry: {open_position['entry_time'].strftime('%Y-%m-%d %H:%M')} @ ${open_position['entry_price']:.2f}")
            print(f"   Trailing Stop: ${open_position['trailing_stop']:.2f}")
            
            # Calculate current P/L
            current_price = df_h1.iloc[-1]['close']
            if open_position['type'] == 'LONG':
                current_profit = (current_price - open_position['entry_price']) * 100 * config['position_size_pct'] * config['leverage']
            else:
                current_profit = (open_position['entry_price'] - current_price) * 100 * config['position_size_pct'] * config['leverage']
            
            print(f"   Current Price: ${current_price:.2f}")
            print(f"   Current P/L: ${current_profit:+.2f}")
    
    print(f"\n" + "="*80)
    print("COMPARISON WITH M1 BOT")
    print("="*80)
    print(f"\nM1 Bot (mean reversion):")
    print(f"  Period 01:00-02:00: Avoided trading (gap warmup)")
    print(f"  Period 02:18-02:50: +$75.04 (5 trades, 80% win rate)")
    
    if trades:
        total_profit = sum(t['profit'] for t in trades)
        print(f"\nTrend Bot (trend following):")
        print(f"  Period 01:00-now: ${total_profit:+.2f} ({len(trades)} trades)")
        
        if total_profit > 75:
            print(f"\n✓ Trend bot captured the gap move better (+${total_profit-75:.2f})")
        else:
            print(f"\n→ M1 bot performed better for this period")
    else:
        print(f"\nTrend Bot (trend following):")
        print(f"  Period 01:00-now: No trades")
        print(f"\n→ M1 bot performed better (trend bot had no valid signals)")
    
    print(f"\n" + "="*80)

if __name__ == "__main__":
    main()
