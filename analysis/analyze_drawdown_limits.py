"""
Analyze if 35%/40% drawdown limits are appropriate
Check worst-case drawdowns and what they mean for actual P/L
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

def backtest_with_drawdown_tracking(df, config, timeframe='M5'):
    """Backtest and track detailed drawdown info"""
    df = compute_indicators(df, timeframe)
    
    position = None
    balance = 1000
    starting_balance = 1000
    peak_balance = 1000
    max_drawdown = 0
    max_drawdown_info = None
    
    balance_history = []
    
    position_size = config['position_size_pct']
    leverage = config['leverage']
    atr_mult = config['atr_multiplier']
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Track balance history
        balance_history.append({
            'index': i,
            'balance': balance,
            'peak': peak_balance,
            'drawdown': (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        })
        
        # Update peak
        if balance > peak_balance:
            peak_balance = balance
        
        # Track max drawdown
        current_dd = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        if current_dd > max_drawdown:
            max_drawdown = current_dd
            max_drawdown_info = {
                'drawdown_pct': current_dd * 100,
                'peak_balance': peak_balance,
                'current_balance': balance,
                'loss_from_peak': peak_balance - balance,
                'profit_from_start': balance - starting_balance,
                'index': i
            }
        
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
                elif row['RSI'] > config.get('rsi_exit_long', 75):
                    exit_price = row['close']
                    exit_reason = "RSI"
            else:
                if row['high'] >= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['low'] <= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] < config.get('rsi_exit_short', 25):
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                if position['type'] == 'long':
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                else:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                position = None
    
    return balance, max_drawdown, max_drawdown_info, balance_history

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("="*100)
    print("DRAWDOWN LIMIT ANALYSIS")
    print("="*100)
    print()
    
    # Load configs
    with open('config/safe_leveraged_params.json', 'r') as f:
        m5_config = json.load(f)
    
    with open('config/m1_scalping_params.json', 'r') as f:
        m1_config = json.load(f)
    
    print(f"Current limits:")
    print(f"  M5: {m5_config['max_drawdown_limit']*100}%")
    print(f"  M1: {m1_config['max_drawdown_limit']*100}%")
    print()
    
    # Get 60 days of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60)
    
    print("Fetching data...")
    df_m5 = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    df_m1 = mt5.get_historical_data('XAUUSD', 'M1', start_date, end_date)
    print()
    
    # Analyze M5
    print("="*100)
    print("M5 BOT ANALYSIS")
    print("="*100)
    balance_m5, max_dd_m5, dd_info_m5, history_m5 = backtest_with_drawdown_tracking(df_m5, m5_config, 'M5')
    
    print(f"\nFinal balance: ${balance_m5:.2f}")
    print(f"Total return: {(balance_m5/1000-1)*100:+.1f}%")
    print(f"\nMax drawdown: {max_dd_m5*100:.1f}%")
    
    if dd_info_m5:
        print(f"\nWorst drawdown details:")
        print(f"  Peak balance: ${dd_info_m5['peak_balance']:.2f}")
        print(f"  Balance at max DD: ${dd_info_m5['current_balance']:.2f}")
        print(f"  Loss from peak: ${dd_info_m5['loss_from_peak']:.2f}")
        print(f"  Profit from start: ${dd_info_m5['profit_from_start']:+.2f}")
        
        if dd_info_m5['profit_from_start'] > 0:
            print(f"  Status: Still profitable overall (+${dd_info_m5['profit_from_start']:.2f})")
        else:
            print(f"  Status: Below starting balance (${dd_info_m5['profit_from_start']:.2f})")
    
    # Check what would happen at 35% DD
    print(f"\nAt 35% drawdown limit:")
    if dd_info_m5 and dd_info_m5['peak_balance'] > 1000:
        balance_at_35 = dd_info_m5['peak_balance'] * 0.65
        profit_at_35 = balance_at_35 - 1000
        print(f"  If peak was ${dd_info_m5['peak_balance']:.2f}")
        print(f"  35% DD would be: ${balance_at_35:.2f}")
        print(f"  Profit from start: ${profit_at_35:+.2f} ({profit_at_35/1000*100:+.1f}%)")
    
    # Analyze M1
    print()
    print("="*100)
    print("M1 BOT ANALYSIS")
    print("="*100)
    balance_m1, max_dd_m1, dd_info_m1, history_m1 = backtest_with_drawdown_tracking(df_m1, m1_config, 'M1')
    
    print(f"\nFinal balance: ${balance_m1:.2f}")
    print(f"Total return: {(balance_m1/1000-1)*100:+.1f}%")
    print(f"\nMax drawdown: {max_dd_m1*100:.1f}%")
    
    if dd_info_m1:
        print(f"\nWorst drawdown details:")
        print(f"  Peak balance: ${dd_info_m1['peak_balance']:.2f}")
        print(f"  Balance at max DD: ${dd_info_m1['current_balance']:.2f}")
        print(f"  Loss from peak: ${dd_info_m1['loss_from_peak']:.2f}")
        print(f"  Profit from start: ${dd_info_m1['profit_from_start']:+.2f}")
        
        if dd_info_m1['profit_from_start'] > 0:
            print(f"  Status: Still profitable overall (+${dd_info_m1['profit_from_start']:.2f})")
        else:
            print(f"  Status: Below starting balance (${dd_info_m1['profit_from_start']:.2f})")
    
    # Check what would happen at 40% DD
    print(f"\nAt 40% drawdown limit:")
    if dd_info_m1 and dd_info_m1['peak_balance'] > 1000:
        balance_at_40 = dd_info_m1['peak_balance'] * 0.60
        profit_at_40 = balance_at_40 - 1000
        print(f"  If peak was ${dd_info_m1['peak_balance']:.2f}")
        print(f"  40% DD would be: ${balance_at_40:.2f}")
        print(f"  Profit from start: ${profit_at_40:+.2f} ({profit_at_40/1000*100:+.1f}%)")
    
    # Recommendations
    print()
    print("="*100)
    print("RECOMMENDATIONS")
    print("="*100)
    print()
    
    print("Understanding Drawdown:")
    print("  - Drawdown = (Peak - Current) / Peak")
    print("  - NOT the same as loss from starting balance")
    print("  - Example: $1000 → $1500 → $1000 = 33% DD but 0% loss")
    print()
    
    print("Current Limits Assessment:")
    print()
    
    # M5 assessment
    print(f"M5 (35% limit):")
    if max_dd_m5 < 0.20:
        print(f"  Max DD was {max_dd_m5*100:.1f}% - limit is very safe")
        print(f"  Could lower to 25-30% for tighter control")
    elif max_dd_m5 < 0.30:
        print(f"  Max DD was {max_dd_m5*100:.1f}% - limit is appropriate")
        print(f"  35% provides good buffer")
    else:
        print(f"  Max DD was {max_dd_m5*100:.1f}% - close to limit!")
        print(f"  Consider keeping 35% or increasing slightly")
    print()
    
    # M1 assessment
    print(f"M1 (40% limit):")
    if max_dd_m1 < 0.20:
        print(f"  Max DD was {max_dd_m1*100:.1f}% - limit is very safe")
        print(f"  Could lower to 30% for tighter control")
    elif max_dd_m1 < 0.35:
        print(f"  Max DD was {max_dd_m1*100:.1f}% - limit is appropriate")
        print(f"  40% provides good buffer")
    else:
        print(f"  Max DD was {max_dd_m1*100:.1f}% - close to limit!")
        print(f"  Consider keeping 40% or increasing slightly")
    print()
    
    print("IMPORTANT:")
    print("  - Drawdown limits protect against runaway losses")
    print("  - They pause trading, not close positions")
    print("  - Emergency threshold (50% equity loss) is the hard stop")
    print("  - Daily loss limit (15%) catches problems faster")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
