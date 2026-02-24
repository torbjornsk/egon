import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from itertools import product

def compute_indicators(df, fast_ema=15, slow_ema=20, rsi_period=10):
    df = df.copy()
    
    # EMAs for trend (from genetic algorithm strategy)
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
    # RSI for entry/exit (from your original strategy)
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR for dynamic stops
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Long-term trend for safety
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['severe_downtrend'] = (df['close'] < df['ema_200']) & (df['ema_fast'] < df['ema_200'])
    
    # EMA crossover signals
    df['ema_cross_up'] = (df['ema_fast'] > df['ema_slow']) & (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1))
    df['ema_cross_down'] = (df['ema_fast'] < df['ema_slow']) & (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1))
    
    return df

def run_hybrid_backtest(df, capital=1000,
                       fast_ema=15, slow_ema=20, rsi_period=10,
                       rsi_buy=30, rsi_sell=70,
                       atr_multiplier=2.0,
                       profit_target_pct=0.03,
                       use_ema_filter=True,
                       use_safety_filter=True,
                       enable_compounding=True):
    """
    Hybrid strategy combining:
    1. EMA crossover for trend direction (genetic algorithm)
    2. RSI for precise entry/exit timing (your original)
    3. ATR for dynamic stops (genetic algorithm)
    4. Safety filters for downtrends (final optimized)
    """
    
    df = compute_indicators(df, fast_ema, slow_ema, rsi_period)
    
    position = None
    balance = capital
    starting_balance = capital
    trades = []
    equity_curve = [balance]
    skipped_trades = 0
    
    for i in range(max(fast_ema, slow_ema, rsi_period, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            # ENTRY LOGIC: Combine EMA trend + RSI oversold
            entry_signal = False
            
            # Primary signal: RSI oversold
            if row['RSI'] < rsi_buy:
                entry_signal = True
                
                # Optional: Require EMA uptrend
                if use_ema_filter:
                    if not (row['ema_fast'] > row['ema_slow']):
                        entry_signal = False
                
                # Safety: Skip if severe downtrend
                if use_safety_filter and row['severe_downtrend']:
                    entry_signal = False
                    skipped_trades += 1
            
            if entry_signal:
                # Position sizing
                if enable_compounding:
                    position_size = balance
                else:
                    position_size = starting_balance
                
                # Calculate stop loss using ATR
                stop_distance = row['ATR'] * atr_multiplier
                
                position = {
                    'entry': price,
                    'time': row['time'],
                    'size': position_size,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * profit_target_pct)
                }
        else:
            entry = position['entry']
            change = (price - entry) / entry
            pnl = change * position['size']
            
            # EXIT LOGIC: Multiple conditions
            should_exit = False
            exit_reason = ''
            
            # 1. RSI overbought (take profit)
            if row['RSI'] > rsi_sell:
                should_exit = True
                exit_reason = f'RSI > {rsi_sell}'
            
            # 2. Profit target hit
            elif price >= position['take_profit']:
                should_exit = True
                exit_reason = f'{profit_target_pct*100:.1f}% profit target'
            
            # 3. Stop loss hit (ATR-based)
            elif price <= position['stop_loss']:
                should_exit = True
                exit_reason = 'ATR stop loss'
            
            # 4. EMA crossover down (trend reversal)
            elif use_ema_filter and row['ema_cross_down']:
                if change < 0:  # Only exit on reversal if losing
                    should_exit = True
                    exit_reason = 'EMA crossover down'
            
            if should_exit:
                balance += pnl
                trades.append({
                    'entry_time': position['time'],
                    'exit_time': row['time'],
                    'entry_price': entry,
                    'exit_price': price,
                    'pnl': pnl,
                    'pnl_pct': change * 100,
                    'reason': exit_reason,
                    'balance_after': balance
                })
                position = None
            
            if balance <= 0:
                break
        
        equity_curve.append(balance)
    
    return balance, trades, equity_curve, skipped_trades

def calculate_metrics(balance, trades, equity_curve, capital=1000):
    """Calculate comprehensive performance metrics"""
    if not trades:
        return None
    
    trades_df = pd.DataFrame(trades)
    winning = trades_df[trades_df['pnl'] > 0]
    losing = trades_df[trades_df['pnl'] < 0]
    
    equity_series = pd.Series(equity_curve)
    running_max = equity_series.expanding().max()
    drawdown = (equity_series - running_max) / running_max
    max_dd = drawdown.min()
    
    return_pct = (balance / capital - 1) * 100
    win_rate = len(winning) / len(trades) if trades else 0
    
    # Sharpe-like ratio (return / drawdown)
    risk_adjusted_return = return_pct / abs(max_dd) if max_dd != 0 else 0
    
    # Combined score: balance return, win rate, and risk
    score = return_pct * (1 + win_rate) * (1 - abs(max_dd))
    
    return {
        'balance': balance,
        'return': return_pct,
        'trades': len(trades),
        'win_rate': win_rate * 100,
        'max_dd': max_dd * 100,
        'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
        'avg_loss': losing['pnl'].mean() if len(losing) > 0 else 0,
        'risk_adjusted_return': risk_adjusted_return,
        'score': score
    }

def optimize_hybrid_strategy(df, capital=1000):
    """Optimize hybrid strategy parameters"""
    
    print("Optimizing hybrid strategy parameters...")
    print("This will test multiple combinations to find the best risk-adjusted returns\n")
    
    # Parameter ranges (reduced for faster optimization)
    param_grid = {
        'fast_ema': [15, 20],
        'slow_ema': [20, 30],
        'rsi_period': [10],
        'rsi_buy': [30, 35],
        'rsi_sell': [70, 75],
        'atr_multiplier': [2.0, 2.5, 3.0],
        'profit_target_pct': [0.025, 0.03],
        'use_ema_filter': [True, False],
        'use_safety_filter': [True]
    }
    
    # Generate all combinations
    keys = param_grid.keys()
    values = param_grid.values()
    combinations = [dict(zip(keys, v)) for v in product(*values)]
    
    print(f"Testing {len(combinations)} parameter combinations...")
    
    results = []
    
    for i, params in enumerate(combinations):
        if (i + 1) % 50 == 0:
            print(f"Progress: {i+1}/{len(combinations)}")
        
        # Skip invalid combinations (fast EMA must be < slow EMA)
        if params['fast_ema'] >= params['slow_ema']:
            continue
        
        balance, trades, equity, skipped = run_hybrid_backtest(
            df, capital=capital,
            enable_compounding=True,
            **params
        )
        
        metrics = calculate_metrics(balance, trades, equity, capital)
        
        if metrics:
            result = {**params, **metrics}
            results.append(result)
    
    # Sort by score (risk-adjusted return)
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return results

def main():
    # Connect and get data
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching maximum available data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data: {len(data)} bars from {data['time'].min()} to {data['time'].max()}")
    days_span = (data['time'].max() - data['time'].min()).days
    print(f"Time span: {days_span} days\n")
    
    # Optimize
    results = optimize_hybrid_strategy(data, capital=1000)
    
    # Display top 10
    print("\n" + "="*100)
    print("TOP 10 HYBRID STRATEGY CONFIGURATIONS (Sorted by Risk-Adjusted Score)")
    print("="*100)
    print(f"{'#':<3} {'FastEMA':<8} {'SlowEMA':<8} {'RSI':<4} {'Buy':<4} {'Sell':<5} {'ATR':<5} "
          f"{'Profit%':<8} {'EMA':<4} {'Return%':<9} {'Win%':<7} {'MaxDD%':<8} {'Score':<8}")
    print("-"*100)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<3} {r['fast_ema']:<8} {r['slow_ema']:<8} {r['rsi_period']:<4} "
              f"{r['rsi_buy']:<4} {r['rsi_sell']:<5} {r['atr_multiplier']:<5.1f} "
              f"{r['profit_target_pct']*100:<8.1f} {'Y' if r['use_ema_filter'] else 'N':<4} "
              f"{r['return']:<9.2f} {r['win_rate']:<7.1f} {abs(r['max_dd']):<8.2f} {r['score']:<8.2f}")
    
    # Test best configuration
    best = results[0]
    
    print("\n" + "="*100)
    print("BEST HYBRID STRATEGY CONFIGURATION")
    print("="*100)
    print(f"Parameters:")
    print(f"  Fast EMA: {best['fast_ema']}")
    print(f"  Slow EMA: {best['slow_ema']}")
    print(f"  RSI Period: {best['rsi_period']}")
    print(f"  RSI Buy: {best['rsi_buy']}")
    print(f"  RSI Sell: {best['rsi_sell']}")
    print(f"  ATR Multiplier: {best['atr_multiplier']}")
    print(f"  Profit Target: {best['profit_target_pct']*100:.1f}%")
    print(f"  Use EMA Filter: {best['use_ema_filter']}")
    print(f"  Use Safety Filter: {best['use_safety_filter']}")
    
    print(f"\nPerformance:")
    print(f"  Final Balance: ${best['balance']:.2f}")
    print(f"  Return: {best['return']:.2f}%")
    print(f"  Total Trades: {best['trades']}")
    print(f"  Win Rate: {best['win_rate']:.2f}%")
    print(f"  Max Drawdown: {abs(best['max_dd']):.2f}%")
    print(f"  Avg Win: ${best['avg_win']:.2f}")
    print(f"  Avg Loss: ${best['avg_loss']:.2f}")
    print(f"  Risk-Adjusted Return: {best['risk_adjusted_return']:.2f}")
    
    # Run detailed backtest with best params
    balance, trades, equity, skipped = run_hybrid_backtest(
        data, capital=1000,
        fast_ema=best['fast_ema'],
        slow_ema=best['slow_ema'],
        rsi_period=best['rsi_period'],
        rsi_buy=best['rsi_buy'],
        rsi_sell=best['rsi_sell'],
        atr_multiplier=best['atr_multiplier'],
        profit_target_pct=best['profit_target_pct'],
        use_ema_filter=best['use_ema_filter'],
        use_safety_filter=best['use_safety_filter'],
        enable_compounding=True
    )
    
    # Save best configuration
    config = {
        'strategy': 'hybrid',
        'fast_ema': best['fast_ema'],
        'slow_ema': best['slow_ema'],
        'rsi_period': best['rsi_period'],
        'rsi_buy': best['rsi_buy'],
        'rsi_sell': best['rsi_sell'],
        'atr_multiplier': best['atr_multiplier'],
        'profit_target_pct': best['profit_target_pct'],
        'use_ema_filter': best['use_ema_filter'],
        'use_safety_filter': best['use_safety_filter'],
        'enable_compounding': True
    }
    
    with open('config/hybrid_strategy_params.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nBest configuration saved to: config/hybrid_strategy_params.json")
    
    # Plot results
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curve
    ax = axes[0, 0]
    ax.plot(equity, linewidth=2, color='purple')
    ax.set_title('Equity Curve - Best Hybrid Strategy', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='red', linestyle='--', alpha=0.5, label='Starting Capital')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Trade PnL distribution
    ax = axes[0, 1]
    trades_df = pd.DataFrame(trades)
    ax.hist(trades_df['pnl'], bins=30, alpha=0.7, color='green', edgecolor='black')
    ax.set_title('Trade PnL Distribution', fontsize=14, fontweight='bold')
    ax.set_xlabel('PnL ($)')
    ax.set_ylabel('Frequency')
    ax.axvline(x=0, color='red', linestyle='--', alpha=0.5)
    ax.grid(True, alpha=0.3)
    
    # Top 10 comparison
    ax = axes[1, 0]
    top_10_returns = [r['return'] for r in results[:10]]
    top_10_labels = [f"#{i+1}" for i in range(10)]
    ax.barh(top_10_labels, top_10_returns, color='purple', alpha=0.7)
    ax.set_title('Top 10 Configurations - Returns', fontsize=14, fontweight='bold')
    ax.set_xlabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='x')
    
    # Return vs Max Drawdown scatter
    ax = axes[1, 1]
    returns_all = [r['return'] for r in results[:50]]
    drawdowns_all = [abs(r['max_dd']) for r in results[:50]]
    scatter = ax.scatter(drawdowns_all, returns_all, c=range(50), cmap='viridis', s=100, alpha=0.6)
    ax.scatter([abs(best['max_dd'])], [best['return']], color='red', s=200, marker='*', 
               edgecolors='black', linewidths=2, label='Best', zorder=5)
    ax.set_title('Return vs Risk (Top 50)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('Return (%)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.colorbar(scatter, ax=ax, label='Rank')
    
    plt.tight_layout()
    plt.savefig('results/hybrid_strategy_optimization.png', dpi=150)
    print(f"Chart saved to: results/hybrid_strategy_optimization.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
