"""
Optimize M5 parameters for RECENT market conditions
Focus on last 90-120 days with comprehensive parameter search
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
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

def simulate_strategy(df, config, max_positions=2):
    """Simulate strategy with multiple positions"""
    positions = []
    closed_trades = []
    
    position_size = 0.15 / max_positions
    leverage = 25
    
    for idx in range(len(df)):
        row = df.iloc[idx]
        
        # Check exits
        for pos in positions[:]:
            exit_signal = False
            exit_reason = None
            exit_price = None
            
            if pos['type'] == 'LONG':
                if row['close'] >= pos['tp']:
                    exit_signal, exit_reason, exit_price = True, 'TP', pos['tp']
                elif row['close'] <= pos['sl']:
                    exit_signal, exit_reason, exit_price = True, 'SL', pos['sl']
                elif row['RSI'] >= config['rsi_exit_long']:
                    exit_signal, exit_reason, exit_price = True, 'RSI_EXIT', row['close']
            else:  # SHORT
                if row['close'] <= pos['tp']:
                    exit_signal, exit_reason, exit_price = True, 'TP', pos['tp']
                elif row['close'] >= pos['sl']:
                    exit_signal, exit_reason, exit_price = True, 'SL', pos['sl']
                elif row['RSI'] <= config['rsi_exit_short']:
                    exit_signal, exit_reason, exit_price = True, 'RSI_EXIT', row['close']
            
            if exit_signal:
                if pos['type'] == 'LONG':
                    pnl_pct = (exit_price - pos['entry']) / pos['entry']
                else:
                    pnl_pct = (pos['entry'] - exit_price) / pos['entry']
                
                profit_pct = pnl_pct * leverage * position_size
                
                closed_trades.append({
                    'profit_pct': profit_pct,
                    'exit_reason': exit_reason,
                    'bars_held': idx - pos['entry_idx']
                })
                positions.remove(pos)
        
        # Check entries
        if len(positions) < max_positions:
            if row['RSI'] < config['rsi_buy'] and row['uptrend']:
                positions.append({
                    'type': 'LONG',
                    'entry': row['close'],
                    'entry_idx': idx,
                    'sl': row['close'] - (row['ATR'] * config['atr_multiplier']),
                    'tp': row['close'] * (1 + config['profit_target_pct'])
                })
            elif config.get('enable_shorts', True) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                positions.append({
                    'type': 'SHORT',
                    'entry': row['close'],
                    'entry_idx': idx,
                    'sl': row['close'] + (row['ATR'] * config['atr_multiplier']),
                    'tp': row['close'] * (1 - config['profit_target_pct'])
                })
    
    return closed_trades

def analyze_results(trades):
    """Analyze trading results"""
    if len(trades) == 0:
        return None
    
    df = pd.DataFrame(trades)
    winning = df[df['profit_pct'] > 0]
    losing = df[df['profit_pct'] <= 0]
    
    total_return = df['profit_pct'].sum()
    win_rate = len(winning) / len(trades) * 100
    
    avg_win = winning['profit_pct'].mean() if len(winning) > 0 else 0
    avg_loss = losing['profit_pct'].mean() if len(losing) > 0 else 0
    
    gross_profit = winning['profit_pct'].sum() if len(winning) > 0 else 0
    gross_loss = abs(losing['profit_pct'].sum()) if len(losing) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    cumulative = df['profit_pct'].cumsum()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max)
    max_drawdown = drawdown.min()
    
    if len(trades) > 1:
        returns_std = df['profit_pct'].std()
        sharpe = (df['profit_pct'].mean() / returns_std * np.sqrt(252)) if returns_std > 0 else 0
    else:
        sharpe = 0
    
    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'total_return': total_return * 100,
        'avg_win': avg_win * 100,
        'avg_loss': avg_loss * 100,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown * 100,
        'sharpe': sharpe
    }


def main():
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return
    
    print("="*100)
    print("M5 OPTIMIZATION FOR RECENT MARKET CONDITIONS")
    print("="*100)
    
    # Get last 120 days of data
    symbol = 'XAUUSD'
    timeframe = mt5.TIMEFRAME_M5
    bars_needed = 120 * 24 * 60 // 5 + 100
    
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars_needed)
    
    if rates is None or len(rates) == 0:
        print("Failed to get market data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    actual_days = (df['time'].iloc[-1] - df['time'].iloc[0]).days
    print(f"\nData Period: {actual_days} days ({len(df)} bars)")
    print(f"From: {df['time'].iloc[0]}")
    print(f"To: {df['time'].iloc[-1]}")
    
    # Load current config for EMA settings
    with open('config/m5_params.json', 'r') as f:
        current_config = json.load(f)
    
    # Compute indicators
    df = compute_indicators(df, current_config['fast_ema'], current_config['slow_ema'], current_config['rsi_period'])
    
    print("\nOptimizing parameters...")
    print("Testing combinations of:")
    print("  - RSI Buy: 20, 22, 25, 27, 30, 32, 35")
    print("  - RSI Sell: 65, 68, 70, 73, 75, 78, 80")
    print("  - Profit Target: 1.0%, 1.5%, 2.0%, 2.5%, 3.0%")
    print("  - RSI Exit Long: 65, 70, 75")
    print("  - RSI Exit Short: 25, 30, 35")
    
    # Parameter ranges
    rsi_buy_values = [20, 22, 25, 27, 30, 32, 35]
    rsi_sell_values = [65, 68, 70, 73, 75, 78, 80]
    profit_target_values = [0.010, 0.015, 0.020, 0.025, 0.030]
    rsi_exit_long_values = [65, 70, 75]
    rsi_exit_short_values = [25, 30, 35]
    
    atr_mult = 2.0
    
    results = []
    total_combinations = (len(rsi_buy_values) * len(rsi_sell_values) * len(profit_target_values) * 
                         len(rsi_exit_long_values) * len(rsi_exit_short_values))
    
    print(f"\nTesting {total_combinations} combinations...")
    
    count = 0
    for rsi_buy, rsi_sell, profit_target, rsi_exit_long, rsi_exit_short in product(
        rsi_buy_values, rsi_sell_values, profit_target_values, rsi_exit_long_values, rsi_exit_short_values
    ):
        count += 1
        if count % 100 == 0:
            print(f"Progress: {count}/{total_combinations}")
        
        config = {
            'rsi_buy': rsi_buy,
            'rsi_sell': rsi_sell,
            'profit_target_pct': profit_target,
            'rsi_exit_long': rsi_exit_long,
            'rsi_exit_short': rsi_exit_short,
            'atr_multiplier': atr_mult,
            'enable_shorts': True
        }
        
        trades = simulate_strategy(df, config, max_positions=2)
        metrics = analyze_results(trades)
        
        if metrics and metrics['total_trades'] >= 15:  # Minimum 15 trades
            results.append({
                'rsi_buy': rsi_buy,
                'rsi_sell': rsi_sell,
                'profit_target_pct': profit_target * 100,
                'rsi_exit_long': rsi_exit_long,
                'rsi_exit_short': rsi_exit_short,
                **metrics
            })
    
    if len(results) == 0:
        print("\nNo configurations met minimum requirements!")
        mt5.shutdown()
        return
    
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('total_return', ascending=False)
    
    print("\n" + "="*100)
    print("TOP 15 CONFIGURATIONS BY TOTAL RETURN")
    print("="*100)
    
    for i, row in df_results.head(15).iterrows():
        print(f"\n#{df_results.index.get_loc(i) + 1}")
        print(f"  RSI: {row['rsi_buy']:.0f}/{row['rsi_sell']:.0f} | Exit: {row['rsi_exit_long']:.0f}/{row['rsi_exit_short']:.0f} | TP: {row['profit_target_pct']:.1f}%")
        print(f"  Return: {row['total_return']:.1f}% | Trades: {row['total_trades']:.0f} | WR: {row['win_rate']:.1f}%")
        print(f"  Avg Win: {row['avg_win']:.2f}% | Avg Loss: {row['avg_loss']:.2f}% | PF: {row['profit_factor']:.2f}")
        print(f"  Max DD: {row['max_drawdown']:.1f}% | Sharpe: {row['sharpe']:.2f}")
    
    # Best by different metrics
    print("\n" + "="*100)
    print("BEST BY DIFFERENT METRICS")
    print("="*100)
    
    best_return = df_results.iloc[0]
    best_winrate = df_results.nlargest(1, 'win_rate').iloc[0]
    best_sharpe = df_results.nlargest(1, 'sharpe').iloc[0]
    best_pf = df_results.nlargest(1, 'profit_factor').iloc[0]
    
    print(f"\nBest Total Return:")
    print(f"  RSI {best_return['rsi_buy']:.0f}/{best_return['rsi_sell']:.0f}, Exit {best_return['rsi_exit_long']:.0f}/{best_return['rsi_exit_short']:.0f}, TP {best_return['profit_target_pct']:.1f}%")
    print(f"  Return: {best_return['total_return']:.1f}%, Trades: {best_return['total_trades']:.0f}, WR: {best_return['win_rate']:.1f}%")
    
    print(f"\nBest Win Rate:")
    print(f"  RSI {best_winrate['rsi_buy']:.0f}/{best_winrate['rsi_sell']:.0f}, Exit {best_winrate['rsi_exit_long']:.0f}/{best_winrate['rsi_exit_short']:.0f}, TP {best_winrate['profit_target_pct']:.1f}%")
    print(f"  Return: {best_winrate['total_return']:.1f}%, WR: {best_winrate['win_rate']:.1f}%")
    
    print(f"\nBest Sharpe Ratio:")
    print(f"  RSI {best_sharpe['rsi_buy']:.0f}/{best_sharpe['rsi_sell']:.0f}, Exit {best_sharpe['rsi_exit_long']:.0f}/{best_sharpe['rsi_exit_short']:.0f}, TP {best_sharpe['profit_target_pct']:.1f}%")
    print(f"  Return: {best_sharpe['total_return']:.1f}%, Sharpe: {best_sharpe['sharpe']:.2f}")
    
    print(f"\nBest Profit Factor:")
    print(f"  RSI {best_pf['rsi_buy']:.0f}/{best_pf['rsi_sell']:.0f}, Exit {best_pf['rsi_exit_long']:.0f}/{best_pf['rsi_exit_short']:.0f}, TP {best_pf['profit_target_pct']:.1f}%")
    print(f"  Return: {best_pf['total_return']:.1f}%, PF: {best_pf['profit_factor']:.2f}")
    
    # Current config performance
    print("\n" + "="*100)
    print("CURRENT CONFIGURATION PERFORMANCE")
    print("="*100)
    
    current_trades = simulate_strategy(df, current_config, max_positions=2)
    current_metrics = analyze_results(current_trades)
    
    if current_metrics:
        print(f"\nCurrent: RSI {current_config['rsi_buy']}/{current_config['rsi_sell']}, Exit {current_config['rsi_exit_long']}/{current_config['rsi_exit_short']}, TP {current_config['profit_target_pct']*100:.1f}%")
        print(f"  Total Return: {current_metrics['total_return']:.1f}%")
        print(f"  Trades: {current_metrics['total_trades']}")
        print(f"  Win Rate: {current_metrics['win_rate']:.1f}%")
        print(f"  Profit Factor: {current_metrics['profit_factor']:.2f}")
    
    # Recommendation
    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    
    recommended = df_results.iloc[0]
    print(f"\nRecommended Configuration for M5:")
    print(f"  \"rsi_buy\": {recommended['rsi_buy']:.0f},")
    print(f"  \"rsi_sell\": {recommended['rsi_sell']:.0f},")
    print(f"  \"rsi_exit_long\": {recommended['rsi_exit_long']:.0f},")
    print(f"  \"rsi_exit_short\": {recommended['rsi_exit_short']:.0f},")
    print(f"  \"profit_target_pct\": {recommended['profit_target_pct']/100:.3f},")
    print(f"\nExpected Performance (last {actual_days} days):")
    print(f"  Total Return: {recommended['total_return']:.1f}%")
    print(f"  Trade Frequency: {recommended['total_trades']:.0f} trades (~{recommended['total_trades']/actual_days:.1f} per day)")
    print(f"  Win Rate: {recommended['win_rate']:.1f}%")
    print(f"  Profit Factor: {recommended['profit_factor']:.2f}")
    print(f"  Max Drawdown: {recommended['max_drawdown']:.1f}%")
    print(f"  Sharpe Ratio: {recommended['sharpe']:.2f}")
    
    improvement = recommended['total_return'] - (current_metrics['total_return'] if current_metrics else 0)
    print(f"\nImprovement vs Current: {improvement:+.1f}%")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
