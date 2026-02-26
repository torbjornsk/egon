"""
Analyze today's trades and test potential improvements
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def connect_mt5():
    """Connect to MT5"""
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return False
    print("Connected to MT5")
    return True

def get_todays_trades(start_hour=1):
    """Get trades from specified hour today"""
    # Get today at specified hour
    today = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)
    
    # Get all deals since then
    deals = mt5.history_deals_get(today, datetime.now())
    
    if deals is None or len(deals) == 0:
        print(f"No deals found since {today}")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Filter for XAUUSD
    df = df[df['symbol'] == 'XAUUSD']
    
    # Separate by magic number
    m5_deals = df[df['magic'] == 234000].copy()
    m1_deals = df[df['magic'] == 234001].copy()
    
    print(f"\n=== Trades since {today.strftime('%Y-%m-%d %H:%M')} ===")
    print(f"M5 Bot: {len(m5_deals)} deals")
    print(f"M1 Bot: {len(m1_deals)} deals")
    
    return m5_deals, m1_deals

def analyze_trades(deals, bot_name):
    """Analyze trade performance"""
    if deals is None or len(deals) == 0:
        print(f"\n{bot_name}: No trades to analyze")
        return
    
    # Group by position ticket to get complete trades
    trades = []
    for ticket in deals['position_id'].unique():
        position_deals = deals[deals['position_id'] == ticket].sort_values('time')
        
        if len(position_deals) >= 2:  # Entry and exit
            entry = position_deals.iloc[0]
            exit_deal = position_deals.iloc[-1]
            
            # Get the actual profit from the exit deal
            profit = exit_deal['profit']
            duration = (exit_deal['time'] - entry['time']).total_seconds() / 60
            
            trades.append({
                'ticket': ticket,
                'entry_time': entry['time'],
                'exit_time': exit_deal['time'],
                'entry_price': entry['price'],
                'exit_price': exit_deal['price'],
                'profit': profit,
                'duration_min': duration,
                'type': 'LONG' if entry['type'] == 0 else 'SHORT',
                'volume': entry['volume']
            })
    
    if not trades:
        print(f"\n{bot_name}: No completed trades")
        return
    
    trades_df = pd.DataFrame(trades)
    
    # Calculate actual totals
    total_profit = trades_df['profit'].sum()
    wins = trades_df[trades_df['profit'] > 0]
    losses = trades_df[trades_df['profit'] < 0]
    
    print(f"\n=== {bot_name} Analysis ===")
    print(f"Total Trades: {len(trades_df)}")
    print(f"Wins: {len(wins)} (${wins['profit'].sum():.2f})")
    print(f"Losses: {len(losses)} (${losses['profit'].sum():.2f})")
    print(f"Win Rate: {len(wins) / len(trades_df) * 100:.1f}%")
    print(f"Total Profit: ${total_profit:.2f}")
    print(f"Avg Profit per Trade: ${trades_df['profit'].mean():.2f}")
    print(f"Avg Duration: {trades_df['duration_min'].mean():.1f} min")
    print(f"Best Trade: ${trades_df['profit'].max():.2f}")
    print(f"Worst Trade: ${trades_df['profit'].min():.2f}")
    
    # Profit factor
    if len(losses) > 0 and losses['profit'].sum() != 0:
        profit_factor = abs(wins['profit'].sum() / losses['profit'].sum())
        print(f"Profit Factor: {profit_factor:.2f}")
    
    # Analyze losing trades
    if len(losses) > 0:
        print(f"\n--- Losing Trades Analysis ---")
        print(f"Total Lost: ${losses['profit'].sum():.2f}")
        print(f"Avg Loss: ${losses['profit'].mean():.2f}")
        print(f"Avg Loss Duration: {losses['duration_min'].mean():.1f} min")
        print(f"Longest Loss Duration: {losses['duration_min'].max():.1f} min")
        
        # Check if losses could have been cut earlier
        quick_losses = losses[losses['duration_min'] < 5]
        slow_losses = losses[losses['duration_min'] >= 5]
        print(f"Quick losses (<5min): {len(quick_losses)} (${quick_losses['profit'].sum():.2f})")
        print(f"Slow losses (>=5min): {len(slow_losses)} (${slow_losses['profit'].sum():.2f})")
    
    # Analyze winning trades
    if len(wins) > 0:
        print(f"\n--- Winning Trades Analysis ---")
        print(f"Total Won: ${wins['profit'].sum():.2f}")
        print(f"Avg Win: ${wins['profit'].mean():.2f}")
        print(f"Avg Win Duration: {wins['duration_min'].mean():.1f} min")
        print(f"Largest Win: ${wins['profit'].max():.2f}")
    
    # Check consecutive losses
    consecutive = 0
    max_consecutive = 0
    for profit in trades_df['profit']:
        if profit < 0:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
    
    print(f"\nMax Consecutive Losses: {max_consecutive}")
    
    # Show trade distribution by hour
    trades_df['hour'] = trades_df['entry_time'].dt.hour
    print(f"\n--- Trades by Hour ---")
    hourly = trades_df.groupby('hour').agg({
        'profit': ['count', 'sum', 'mean']
    }).round(2)
    print(hourly)
    
    return trades_df

def test_improved_exit_timing(bot_name):
    """Test if earlier exits would improve performance"""
    print(f"\n=== Testing Improved Exit Timing for {bot_name} ===")
    
    # Get historical data
    symbol = 'XAUUSD'
    timeframe = mt5.TIMEFRAME_M1 if bot_name == "M1" else mt5.TIMEFRAME_M5
    
    # Get data from today
    today = datetime.now().replace(hour=1, minute=0, second=0, microsecond=0)
    rates = mt5.copy_rates_range(symbol, timeframe, today, datetime.now())
    
    if rates is None or len(rates) == 0:
        print("Could not fetch historical data")
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"Fetched {len(df)} candles from {df['time'].min()} to {df['time'].max()}")
    
    # Calculate indicators
    df = compute_indicators(df, bot_name)
    
    # Simulate trades with current strategy vs improved
    print("\nSimulation would require full backtest - recommend running:")
    print(f"  python analysis/test_m1_robustness.py  # for M1")
    print(f"  python analysis/test_both_bots_robustness.py  # for both")

def compute_indicators(df, bot_name):
    """Compute technical indicators"""
    if bot_name == "M5":
        fast_ema = 9
        slow_ema = 21
    else:
        fast_ema = 5
        slow_ema = 12
    
    # EMAs
    df['ema_fast'] = df['close'].ewm(span=fast_ema, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema, adjust=False).mean()
    
    # Trend
    df['uptrend'] = df['ema_fast'] > df['ema_slow']
    df['downtrend'] = df['ema_fast'] < df['ema_slow']
    
    # RSI
    rsi_period = 14 if bot_name == "M5" else 5
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['ATR'] = df['tr'].rolling(window=14).mean()
    
    return df

def main():
    if not connect_mt5():
        return
    
    # Get today's trades
    result = get_todays_trades(start_hour=1)
    
    if result:
        m5_deals, m1_deals = result
        
        # Analyze each bot
        m5_trades = analyze_trades(m5_deals, "M5 Bot")
        m1_trades = analyze_trades(m1_deals, "M1 Bot")
        
        # Test improvements
        if m1_trades is not None and len(m1_trades) > 0:
            test_improved_exit_timing("M1")
    
    mt5.shutdown()
    print("\n=== Analysis Complete ===")
    print("\nRecommendations:")
    print("1. Run full backtest to test parameter changes")
    print("2. Consider tighter stop losses if many slow losses")
    print("3. Review max consecutive losses setting (now 12 for 2 positions)")

if __name__ == "__main__":
    main()
