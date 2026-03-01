"""
Backtest trend strategy with SAMPLED historical sentiment
Uses Alpha Vantage historical news but only for actual trade signals
to stay within free tier limits (25 API calls/day)

Strategy:
1. Run technical backtest first to find all signals
2. Fetch historical sentiment only for those signals
3. Filter trades based on sentiment alignment
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from src.strategies.trend_following import TrendFollowingStrategy
from src.integrations.alpha_vantage import AlphaVantageSentiment

# Load config
config_path = Path('config/trend_params.json')
with open(config_path, 'r') as f:
    config = json.load(f)

API_KEY = config.get('alpha_vantage_api_key', '')

if not API_KEY:
    print("\n⚠️  No Alpha Vantage API key found")
    sys.exit(1)

print("\n" + "="*60)
print("SAMPLED SENTIMENT BACKTEST")
print("="*60)
print("\nThis backtest:")
print("1. Finds all technical signals first")
print("2. Fetches historical sentiment for each signal")
print("3. Filters trades based on sentiment")
print("\nFree tier: 25 API calls/day")
print("Will use 1 call per signal found")

# Initialize
if not mt5.initialize():
    print(f"MT5 initialization failed: {mt5.last_error()}")
    sys.exit(1)

sentiment_analyzer = AlphaVantageSentiment(API_KEY)

# Fetch data
print("\nFetching 90 days of data...")
h1_bars = 90 * 24
h1_rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H1, 0, h1_bars)
h1_data = pd.DataFrame(h1_rates)
h1_data['time'] = pd.to_datetime(h1_data['time'], unit='s')

h4_bars = 90 * 6
h4_rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_H4, 0, h4_bars)
h4_data = pd.DataFrame(h4_rates)
h4_data['time'] = pd.to_datetime(h4_data['time'], unit='s')

print(f"✓ Data fetched: {len(h1_data)} H1 candles, {len(h4_data)} H4 candles")

# Initialize strategy
strategy = TrendFollowingStrategy(config)

# Pre-calculate indicators
print("\nCalculating indicators...")
h4_with_indicators = strategy.calculate_indicators(h4_data, 'H4')
h1_with_signals = strategy.calculate_indicators(h1_data, 'H1')

# PHASE 1: Find all technical signals
print("\nPhase 1: Finding technical signals...")
signals = []

for i in range(200, len(h1_with_signals)):
    current_bar = h1_with_signals.iloc[i]
    current_time = current_bar['time']
    current_price = current_bar['close']
    
    # Get H4 trend
    h4_at_time = h4_with_indicators[h4_with_indicators['time'] <= current_time]
    if len(h4_at_time) == 0:
        continue
    
    h4_last = h4_at_time.iloc[-1]
    ema_uptrend = h4_last['ema_50'] > h4_last['ema_200']
    ema_downtrend = h4_last['ema_50'] < h4_last['ema_200']
    strong_trend = h4_last['adx'] > config.get('adx_threshold', 25)
    
    if ema_uptrend and strong_trend:
        h4_trend = 'UPTREND'
    elif ema_downtrend and strong_trend:
        h4_trend = 'DOWNTREND'
    else:
        h4_trend = 'NO_TREND'
    
    # Check for entry signals
    if h4_trend != 'NO_TREND':
        signal_type = None
        
        # LONG entry check
        if h4_trend == 'UPTREND':
            pullback = current_price <= current_bar['ema_20'] * 1.002
            rsi_ok = (current_bar['rsi'] >= config.get('rsi_min', 40)) and \
                     (current_bar['rsi'] <= config.get('rsi_max', 60))
            h1_uptrend = current_price > current_bar['ema_50']
            
            if i > 0:
                prev_bar = h1_with_signals.iloc[i-1]
                macd_bullish = (current_bar['macd_hist'] > 0) and (prev_bar['macd_hist'] <= 0)
            else:
                macd_bullish = False
            
            if pullback and rsi_ok and macd_bullish and h1_uptrend:
                signal_type = 'LONG'
        
        # SHORT entry check
        elif h4_trend == 'DOWNTREND':
            pullback = current_price >= current_bar['ema_20'] * 0.998
            rsi_ok = (current_bar['rsi'] >= config.get('rsi_min', 40)) and \
                     (current_bar['rsi'] <= config.get('rsi_max', 60))
            h1_downtrend = current_price < current_bar['ema_50']
            
            if i > 0:
                prev_bar = h1_with_signals.iloc[i-1]
                macd_bearish = (current_bar['macd_hist'] < 0) and (prev_bar['macd_hist'] >= 0)
            else:
                macd_bearish = False
            
            if pullback and rsi_ok and macd_bearish and h1_downtrend:
                signal_type = 'SHORT'
        
        if signal_type:
            signals.append({
                'time': current_time,
                'type': signal_type,
                'price': current_price,
                'bar_index': i,
                'atr': current_bar['atr'],
                'h4_trend': h4_trend
            })

print(f"✓ Found {len(signals)} technical signals")

if len(signals) == 0:
    print("\n⚠️  No signals found in this period")
    mt5.shutdown()
    sys.exit(0)

if len(signals) > 20:
    print(f"\n⚠️  Too many signals ({len(signals)}) for free tier (25/day)")
    print("Using first 20 signals only")
    signals = signals[:20]

# PHASE 2: Fetch sentiment for each signal
print(f"\nPhase 2: Fetching sentiment for {len(signals)} signals...")
print("(Rate limited to 1 call per second)\n")

for idx, signal in enumerate(signals):
    # Rate limit: 1 call per second
    if idx > 0:
        time.sleep(1)
    
    # Fetch sentiment from 24 hours before signal
    time_from = (signal['time'] - timedelta(hours=24)).strftime('%Y%m%dT%H%M')
    time_to = signal['time'].strftime('%Y%m%dT%H%M')
    
    print(f"[{idx+1}/{len(signals)}] {signal['time']} - {signal['type']}")
    print(f"  Querying: {time_from} to {time_to}")
    
    try:
        sentiment = sentiment_analyzer.get_gold_sentiment(time_from, time_to)
        signal['sentiment'] = sentiment['sentiment']
        signal['sentiment_confidence'] = sentiment['confidence']
        signal['sentiment_score'] = sentiment['score']
        
        # Check if should trade
        should_trade, confidence = sentiment_analyzer.should_trade(signal['type'], sentiment)
        signal['should_trade'] = should_trade
        signal['trade_confidence'] = confidence
        
        # Adjust position size
        base_size = config['position_size_pct']
        signal['position_size'] = sentiment_analyzer.adjust_position_size(base_size, sentiment)
        
        print(f"  Sentiment: {sentiment['sentiment']} (confidence: {sentiment['confidence']:.2f})")
        print(f"  Decision: {'✓ TAKE' if should_trade else '✗ SKIP'}")
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        # Default to neutral if error
        signal['sentiment'] = 'neutral'
        signal['sentiment_confidence'] = 0.5
        signal['sentiment_score'] = 0.0
        signal['should_trade'] = True
        signal['trade_confidence'] = 0.5
        signal['position_size'] = config['position_size_pct']

# PHASE 3: Simulate trades with sentiment filter
print("\nPhase 3: Simulating trades with sentiment filter...")

trades = []
balance = 10000
starting_balance = balance

# Convert signals to dict for fast lookup
signal_dict = {s['bar_index']: s for s in signals}

open_positions = []

for i in range(200, len(h1_with_signals)):
    current_bar = h1_with_signals.iloc[i]
    current_time = current_bar['time']
    current_price = current_bar['close']
    
    # Check if this bar has a signal
    if i in signal_dict:
        signal = signal_dict[i]
        
        # Only enter if sentiment allows
        if signal['should_trade'] and len(open_positions) < config.get('max_positions', 2):
            sl_distance = signal['atr'] * config.get('atr_multiplier', 2.0)
            
            if signal['type'] == 'LONG':
                sl = current_price - sl_distance
                tp = current_price + (current_price * config.get('profit_target_pct', 0.05))
            else:
                sl = current_price + sl_distance
                tp = current_price - (current_price * config.get('profit_target_pct', 0.05))
            
            position = {
                'type': signal['type'],
                'entry_time': current_time,
                'entry_price': current_price,
                'sl': sl,
                'tp': tp,
                'trailing_stop': sl,
                'peak_price': current_price,
                'entry_bar': i,
                'position_size': signal['position_size'],
                'sentiment': signal['sentiment'],
                'sentiment_confidence': signal['sentiment_confidence']
            }
            open_positions.append(position)
    
    # Get H4 trend for exits
    h4_at_time = h4_with_indicators[h4_with_indicators['time'] <= current_time]
    if len(h4_at_time) > 0:
        h4_last = h4_at_time.iloc[-1]
        ema_uptrend = h4_last['ema_50'] > h4_last['ema_200']
        ema_downtrend = h4_last['ema_50'] < h4_last['ema_200']
        strong_trend = h4_last['adx'] > config.get('adx_threshold', 25)
        
        if ema_uptrend and strong_trend:
            h4_trend = 'UPTREND'
        elif ema_downtrend and strong_trend:
            h4_trend = 'DOWNTREND'
        else:
            h4_trend = 'NO_TREND'
    else:
        h4_trend = 'NO_TREND'
    
    # Check exits
    positions_to_close = []
    
    for pos_idx, pos in enumerate(open_positions):
        atr = current_bar['atr']
        trail_distance = atr * config.get('atr_multiplier', 2.0)
        
        if pos['type'] == 'LONG':
            if current_price > pos['peak_price']:
                pos['peak_price'] = current_price
            
            profit_pct = (current_price - pos['entry_price']) / pos['entry_price']
            
            if profit_pct >= 0.05:
                min_profit_lock = pos['entry_price'] + (pos['peak_price'] - pos['entry_price']) * 0.5
                new_stop = max(pos['trailing_stop'], current_price - trail_distance, min_profit_lock)
            else:
                new_stop = max(pos['trailing_stop'], current_price - trail_distance)
            
            pos['trailing_stop'] = new_stop
            
            exit_reason = None
            if current_price <= pos['trailing_stop']:
                exit_reason = 'trailing_stop'
            elif current_price >= pos['tp']:
                exit_reason = 'take_profit'
            elif h4_trend == 'DOWNTREND':
                exit_reason = 'trend_reversal'
            elif (i - pos['entry_bar']) > 168:
                exit_reason = 'time_limit'
            
            if exit_reason:
                profit = current_price - pos['entry_price']
                profit_pct = (profit / pos['entry_price']) * 100
                
                position_size = balance * pos['position_size']
                leverage = config['leverage']
                position_value = position_size * leverage
                lots = position_value / (pos['entry_price'] * 100)
                
                profit_usd = profit * lots * 100
                balance += profit_usd
                
                trades.append({
                    'type': pos['type'],
                    'entry_time': pos['entry_time'],
                    'exit_time': current_time,
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'profit_usd': profit_usd,
                    'exit_reason': exit_reason,
                    'hold_hours': (i - pos['entry_bar']),
                    'sentiment': pos['sentiment'],
                    'sentiment_confidence': pos['sentiment_confidence'],
                    'position_size': pos['position_size']
                })
                
                positions_to_close.append(pos_idx)
        
        else:  # SHORT
            if current_price < pos['peak_price']:
                pos['peak_price'] = current_price
            
            profit_pct = (pos['entry_price'] - current_price) / pos['entry_price']
            
            if profit_pct >= 0.05:
                min_profit_lock = pos['entry_price'] - (pos['entry_price'] - pos['peak_price']) * 0.5
                new_stop = min(pos['trailing_stop'], current_price + trail_distance, min_profit_lock)
            else:
                new_stop = min(pos['trailing_stop'], current_price + trail_distance)
            
            pos['trailing_stop'] = new_stop
            
            exit_reason = None
            if current_price >= pos['trailing_stop']:
                exit_reason = 'trailing_stop'
            elif current_price <= pos['tp']:
                exit_reason = 'take_profit'
            elif h4_trend == 'UPTREND':
                exit_reason = 'trend_reversal'
            elif (i - pos['entry_bar']) > 168:
                exit_reason = 'time_limit'
            
            if exit_reason:
                profit = pos['entry_price'] - current_price
                profit_pct = (profit / pos['entry_price']) * 100
                
                position_size = balance * pos['position_size']
                leverage = config['leverage']
                position_value = position_size * leverage
                lots = position_value / (pos['entry_price'] * 100)
                
                profit_usd = profit * lots * 100
                balance += profit_usd
                
                trades.append({
                    'type': pos['type'],
                    'entry_time': pos['entry_time'],
                    'exit_time': current_time,
                    'entry_price': pos['entry_price'],
                    'exit_price': current_price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'profit_usd': profit_usd,
                    'exit_reason': exit_reason,
                    'hold_hours': (i - pos['entry_bar']),
                    'sentiment': pos['sentiment'],
                    'sentiment_confidence': pos['sentiment_confidence'],
                    'position_size': pos['position_size']
                })
                
                positions_to_close.append(pos_idx)
        
        for idx in sorted(positions_to_close, reverse=True):
            open_positions.pop(idx)

# Close remaining positions
if open_positions:
    final_bar = h1_with_signals.iloc[-1]
    final_price = final_bar['close']
    final_time = final_bar['time']
    
    for pos in open_positions:
        if pos['type'] == 'LONG':
            profit = final_price - pos['entry_price']
        else:
            profit = pos['entry_price'] - final_price
        
        profit_pct = (profit / pos['entry_price']) * 100
        
        position_size = balance * pos['position_size']
        leverage = config['leverage']
        position_value = position_size * leverage
        lots = position_value / (pos['entry_price'] * 100)
        
        profit_usd = profit * lots * 100
        balance += profit_usd
        
        trades.append({
            'type': pos['type'],
            'entry_time': pos['entry_time'],
            'exit_time': final_time,
            'entry_price': pos['entry_price'],
            'exit_price': final_price,
            'profit': profit,
            'profit_pct': profit_pct,
            'profit_usd': profit_usd,
            'exit_reason': 'end_of_data',
            'hold_hours': len(h1_with_signals) - pos['entry_bar'],
            'sentiment': pos['sentiment'],
            'sentiment_confidence': pos['sentiment_confidence'],
            'position_size': pos['position_size']
        })

# Analyze results
print("\n" + "="*60)
print("BACKTEST RESULTS WITH SENTIMENT FILTER")
print("="*60)

print(f"\nSignal Analysis:")
print(f"  Total technical signals: {len(signals)}")
signals_taken = sum(1 for s in signals if s['should_trade'])
signals_filtered = len(signals) - signals_taken
print(f"  Signals taken: {signals_taken}")
print(f"  Signals filtered: {signals_filtered} ({signals_filtered/len(signals)*100:.1f}%)")

if not trades:
    print("\n⚠️  No trades executed")
else:
    df = pd.DataFrame(trades)
    
    total_return = ((balance - starting_balance) / starting_balance) * 100
    
    winning_trades = df[df['profit_usd'] > 0]
    losing_trades = df[df['profit_usd'] < 0]
    
    win_rate = (len(winning_trades) / len(df)) * 100 if len(df) > 0 else 0
    
    avg_win = winning_trades['profit_pct'].mean() if len(winning_trades) > 0 else 0
    avg_loss = losing_trades['profit_pct'].mean() if len(losing_trades) > 0 else 0
    
    profit_factor = abs(winning_trades['profit_usd'].sum() / losing_trades['profit_usd'].sum()) if len(losing_trades) > 0 and losing_trades['profit_usd'].sum() != 0 else float('inf')
    
    print(f"\nTrade Results:")
    print(f"  Total Trades: {len(df)}")
    print(f"  Winning: {len(winning_trades)} ({win_rate:.1f}%)")
    print(f"  Losing: {len(losing_trades)} ({100-win_rate:.1f}%)")
    
    print(f"\nReturns:")
    print(f"  Starting Balance: ${starting_balance:,.2f}")
    print(f"  Final Balance: ${balance:,.2f}")
    print(f"  Total Return: {total_return:+.2f}%")
    
    print(f"\nTrade Statistics:")
    print(f"  Average Win: {avg_win:+.2f}%")
    print(f"  Average Loss: {avg_loss:+.2f}%")
    print(f"  Profit Factor: {profit_factor:.2f}")
    
    print(f"\nSentiment Breakdown:")
    for sent in ['bullish', 'bearish', 'neutral']:
        sent_trades = df[df['sentiment'] == sent]
        if len(sent_trades) > 0:
            sent_wins = len(sent_trades[sent_trades['profit_usd'] > 0])
            sent_wr = (sent_wins / len(sent_trades)) * 100
            sent_profit = sent_trades['profit_usd'].sum()
            print(f"  {sent.capitalize()}: {len(sent_trades)} trades, {sent_wr:.1f}% WR, ${sent_profit:+.2f}")

print("\n" + "="*60)

mt5.shutdown()
print("\n✓ Backtest complete")
