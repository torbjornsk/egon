"""
Comprehensive M5 Analysis - Test current parameters against ALL available data
Compare with previous optimization results
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import json

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

def simulate_with_multiple_positions(df, config, max_positions=2):
    """Simulate strategy allowing multiple positions"""
    positions = []
    closed_trades = []
    
    position_size = 0.15 / max_positions
    leverage = 25
    
    for idx in range(len(df)):
        row = df.iloc[idx]
        
        # Check exits for open positions
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
                    'entry_time': pos['entry_time'],
                    'exit_time': row['time'],
                    'type': pos['type'],
                    'entry': pos['entry'],
                    'exit': exit_price,
                    'profit_pct': profit_pct,
                    'exit_reason': exit_reason,
                    'bars_held': idx - pos['entry_idx']
                })
                positions.remove(pos)
        
        # Check entry conditions
        if len(positions) < max_positions:
            # LONG entry
            if row['RSI'] < config['rsi_buy'] and row['uptrend']:
                positions.append({
                    'type': 'LONG',
                    'entry': row['close'],
                    'entry_time': row['time'],
                    'entry_idx': idx,
                    'sl': row['close'] - (row['ATR'] * config['atr_multiplier']),
                    'tp': row['close'] * (1 + config['profit_target_pct'])
                })
            
            # SHORT entry
            elif config.get('enable_shorts', True) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
                positions.append({
                    'type': 'SHORT',
                    'entry': row['close'],
                    'entry_time': row['time'],
                    'entry_idx': idx,
                    'sl': row['close'] + (row['ATR'] * config['atr_multiplier']),
                    'tp': row['close'] * (1 - config['profit_target_pct'])
                })
    
    return closed_trades


def analyze_trades(trades):
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
    
    exit_reasons = df['exit_reason'].value_counts().to_dict()
    
    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'total_return': total_return * 100,
        'avg_win': avg_win * 100,
        'avg_loss': avg_loss * 100,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown * 100,
        'exit_reasons': exit_reasons,
        'avg_bars_held': df['bars_held'].mean()
    }

def main():
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return
    
    print("="*100)
    print("COMPREHENSIVE M5 STRATEGY ANALYSIS")
    print("="*100)
    
    # Load current config
    with open('config/m5_params.json', 'r') as f:
        config = json.load(f)
    
    print("\nCurrent Configuration:")
    for key in ['fast_ema', 'slow_ema', 'rsi_period', 'rsi_buy', 'rsi_sell', 
                'rsi_exit_long', 'rsi_exit_short', 'atr_multiplier', 'profit_target_pct']:
        print(f"  {key}: {config[key]}")
    
    print("\nClaimed Optimization Results:")
    if '_optimization_results' in config:
        for key, value in config['_optimization_results'].items():
            print(f"  {key}: {value}")
    
    # Test on different time periods
    symbol = 'XAUUSD'
    timeframe = mt5.TIMEFRAME_M5
    
    test_periods = [
        ('30 days', 30 * 24 * 60 // 5 + 100),
        ('60 days', 60 * 24 * 60 // 5 + 100),
        ('90 days', 90 * 24 * 60 // 5 + 100),
        ('120 days', 120 * 24 * 60 // 5 + 100),
        ('ALL AVAILABLE', 50000)  # Get maximum available
    ]
    
    print("\n" + "="*100)
    print("TESTING ACROSS DIFFERENT TIME PERIODS")
    print("="*100)
    
    for period_name, bars_needed in test_periods:
        print(f"\n{'-'*100}")
        print(f"Testing: {period_name}")
        print(f"{'-'*100}")
        
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars_needed)
        
        if rates is None or len(rates) == 0:
            print("Failed to get data")
            continue
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        actual_days = (df['time'].iloc[-1] - df['time'].iloc[0]).days
        print(f"Actual period: {actual_days} days ({len(df)} bars)")
        print(f"From: {df['time'].iloc[0]}")
        print(f"To: {df['time'].iloc[-1]}")
        
        # Compute indicators
        df = compute_indicators(df, config['fast_ema'], config['slow_ema'], config['rsi_period'])
        
        # Simulate with 1 position (original)
        print("\n  Testing with 1 position (original):")
        trades_single = simulate_with_multiple_positions(df, config, max_positions=1)
        results_single = analyze_trades(trades_single)
        
        if results_single:
            print(f"    Trades: {results_single['total_trades']}")
            print(f"    Total Return: {results_single['total_return']:.1f}%")
            print(f"    Win Rate: {results_single['win_rate']:.1f}%")
            print(f"    Profit Factor: {results_single['profit_factor']:.2f}")
            print(f"    Max Drawdown: {results_single['max_drawdown']:.1f}%")
            print(f"    Exit Reasons: {results_single['exit_reasons']}")
        else:
            print("    No trades")
        
        # Simulate with 2 positions (current)
        print("\n  Testing with 2 positions (current):")
        trades_double = simulate_with_multiple_positions(df, config, max_positions=2)
        results_double = analyze_trades(trades_double)
        
        if results_double:
            print(f"    Trades: {results_double['total_trades']}")
            print(f"    Total Return: {results_double['total_return']:.1f}%")
            print(f"    Win Rate: {results_double['win_rate']:.1f}%")
            print(f"    Profit Factor: {results_double['profit_factor']:.2f}")
            print(f"    Max Drawdown: {results_double['max_drawdown']:.1f}%")
            print(f"    Exit Reasons: {results_double['exit_reasons']}")
        else:
            print("    No trades")
    
    mt5.shutdown()
    
    print("\n" + "="*100)
    print("ANALYSIS COMPLETE")
    print("="*100)

if __name__ == "__main__":
    main()
