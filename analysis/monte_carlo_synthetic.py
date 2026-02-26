"""
Monte Carlo simulation with synthetic market data
Generate thousands of realistic market scenarios to test bot robustness

Synthetic data will include:
- Trending markets (up/down)
- Ranging/sideways markets
- High/low volatility periods
- Mean reversion patterns
- Realistic noise and gaps
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

sys.path.append('.')

def generate_synthetic_market(bars=8640, base_price=5000, trend=0.0, volatility=0.02, 
                              mean_reversion=0.1, noise=0.005):
    """
    Generate synthetic OHLC data with realistic characteristics
    
    Parameters:
    - bars: Number of bars to generate
    - base_price: Starting price
    - trend: Drift per bar (0.0001 = 0.01% per bar)
    - volatility: Standard deviation of returns
    - mean_reversion: Strength of mean reversion (0-1)
    - noise: Random noise level
    """
    np.random.seed(None)  # Different seed each time
    
    prices = [base_price]
    current_price = base_price
    
    for i in range(bars):
        # Trend component
        drift = trend
        
        # Mean reversion (pull back to base price)
        reversion = -mean_reversion * (current_price - base_price) / base_price
        
        # Random walk with volatility
        random_change = np.random.normal(0, volatility)
        
        # Noise
        noise_component = np.random.normal(0, noise)
        
        # Combine components
        total_change = drift + reversion + random_change + noise_component
        
        # Apply change
        current_price = current_price * (1 + total_change)
        prices.append(current_price)
    
    # Generate OHLC from prices
    data = []
    for i in range(len(prices) - 1):
        open_price = prices[i]
        close_price = prices[i + 1]
        
        # High/Low with some randomness
        high_offset = abs(np.random.normal(0, volatility * 0.5))
        low_offset = abs(np.random.normal(0, volatility * 0.5))
        
        high = max(open_price, close_price) * (1 + high_offset)
        low = min(open_price, close_price) * (1 - low_offset)
        
        data.append({
            'time': datetime.now() + timedelta(minutes=i*5),  # M5 bars
            'open': open_price,
            'high': high,
            'low': low,
            'close': close_price,
            'tick_volume': np.random.randint(100, 1000),
            'spread': 0,
            'real_volume': 0
        })
    
    return pd.DataFrame(data)

def compute_indicators(df, config):
    """Compute indicators based on config"""
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

def simulate_m5_strategy(df):
    """Simulate M5 bot with adaptive profit taking"""
    config = {
        'fast_ema': 9,
        'slow_ema': 21,
        'rsi_period': 14,
        'rsi_buy': 25,
        'rsi_sell': 70,
        'atr_multiplier': 2.0,
        'profit_target_pct': 0.01
    }
    
    df = compute_indicators(df, config)
    
    position = None
    balance = 1000
    starting_balance = 1000
    trades = []
    peak_profit = 0
    peak_balance = 1000
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Drawdown check
        drawdown = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        if drawdown > 0.35:  # Max 35% drawdown
            break
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                # Fixed position size based on starting balance
                lev_pos = starting_balance * 0.15 * 25
                sl = entry - (row['ATR'] * config['atr_multiplier'])
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i
                }
                peak_profit = 0
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            current_pnl = current_pnl_pct * position['lev_pos']
            peak_profit = max(peak_profit, current_pnl)
            
            bars_held = i - position['entry_bar']
            
            # Adaptive: profit decline
            if current_pnl > 100 and peak_profit > 100:
                decline_pct = ((peak_profit - current_pnl) / peak_profit) * 100
                if decline_pct > 30:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_DECLINE"
            
            # Adaptive: trend reversal
            if not exit_price and current_pnl > 50 and bars_held >= 3:
                if row['RSI'] > 60 and row['downtrend']:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
            
            # Standard exits
            if not exit_price:
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > config['rsi_sell']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                peak_balance = max(peak_balance, balance)
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0
                })
                
                position = None
                peak_profit = 0
    
    return balance, trades

def simulate_m1_strategy(df):
    """Simulate M1 bot with signal-based exits (convert M5 to M1-like)"""
    config = {
        'fast_ema': 5,
        'slow_ema': 12,
        'rsi_period': 5,
        'rsi_buy': 35,
        'rsi_sell': 75,
        'atr_multiplier': 4.0,
        'profit_target_pct': 0.008
    }
    
    df = compute_indicators(df, config)
    
    position = None
    balance = 1000
    starting_balance = 1000
    trades = []
    peak_balance = 1000
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        
        # Drawdown check
        drawdown = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
        if drawdown > 0.40:  # Max 40% drawdown
            break
        
        if position is None:
            if row['RSI'] < config['rsi_buy']:
                entry = row['close']
                # Fixed position size based on starting balance
                lev_pos = starting_balance * 0.15 * 25
                sl = entry - (row['ATR'] * config['atr_multiplier'])
                tp = entry + (entry * config['profit_target_pct'])
                
                position = {
                    'type': 'long',
                    'entry': entry,
                    'lev_pos': lev_pos,
                    'sl': sl,
                    'tp': tp,
                    'entry_bar': i,
                    'entry_atr': row['ATR']
                }
        
        elif position is not None:
            exit_price = None
            exit_reason = None
            
            current_pnl_pct = (row['close'] - position['entry']) / position['entry']
            current_pnl = current_pnl_pct * position['lev_pos']
            
            bars_held = i - position['entry_bar']
            
            # Adaptive exits (M1 style)
            if current_pnl < 0 and bars_held >= 3:
                price_movement = abs(row['close'] - position['entry'])
                is_sideways = price_movement < position['entry_atr'] * 0.3
                
                # Trend reversal
                if row['downtrend']:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_TREND"
                # Signal fade + sideways
                elif row['RSI'] > 50 and is_sideways:
                    exit_price = row['close']
                    exit_reason = "ADAPTIVE_FADE"
            
            # Time fallback
            if not exit_price and current_pnl < 0 and bars_held >= 10:
                exit_price = row['close']
                exit_reason = "ADAPTIVE_TIME"
            
            # Standard exits
            if not exit_price:
                if row['low'] <= position['sl']:
                    exit_price = position['sl']
                    exit_reason = "SL"
                elif row['high'] >= position['tp']:
                    exit_price = position['tp']
                    exit_reason = "TP"
                elif row['RSI'] > config['rsi_sell']:
                    exit_price = row['close']
                    exit_reason = "RSI"
            
            if exit_price:
                pnl_pct = (exit_price - position['entry']) / position['entry']
                pnl = pnl_pct * position['lev_pos']
                balance += pnl
                peak_balance = max(peak_balance, balance)
                
                trades.append({
                    'pnl': pnl,
                    'reason': exit_reason,
                    'profitable': pnl > 0
                })
                
                position = None
    
    return balance, trades

def main():
    print("=" * 100)
    print("MONTE CARLO SIMULATION - SYNTHETIC MARKET DATA")
    print("=" * 100)
    print()
    print("Testing bots against thousands of synthetic market scenarios")
    print()
    
    # Define market scenarios
    scenarios = [
        {'name': 'Bull Trend', 'trend': 0.0002, 'volatility': 0.015, 'mean_reversion': 0.05},
        {'name': 'Bear Trend', 'trend': -0.0002, 'volatility': 0.015, 'mean_reversion': 0.05},
        {'name': 'Sideways Low Vol', 'trend': 0.0, 'volatility': 0.01, 'mean_reversion': 0.2},
        {'name': 'Sideways High Vol', 'trend': 0.0, 'volatility': 0.03, 'mean_reversion': 0.2},
        {'name': 'High Volatility', 'trend': 0.0001, 'volatility': 0.04, 'mean_reversion': 0.1},
        {'name': 'Mean Reverting', 'trend': 0.0, 'volatility': 0.02, 'mean_reversion': 0.3},
    ]
    
    simulations_per_scenario = 100
    bars_per_sim = 8640  # 30 days of M5 data
    
    print(f"Scenarios: {len(scenarios)}")
    print(f"Simulations per scenario: {simulations_per_scenario}")
    print(f"Total simulations: {len(scenarios) * simulations_per_scenario}")
    print(f"Bars per simulation: {bars_per_sim} (30 days)")
    print()
    
    results = {
        'M5': {scenario['name']: [] for scenario in scenarios},
        'M1': {scenario['name']: [] for scenario in scenarios}
    }
    
    for scenario in scenarios:
        print(f"Testing {scenario['name']}...")
        
        for sim in range(simulations_per_scenario):
            # Generate synthetic data
            df = generate_synthetic_market(
                bars=bars_per_sim,
                base_price=5000,
                trend=scenario['trend'],
                volatility=scenario['volatility'],
                mean_reversion=scenario['mean_reversion']
            )
            
            # Test M5 strategy
            m5_balance, m5_trades = simulate_m5_strategy(df)
            m5_return = (m5_balance / 1000 - 1) * 100
            m5_win_rate = sum(1 for t in m5_trades if t['profitable']) / len(m5_trades) * 100 if m5_trades else 0
            
            results['M5'][scenario['name']].append({
                'return': m5_return,
                'trades': len(m5_trades),
                'win_rate': m5_win_rate,
                'profitable': m5_return > 0
            })
            
            # Test M1 strategy
            m1_balance, m1_trades = simulate_m1_strategy(df)
            m1_return = (m1_balance / 1000 - 1) * 100
            m1_win_rate = sum(1 for t in m1_trades if t['profitable']) / len(m1_trades) * 100 if m1_trades else 0
            
            results['M1'][scenario['name']].append({
                'return': m1_return,
                'trades': len(m1_trades),
                'win_rate': m1_win_rate,
                'profitable': m1_return > 0
            })
        
        print(f"  Completed {simulations_per_scenario} simulations")
    
    print()
    print("=" * 100)
    print("RESULTS BY SCENARIO")
    print("=" * 100)
    print()
    
    for scenario in scenarios:
        print(f"{scenario['name']}:")
        print(f"  Trend: {scenario['trend']:+.4f}, Volatility: {scenario['volatility']:.3f}, Mean Reversion: {scenario['mean_reversion']:.2f}")
        print()
        
        m5_results = results['M5'][scenario['name']]
        m1_results = results['M1'][scenario['name']]
        
        m5_avg_return = np.mean([r['return'] for r in m5_results])
        m5_profitable_pct = sum(1 for r in m5_results if r['profitable']) / len(m5_results) * 100
        m5_avg_win_rate = np.mean([r['win_rate'] for r in m5_results])
        
        m1_avg_return = np.mean([r['return'] for r in m1_results])
        m1_profitable_pct = sum(1 for r in m1_results if r['profitable']) / len(m1_results) * 100
        m1_avg_win_rate = np.mean([r['win_rate'] for r in m1_results])
        
        print(f"  M5: {m5_avg_return:+.1f}% avg return, {m5_profitable_pct:.0f}% profitable, {m5_avg_win_rate:.1f}% win rate")
        print(f"  M1: {m1_avg_return:+.1f}% avg return, {m1_profitable_pct:.0f}% profitable, {m1_avg_win_rate:.1f}% win rate")
        print()
    
    print("=" * 100)
    print("OVERALL STATISTICS")
    print("=" * 100)
    print()
    
    all_m5_returns = []
    all_m1_returns = []
    
    for scenario in scenarios:
        all_m5_returns.extend([r['return'] for r in results['M5'][scenario['name']]])
        all_m1_returns.extend([r['return'] for r in results['M1'][scenario['name']]])
    
    print(f"M5 Bot ({len(all_m5_returns)} simulations):")
    print(f"  Average Return: {np.mean(all_m5_returns):+.1f}%")
    print(f"  Median Return: {np.median(all_m5_returns):+.1f}%")
    print(f"  Std Dev: {np.std(all_m5_returns):.1f}%")
    print(f"  Best: {np.max(all_m5_returns):+.1f}%")
    print(f"  Worst: {np.min(all_m5_returns):+.1f}%")
    print(f"  Profitable: {sum(1 for r in all_m5_returns if r > 0) / len(all_m5_returns) * 100:.1f}%")
    print()
    
    print(f"M1 Bot ({len(all_m1_returns)} simulations):")
    print(f"  Average Return: {np.mean(all_m1_returns):+.1f}%")
    print(f"  Median Return: {np.median(all_m1_returns):+.1f}%")
    print(f"  Std Dev: {np.std(all_m1_returns):.1f}%")
    print(f"  Best: {np.max(all_m1_returns):+.1f}%")
    print(f"  Worst: {np.min(all_m1_returns):+.1f}%")
    print(f"  Profitable: {sum(1 for r in all_m1_returns if r > 0) / len(all_m1_returns) * 100:.1f}%")
    print()
    
    print("=" * 100)
    print("RISK ANALYSIS")
    print("=" * 100)
    print()
    
    m5_losses = [r for r in all_m5_returns if r < 0]
    m1_losses = [r for r in all_m1_returns if r < 0]
    
    if m5_losses:
        print(f"M5 Losses:")
        print(f"  Average Loss: {np.mean(m5_losses):.1f}%")
        print(f"  Worst Loss: {np.min(m5_losses):.1f}%")
        print(f"  Loss Frequency: {len(m5_losses) / len(all_m5_returns) * 100:.1f}%")
        print()
    
    if m1_losses:
        print(f"M1 Losses:")
        print(f"  Average Loss: {np.mean(m1_losses):.1f}%")
        print(f"  Worst Loss: {np.min(m1_losses):.1f}%")
        print(f"  Loss Frequency: {len(m1_losses) / len(all_m1_returns) * 100:.1f}%")
        print()
    
    print("=" * 100)
    print("CONCLUSION")
    print("=" * 100)
    print()
    
    m5_sharpe = np.mean(all_m5_returns) / np.std(all_m5_returns) if np.std(all_m5_returns) > 0 else 0
    m1_sharpe = np.mean(all_m1_returns) / np.std(all_m1_returns) if np.std(all_m1_returns) > 0 else 0
    
    print(f"M5 Sharpe Ratio: {m5_sharpe:.2f}")
    print(f"M1 Sharpe Ratio: {m1_sharpe:.2f}")
    print()
    
    if np.mean(all_m5_returns) > 0 and np.mean(all_m1_returns) > 0:
        print("✅ Both bots are profitable across diverse market conditions")
        print(f"   Combined expected return: {np.mean(all_m5_returns) + np.mean(all_m1_returns):+.1f}%")
    else:
        print("⚠ One or both bots struggle in synthetic markets")
        print("   May need parameter adjustment or additional safety mechanisms")

if __name__ == "__main__":
    main()
