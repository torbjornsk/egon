"""
Analyze bot performance from 01:00 to 12:30 MT5 time
Fetch actual trades and compare with what should have happened
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

def get_actual_trades(from_time, to_time, magic_number, symbol='XAUUSD.p'):
    """Get actual trades from MT5"""
    deals = mt5.history_deals_get(from_time, to_time)
    
    if deals is None or len(deals) == 0:
        return []
    
    # Filter for this bot and symbol
    bot_deals = [d for d in deals if d.magic == magic_number and d.symbol == symbol]
    
    # Group into trades (entry + exit)
    trades = []
    positions = {}
    
    for deal in sorted(bot_deals, key=lambda x: x.time):
        pos_id = deal.position_id
        
        if pos_id not in positions:
            # Opening deal
            positions[pos_id] = {
                'entry_time': datetime.fromtimestamp(deal.time),
                'entry_price': deal.price,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'volume': deal.volume,
                'ticket': deal.ticket
            }
        else:
            # Closing deal
            entry = positions[pos_id]
            exit_time = datetime.fromtimestamp(deal.time)
            exit_price = deal.price
            profit = deal.profit
            
            trades.append({
                'entry_time': entry['entry_time'],
                'exit_time': exit_time,
                'type': entry['type'],
                'entry_price': entry['entry_price'],
                'exit_price': exit_price,
                'volume': entry['volume'],
                'profit': profit,
                'duration_min': (exit_time - entry['entry_time']).total_seconds() / 60,
                'ticket': entry['ticket']
            })
            
            del positions[pos_id]
    
    # Check for open positions
    open_positions = []
    for pos_id, pos in positions.items():
        open_positions.append(pos)
    
    return trades, open_positions

def main():
    """Analyze today's performance"""
    print("="*100)
    print("BOT PERFORMANCE ANALYSIS: 01:00 - 12:30 MT5 TIME")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get current MT5 time
    tick = mt5.symbol_info_tick(symbol)
    current_time = datetime.fromtimestamp(tick.time)
    
    # Set time range (01:00 to 12:30 today)
    today_0100 = current_time.replace(hour=1, minute=0, second=0, microsecond=0)
    today_1230 = current_time.replace(hour=12, minute=30, second=0, microsecond=0)
    
    # If current time is before 01:00, use yesterday
    if current_time.hour < 1:
        today_0100 = today_0100 - timedelta(days=1)
        today_1230 = today_1230 - timedelta(days=1)
    
    print(f"\nCurrent MT5 time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Analysis period: {today_0100.strftime('%Y-%m-%d %H:%M')} to {today_1230.strftime('%Y-%m-%d %H:%M')}")
    
    # Get account info
    account = mt5.account_info()
    if account:
        print(f"\nAccount Info:")
        print(f"  Balance: ${account.balance:.2f}")
        print(f"  Equity: ${account.equity:.2f}")
        print(f"  Profit: ${account.profit:.2f}")
    
    # Fetch M1 trades
    print(f"\n" + "="*100)
    print("M1 BOT TRADES (Magic 234001)")
    print("="*100)
    
    m1_trades, m1_open = get_actual_trades(today_0100, today_1230, 234001, symbol)
    
    if len(m1_trades) == 0 and len(m1_open) == 0:
        print("\n❌ NO M1 TRADES FOUND")
    else:
        if m1_trades:
            print(f"\nCompleted Trades: {len(m1_trades)}")
            print("-"*100)
            
            total_profit = 0
            winning = 0
            
            for i, t in enumerate(m1_trades, 1):
                total_profit += t['profit']
                if t['profit'] > 0:
                    winning += 1
                
                print(f"\n{i}. {t['type']} Trade (Ticket {t['ticket']})")
                print(f"   Entry:  {t['entry_time'].strftime('%H:%M:%S')} @ ${t['entry_price']:.2f}")
                print(f"   Exit:   {t['exit_time'].strftime('%H:%M:%S')} @ ${t['exit_price']:.2f}")
                print(f"   Duration: {t['duration_min']:.1f} minutes")
                print(f"   Volume: {t['volume']} lots")
                print(f"   Profit: ${t['profit']:+.2f}")
            
            print(f"\n" + "-"*100)
            print(f"Summary:")
            print(f"  Total Trades: {len(m1_trades)}")
            print(f"  Winning: {winning}/{len(m1_trades)} ({winning/len(m1_trades)*100:.0f}%)")
            print(f"  Total P/L: ${total_profit:+.2f}")
        
        if m1_open:
            print(f"\n⚠️  Open Positions: {len(m1_open)}")
            for pos in m1_open:
                print(f"   {pos['type']} @ ${pos['entry_price']:.2f} (opened {pos['entry_time'].strftime('%H:%M:%S')})")
    
    # Fetch M5 trades
    print(f"\n" + "="*100)
    print("M5 BOT TRADES (Magic 234000)")
    print("="*100)
    
    m5_trades, m5_open = get_actual_trades(today_0100, today_1230, 234000, symbol)
    
    if len(m5_trades) == 0 and len(m5_open) == 0:
        print("\n❌ NO M5 TRADES FOUND")
    else:
        if m5_trades:
            print(f"\nCompleted Trades: {len(m5_trades)}")
            print("-"*100)
            
            total_profit = 0
            winning = 0
            
            for i, t in enumerate(m5_trades, 1):
                total_profit += t['profit']
                if t['profit'] > 0:
                    winning += 1
                
                print(f"\n{i}. {t['type']} Trade (Ticket {t['ticket']})")
                print(f"   Entry:  {t['entry_time'].strftime('%H:%M:%S')} @ ${t['entry_price']:.2f}")
                print(f"   Exit:   {t['exit_time'].strftime('%H:%M:%S')} @ ${t['exit_price']:.2f}")
                print(f"   Duration: {t['duration_min']:.1f} minutes")
                print(f"   Volume: {t['volume']} lots")
                print(f"   Profit: ${t['profit']:+.2f}")
            
            print(f"\n" + "-"*100)
            print(f"Summary:")
            print(f"  Total Trades: {len(m5_trades)}")
            print(f"  Winning: {winning}/{len(m5_trades)} ({winning/len(m5_trades)*100:.0f}%)")
            print(f"  Total P/L: ${total_profit:+.2f}")
        
        if m5_open:
            print(f"\n⚠️  Open Positions: {len(m5_open)}")
            for pos in m5_open:
                print(f"   {pos['type']} @ ${pos['entry_price']:.2f} (opened {pos['entry_time'].strftime('%H:%M:%S')})")
    
    # Analyze market conditions
    print(f"\n" + "="*100)
    print("MARKET CONDITIONS ANALYSIS")
    print("="*100)
    
    # Get M1 data
    print(f"\nFetching M1 data...")
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
            
            # Analyze period
            analysis_df = df_m1.iloc[closest_idx:].copy()
            
            print(f"\nM1 Market Conditions (01:00 - 12:30):")
            print(f"  Bars analyzed: {len(analysis_df)}")
            
            # Price action
            start_price = analysis_df.iloc[0]['open']
            end_price = analysis_df.iloc[-1]['close']
            highest = analysis_df['high'].max()
            lowest = analysis_df['low'].min()
            
            print(f"\n  Price Action:")
            print(f"    Start: ${start_price:.2f}")
            print(f"    End: ${end_price:.2f} ({end_price-start_price:+.2f}, {((end_price-start_price)/start_price)*100:+.2f}%)")
            print(f"    High: ${highest:.2f} (+${highest-start_price:.2f})")
            print(f"    Low: ${lowest:.2f} (${lowest-start_price:.2f})")
            
            # RSI analysis
            rsi_values = analysis_df['RSI'].dropna()
            
            print(f"\n  RSI Statistics:")
            print(f"    Min: {rsi_values.min():.1f}")
            print(f"    Max: {rsi_values.max():.1f}")
            print(f"    Mean: {rsi_values.mean():.1f}")
            print(f"    Median: {rsi_values.median():.1f}")
            
            # Count signals
            long_signals = (rsi_values < m1_config['rsi_buy']).sum()
            short_signals = (rsi_values > m1_config['rsi_sell']).sum()
            
            print(f"\n  M1 Entry Signals:")
            print(f"    LONG signals (RSI < {m1_config['rsi_buy']}): {long_signals} candles")
            print(f"    SHORT signals (RSI > {m1_config['rsi_sell']}): {short_signals} candles")
            
            if long_signals == 0 and short_signals == 0:
                print(f"\n  ⚠️  NO ENTRY SIGNALS - RSI stayed in neutral zone")
            elif len(m1_trades) == 0:
                print(f"\n  ⚠️  SIGNALS PRESENT BUT NO TRADES - Check bot status")
    
    # Get M5 data
    print(f"\nFetching M5 data...")
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
            
            # Analyze period
            analysis_df = df_m5.iloc[closest_idx:].copy()
            
            print(f"\nM5 Market Conditions (01:00 - 12:30):")
            print(f"  Bars analyzed: {len(analysis_df)}")
            
            # RSI analysis
            rsi_values = analysis_df['RSI'].dropna()
            
            print(f"\n  RSI Statistics:")
            print(f"    Min: {rsi_values.min():.1f}")
            print(f"    Max: {rsi_values.max():.1f}")
            print(f"    Mean: {rsi_values.mean():.1f}")
            print(f"    Median: {rsi_values.median():.1f}")
            
            # Count signals
            long_signals = (rsi_values < m5_config['rsi_buy']).sum()
            short_signals = (rsi_values > m5_config['rsi_sell']).sum()
            
            print(f"\n  M5 Entry Signals:")
            print(f"    LONG signals (RSI < {m5_config['rsi_buy']}): {long_signals} candles")
            print(f"    SHORT signals (RSI > {m5_config['rsi_sell']}): {short_signals} candles")
            
            if long_signals == 0 and short_signals == 0:
                print(f"\n  ⚠️  NO ENTRY SIGNALS - RSI stayed in neutral zone")
            elif len(m5_trades) == 0:
                print(f"\n  ⚠️  SIGNALS PRESENT BUT NO TRADES - Check bot status")
    
    mt5.shutdown()
    
    # Summary
    print(f"\n" + "="*100)
    print("SUMMARY")
    print("="*100)
    
    m1_total = sum(t['profit'] for t in m1_trades) if m1_trades else 0
    m5_total = sum(t['profit'] for t in m5_trades) if m5_trades else 0
    combined_total = m1_total + m5_total
    
    print(f"\nPeriod: 01:00 - 12:30 MT5 time ({minutes_elapsed} minutes)")
    print(f"\nM1 Bot: {len(m1_trades)} trades, ${m1_total:+.2f}")
    print(f"M5 Bot: {len(m5_trades)} trades, ${m5_total:+.2f}")
    print(f"Combined: ${combined_total:+.2f}")
    
    if combined_total < 0:
        print(f"\n⚠️  NEGATIVE PERFORMANCE")
        print(f"\nPossible reasons:")
        print(f"  1. Strong trending market (mean reversion struggles)")
        print(f"  2. High volatility (stops hit frequently)")
        print(f"  3. Choppy/ranging market (whipsaws)")
        print(f"  4. Gap period (bots in warmup)")
        print(f"\nCheck:")
        print(f"  - Are bots running?")
        print(f"  - Any error messages in logs?")
        print(f"  - Market conditions suitable for strategy?")
    elif len(m1_trades) == 0 and len(m5_trades) == 0:
        print(f"\n⚠️  NO TRADES")
        print(f"\nPossible reasons:")
        print(f"  1. Bots not running")
        print(f"  2. No entry signals (RSI in neutral zone)")
        print(f"  3. Gap warmup period active")
        print(f"  4. Safety mechanisms paused trading")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
