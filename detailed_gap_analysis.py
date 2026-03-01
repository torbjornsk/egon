"""
Detailed analysis of the gap period from 01:00 MT5 time
Show minute-by-minute what happened and why M1 bot struggled
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
    """Detailed gap analysis"""
    print("="*100)
    print("DETAILED GAP ANALYSIS - Minute by Minute")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get current MT5 server time
    server_time = datetime.fromtimestamp(mt5.symbol_info_tick(symbol).time)
    today_0100 = server_time.replace(hour=1, minute=0, second=0, microsecond=0)
    
    if server_time.hour < 1:
        today_0100 = today_0100 - timedelta(days=1)
    
    # Fetch M1 data
    bars_needed = 400
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars_needed)
    
    if rates is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Check for actual trades
    print("\nChecking actual M1 bot trades...")
    from_date = today_0100 - timedelta(hours=1)
    deals = mt5.history_deals_get(from_date, server_time)
    
    actual_trades = []
    if deals:
        m1_deals = [d for d in deals if d.magic == 234001 and d.symbol == 'XAUUSD.p']
        if m1_deals:
            print(f"Found {len(m1_deals)} M1 bot deals")
            for deal in m1_deals:
                actual_trades.append({
                    'time': datetime.fromtimestamp(deal.time),
                    'type': 'BUY' if deal.type == mt5.DEAL_TYPE_BUY else 'SELL',
                    'price': deal.price,
                    'volume': deal.volume,
                    'profit': deal.profit
                })
        else:
            print("No M1 bot trades found (magic 234001)")
    
    mt5.shutdown()
    
    # Load M1 config
    config = load_config('config/m1_params.json')
    
    # Calculate indicators
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
    
    # Get data from 01:00 onwards
    analysis_df = df.iloc[closest_idx:closest_idx+120].copy()  # 2 hours
    analysis_df = analysis_df.reset_index(drop=True)
    
    print(f"\n" + "="*100)
    print(f"MINUTE-BY-MINUTE ANALYSIS FROM 01:00")
    print("="*100)
    
    print(f"\nM1 Bot Settings:")
    print(f"  LONG Entry:  RSI < {config['rsi_buy']}")
    print(f"  LONG Exit:   RSI > {config['rsi_exit_long']}")
    print(f"  SHORT Entry: RSI > {config['rsi_sell']} + downtrend")
    print(f"  SHORT Exit:  RSI < {config['rsi_exit_short']}")
    print(f"  Position Size: {config['position_size_pct']*100}% @ {config['leverage']}x leverage")
    print(f"  Warmup: 2 candles after gap")
    print(f"  Cooldown: 2 candles after exit")
    
    # Find the gap
    gap_idx = None
    for i in range(1, len(analysis_df)):
        time_diff = (analysis_df.iloc[i]['time'] - analysis_df.iloc[i-1]['time']).total_seconds() / 60
        if time_diff > 5:  # More than 5 minutes gap
            gap_idx = i
            break
    
    if gap_idx:
        print(f"\n⚠️  GAP DETECTED at index {gap_idx}")
        print(f"   Before gap: {analysis_df.iloc[gap_idx-1]['time']} @ ${analysis_df.iloc[gap_idx-1]['close']:.2f}")
        print(f"   After gap:  {analysis_df.iloc[gap_idx]['time']} @ ${analysis_df.iloc[gap_idx]['open']:.2f}")
        gap_size = analysis_df.iloc[gap_idx]['open'] - analysis_df.iloc[gap_idx-1]['close']
        print(f"   Gap size: ${gap_size:+.2f} ({(gap_size/analysis_df.iloc[gap_idx-1]['close'])*100:+.2f}%)")
    
    # Show first 60 minutes in detail
    print(f"\n" + "-"*100)
    print(f"{'Time':<10} {'Price':>8} {'RSI':>6} {'EMA':>6} {'Signal':<30} {'Action':<30}")
    print("-"*100)
    
    position = None
    warmup_until = (gap_idx + 2) if gap_idx else 2
    cooldown_until = 0
    trades = []
    
    for i in range(min(60, len(analysis_df))):
        row = analysis_df.iloc[i]
        
        time_str = row['time'].strftime('%H:%M')
        price = row['close']
        rsi = row['RSI']
        trend = "UP" if row['uptrend'] else "DN"
        
        signal = ""
        action = ""
        
        # Check if in warmup
        if i < warmup_until:
            signal = "[WARMUP]"
            action = "No trading"
        # Check if in cooldown
        elif i < cooldown_until:
            signal = "[COOLDOWN]"
            action = "No trading"
        # Check exit
        elif position:
            bars_held = i - position['entry_bar']
            current_profit = 0
            
            if position['type'] == 'LONG':
                current_profit = (price - position['entry_price']) * 100 * config['position_size_pct'] * config['leverage']
                
                if rsi > config['rsi_exit_long']:
                    signal = f"RSI > {config['rsi_exit_long']}"
                    action = f"EXIT LONG @ ${price:.2f}"
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['time'],
                        'type': 'LONG',
                        'entry_price': position['entry_price'],
                        'exit_price': price,
                        'profit': current_profit,
                        'duration': bars_held
                    })
                    
                    position = None
                    cooldown_until = i + 2
                elif current_profit < 0 and bars_held >= 10:
                    signal = f"10min stop loss"
                    action = f"EXIT LONG @ ${price:.2f}"
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['time'],
                        'type': 'LONG',
                        'entry_price': position['entry_price'],
                        'exit_price': price,
                        'profit': current_profit,
                        'duration': bars_held
                    })
                    
                    position = None
                    cooldown_until = i + 2
                else:
                    signal = f"Holding ({bars_held}min)"
                    action = f"P/L: ${current_profit:+.2f}"
            else:  # SHORT
                current_profit = (position['entry_price'] - price) * 100 * config['position_size_pct'] * config['leverage']
                
                if rsi < config['rsi_exit_short']:
                    signal = f"RSI < {config['rsi_exit_short']}"
                    action = f"EXIT SHORT @ ${price:.2f}"
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['time'],
                        'type': 'SHORT',
                        'entry_price': position['entry_price'],
                        'exit_price': price,
                        'profit': current_profit,
                        'duration': bars_held
                    })
                    
                    position = None
                    cooldown_until = i + 2
                elif current_profit < 0 and bars_held >= 10:
                    signal = f"10min stop loss"
                    action = f"EXIT SHORT @ ${price:.2f}"
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['time'],
                        'type': 'SHORT',
                        'entry_price': position['entry_price'],
                        'exit_price': price,
                        'profit': current_profit,
                        'duration': bars_held
                    })
                    
                    position = None
                    cooldown_until = i + 2
                else:
                    signal = f"Holding ({bars_held}min)"
                    action = f"P/L: ${current_profit:+.2f}"
        # Check entry
        elif not position and i >= cooldown_until:
            if rsi < config['rsi_buy']:
                signal = f"RSI < {config['rsi_buy']} ✓"
                action = f"ENTER LONG @ ${price:.2f}"
                
                position = {
                    'type': 'LONG',
                    'entry_time': row['time'],
                    'entry_price': price,
                    'entry_bar': i
                }
            elif config.get('enable_shorts', False) and rsi > config['rsi_sell'] and row['downtrend']:
                signal = f"RSI > {config['rsi_sell']} + DN ✓"
                action = f"ENTER SHORT @ ${price:.2f}"
                
                position = {
                    'type': 'SHORT',
                    'entry_time': row['time'],
                    'entry_price': price,
                    'entry_bar': i
                }
            else:
                signal = f"No signal"
                action = ""
        
        # Print row
        if pd.notna(rsi):
            print(f"{time_str:<10} ${price:7.2f} {rsi:6.1f} {trend:>6} {signal:<30} {action:<30}")
        else:
            print(f"{time_str:<10} ${price:7.2f} {'--':>6} {trend:>6} {signal:<30} {action:<30}")
    
    # Summary
    print(f"\n" + "="*100)
    print("SIMULATION SUMMARY")
    print("="*100)
    
    if len(trades) == 0:
        print(f"\n❌ NO TRADES COMPLETED")
    else:
        total_profit = sum(t['profit'] for t in trades)
        winning = sum(1 for t in trades if t['profit'] > 0)
        
        print(f"\nTrades: {len(trades)}")
        print(f"Winning: {winning}/{len(trades)} ({winning/len(trades)*100:.0f}%)")
        print(f"Total P/L: ${total_profit:+.2f}")
        
        print(f"\nTrade Details:")
        for i, t in enumerate(trades, 1):
            print(f"\n{i}. {t['type']} Trade")
            print(f"   Entry:  {t['entry_time'].strftime('%H:%M')} @ ${t['entry_price']:.2f}")
            print(f"   Exit:   {t['exit_time'].strftime('%H:%M')} @ ${t['exit_price']:.2f}")
            print(f"   Duration: {t['duration']} minutes")
            print(f"   Profit: ${t['profit']:+.2f}")
    
    if position:
        print(f"\n⚠️  OPEN POSITION:")
        print(f"   Type: {position['type']}")
        print(f"   Entry: {position['entry_time'].strftime('%H:%M')} @ ${position['entry_price']:.2f}")
    
    # Compare with actual trades
    if actual_trades:
        print(f"\n" + "="*100)
        print("ACTUAL BOT TRADES (from MT5 history)")
        print("="*100)
        for i, t in enumerate(actual_trades, 1):
            print(f"\n{i}. {t['type']} @ {t['time'].strftime('%H:%M:%S')}")
            print(f"   Price: ${t['price']:.2f}")
            print(f"   Volume: {t['volume']}")
            print(f"   Profit: ${t['profit']:+.2f}")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
