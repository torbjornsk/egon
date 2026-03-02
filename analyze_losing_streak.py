"""
Analyze the losing streak from 10:50 to 12:40 MT5 time
Look at what went wrong and market conditions during this period
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

def get_trades_in_period(from_time, to_time, magic_number, symbol='XAUUSD.p'):
    """Get trades in specific period"""
    deals = mt5.history_deals_get(from_time, to_time)
    
    if deals is None or len(deals) == 0:
        return []
    
    bot_deals = [d for d in deals if d.magic == magic_number and d.symbol == symbol]
    
    trades = []
    positions = {}
    
    for deal in sorted(bot_deals, key=lambda x: x.time):
        pos_id = deal.position_id
        
        if pos_id not in positions:
            positions[pos_id] = {
                'entry_time': datetime.fromtimestamp(deal.time),
                'entry_price': deal.price,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'volume': deal.volume,
                'ticket': deal.ticket
            }
        else:
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
    
    return trades

def main():
    """Analyze losing streak"""
    print("="*100)
    print("LOSING STREAK ANALYSIS: 10:50 - 12:40 MT5 TIME")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get current time
    tick = mt5.symbol_info_tick(symbol)
    current_time = datetime.fromtimestamp(tick.time)
    
    # Set time range
    today_1050 = current_time.replace(hour=10, minute=50, second=0, microsecond=0)
    today_1240 = current_time.replace(hour=12, minute=40, second=0, microsecond=0)
    
    print(f"\nCurrent MT5 time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Analysis period: {today_1050.strftime('%H:%M')} to {today_1240.strftime('%H:%M')}")
    
    # Get M1 trades in this period
    print(f"\n" + "="*100)
    print("M1 BOT TRADES (10:50 - 12:40)")
    print("="*100)
    
    m1_trades = get_trades_in_period(today_1050, today_1240, 234001, symbol)
    
    if m1_trades:
        print(f"\nTotal Trades: {len(m1_trades)}")
        
        total_profit = 0
        winning = 0
        losing = 0
        
        print(f"\n{'#':<4} {'Time':<12} {'Type':<6} {'Entry':>10} {'Exit':>10} {'Dur':>6} {'Profit':>12}")
        print("-"*100)
        
        for i, t in enumerate(m1_trades, 1):
            total_profit += t['profit']
            if t['profit'] > 0:
                winning += 1
                status = "WIN"
            else:
                losing += 1
                status = "LOSS"
            
            print(f"{i:<4} {t['entry_time'].strftime('%H:%M:%S'):<12} {t['type']:<6} "
                  f"${t['entry_price']:>9.2f} ${t['exit_price']:>9.2f} "
                  f"{t['duration_min']:>5.1f}m ${t['profit']:>+10.2f} {status}")
        
        print("-"*100)
        print(f"Summary: {winning} wins, {losing} losses ({winning/(winning+losing)*100:.0f}% win rate)")
        print(f"Total P/L: ${total_profit:+.2f}")
    else:
        print("\nNo M1 trades in this period")
    
    # Get M5 trades
    print(f"\n" + "="*100)
    print("M5 BOT TRADES (10:50 - 12:40)")
    print("="*100)
    
    m5_trades = get_trades_in_period(today_1050, today_1240, 234000, symbol)
    
    if m5_trades:
        print(f"\nTotal Trades: {len(m5_trades)}")
        
        total_profit = 0
        winning = 0
        losing = 0
        
        print(f"\n{'#':<4} {'Time':<12} {'Type':<6} {'Entry':>10} {'Exit':>10} {'Dur':>6} {'Profit':>12}")
        print("-"*100)
        
        for i, t in enumerate(m5_trades, 1):
            total_profit += t['profit']
            if t['profit'] > 0:
                winning += 1
                status = "WIN"
            else:
                losing += 1
                status = "LOSS"
            
            print(f"{i:<4} {t['entry_time'].strftime('%H:%M:%S'):<12} {t['type']:<6} "
                  f"${t['entry_price']:>9.2f} ${t['exit_price']:>9.2f} "
                  f"{t['duration_min']:>5.1f}m ${t['profit']:>+10.2f} {status}")
        
        print("-"*100)
        print(f"Summary: {winning} wins, {losing} losses ({winning/(winning+losing)*100:.0f}% win rate)" if winning+losing > 0 else "Summary: No completed trades")
        print(f"Total P/L: ${total_profit:+.2f}")
    else:
        print("\nNo M5 trades in this period")
    
    # Analyze market conditions
    print(f"\n" + "="*100)
    print("MARKET CONDITIONS (10:50 - 12:40)")
    print("="*100)
    
    # Get M1 data
    minutes = 110 + 200  # 110 minutes + 200 for indicators
    rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, minutes)
    
    if rates_m1 is not None:
        df_m1 = pd.DataFrame(rates_m1)
        df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
        
        # Find 10:50
        target_time = today_1050
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
            analysis_df = df_m1.iloc[closest_idx:closest_idx+110].copy()
            
            print(f"\nPrice Action:")
            start_price = analysis_df.iloc[0]['open']
            end_price = analysis_df.iloc[-1]['close']
            highest = analysis_df['high'].max()
            lowest = analysis_df['low'].min()
            
            print(f"  Start (10:50): ${start_price:.2f}")
            print(f"  End (12:40):   ${end_price:.2f} ({end_price-start_price:+.2f}, {((end_price-start_price)/start_price)*100:+.2f}%)")
            print(f"  High:          ${highest:.2f} (+${highest-start_price:.2f})")
            print(f"  Low:           ${lowest:.2f} (${lowest-start_price:.2f})")
            
            # RSI analysis
            rsi_values = analysis_df['RSI'].dropna()
            
            print(f"\nRSI Statistics:")
            print(f"  Min:    {rsi_values.min():.1f}")
            print(f"  Max:    {rsi_values.max():.1f}")
            print(f"  Mean:   {rsi_values.mean():.1f}")
            print(f"  Median: {rsi_values.median():.1f}")
            
            # ATR analysis
            atr_values = analysis_df['ATR'].dropna()
            print(f"\nVolatility (ATR):")
            print(f"  Mean ATR: ${atr_values.mean():.2f}")
            print(f"  Max ATR:  ${atr_values.max():.2f}")
            
            # Trend analysis
            uptrend_pct = (analysis_df['uptrend'].sum() / len(analysis_df)) * 100
            print(f"\nTrend:")
            print(f"  Uptrend: {uptrend_pct:.0f}% of candles")
            print(f"  Downtrend: {100-uptrend_pct:.0f}% of candles")
            
            # Count signals
            long_signals = (rsi_values < m1_config['rsi_buy']).sum()
            short_signals = (rsi_values > m1_config['rsi_sell']).sum()
            
            print(f"\nEntry Signals:")
            print(f"  LONG signals (RSI < {m1_config['rsi_buy']}): {long_signals} candles")
            print(f"  SHORT signals (RSI > {m1_config['rsi_sell']}): {short_signals} candles")
            
            # Show price chart
            print(f"\nPrice Movement (every 10 minutes):")
            print(f"{'Time':<10} {'Price':>10} {'RSI':>8} {'Trend':<10}")
            print("-"*50)
            
            for i in range(0, len(analysis_df), 10):
                if i < len(analysis_df):
                    row = analysis_df.iloc[i]
                    trend = "Uptrend" if row['uptrend'] else "Downtrend"
                    print(f"{row['time'].strftime('%H:%M'):<10} ${row['close']:>9.2f} {row['RSI']:>7.1f} {trend:<10}")
    
    mt5.shutdown()
    
    # Analysis
    print(f"\n" + "="*100)
    print("ANALYSIS")
    print("="*100)
    
    if m1_trades:
        m1_total = sum(t['profit'] for t in m1_trades)
        m1_losses = [t for t in m1_trades if t['profit'] < 0]
        
        print(f"\nM1 Bot Performance:")
        print(f"  Total P/L: ${m1_total:+.2f}")
        print(f"  Losses: {len(m1_losses)}/{len(m1_trades)}")
        
        if len(m1_losses) > 0:
            avg_loss = sum(t['profit'] for t in m1_losses) / len(m1_losses)
            print(f"  Average loss: ${avg_loss:.2f}")
            
            # Find biggest losses
            biggest_losses = sorted(m1_losses, key=lambda x: x['profit'])[:5]
            print(f"\n  Biggest losses:")
            for i, t in enumerate(biggest_losses, 1):
                print(f"    {i}. {t['entry_time'].strftime('%H:%M')} {t['type']}: ${t['profit']:.2f}")
    
    if m5_trades:
        m5_total = sum(t['profit'] for t in m5_trades)
        print(f"\nM5 Bot Performance:")
        print(f"  Total P/L: ${m5_total:+.2f}")
    
    print(f"\nPossible Issues:")
    print(f"  1. Choppy/ranging market (whipsaws)")
    print(f"  2. High volatility (stops hit frequently)")
    print(f"  3. Overtrading (too many positions)")
    print(f"  4. Mean reversion not working in this period")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
