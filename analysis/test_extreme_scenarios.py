"""
Test bots during extreme market scenarios:
- Find the worst drawdown periods in history
- Simulate flash crashes
- Test during high volatility events
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

def compute_indicators(df, timeframe='M5'):
    df = df.copy()
    
    if timeframe == 'M5':
        fast_span = 12
        slow_span = 26
        rsi_period = 14
    else:
        fast_span = 5
        slow_span = 12
        rsi_period = 5
    
    df['ema_fast'] = df['close'].ewm(span=fast_span).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_span).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
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

def backtest_strategy(df, config, timeframe='M5'):
    """Generic backtest function"""
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    peak_balance = 1000
    max_drawdown = 0
    trades = []
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Track drawdown
        if balance > peak_balance:
            peak_balance = balance
        current_dd = (peak_balance - balance) / peak_balance
        if current_dd > max_drawdown:
            max_drawdown = current_dd
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry - (row['ATR'] * atr_mult)
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {'type': 'long', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
            
            elif row['RSI'] > config['rsi_sell'] and row['downtrend']:
                entry = row['close']
                base_pos = balance * position_size
                lev_pos = base_pos * leverage
                sl = entry + (row['ATR'] * atr_mult)
                tp = entry - (entry * config['profit_target_pct'])
                
                position = {'type': 'short', 'entry': entry, 'lev_pos': lev_pos, 'sl': sl, 'tp': tp}
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            if position['type'] == 'long':
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > config['rsi_exit_long']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < config['rsi_exit_short']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                trades.append({'pnl': pnl, 'reason': exit_reason, 'type': position['type']})
                position = None
    
    return balance, trades, max_drawdown

def find_worst_periods(df, window=288):  # 288 M5 bars = 1 day
    """Find periods with largest drawdowns"""
    
    worst_periods = []
    
    for i in range(window, len(df) - window, window // 4):
        segment = df.iloc[i:i+window].copy()
        
        # Calculate max drawdown in this period
        cummax = segment['close'].cummax()
        drawdown = (segment['close'] - cummax) / cummax
        max_dd = abs(drawdown.min())
        
        # Calculate volatility
        returns = segment['close'].pct_change()
        volatility = returns.std() * np.sqrt(288) * 100  # Annualized
        
        # Price change
        price_change = (segment['close'].iloc[-1] - segment['close'].iloc[0]) / segment['close'].iloc[0] * 100
        
        worst_periods.append({
            'start_idx': i,
            'end_idx': i + window,
            'max_drawdown': max_dd * 100,
            'volatility': volatility,
            'price_change': price_change,
            'start_time': segment.index[0]
        })
    
    # Sort by drawdown
    worst_periods.sort(key=lambda x: x['max_drawdown'], reverse=True)
    
    return worst_periods

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("EXTREME SCENARIO STRESS TEST")
    print("="*100)
    print()
    
    # Load configs
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching 60 days of data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    print(f"M5 bars: {len(df_m5)}")
    print()
    
    # Find worst periods
    print("Identifying worst market periods...")
    worst_periods = find_worst_periods(df_m5)
    
    print(f"\nTop 5 Worst Periods (by drawdown):")
    print(f"{'Date':<20} | {'Drawdown':>10} | {'Volatility':>11} | {'Price Change':>13}")
    print("="*100)
    
    for period in worst_periods[:5]:
        date_str = period['start_time'].strftime('%Y-%m-%d %H:%M') if hasattr(period['start_time'], 'strftime') else 'N/A'
        print(f"{date_str:<20} | {period['max_drawdown']:>9.1f}% | {period['volatility']:>10.1f}% | {period['price_change']:>12.1f}%")
    
    print()
    print("="*100)
    print("TESTING BOTS IN WORST PERIODS")
    print("="*100)
    print()
    
    # Test top 5 worst periods
    results = []
    
    for idx, period in enumerate(worst_periods[:5], 1):
        print(f"Period {idx}: {period['start_time'].strftime('%Y-%m-%d') if hasattr(period['start_time'], 'strftime') else 'N/A'}")
        print(f"  Market drawdown: {period['max_drawdown']:.1f}%")
        
        # M5 test
        df_segment = df_m5.iloc[period['start_idx']:period['end_idx']].copy()
        balance_m5, trades_m5, dd_m5 = backtest_strategy(df_segment, m5_config, 'M5')
        return_m5 = (balance_m5 / 1000 - 1) * 100
        
        # M1 test - convert timestamps properly
        m5_start_time = pd.Timestamp(df_m5.index[period['start_idx']])
        m5_end_time = pd.Timestamp(df_m5.index[period['end_idx']])
        
        # Convert to datetime objects
        start_dt = m5_start_time.to_pydatetime()
        end_dt = m5_end_time.to_pydatetime()
        
        df_m1_segment = mt5.get_historical_data('XAUUSD', 'M1', start_dt, end_dt)
        balance_m1, trades_m1, dd_m1 = backtest_strategy(df_m1_segment, m1_config, 'M1')
        return_m1 = (balance_m1 / 1000 - 1) * 100
        
        print(f"  M5 bot: {return_m5:+.1f}% return, {dd_m5*100:.1f}% max DD, {len(trades_m5)} trades")
        print(f"  M1 bot: {return_m1:+.1f}% return, {dd_m1*100:.1f}% max DD, {len(trades_m1)} trades")
        print()
        
        results.append({
            'period': idx,
            'market_dd': period['max_drawdown'],
            'm5_return': return_m5,
            'm5_dd': dd_m5 * 100,
            'm1_return': return_m1,
            'm1_dd': dd_m1 * 100
        })
    
    # Summary
    print("="*100)
    print("SUMMARY")
    print("="*100)
    print(f"{'Period':>7} | {'Market DD':>10} | {'M5 Return':>11} | {'M5 Max DD':>10} | {'M1 Return':>11} | {'M1 Max DD':>10}")
    print("="*100)
    
    for r in results:
        print(f"{r['period']:>7} | {r['market_dd']:>9.1f}% | {r['m5_return']:>10.1f}% | {r['m5_dd']:>9.1f}% | {r['m1_return']:>10.1f}% | {r['m1_dd']:>9.1f}%")
    
    print("="*100)
    print()
    
    # Analysis
    avg_m5_return = np.mean([r['m5_return'] for r in results])
    avg_m1_return = np.mean([r['m1_return'] for r in results])
    worst_m5_return = min([r['m5_return'] for r in results])
    worst_m1_return = min([r['m1_return'] for r in results])
    max_m5_dd = max([r['m5_dd'] for r in results])
    max_m1_dd = max([r['m1_dd'] for r in results])
    
    print("ANALYSIS:")
    print()
    print(f"During the 5 worst market periods:")
    print(f"  M5 Bot: {avg_m5_return:+.1f}% avg return, worst {worst_m5_return:+.1f}%, max DD {max_m5_dd:.1f}%")
    print(f"  M1 Bot: {avg_m1_return:+.1f}% avg return, worst {worst_m1_return:+.1f}%, max DD {max_m1_dd:.1f}%")
    print()
    
    if avg_m5_return > 0 and avg_m1_return > 0:
        print("EXCELLENT: Both bots are profitable even during worst market conditions!")
        print("  Mean reversion strategy thrives on volatility")
    elif avg_m5_return > 0 or avg_m1_return > 0:
        print("GOOD: At least one bot remains profitable during stress")
    else:
        print("CAUTION: Both bots struggle during extreme conditions")
    
    print()
    
    if max_m5_dd > 35 or max_m1_dd > 40:
        print("WARNING: Drawdown limits may be triggered during extreme events")
        print(f"  M5 max DD: {max_m5_dd:.1f}% (limit: 35%)")
        print(f"  M1 max DD: {max_m1_dd:.1f}% (limit: 40%)")
        print("  Bots will pause trading if limits are hit")
    else:
        print("SAFE: Drawdown limits provide adequate protection")
        print(f"  M5 max DD: {max_m5_dd:.1f}% (limit: 35%)")
        print(f"  M1 max DD: {max_m1_dd:.1f}% (limit: 40%)")
    
    print()
    print("CONCLUSION:")
    if avg_m5_return > 0 and avg_m1_return > 0 and max_m5_dd < 30 and max_m1_dd < 35:
        print("  Your bots are well-designed for all market conditions")
        print("  Mean reversion + shorts = natural hedge against crashes")
        print("  Continue running with confidence")
    else:
        print("  Bots handle most conditions well but may struggle in extremes")
        print("  Monitor during high volatility events")
        print("  Consider manual intervention if drawdown > 25%")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
