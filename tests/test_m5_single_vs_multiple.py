"""
Test M5 bot with single position vs multiple positions
Compare performance to see if M5 benefits from single larger position
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

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

def simulate_strategy(df, config, max_positions=1):
    """Simulate M5 strategy with configurable max positions"""
    
    # Adjust position size based on max positions
    position_size_per_trade = config['position_size_pct'] / max_positions
    
    positions = []
    balance = 10000
    trades = []
    cooldown_until = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Skip if indicators not ready
        if pd.isna(row['RSI']) or pd.isna(row['ATR']):
            continue
        
        # Check exits first
        positions_to_remove = []
        for idx, pos in enumerate(positions):
            should_exit = False
            exit_price = None
            exit_reason = None
            
            # RSI exits
            if pos['type'] == 'LONG':
                if row['RSI'] > config['rsi_exit_long']:
                    should_exit = True
                    exit_price = row['close']
                    exit_reason = 'RSI exit'
            else:  # SHORT
                if row['RSI'] < config['rsi_exit_short']:
                    should_exit = True
                    exit_price = row['close']
                    exit_reason = 'RSI exit'
            
            # Stop loss
            if not should_exit:
                if pos['type'] == 'LONG' and row['low'] <= pos['sl']:
                    should_exit = True
                    exit_price = pos['sl']
                    exit_reason = 'Stop loss'
                elif pos['type'] == 'SHORT' and row['high'] >= pos['sl']:
                    should_exit = True
                    exit_price = pos['sl']
                    exit_reason = 'Stop loss'
            
            # Take profit
            if not should_exit:
                if pos['type'] == 'LONG' and row['high'] >= pos['tp']:
                    should_exit = True
                    exit_price = pos['tp']
                    exit_reason = 'Take profit'
                elif pos['type'] == 'SHORT' and row['low'] <= pos['tp']:
                    should_exit = True
                    exit_price = pos['tp']
                    exit_reason = 'Take profit'
            
            if should_exit:
                # Calculate profit
                if pos['type'] == 'LONG':
                    profit = (exit_price - pos['entry_price']) * 100 * position_size_per_trade * config['leverage']
                else:
                    profit = (pos['entry_price'] - exit_price) * 100 * position_size_per_trade * config['leverage']
                
                balance += profit
                
                trades.append({
                    'type': pos['type'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'profit': profit,
                    'exit_reason': exit_reason,
                    'bars_held': i - pos['entry_bar']
                })
                
                positions_to_remove.append(idx)
                cooldown_until = i + 2  # 2-candle cooldown
        
        # Remove closed positions
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
        
        # Check entry (if not in cooldown and not at max positions)
        if i >= cooldown_until and len(positions) < max_positions:
            # LONG entry
            if row['RSI'] < config['rsi_buy']:
                atr = row['ATR']
                entry_price = row['close']
                sl = entry_price - (atr * config['atr_multiplier'])
                tp = entry_price + (entry_price * config['profit_target_pct'])
                
                positions.append({
                    'type': 'LONG',
                    'entry_price': entry_price,
                    'entry_bar': i,
                    'sl': sl,
                    'tp': tp
                })
            
            # SHORT entry
            elif config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                atr = row['ATR']
                entry_price = row['close']
                sl = entry_price + (atr * config['atr_multiplier'])
                tp = entry_price - (entry_price * config['profit_target_pct'])
                
                positions.append({
                    'type': 'SHORT',
                    'entry_price': entry_price,
                    'entry_bar': i,
                    'sl': sl,
                    'tp': tp
                })
    
    return balance, trades

def analyze_results(trades):
    """Analyze trade results"""
    if not trades:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_profit': 0,
            'avg_profit': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'max_consecutive_losses': 0
        }
    
    winning_trades = [t for t in trades if t['profit'] > 0]
    losing_trades = [t for t in trades if t['profit'] < 0]
    
    total_profit = sum(t['profit'] for t in trades)
    total_wins = sum(t['profit'] for t in winning_trades)
    total_losses = abs(sum(t['profit'] for t in losing_trades))
    
    # Calculate max consecutive losses
    max_consecutive = 0
    current_consecutive = 0
    for t in trades:
        if t['profit'] < 0:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
    
    return {
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': len(winning_trades) / len(trades) * 100 if trades else 0,
        'total_profit': total_profit,
        'avg_profit': total_profit / len(trades) if trades else 0,
        'avg_win': total_wins / len(winning_trades) if winning_trades else 0,
        'avg_loss': total_losses / len(losing_trades) if losing_trades else 0,
        'profit_factor': total_wins / total_losses if total_losses > 0 else float('inf'),
        'max_consecutive_losses': max_consecutive
    }

def main():
    """Run comparison test"""
    print("="*100)
    print("M5 BOT: SINGLE POSITION vs MULTIPLE POSITIONS")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get 90 days of M5 data
    print(f"\nFetching 90 days of M5 data...")
    bars = 90 * 24 * 12  # 90 days * 24 hours * 12 five-minute bars
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars)
    
    if rates is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    mt5.shutdown()
    
    print(f"Loaded {len(df)} bars ({df.iloc[0]['time']} to {df.iloc[-1]['time']})")
    
    # Load M5 config
    config = load_config('config/m5_params.json')
    
    print(f"\nM5 Bot Configuration:")
    print(f"  Base Position Size: {config['position_size_pct']*100}%")
    print(f"  Leverage: {config['leverage']}x")
    print(f"  RSI Buy: {config['rsi_buy']}")
    print(f"  RSI Sell: {config['rsi_sell']}")
    print(f"  RSI Exit Long: {config['rsi_exit_long']}")
    print(f"  RSI Exit Short: {config['rsi_exit_short']}")
    
    # Calculate indicators
    print(f"\nCalculating indicators...")
    df = calculate_indicators(df, config)
    
    # Test configurations
    configs_to_test = [
        {'name': 'Single Position (1x full size)', 'max_positions': 1},
        {'name': 'Multiple Positions (2x half size)', 'max_positions': 2},
    ]
    
    print(f"\n" + "="*100)
    print("RUNNING SIMULATIONS")
    print("="*100)
    
    results = {}
    
    for test_config in configs_to_test:
        name = test_config['name']
        max_positions = test_config['max_positions']
        
        print(f"\n{name}:")
        print(f"  Max Positions: {max_positions}")
        print(f"  Position Size per trade: {config['position_size_pct']/max_positions*100:.2f}%")
        print(f"  Total exposure: {config['position_size_pct']*100}%")
        
        balance, trades = simulate_strategy(df, config, max_positions)
        stats = analyze_results(trades)
        
        return_pct = (balance - 10000) / 10000 * 100
        
        results[name] = {
            'balance': balance,
            'return_pct': return_pct,
            'stats': stats
        }
        
        print(f"\n  Results:")
        print(f"    Final Balance: ${balance:,.2f}")
        print(f"    Return: {return_pct:+.2f}%")
        print(f"    Total Trades: {stats['total_trades']}")
        print(f"    Win Rate: {stats['win_rate']:.1f}%")
        print(f"    Avg Profit/Trade: ${stats['avg_profit']:.2f}")
        print(f"    Profit Factor: {stats['profit_factor']:.2f}")
        print(f"    Max Consecutive Losses: {stats['max_consecutive_losses']}")
    
    # Comparison
    print(f"\n" + "="*100)
    print("COMPARISON")
    print("="*100)
    
    single_return = results['Single Position (1x full size)']['return_pct']
    multiple_return = results['Multiple Positions (2x half size)']['return_pct']
    
    single_trades = results['Single Position (1x full size)']['stats']['total_trades']
    multiple_trades = results['Multiple Positions (2x half size)']['stats']['total_trades']
    
    single_win_rate = results['Single Position (1x full size)']['stats']['win_rate']
    multiple_win_rate = results['Multiple Positions (2x half size)']['stats']['win_rate']
    
    single_max_losses = results['Single Position (1x full size)']['stats']['max_consecutive_losses']
    multiple_max_losses = results['Multiple Positions (2x half size)']['stats']['max_consecutive_losses']
    
    print(f"\n{'Metric':<30} | {'Single':>15} | {'Multiple':>15} | {'Difference':>15}")
    print("-"*100)
    print(f"{'Return':<30} | {single_return:>14.2f}% | {multiple_return:>14.2f}% | {multiple_return-single_return:>+14.2f}%")
    print(f"{'Total Trades':<30} | {single_trades:>15} | {multiple_trades:>15} | {multiple_trades-single_trades:>+15}")
    print(f"{'Win Rate':<30} | {single_win_rate:>14.1f}% | {multiple_win_rate:>14.1f}% | {multiple_win_rate-single_win_rate:>+14.1f}%")
    print(f"{'Max Consecutive Losses':<30} | {single_max_losses:>15} | {multiple_max_losses:>15} | {multiple_max_losses-single_max_losses:>+15}")
    
    # Recommendation
    print(f"\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    improvement_threshold = 10  # 10% improvement to justify change
    
    if multiple_return > single_return * (1 + improvement_threshold/100):
        print(f"\n✓ KEEP MULTIPLE POSITIONS")
        print(f"  Multiple positions show {((multiple_return/single_return - 1)*100):+.1f}% better returns")
        print(f"  Risk is spread across {configs_to_test[1]['max_positions']} positions")
    elif single_return > multiple_return * (1 + improvement_threshold/100):
        print(f"\n✓ SWITCH TO SINGLE POSITION")
        print(f"  Single position shows {((single_return/multiple_return - 1)*100):+.1f}% better returns")
        print(f"  Simpler to manage, fewer trades")
        print(f"\n  Reasons M5 may benefit from single position:")
        print(f"    - Entry signals are rarer (RSI {config['rsi_buy']}/{config['rsi_sell']})")
        print(f"    - Larger position size per trade = better profit per signal")
        print(f"    - Less complexity in position management")
    else:
        print(f"\n→ MARGINAL DIFFERENCE")
        print(f"  Single: {single_return:+.2f}% | Multiple: {multiple_return:+.2f}%")
        print(f"  Difference: {abs(multiple_return-single_return):.2f}% (< {improvement_threshold}% threshold)")
        print(f"\n  Current setup (multiple positions) is fine")
        print(f"  But single position would also work well")
        print(f"  Consider:")
        print(f"    - Multiple positions: Better risk spreading")
        print(f"    - Single position: Simpler management")
    
    # Additional insights
    print(f"\n" + "="*100)
    print("INSIGHTS")
    print("="*100)
    
    print(f"\nM5 Strategy Characteristics:")
    print(f"  - Entry signals are RARE (RSI < {config['rsi_buy']} or > {config['rsi_sell']})")
    print(f"  - Trades: Single={single_trades}, Multiple={multiple_trades} over 90 days")
    print(f"  - That's ~{single_trades/90:.1f} trades/day for single, ~{multiple_trades/90:.1f} for multiple")
    
    if single_trades < multiple_trades * 1.5:
        print(f"\n  → Multiple positions don't significantly increase trade frequency")
        print(f"  → Rare signals mean second position rarely opens")
        print(f"  → Single larger position may be more efficient")
    
    print(f"\nM1 vs M5 Comparison:")
    print(f"  M1: Frequent signals (RSI < 35) → Benefits from multiple positions")
    print(f"  M5: Rare signals (RSI < {config['rsi_buy']}) → May benefit from single position")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
