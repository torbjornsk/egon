"""
Backtest trend-following strategy on H1 data
Tests the strategy without sentiment filter first
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from src.strategies.trend_following import TrendFollowingStrategy

def initialize_mt5():
    """Initialize MT5 connection"""
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return False
    print("✓ Connected to MT5")
    return True

def fetch_h1_data(symbol='XAUUSD', days=90):
    """Fetch H1 historical data"""
    print(f"\nFetching {days} days of H1 data...")
    
    bars = days * 24  # H1 bars per day
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, bars)
    
    if rates is None or len(rates) == 0:
        print(f"Failed to fetch data: {mt5.last_error()}")
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"✓ Fetched {len(df)} H1 candles")
    print(f"  Period: {df['time'].min()} to {df['time'].max()}")
    
    return df

def fetch_h4_data(symbol='XAUUSD', days=90):
    """Fetch H4 historical data for trend detection"""
    print(f"Fetching {days} days of H4 data...")
    
    bars = days * 6  # H4 bars per day
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, bars)
    
    if rates is None or len(rates) == 0:
        print(f"Failed to fetch data: {mt5.last_error()}")
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"✓ Fetched {len(df)} H4 candles")
    
    return df

def simulate_trend_strategy(h1_data, h4_data, config):
    """Simulate trend following strategy"""
    
    strategy = TrendFollowingStrategy(config)
    
    # Pre-calculate H4 indicators
    h4_with_indicators = strategy.calculate_indicators(h4_data, 'H4')
    
    # Generate H1 signals
    print("\nGenerating signals...")
    h1_with_signals = strategy.calculate_indicators(h1_data, 'H1')
    
    # Simulate trading
    print("Simulating trades...")
    
    trades = []
    open_positions = []
    balance = 10000
    starting_balance = balance
    
    for i in range(200, len(h1_with_signals)):  # Start after warmup
        current_bar = h1_with_signals.iloc[i]
        current_time = current_bar['time']
        current_price = current_bar['close']
        
        # Get H4 trend at this time
        h4_at_time = h4_with_indicators[h4_with_indicators['time'] <= current_time]
        if len(h4_at_time) == 0:
            continue
        
        h4_last = h4_at_time.iloc[-1]
        
        # Determine H4 trend
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
        if len(open_positions) < config.get('max_positions', 2):
            # LONG entry
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
                    # Enter LONG
                    sl_distance = current_bar['atr'] * config.get('atr_multiplier', 2.0)
                    sl = current_price - sl_distance
                    tp = current_price + (current_price * config.get('profit_target_pct', 0.05))
                    
                    position = {
                        'type': 'LONG',
                        'entry_time': current_time,
                        'entry_price': current_price,
                        'sl': sl,
                        'tp': tp,
                        'trailing_stop': sl,
                        'peak_price': current_price,
                        'entry_bar': i
                    }
                    open_positions.append(position)
            
            # SHORT entry
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
                    # Enter SHORT
                    sl_distance = current_bar['atr'] * config.get('atr_multiplier', 2.0)
                    sl = current_price + sl_distance
                    tp = current_price - (current_price * config.get('profit_target_pct', 0.05))
                    
                    position = {
                        'type': 'SHORT',
                        'entry_time': current_time,
                        'entry_price': current_price,
                        'sl': sl,
                        'tp': tp,
                        'trailing_stop': sl,
                        'peak_price': current_price,
                        'entry_bar': i
                    }
                    open_positions.append(position)
        
        # Check exits for open positions
        positions_to_close = []
        
        for pos_idx, pos in enumerate(open_positions):
            # Update trailing stop
            atr = current_bar['atr']
            trail_distance = atr * config.get('atr_multiplier', 2.0)
            
            if pos['type'] == 'LONG':
                # Update peak price
                if current_price > pos['peak_price']:
                    pos['peak_price'] = current_price
                
                # Calculate profit
                profit_pct = (current_price - pos['entry_price']) / pos['entry_price']
                
                # Update trailing stop
                if profit_pct >= 0.05:
                    # Lock 50% profit
                    min_profit_lock = pos['entry_price'] + (pos['peak_price'] - pos['entry_price']) * 0.5
                    new_stop = max(pos['trailing_stop'], current_price - trail_distance, min_profit_lock)
                else:
                    new_stop = max(pos['trailing_stop'], current_price - trail_distance)
                
                pos['trailing_stop'] = new_stop
                
                # Check exit conditions
                exit_reason = None
                
                if current_price <= pos['trailing_stop']:
                    exit_reason = 'trailing_stop'
                elif current_price >= pos['tp']:
                    exit_reason = 'take_profit'
                elif h4_trend == 'DOWNTREND':
                    exit_reason = 'trend_reversal'
                elif (i - pos['entry_bar']) > (168):  # 7 days in hours
                    exit_reason = 'time_limit'
                
                if exit_reason:
                    profit = current_price - pos['entry_price']
                    profit_pct = (profit / pos['entry_price']) * 100
                    
                    position_size = balance * config['position_size_pct']
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
                        'hold_hours': (i - pos['entry_bar'])
                    })
                    
                    positions_to_close.append(pos_idx)
            
            else:  # SHORT
                # Update peak price (lowest for shorts)
                if current_price < pos['peak_price']:
                    pos['peak_price'] = current_price
                
                # Calculate profit
                profit_pct = (pos['entry_price'] - current_price) / pos['entry_price']
                
                # Update trailing stop
                if profit_pct >= 0.05:
                    # Lock 50% profit
                    min_profit_lock = pos['entry_price'] - (pos['entry_price'] - pos['peak_price']) * 0.5
                    new_stop = min(pos['trailing_stop'], current_price + trail_distance, min_profit_lock)
                else:
                    new_stop = min(pos['trailing_stop'], current_price + trail_distance)
                
                pos['trailing_stop'] = new_stop
                
                # Check exit conditions
                exit_reason = None
                
                if current_price >= pos['trailing_stop']:
                    exit_reason = 'trailing_stop'
                elif current_price <= pos['tp']:
                    exit_reason = 'take_profit'
                elif h4_trend == 'UPTREND':
                    exit_reason = 'trend_reversal'
                elif (i - pos['entry_bar']) > (168):  # 7 days in hours
                    exit_reason = 'time_limit'
                
                if exit_reason:
                    profit = pos['entry_price'] - current_price
                    profit_pct = (profit / pos['entry_price']) * 100
                    
                    position_size = balance * config['position_size_pct']
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
                        'hold_hours': (i - pos['entry_bar'])
                    })
                    
                    positions_to_close.append(pos_idx)
        
        # Remove closed positions
        for idx in sorted(positions_to_close, reverse=True):
            open_positions.pop(idx)
    
    # Close any remaining positions
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
            
            position_size = balance * config['position_size_pct']
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
                'hold_hours': len(h1_with_signals) - pos['entry_bar']
            })
    
    return trades, balance, starting_balance

def analyze_results(trades, final_balance, starting_balance):
    """Analyze backtest results"""
    if not trades:
        print("\n⚠️  No trades executed")
        return
    
    df = pd.DataFrame(trades)
    
    total_return = ((final_balance - starting_balance) / starting_balance) * 100
    
    winning_trades = df[df['profit_usd'] > 0]
    losing_trades = df[df['profit_usd'] < 0]
    
    win_rate = (len(winning_trades) / len(df)) * 100 if len(df) > 0 else 0
    
    avg_win = winning_trades['profit_pct'].mean() if len(winning_trades) > 0 else 0
    avg_loss = losing_trades['profit_pct'].mean() if len(losing_trades) > 0 else 0
    
    profit_factor = abs(winning_trades['profit_usd'].sum() / losing_trades['profit_usd'].sum()) if len(losing_trades) > 0 and losing_trades['profit_usd'].sum() != 0 else 0
    
    # Calculate max drawdown
    df['cumulative_profit'] = df['profit_usd'].cumsum()
    df['peak'] = df['cumulative_profit'].cummax()
    df['drawdown'] = df['peak'] - df['cumulative_profit']
    max_drawdown = (df['drawdown'].max() / starting_balance) * 100
    
    # Average hold time
    avg_hold_hours = df['hold_hours'].mean()
    avg_hold_days = avg_hold_hours / 24
    
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    print(f"\nTotal Trades: {len(df)}")
    print(f"  Winning: {len(winning_trades)} ({win_rate:.1f}%)")
    print(f"  Losing: {len(losing_trades)} ({100-win_rate:.1f}%)")
    
    print(f"\nReturns:")
    print(f"  Starting Balance: ${starting_balance:,.2f}")
    print(f"  Final Balance: ${final_balance:,.2f}")
    print(f"  Total Return: {total_return:+.2f}%")
    
    print(f"\nTrade Statistics:")
    print(f"  Average Win: {avg_win:+.2f}%")
    print(f"  Average Loss: {avg_loss:+.2f}%")
    print(f"  Profit Factor: {profit_factor:.2f}")
    print(f"  Max Drawdown: {max_drawdown:.2f}%")
    
    print(f"\nHolding Period:")
    print(f"  Average: {avg_hold_days:.1f} days ({avg_hold_hours:.0f} hours)")
    print(f"  Min: {df['hold_hours'].min():.0f} hours")
    print(f"  Max: {df['hold_hours'].max():.0f} hours")
    
    # Exit reasons
    print(f"\nExit Reasons:")
    exit_counts = df['exit_reason'].value_counts()
    for reason, count in exit_counts.items():
        pct = (count / len(df)) * 100
        print(f"  {reason}: {count} ({pct:.1f}%)")
    
    # Trade types
    print(f"\nTrade Types:")
    type_counts = df['type'].value_counts()
    for trade_type, count in type_counts.items():
        pct = (count / len(df)) * 100
        avg_profit = df[df['type'] == trade_type]['profit_pct'].mean()
        print(f"  {trade_type}: {count} ({pct:.1f}%) | Avg: {avg_profit:+.2f}%")
    
    print("\n" + "="*60)
    
    return {
        'total_trades': len(df),
        'win_rate': win_rate,
        'total_return': total_return,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'avg_hold_days': avg_hold_days
    }

def main():
    """Run backtest"""
    print("\n" + "="*60)
    print("TREND STRATEGY BACKTEST")
    print("="*60)
    
    # Initialize MT5
    if not initialize_mt5():
        return
    
    # Load config
    config_path = Path('config/trend_params.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    print(f"\nConfiguration:")
    print(f"  Position Size: {config['position_size_pct']*100}%")
    print(f"  Leverage: {config['leverage']}x")
    print(f"  ADX Threshold: {config['adx_threshold']}")
    print(f"  RSI Range: {config['rsi_min']}-{config['rsi_max']}")
    print(f"  Profit Target: {config['profit_target_pct']*100}%")
    
    # Fetch data
    h1_data = fetch_h1_data(days=90)
    h4_data = fetch_h4_data(days=90)
    
    if h1_data is None or h4_data is None:
        print("Failed to fetch data")
        mt5.shutdown()
        return
    
    # Run simulation
    trades, final_balance, starting_balance = simulate_trend_strategy(h1_data, h4_data, config)
    
    # Analyze results
    results = analyze_results(trades, final_balance, starting_balance)
    
    # Cleanup
    mt5.shutdown()
    print("\n✓ Backtest complete")

if __name__ == '__main__':
    main()
