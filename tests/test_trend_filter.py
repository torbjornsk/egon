"""
Test baseline strategy vs trend-filtered strategy
Compare performance to see if trend filter improves results
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

def calculate_indicators(df, config, add_trend_filter=False):
    """Calculate indicators with optional trend filter"""
    df = df.copy()
    
    # Standard indicators
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
    
    # Add trend filter if requested
    if add_trend_filter:
        # EMA 200 for longer-term trend
        df['ema_200'] = df['close'].ewm(span=200).mean()
        
        # Strong uptrend: price > EMA 200 and EMA fast > EMA slow
        df['strong_uptrend'] = (df['close'] > df['ema_200']) & (df['ema_fast'] > df['ema_slow'])
        
        # Strong downtrend: price < EMA 200 and EMA fast < EMA slow
        df['strong_downtrend'] = (df['close'] < df['ema_200']) & (df['ema_fast'] < df['ema_slow'])
    
    return df

def simulate_strategy(df, config, max_positions=2, use_trend_filter=False):
    """Simulate strategy with optional trend filter"""
    
    position_size_per_trade = config['position_size_pct'] / max_positions
    
    positions = []
    balance = 10000
    trades = []
    cooldown_until = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        if pd.isna(row['RSI']) or pd.isna(row['ATR']):
            continue
        
        # Check exits
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
            else:
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
                if pos['type'] == 'LONG':
                    profit = (exit_price - pos['entry_price']) * 100 * position_size_per_trade * config['leverage']
                else:
                    profit = (pos['entry_price'] - exit_price) * 100 * position_size_per_trade * config['leverage']
                
                balance += profit
                
                trades.append({
                    'profit': profit,
                    'exit_reason': exit_reason,
                    'type': pos['type']
                })
                
                positions_to_remove.append(idx)
                cooldown_until = i + 2
        
        for idx in reversed(positions_to_remove):
            positions.pop(idx)
        
        # Check entry
        if i >= cooldown_until and len(positions) < max_positions:
            # Apply trend filter if enabled
            can_trade_long = True
            can_trade_short = True
            
            if use_trend_filter and 'strong_uptrend' in row.index:
                # In strong uptrend, avoid LONG entries (mean reversion doesn't work)
                # Allow SHORT entries only if strong downtrend
                if row['strong_uptrend']:
                    can_trade_long = False
                
                if not row['strong_downtrend']:
                    can_trade_short = False
            
            # LONG entry
            if can_trade_long and row['RSI'] < config['rsi_buy']:
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
            elif can_trade_short and config.get('enable_shorts', False) and row['RSI'] > config['rsi_sell'] and row['downtrend']:
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
    
    return_pct = (balance - 10000) / 10000 * 100
    win_rate = sum(1 for t in trades if t['profit'] > 0) / len(trades) * 100 if trades else 0
    
    # Calculate max drawdown
    running_balance = 10000
    peak = 10000
    max_dd = 0
    
    for t in trades:
        running_balance += t['profit']
        if running_balance > peak:
            peak = running_balance
        dd = (peak - running_balance) / peak
        if dd > max_dd:
            max_dd = dd
    
    return {
        'return_pct': return_pct,
        'trades': len(trades),
        'win_rate': win_rate,
        'balance': balance,
        'max_drawdown': max_dd * 100,
        'trades_list': trades
    }

def main():
    """Run comparison test"""
    print("="*100)
    print("TREND FILTER TEST: Baseline vs Trend-Filtered Strategy")
    print("="*100)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Test both M1 and M5
    for bot_name, timeframe, config_path, max_pos in [
        ('M1', mt5.TIMEFRAME_M1, 'config/m1_params.json', 2),
        ('M5', mt5.TIMEFRAME_M5, 'config/m5_params.json', 2)
    ]:
        print(f"\n" + "="*100)
        print(f"{bot_name} BOT ANALYSIS")
        print("="*100)
        
        # Get data
        print(f"\nFetching {bot_name} data...")
        # Use available data (may be less than 90 days for M1)
        bars = 30000 if timeframe == mt5.TIMEFRAME_M1 else 26000
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        
        if rates is None or len(rates) == 0:
            print(f"Failed to get {bot_name} data")
            continue
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        print(f"Loaded {len(df)} bars ({df.iloc[0]['time']} to {df.iloc[-1]['time']})")
        
        # Load config
        config = load_config(config_path)
        
        # Calculate indicators for both strategies
        print(f"Calculating indicators...")
        df_baseline = calculate_indicators(df, config, add_trend_filter=False)
        df_filtered = calculate_indicators(df, config, add_trend_filter=True)
        
        # Run baseline
        print(f"\nRunning BASELINE strategy...")
        baseline_result = simulate_strategy(df_baseline, config, max_pos, use_trend_filter=False)
        
        # Run trend-filtered
        print(f"Running TREND-FILTERED strategy...")
        filtered_result = simulate_strategy(df_filtered, config, max_pos, use_trend_filter=True)
        
        # Compare
        print(f"\n" + "-"*100)
        print(f"RESULTS COMPARISON")
        print("-"*100)
        
        print(f"\n{'Metric':<30} | {'Baseline':>20} | {'Trend-Filtered':>20} | {'Difference':>15}")
        print("-"*100)
        
        metrics = [
            ('Return', baseline_result['return_pct'], filtered_result['return_pct'], '%'),
            ('Total Trades', baseline_result['trades'], filtered_result['trades'], ''),
            ('Win Rate', baseline_result['win_rate'], filtered_result['win_rate'], '%'),
            ('Max Drawdown', baseline_result['max_drawdown'], filtered_result['max_drawdown'], '%'),
            ('Final Balance', baseline_result['balance'], filtered_result['balance'], '$'),
        ]
        
        for name, base_val, filt_val, unit in metrics:
            diff = filt_val - base_val
            if unit == '%':
                print(f"{name:<30} | {base_val:>19.1f}% | {filt_val:>19.1f}% | {diff:>+14.1f}%")
            elif unit == '$':
                print(f"{name:<30} | ${base_val:>18,.2f} | ${filt_val:>18,.2f} | ${diff:>+13,.2f}")
            else:
                print(f"{name:<30} | {base_val:>20.0f} | {filt_val:>20.0f} | {diff:>+15.0f}")
        
        # Analysis
        print(f"\n" + "-"*100)
        print(f"ANALYSIS")
        print("-"*100)
        
        improvement = ((filtered_result['return_pct'] - baseline_result['return_pct']) / abs(baseline_result['return_pct'])) * 100 if baseline_result['return_pct'] != 0 else 0
        
        if filtered_result['return_pct'] > baseline_result['return_pct'] * 1.05:
            print(f"\n✓ TREND FILTER IMPROVES PERFORMANCE")
            print(f"  Return improvement: {improvement:+.1f}%")
            print(f"  Fewer trades: {baseline_result['trades']} → {filtered_result['trades']}")
            print(f"  Better selectivity: Avoids mean reversion in strong trends")
        elif baseline_result['return_pct'] > filtered_result['return_pct'] * 1.05:
            print(f"\n✗ BASELINE PERFORMS BETTER")
            print(f"  Return difference: {improvement:+.1f}%")
            print(f"  Trend filter too restrictive")
            print(f"  Missing profitable opportunities")
        else:
            print(f"\n→ SIMILAR PERFORMANCE")
            print(f"  Return difference: {improvement:+.1f}%")
            print(f"  Trend filter has minimal impact")
            print(f"  Market conditions may not have strong trends")
        
        # Trade analysis
        baseline_stop_losses = sum(1 for t in baseline_result['trades_list'] if t['exit_reason'] == 'Stop loss')
        filtered_stop_losses = sum(1 for t in filtered_result['trades_list'] if t['exit_reason'] == 'Stop loss')
        
        print(f"\nStop Loss Analysis:")
        print(f"  Baseline: {baseline_stop_losses}/{baseline_result['trades']} ({baseline_stop_losses/baseline_result['trades']*100:.1f}%)")
        print(f"  Filtered: {filtered_stop_losses}/{filtered_result['trades']} ({filtered_stop_losses/filtered_result['trades']*100:.1f}%)")
        
        if filtered_stop_losses < baseline_stop_losses:
            print(f"  ✓ Trend filter reduces stop-outs by {baseline_stop_losses - filtered_stop_losses}")
    
    mt5.shutdown()
    
    # Final recommendation
    print(f"\n" + "="*100)
    print("FINAL RECOMMENDATION")
    print("="*100)
    
    print(f"\nBased on 90-day backtest:")
    print(f"\nIf trend filter improves both M1 and M5:")
    print(f"  → IMPLEMENT trend filter")
    print(f"  → Avoids mean reversion in strong trends")
    print(f"  → Reduces stop-outs and improves win rate")
    
    print(f"\nIf trend filter hurts performance:")
    print(f"  → KEEP baseline strategy")
    print(f"  → Trend filter too restrictive")
    print(f"  → Consider other improvements (gap warmup, volatility filter)")
    
    print(f"\nIf results are mixed:")
    print(f"  → Consider ADAPTIVE approach")
    print(f"  → Use trend filter only during high volatility")
    print(f"  → Or only after gap openings")
    
    print(f"\n" + "="*100)

if __name__ == "__main__":
    main()
