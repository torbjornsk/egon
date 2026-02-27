"""
Optimize M5 bot for extreme conditions with higher profit targets
Test different RSI thresholds and profit targets on historical data
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from itertools import product

def compute_indicators(df, fast_ema, slow_ema, rsi_period):
    """Compute technical indicators"""
    df['ema_fast'] = df['close'].ewm(span=fast_ema, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema, adjust=False).mean()
    df['uptrend'] = df['ema_fast'] > df['ema_slow']
    df['downtrend'] = df['ema_fast'] < df['ema_slow']
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['ATR'] = df['tr'].rolling(window=14).mean()
    
    return df

def simulate_strategy(df, rsi_buy, rsi_sell, profit_target_pct, rsi_exit_long, rsi_exit_short, atr_mult):
    """Simulate trading strategy with given parameters"""
    trades = []
    position = None
    max_positions = 2
    position_size = 0.15 / max_positions  # Split for 2 positions
    leverage = 25
    
    for idx in range(len(df)):
        row = df.iloc[idx]
        
        # Check exit conditions for open position
        if position is not None:
            exit_signal = False
            exit_reason = None
            
            if position['type'] == 'LONG':
                # Take profit
                if row['close'] >= position['tp']:
                    exit_signal = True
                    exit_reason = 'TP'
                # Stop loss
                elif row['close'] <= position['sl']:
                    exit_signal = True
                    exit_reason = 'SL'
                # RSI exit
                elif row['RSI'] >= rsi_exit_long:
                    exit_signal = True
                    exit_reason = 'RSI_EXIT'
            else:  # SHORT
                # Take profit
                if row['close'] <= position['tp']:
                    exit_signal = True
                    exit_reason = 'TP'
                # Stop loss
                elif row['close'] >= position['sl']:
                    exit_signal = True
                    exit_reason = 'SL'
                # RSI exit
                elif row['RSI'] <= rsi_exit_short:
                    exit_signal = True
                    exit_reason = 'RSI_EXIT'
            
            if exit_signal:
                # Calculate profit
                if position['type'] == 'LONG':
                    price_change_pct = (row['close'] - position['entry']) / position['entry']
                else:
                    price_change_pct = (position['entry'] - row['close']) / position['entry']
                
                profit_pct = price_change_pct * leverage * position_size
                
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': row['time'],
                    'type': position['type'],
                    'entry': position['entry'],
                    'exit': row['close'],
                    'profit_pct': profit_pct,
                    'exit_reason': exit_reason,
                    'bars_held': idx - position['entry_idx']
                })
                position = None
        
        # Check entry conditions (only if no position)
        if position is None:
            # LONG entry
            if row['RSI'] < rsi_buy and row['uptrend']:
                atr = row['ATR']
                entry_price = row['close']
                position = {
                    'type': 'LONG',
                    'entry': entry_price,
                    'entry_time': row['time'],
                    'entry_idx': idx,
                    'sl': entry_price - (atr * atr_mult),
                    'tp': entry_price * (1 + profit_target_pct)
                }
            
            # SHORT entry
            elif row['RSI'] > rsi_sell and row['downtrend']:
                atr = row['ATR']
                entry_price = row['close']
                position = {
                    'type': 'SHORT',
                    'entry': entry_price,
                    'entry_time': row['time'],
                    'entry_idx': idx,
                    'sl': entry_price + (atr * atr_mult),
                    'tp': entry_price * (1 - profit_target_pct)
                }
    
    return trades

def analyze_results(trades):
    """Analyze trading results"""
    if len(trades) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'total_return': 0,
            'avg_profit': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'max_drawdown': 0,
            'sharpe': 0
        }
    
    df_trades = pd.DataFrame(trades)
    
    winning_trades = df_trades[df_trades['profit_pct'] > 0]
    losing_trades = df_trades[df_trades['profit_pct'] <= 0]
    
    total_return = df_trades['profit_pct'].sum()
    win_rate = len(winning_trades) / len(trades) * 100
    
    avg_profit = winning_trades['profit_pct'].mean() if len(winning_trades) > 0 else 0
    avg_loss = losing_trades['profit_pct'].mean() if len(losing_trades) > 0 else 0
    
    gross_profit = winning_trades['profit_pct'].sum() if len(winning_trades) > 0 else 0
    gross_loss = abs(losing_trades['profit_pct'].sum()) if len(losing_trades) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Calculate drawdown
    cumulative = df_trades['profit_pct'].cumsum()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max)
    max_drawdown = drawdown.min()
    
    # Sharpe ratio (simplified)
    if len(trades) > 1:
        returns_std = df_trades['profit_pct'].std()
        sharpe = (df_trades['profit_pct'].mean() / returns_std * np.sqrt(252)) if returns_std > 0 else 0
    else:
        sharpe = 0
    
    # Exit reason breakdown
    exit_reasons = df_trades['exit_reason'].value_counts().to_dict()
    
    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'total_return': total_return * 100,
        'avg_profit': avg_profit * 100,
        'avg_loss': avg_loss * 100,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown * 100,
        'sharpe': sharpe,
        'exit_reasons': exit_reasons,
        'avg_bars_held': df_trades['bars_held'].mean()
    }

def main():
    # Initialize MT5
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return
    
    print("Connected to MT5")
    print("Fetching historical data...")
    
    # Get 90 days of M5 data
    symbol = 'XAUUSD'
    timeframe = mt5.TIMEFRAME_M5
    bars_needed = 90 * 24 * 60 // 5 + 100  # 90 days + warmup
    
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars_needed)
    
    if rates is None or len(rates) == 0:
        print("Failed to get market data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"Fetched {len(df)} M5 bars")
    print(f"From: {df['time'].iloc[0]}")
    print(f"To: {df['time'].iloc[-1]}")
    
    # Load current config
    with open('config/m5_params.json', 'r') as f:
        current_config = json.load(f)
    
    # Compute indicators with current settings
    df = compute_indicators(df, current_config['fast_ema'], current_config['slow_ema'], current_config['rsi_period'])
    
    print("\nOptimizing parameters...")
    print("Testing combinations of:")
    print("  - RSI Buy thresholds: 20, 22, 25, 27, 30")
    print("  - RSI Sell thresholds: 70, 73, 75, 78, 80")
    print("  - Profit targets: 1.0%, 1.5%, 2.0%, 2.5%, 3.0%")
    
    # Parameter ranges to test
    rsi_buy_values = [20, 22, 25, 27, 30]
    rsi_sell_values = [70, 73, 75, 78, 80]
    profit_target_values = [0.010, 0.015, 0.020, 0.025, 0.030]
    
    # Fixed parameters
    rsi_exit_long = 70
    rsi_exit_short = 30
    atr_mult = 2.0
    
    results = []
    total_combinations = len(rsi_buy_values) * len(rsi_sell_values) * len(profit_target_values)
    
    print(f"\nTesting {total_combinations} combinations...")
    
    for i, (rsi_buy, rsi_sell, profit_target) in enumerate(product(rsi_buy_values, rsi_sell_values, profit_target_values), 1):
        if i % 10 == 0:
            print(f"Progress: {i}/{total_combinations}")
        
        trades = simulate_strategy(df, rsi_buy, rsi_sell, profit_target, rsi_exit_long, rsi_exit_short, atr_mult)
        metrics = analyze_results(trades)
        
        results.append({
            'rsi_buy': rsi_buy,
            'rsi_sell': rsi_sell,
            'profit_target_pct': profit_target * 100,
            **metrics
        })
    
    # Convert to DataFrame and sort
    df_results = pd.DataFrame(results)
    
    # Filter for reasonable trade frequency (at least 20 trades in 90 days)
    df_results = df_results[df_results['total_trades'] >= 20]
    
    if len(df_results) == 0:
        print("\nNo configurations met minimum trade frequency requirement!")
        mt5.shutdown()
        return
    
    # Sort by total return
    df_results = df_results.sort_values('total_return', ascending=False)
    
    print("\n" + "="*100)
    print("TOP 10 CONFIGURATIONS BY TOTAL RETURN")
    print("="*100)
    
    for i, row in df_results.head(10).iterrows():
        print(f"\n#{df_results.index.get_loc(i) + 1}")
        print(f"  RSI Buy: {row['rsi_buy']:.0f} | RSI Sell: {row['rsi_sell']:.0f} | Profit Target: {row['profit_target_pct']:.1f}%")
        print(f"  Total Return: {row['total_return']:.1f}% | Trades: {row['total_trades']:.0f} | Win Rate: {row['win_rate']:.1f}%")
        print(f"  Avg Profit: {row['avg_profit']:.2f}% | Avg Loss: {row['avg_loss']:.2f}% | Profit Factor: {row['profit_factor']:.2f}")
        print(f"  Max Drawdown: {row['max_drawdown']:.1f}% | Sharpe: {row['sharpe']:.2f}")
        print(f"  Avg Bars Held: {row['avg_bars_held']:.1f} ({row['avg_bars_held']*5:.0f} minutes)")
        if 'exit_reasons' in row and row['exit_reasons']:
            print(f"  Exit Reasons: {row['exit_reasons']}")
    
    # Best by different metrics
    print("\n" + "="*100)
    print("BEST BY DIFFERENT METRICS")
    print("="*100)
    
    best_return = df_results.iloc[0]
    best_winrate = df_results.nlargest(1, 'win_rate').iloc[0]
    best_sharpe = df_results.nlargest(1, 'sharpe').iloc[0]
    best_pf = df_results.nlargest(1, 'profit_factor').iloc[0]
    
    print(f"\nBest Total Return:")
    print(f"  RSI {best_return['rsi_buy']:.0f}/{best_return['rsi_sell']:.0f}, TP {best_return['profit_target_pct']:.1f}%")
    print(f"  Return: {best_return['total_return']:.1f}%, Trades: {best_return['total_trades']:.0f}, WR: {best_return['win_rate']:.1f}%")
    
    print(f"\nBest Win Rate:")
    print(f"  RSI {best_winrate['rsi_buy']:.0f}/{best_winrate['rsi_sell']:.0f}, TP {best_winrate['profit_target_pct']:.1f}%")
    print(f"  Return: {best_winrate['total_return']:.1f}%, Trades: {best_winrate['total_trades']:.0f}, WR: {best_winrate['win_rate']:.1f}%")
    
    print(f"\nBest Sharpe Ratio:")
    print(f"  RSI {best_sharpe['rsi_buy']:.0f}/{best_sharpe['rsi_sell']:.0f}, TP {best_sharpe['profit_target_pct']:.1f}%")
    print(f"  Return: {best_sharpe['total_return']:.1f}%, Trades: {best_sharpe['total_trades']:.0f}, Sharpe: {best_sharpe['sharpe']:.2f}")
    
    print(f"\nBest Profit Factor:")
    print(f"  RSI {best_pf['rsi_buy']:.0f}/{best_pf['rsi_sell']:.0f}, TP {best_pf['profit_target_pct']:.1f}%")
    print(f"  Return: {best_pf['total_return']:.1f}%, PF: {best_pf['profit_factor']:.2f}, WR: {best_pf['win_rate']:.1f}%")
    
    # Current configuration performance
    print("\n" + "="*100)
    print("CURRENT CONFIGURATION PERFORMANCE")
    print("="*100)
    
    current_trades = simulate_strategy(
        df,
        current_config['rsi_buy'],
        current_config['rsi_sell'],
        current_config['profit_target_pct'],
        current_config['rsi_exit_long'],
        current_config['rsi_exit_short'],
        current_config['atr_multiplier']
    )
    current_metrics = analyze_results(current_trades)
    
    print(f"\nCurrent: RSI {current_config['rsi_buy']}/{current_config['rsi_sell']}, TP {current_config['profit_target_pct']*100:.1f}%")
    print(f"  Total Return: {current_metrics['total_return']:.1f}%")
    print(f"  Trades: {current_metrics['total_trades']}")
    print(f"  Win Rate: {current_metrics['win_rate']:.1f}%")
    print(f"  Profit Factor: {current_metrics['profit_factor']:.2f}")
    print(f"  Max Drawdown: {current_metrics['max_drawdown']:.1f}%")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    recommended = df_results.iloc[0]
    print(f"\nRecommended Configuration:")
    print(f"  rsi_buy: {recommended['rsi_buy']:.0f}")
    print(f"  rsi_sell: {recommended['rsi_sell']:.0f}")
    print(f"  profit_target_pct: {recommended['profit_target_pct']/100:.3f} ({recommended['profit_target_pct']:.1f}%)")
    print(f"\nExpected Performance:")
    print(f"  Total Return: {recommended['total_return']:.1f}% over 90 days")
    print(f"  Trade Frequency: {recommended['total_trades']:.0f} trades (~{recommended['total_trades']/90:.1f} per day)")
    print(f"  Win Rate: {recommended['win_rate']:.1f}%")
    print(f"  Risk: Max Drawdown {recommended['max_drawdown']:.1f}%")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
