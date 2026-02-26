"""
Optimize M1 parameters based on 7-day analysis findings

Key issues identified:
1. Profit factor too low (1.09, target >1.5)
2. Win/Loss ratio too low (1.13, target >1.5)
3. SHORT trades underperforming ($7 vs $165 for LONG)
4. Large losses (>$10) are the main problem
5. Quick losses (<3min) still significant

Test improvements:
- Disable SHORT trades (focus on LONG only)
- Stricter entry filters (lower RSI thresholds)
- Tighter stop loss (reduce large losses)
- Wider profit targets (improve win/loss ratio)
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
    return True

def get_historical_data(symbol="XAUUSD", timeframe=mt5.TIMEFRAME_M1, days=7):
    """Get historical candle data"""
    # Get extra days for indicator warmup
    start_date = datetime.now() - timedelta(days=days+1)
    rates = mt5.copy_rates_range(symbol, timeframe, start_date, datetime.now())
    
    if rates is None or len(rates) == 0:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calculate_indicators(df, fast_ema=5, slow_ema=12, rsi_period=5):
    """Calculate technical indicators"""
    # EMA
    df['ema_fast'] = df['close'].ewm(span=fast_ema, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    return df

def backtest_strategy(df, params):
    """Backtest a strategy configuration"""
    df = df.copy()
    df = calculate_indicators(
        df, 
        fast_ema=params['fast_ema'],
        slow_ema=params['slow_ema'],
        rsi_period=params['rsi_period']
    )
    
    # Drop NaN rows
    df = df.dropna().reset_index(drop=True)
    
    if len(df) < 100:
        print(f"  Not enough data after indicator calculation: {len(df)} rows")
        return None
    
    positions = []
    balance = 10000
    equity_curve = []
    trades_log = []
    
    for i in range(len(df)):
        current = df.iloc[i]
        
        # Check for exits first
        for pos in positions[:]:
            duration_min = (current['time'] - pos['entry_time']).total_seconds() / 60
            
            # Exit conditions
            exit_signal = False
            exit_reason = ""
            
            if pos['type'] == 'LONG':
                # Take profit
                if current['close'] >= pos['tp']:
                    exit_signal = True
                    exit_reason = "TP"
                # Stop loss
                elif current['close'] <= pos['sl']:
                    exit_signal = True
                    exit_reason = "SL"
                # RSI exit
                elif current['rsi'] >= params['rsi_exit_long']:
                    exit_signal = True
                    exit_reason = "RSI"
                # Time-based exit (10 min)
                elif duration_min >= 10 and current['close'] < pos['entry_price']:
                    exit_signal = True
                    exit_reason = "TIME"
            
            else:  # SHORT
                # Take profit
                if current['close'] <= pos['tp']:
                    exit_signal = True
                    exit_reason = "TP"
                # Stop loss
                elif current['close'] >= pos['sl']:
                    exit_signal = True
                    exit_reason = "SL"
                # RSI exit
                elif current['rsi'] <= params['rsi_exit_short']:
                    exit_signal = True
                    exit_reason = "RSI"
                # Time-based exit (10 min)
                elif duration_min >= 10 and current['close'] > pos['entry_price']:
                    exit_signal = True
                    exit_reason = "TIME"
            
            if exit_signal:
                # Calculate profit
                if pos['type'] == 'LONG':
                    profit = (current['close'] - pos['entry_price']) * pos['volume'] * 100
                else:
                    profit = (pos['entry_price'] - current['close']) * pos['volume'] * 100
                
                balance += profit
                pos['exit_price'] = current['close']
                pos['exit_time'] = current['time']
                pos['profit'] = profit
                pos['exit_reason'] = exit_reason
                pos['duration_min'] = duration_min
                
                trades_log.append(pos.copy())
                positions.remove(pos)
        
        # Check for new entries (max 2 positions)
        if len(positions) < 2:
            trend = "UP" if current['ema_fast'] > current['ema_slow'] else "DOWN"
            
            # LONG entry
            if (params['enable_longs'] and 
                trend == "UP" and 
                current['rsi'] < params['rsi_buy']):
                
                volume = 0.01  # Fixed for backtesting
                sl = current['close'] - (current['atr'] * params['atr_multiplier'])
                tp = current['close'] * (1 + params['profit_target_pct'])
                
                positions.append({
                    'type': 'LONG',
                    'entry_price': current['close'],
                    'entry_time': current['time'],
                    'volume': volume,
                    'sl': sl,
                    'tp': tp
                })
            
            # SHORT entry
            elif (params['enable_shorts'] and 
                  trend == "DOWN" and 
                  current['rsi'] > params['rsi_sell']):
                
                volume = 0.01
                sl = current['close'] + (current['atr'] * params['atr_multiplier'])
                tp = current['close'] * (1 - params['profit_target_pct'])
                
                positions.append({
                    'type': 'SHORT',
                    'entry_price': current['close'],
                    'entry_time': current['time'],
                    'volume': volume,
                    'sl': sl,
                    'tp': tp
                })
        
        equity_curve.append(balance)
    
    # Close any remaining positions at last price
    for pos in positions:
        if pos['type'] == 'LONG':
            profit = (df.iloc[-1]['close'] - pos['entry_price']) * pos['volume'] * 100
        else:
            profit = (pos['entry_price'] - df.iloc[-1]['close']) * pos['volume'] * 100
        
        balance += profit
        pos['exit_price'] = df.iloc[-1]['close']
        pos['exit_time'] = df.iloc[-1]['time']
        pos['profit'] = profit
        pos['exit_reason'] = "EOD"
        pos['duration_min'] = (df.iloc[-1]['time'] - pos['entry_time']).total_seconds() / 60
        trades_log.append(pos.copy())
    
    # Calculate metrics
    if not trades_log:
        print(f"  No trades generated")
        return None
    
    profits = [p['profit'] for p in trades_log]
    wins = [p for p in trades_log if p['profit'] > 0]
    losses = [p for p in trades_log if p['profit'] < 0]
    
    total_profit = sum(profits)
    win_rate = len(wins) / len(trades_log) if trades_log else 0
    
    avg_win = np.mean([p['profit'] for p in wins]) if wins else 0
    avg_loss = np.mean([p['profit'] for p in losses]) if losses else 0
    
    profit_factor = abs(sum([p['profit'] for p in wins]) / sum([p['profit'] for p in losses])) if losses and wins else 0
    
    return {
        'total_profit': total_profit,
        'num_trades': len(trades_log),
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'win_loss_ratio': abs(avg_win / avg_loss) if avg_loss != 0 else 0,
        'max_equity': max(equity_curve),
        'min_equity': min(equity_curve),
        'final_balance': balance
    }

def test_configurations():
    """Test different parameter configurations"""
    
    # Current parameters
    current_params = {
        'fast_ema': 5,
        'slow_ema': 12,
        'rsi_period': 5,
        'rsi_buy': 35,
        'rsi_sell': 65,
        'rsi_exit_long': 75,
        'rsi_exit_short': 25,
        'atr_multiplier': 4.0,
        'profit_target_pct': 0.008,
        'enable_longs': True,
        'enable_shorts': True
    }
    
    # Test configurations
    configs = [
        {
            'name': 'Current (Baseline)',
            'params': current_params.copy()
        },
        {
            'name': 'LONG Only',
            'params': {**current_params, 'enable_shorts': False}
        },
        {
            'name': 'LONG Only + Stricter RSI',
            'params': {**current_params, 'enable_shorts': False, 'rsi_buy': 30}
        },
        {
            'name': 'LONG Only + Tighter SL',
            'params': {**current_params, 'enable_shorts': False, 'atr_multiplier': 3.0}
        },
        {
            'name': 'LONG Only + Wider TP',
            'params': {**current_params, 'enable_shorts': False, 'profit_target_pct': 0.010}
        },
        {
            'name': 'LONG Only + All Improvements',
            'params': {
                **current_params,
                'enable_shorts': False,
                'rsi_buy': 30,
                'atr_multiplier': 3.0,
                'profit_target_pct': 0.010
            }
        }
    ]
    
    return configs

def main():
    print("M1 Strategy Optimization Based on 7-Day Analysis")
    print("="*80)
    
    if not connect_mt5():
        return
    
    # Get historical data
    print("\nFetching historical data...")
    df = get_historical_data(days=7)
    
    if df is None:
        print("Failed to fetch data")
        mt5.shutdown()
        return
    
    print(f"Loaded {len(df)} candles")
    
    # Test configurations
    configs = test_configurations()
    results = []
    
    print("\nTesting configurations...")
    print("="*80)
    
    for config in configs:
        print(f"\nTesting: {config['name']}")
        result = backtest_strategy(df, config['params'])
        
        if result:
            result['name'] = config['name']
            result['params'] = config['params']
            results.append(result)
            
            print(f"  Trades: {result['num_trades']}")
            print(f"  Win Rate: {result['win_rate']*100:.1f}%")
            print(f"  Profit Factor: {result['profit_factor']:.2f}")
            print(f"  Win/Loss Ratio: {result['win_loss_ratio']:.2f}")
            print(f"  Total Profit: ${result['total_profit']:.2f}")
    
    # Sort by profit factor
    results.sort(key=lambda x: x['profit_factor'], reverse=True)
    
    print("\n" + "="*80)
    print("RESULTS SUMMARY (sorted by Profit Factor)")
    print("="*80)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['name']}")
        print(f"   Profit Factor: {result['profit_factor']:.2f}")
        print(f"   Win/Loss Ratio: {result['win_loss_ratio']:.2f}")
        print(f"   Win Rate: {result['win_rate']*100:.1f}%")
        print(f"   Total Profit: ${result['total_profit']:.2f}")
        print(f"   Trades: {result['num_trades']}")
    
    # Recommend best configuration
    if results:
        best = results[0]
        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80)
        print(f"\nBest configuration: {best['name']}")
        print(f"Profit Factor: {best['profit_factor']:.2f} (current: 1.09)")
        print(f"Win/Loss Ratio: {best['win_loss_ratio']:.2f} (current: 1.13)")
        
        if best['profit_factor'] > 1.5:
            print("\n✅ This configuration meets the target profit factor (>1.5)")
            print("\nRecommended parameters:")
            print(json.dumps(best['params'], indent=2))
        else:
            print("\n⚠️  Even the best configuration doesn't meet target profit factor")
            print("   Consider: More conservative approach or different strategy")
    
    mt5.shutdown()
    print("\n" + "="*80)
    print("Optimization complete!")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
