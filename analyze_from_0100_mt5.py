"""
Analyze trading period from 01:00 MT5 time (GMT+2) until now
Check what opportunities existed and what the bots could have done
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def load_config(path):
    """Load strategy config"""
    with open(path, 'r') as f:
        return json.load(f)

def calculate_indicators(df, config):
    """Calculate trading indicators"""
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

def main():
    """Analyze from 01:00 MT5 time until now"""
    print("="*80)
    print("ANALYSIS FROM 01:00 MT5 TIME (GMT+2) UNTIL NOW")
    print("="*80)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get current MT5 server time
    server_time = datetime.fromtimestamp(mt5.symbol_info_tick(symbol).time)
    print(f"\nCurrent MT5 server time: {server_time.strftime('%Y-%m-%d %H:%M:%S')} (GMT+2)")
    
    # Calculate time from 01:00 today
    today_0100 = server_time.replace(hour=1, minute=0, second=0, microsecond=0)
    
    # If current time is before 01:00, use yesterday's 01:00
    if server_time.hour < 1:
        today_0100 = today_0100 - timedelta(days=1)
    
    print(f"Analysis start time: {today_0100.strftime('%Y-%m-%d %H:%M:%S')} (GMT+2)")
    
    # Calculate how many minutes from 01:00 to now
    minutes_elapsed = int((server_time - today_0100).total_seconds() / 60)
    print(f"Minutes elapsed: {minutes_elapsed}")
    
    # Fetch M1 data (need extra for indicators)
    print(f"\nFetching M1 data...")
    bars_needed = minutes_elapsed + 200  # Extra for indicators
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars_needed)
    
    if rates is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    mt5.shutdown()
    
    # Load M1 config
    config = load_config('config/m1_params.json')
    
    # Calculate indicators
    print("Calculating indicators...")
    df = calculate_indicators(df, config)
    
    # Find the 01:00 candle
    target_time = today_0100
    closest_idx = None
    min_diff = float('inf')
    
    for i, row in df.iterrows():
        time_diff = abs((row['time'] - target_time).total_seconds())
        if time_diff < min_diff:
            min_diff = time_diff
            closest_idx = i
    
    if closest_idx is None:
        print("Could not find 01:00 candle")
        return
    
    print(f"Found closest candle to 01:00: {df.iloc[closest_idx]['time']}")
    
    # Analyze from 01:00 onwards
    analysis_df = df.iloc[closest_idx:].copy()
    analysis_df = analysis_df.reset_index(drop=True)
    
    print(f"\n" + "="*80)
    print(f"PERIOD ANALYSIS: {analysis_df.iloc[0]['time']} to {analysis_df.iloc[-1]['time']}")
    print("="*80)
    
    # Price action summary
    start_price = analysis_df.iloc[0]['open']
    end_price = analysis_df.iloc[-1]['close']
    highest = analysis_df['high'].max()
    lowest = analysis_df['low'].min()
    
    print(f"\nPrice Action:")
    print(f"  Start (01:00): ${start_price:.2f}")
    print(f"  Current:       ${end_price:.2f} ({end_price-start_price:+.2f}, {((end_price-start_price)/start_price)*100:+.2f}%)")
    print(f"  Highest:       ${highest:.2f} (+${highest-start_price:.2f}, +{((highest-start_price)/start_price)*100:.2f}%)")
    print(f"  Lowest:        ${lowest:.2f} (${lowest-start_price:.2f}, {((lowest-start_price)/start_price)*100:.2f}%)")
    
    # RSI analysis
    rsi_values = analysis_df['RSI'].dropna()
    
    print(f"\nRSI Statistics:")
    print(f"  Min:    {rsi_values.min():.1f}")
    print(f"  Max:    {rsi_values.max():.1f}")
    print(f"  Mean:   {rsi_values.mean():.1f}")
    print(f"  Median: {rsi_values.median():.1f}")
    
    # M1 Bot Entry Signals
    print(f"\n" + "-"*80)
    print(f"M1 BOT ENTRY SIGNALS (RSI < {config['rsi_buy']} for LONG)")
    print("-"*80)
    
    long_signals = analysis_df[analysis_df['RSI'] < config['rsi_buy']].copy()
    
    if len(long_signals) == 0:
        print(f"\n❌ NO LONG SIGNALS")
        print(f"   RSI never dropped below {config['rsi_buy']}")
        print(f"   Minimum RSI was {rsi_values.min():.1f}")
        print(f"   Gap up kept price overbought")
    else:
        print(f"\n✓ Found {len(long_signals)} LONG entry signals")
        print(f"\nFirst 10 signals:")
        for i, (idx, row) in enumerate(long_signals.head(10).iterrows()):
            print(f"  {i+1}. {row['time'].strftime('%H:%M:%S')} | "
                  f"Price: ${row['close']:7.2f} | RSI: {row['RSI']:5.1f}")
        
        if len(long_signals) > 10:
            print(f"  ... and {len(long_signals)-10} more signals")
    
    # Check for SHORT signals
    short_signals = analysis_df[
        (analysis_df['RSI'] > config['rsi_sell']) & 
        (analysis_df['downtrend'] == True)
    ].copy()
    
    if len(short_signals) > 0:
        print(f"\n✓ Found {len(short_signals)} SHORT entry signals (RSI > {config['rsi_sell']} + downtrend)")
    
    # Simulate M1 strategy
    print(f"\n" + "="*80)
    print("M1 BOT SIMULATION")
    print("="*80)
    
    trades = []
    position = None
    warmup_until = 2  # Skip first 2 candles for warmup
    cooldown_until = 0
    
    for i in range(len(analysis_df)):
        row = analysis_df.iloc[i]
        
        # Skip warmup
        if i < warmup_until:
            continue
        
        # Skip cooldown
        if i < cooldown_until:
            continue
        
        # Check exit first
        if position:
            should_exit = False
            bars_held = i - position['entry_bar']
            
            # RSI exits
            if position['type'] == 'LONG':
                if row['RSI'] > config['rsi_exit_long']:
                    should_exit = True
            else:
                if row['RSI'] < config['rsi_exit_short']:
                    should_exit = True
            
            # Time-based exit for losing positions
            if position['profit'] < 0 and bars_held >= 10:
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
                    'profit': profit,
                    'duration': bars_held
                })
                
                position = None
                cooldown_until = i + 2  # 2-candle cooldown
        
        # Check entry
        if not position and i >= cooldown_until:
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
    
    # Results
    if len(trades) == 0:
        print(f"\n❌ NO TRADES EXECUTED")
        print(f"\nReasons:")
        print(f"  - No RSI signals below {config['rsi_buy']} (after warmup)")
        print(f"  - Gap up pushed RSI too high")
        print(f"  - Price kept trending up (not oversold)")
    else:
        print(f"\n✓ Executed {len(trades)} trades")
        print(f"\nTrade Details:")
        
        total_profit = 0
        winning = 0
        
        for i, t in enumerate(trades, 1):
            total_profit += t['profit']
            if t['profit'] > 0:
                winning += 1
            
            print(f"\n{i}. {t['type']} Trade")
            print(f"   Entry:  {t['entry_time'].strftime('%H:%M:%S')} @ ${t['entry_price']:.2f}")
            print(f"   Exit:   {t['exit_time'].strftime('%H:%M:%S')} @ ${t['exit_price']:.2f}")
            print(f"   Duration: {t['duration']} minutes")
            print(f"   Profit: ${t['profit']:+.2f}")
        
        print(f"\n" + "-"*80)
        print(f"Summary:")
        print(f"  Total Trades: {len(trades)}")
        print(f"  Winning: {winning}/{len(trades)} ({winning/len(trades)*100:.0f}%)")
        print(f"  Total P/L: ${total_profit:+.2f}")
    
    # Check if there's an open position
    if position:
        print(f"\n⚠️  OPEN POSITION:")
        print(f"   Type: {position['type']}")
        print(f"   Entry: {position['entry_time'].strftime('%H:%M:%S')} @ ${position['entry_price']:.2f}")
        print(f"   Current P/L: ${position['profit']:+.2f}")
    
    print(f"\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    
    if len(trades) == 0 and len(long_signals) == 0:
        print(f"\nM1 bot correctly did NOT trade:")
        print(f"  ✓ No valid entry signals (RSI stayed above {config['rsi_buy']})")
        print(f"  ✓ Gap up created strong uptrend")
        print(f"  ✓ Mean-reversion strategy avoided chasing the move")
        print(f"\nTo capitalize on such moves, you need:")
        print(f"  → Trend-following strategy (not mean reversion)")
        print(f"  → Gap detection with momentum confirmation")
        print(f"  → Breakout strategy for strong trending moves")
    elif len(trades) > 0:
        total_profit = sum(t['profit'] for t in trades)
        if total_profit > 0:
            print(f"\n✓ M1 bot would have profited: ${total_profit:+.2f}")
        else:
            print(f"\n⚠️  M1 bot would have lost: ${total_profit:+.2f}")
            print(f"   Strategy not suited for this type of move")
    
    print(f"\n" + "="*80)

if __name__ == "__main__":
    main()
