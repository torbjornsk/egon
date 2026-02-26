"""
Test if using limit orders for better entry prices improves performance.

Strategy:
- When RSI signals entry, instead of market order, place limit order
- For LONG: Place buy limit slightly below current price (better entry)
- For SHORT: Place sell limit slightly above current price (better entry)
- Update limit price each candle if not filled
- Cancel if RSI moves away from entry zone

This could help:
1. Get better entry prices (lower for longs, higher for shorts)
2. Avoid entering on temporary spikes
3. Filter out weak signals that don't retrace
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

sys.path.append('.')
from src.mt5_connector import MT5Connector

def calculate_indicators(df):
    """Calculate RSI and ATR"""
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    return df

def backtest_market_orders(df, config):
    """Original strategy: Market orders when RSI crosses threshold"""
    balance = 10000
    position = None
    trades = []
    equity_curve = [balance]
    
    for i in range(50, len(df)):
        current = df.iloc[i]
        
        if position is None:
            # Check for LONG entry
            if current['RSI'] < config['rsi_buy']:
                entry_price = current['close']
                stop_distance = current['ATR'] * config['atr_multiplier']
                sl = entry_price - stop_distance
                tp = entry_price * (1 + config['profit_target_pct'])
                
                position = {
                    'type': 'LONG',
                    'entry_price': entry_price,
                    'entry_rsi': current['RSI'],
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
        else:
            # Check exit conditions
            exit_signal = False
            exit_reason = None
            exit_price = current['close']
            
            if position['type'] == 'LONG':
                # Stop loss
                if current['low'] <= position['sl']:
                    exit_signal = True
                    exit_reason = 'SL'
                    exit_price = position['sl']
                # Take profit
                elif current['high'] >= position['tp']:
                    exit_signal = True
                    exit_reason = 'TP'
                    exit_price = position['tp']
                # RSI exit
                elif current['RSI'] > config['rsi_exit_long']:
                    exit_signal = True
                    exit_reason = 'RSI'
            
            if exit_signal:
                profit_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
                balance += balance * (profit_pct / 100)
                
                trades.append({
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'profit_pct': profit_pct,
                    'reason': exit_reason,
                    'bars_held': i - position['entry_bar']
                })
                
                position = None
        
        equity_curve.append(balance)
    
    return trades, equity_curve

def backtest_limit_orders(df, config, limit_offset_pct=0.05):
    """
    New strategy: Limit orders at better prices
    
    limit_offset_pct: How much better price to target (0.05 = 0.05% better entry)
    """
    balance = 10000
    position = None
    pending_order = None
    trades = []
    equity_curve = [balance]
    filled_orders = 0
    cancelled_orders = 0
    
    for i in range(50, len(df)):
        current = df.iloc[i]
        
        if position is None and pending_order is None:
            # Check for LONG entry signal
            if current['RSI'] < config['rsi_buy']:
                # Place limit order BELOW current price for better entry
                limit_price = current['close'] * (1 - limit_offset_pct / 100)
                stop_distance = current['ATR'] * config['atr_multiplier']
                sl = limit_price - stop_distance
                tp = limit_price * (1 + config['profit_target_pct'])
                
                pending_order = {
                    'type': 'BUY_LIMIT',
                    'limit_price': limit_price,
                    'entry_rsi': current['RSI'],
                    'sl': sl,
                    'tp': tp,
                    'placed_bar': i
                }
        
        elif pending_order is not None:
            # Check if limit order would be filled
            if current['low'] <= pending_order['limit_price']:
                # Order filled!
                filled_orders += 1
                position = {
                    'type': 'LONG',
                    'entry_price': pending_order['limit_price'],
                    'entry_rsi': pending_order['entry_rsi'],
                    'sl': pending_order['sl'],
                    'tp': pending_order['tp'],
                    'entry_bar': i
                }
                pending_order = None
            
            # Cancel order if RSI moved away from entry zone (signal invalidated)
            elif current['RSI'] > config['rsi_buy'] + 5:  # RSI moved up 5 points
                cancelled_orders += 1
                pending_order = None
            
            # Update limit price if still in entry zone (follow price down)
            elif current['RSI'] < config['rsi_buy']:
                new_limit = current['close'] * (1 - limit_offset_pct / 100)
                if new_limit < pending_order['limit_price']:  # Only update if better
                    stop_distance = current['ATR'] * config['atr_multiplier']
                    pending_order['limit_price'] = new_limit
                    pending_order['sl'] = new_limit - stop_distance
                    pending_order['tp'] = new_limit * (1 + config['profit_target_pct'])
        
        elif position is not None:
            # Check exit conditions (same as market orders)
            exit_signal = False
            exit_reason = None
            exit_price = current['close']
            
            if position['type'] == 'LONG':
                if current['low'] <= position['sl']:
                    exit_signal = True
                    exit_reason = 'SL'
                    exit_price = position['sl']
                elif current['high'] >= position['tp']:
                    exit_signal = True
                    exit_reason = 'TP'
                    exit_price = position['tp']
                elif current['RSI'] > config['rsi_exit_long']:
                    exit_signal = True
                    exit_reason = 'RSI'
            
            if exit_signal:
                profit_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
                balance += balance * (profit_pct / 100)
                
                trades.append({
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'profit_pct': profit_pct,
                    'reason': exit_reason,
                    'bars_held': i - position['entry_bar']
                })
                
                position = None
        
        equity_curve.append(balance)
    
    return trades, equity_curve, filled_orders, cancelled_orders

def main():
    import sys
    
    # Check if M5 or M1 specified
    timeframe = 'M1'
    if len(sys.argv) > 1 and sys.argv[1].upper() == 'M5':
        timeframe = 'M5'
    
    print("=" * 80)
    print(f"LIMIT ORDERS VS MARKET ORDERS BACKTEST - {timeframe}")
    print("=" * 80)
    
    # Connect and get data
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return
    
    print(f"\nFetching {timeframe} data (last 60 days)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    df = connector.get_historical_data('XAUUSD', timeframe, start_date, end_date)
    connector.disconnect()
    
    if df is None or len(df) == 0:
        print("No data received")
        return
    
    print(f"Data points: {len(df)}")
    
    # Calculate indicators
    df = calculate_indicators(df)
    df = df.dropna()
    
    # Config based on timeframe
    if timeframe == 'M5':
        config = {
            'rsi_buy': 30,
            'rsi_exit_long': 70,
            'atr_multiplier': 2.0,
            'profit_target_pct': 0.01
        }
        offsets = [0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10]
    else:  # M1
        config = {
            'rsi_buy': 35,
            'rsi_exit_long': 75,
            'atr_multiplier': 1.5,
            'profit_target_pct': 0.015
        }
        offsets = [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]
    
    print("\n" + "=" * 80)
    print("TESTING MARKET ORDERS (Current Strategy)")
    print("=" * 80)
    
    market_trades, market_equity = backtest_market_orders(df, config)
    
    market_return = ((market_equity[-1] - 10000) / 10000) * 100
    market_wins = len([t for t in market_trades if t['profit_pct'] > 0])
    market_win_rate = (market_wins / len(market_trades)) * 100 if market_trades else 0
    
    print(f"\nTotal trades: {len(market_trades)}")
    print(f"Win rate: {market_win_rate:.1f}%")
    print(f"Final return: {market_return:.1f}%")
    
    # Test different limit offsets
    print("\n" + "=" * 80)
    print("TESTING LIMIT ORDERS (Different Offsets)")
    print("=" * 80)
    
    results = []
    
    for offset in offsets:
        limit_trades, limit_equity, filled, cancelled = backtest_limit_orders(df, config, offset)
        
        limit_return = ((limit_equity[-1] - 10000) / 10000) * 100
        limit_wins = len([t for t in limit_trades if t['profit_pct'] > 0])
        limit_win_rate = (limit_wins / len(limit_trades)) * 100 if limit_trades else 0
        fill_rate = (filled / (filled + cancelled)) * 100 if (filled + cancelled) > 0 else 0
        
        results.append({
            'offset': offset,
            'trades': len(limit_trades),
            'win_rate': limit_win_rate,
            'return': limit_return,
            'filled': filled,
            'cancelled': cancelled,
            'fill_rate': fill_rate
        })
        
        print(f"\nOffset: {offset}%")
        print(f"  Trades: {len(limit_trades)} (filled: {filled}, cancelled: {cancelled})")
        print(f"  Fill rate: {fill_rate:.1f}%")
        print(f"  Win rate: {limit_win_rate:.1f}%")
        print(f"  Return: {limit_return:.1f}%")
        print(f"  vs Market: {limit_return - market_return:+.1f}%")
    
    # Find best offset
    best = max(results, key=lambda x: x['return'])
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nMarket Orders: {market_return:.1f}% return")
    print(f"Best Limit Orders: {best['return']:.1f}% return (offset: {best['offset']}%)")
    print(f"Improvement: {best['return'] - market_return:+.1f}%")
    print(f"\nBest offset fill rate: {best['fill_rate']:.1f}%")
    print(f"Best offset trades: {best['trades']} vs {len(market_trades)} market")
    
    # Plot comparison
    _, limit_equity_best, _, _ = backtest_limit_orders(df, config, best['offset'])
    
    plt.figure(figsize=(12, 6))
    plt.plot(market_equity, label=f'Market Orders ({market_return:.1f}%)', linewidth=2)
    plt.plot(limit_equity_best, label=f'Limit Orders {best["offset"]}% ({best["return"]:.1f}%)', linewidth=2)
    plt.xlabel('Candles')
    plt.ylabel('Balance ($)')
    plt.title(f'Market Orders vs Limit Orders - {timeframe} Strategy')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f'results/limit_orders_comparison_{timeframe}.png', dpi=150)
    print(f"\nChart saved: results/limit_orders_comparison_{timeframe}.png")
    
    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    
    if best['return'] > market_return:
        improvement_pct = ((best['return'] - market_return) / abs(market_return)) * 100
        print(f"\n✅ Limit orders IMPROVE performance by {improvement_pct:.1f}%")
        print(f"\nWhy it works:")
        print(f"  - Better entry prices ({best['offset']}% better)")
        print(f"  - Filters weak signals (cancelled: {best['cancelled']})")
        print(f"  - Still catches {best['fill_rate']:.0f}% of opportunities")
        print(f"\nRecommendation: IMPLEMENT limit orders with {best['offset']}% offset")
    else:
        print(f"\n❌ Limit orders HURT performance")
        print(f"\nWhy it fails:")
        print(f"  - Missing too many trades (fill rate: {best['fill_rate']:.1f}%)")
        print(f"  - Price doesn't retrace enough")
        print(f"  - M1 moves too fast for limit orders")
        print(f"\nRecommendation: KEEP market orders")

if __name__ == '__main__':
    main()
