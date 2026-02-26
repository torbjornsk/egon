import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from itertools import product

def compute_indicators(df, fast_ema=20, slow_ema=30, rsi_period=10):
    df = df.copy()
    
    # EMAs for trend
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
    # RSI for entry/exit
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
    
    # Long-term trend
    df['ema_200'] = df['close'].ewm(span=200).mean()
    
    # Trend direction
    df['uptrend'] = (df['ema_fast'] > df['ema_slow']) & (df['close'] > df['ema_200'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow']) & (df['close'] < df['ema_200'])
    
    return df

def run_bidirectional_backtest(df, capital=1000,
                               fast_ema=20, slow_ema=30, rsi_period=10,
                               rsi_buy=35, rsi_sell=75,
                               atr_multiplier=3.0,
                               profit_target_pct=0.025,
                               enable_shorts=True,
                               enable_compounding=True):
    """
    Bidirectional strategy:
    - LONG: RSI oversold in uptrend
    - SHORT: RSI overbought in downtrend
    """
    
    df = compute_indicators(df, fast_ema, slow_ema, rsi_period)
    
    position = None
    balance = capital
    starting_balance = capital
    trades = []
    equity_curve = [balance]
    
    for i in range(max(fast_ema, slow_ema, rsi_period, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            # LONG ENTRY: RSI oversold
            if row['RSI'] < rsi_buy:
                # Position sizing
                if enable_compounding:
                    position_size = balance
                else:
                    position_size = starting_balance
                
                stop_distance = row['ATR'] * atr_multiplier
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'time': row['time'],
                    'size': position_size,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * profit_target_pct)
                }
            
            # SHORT ENTRY: RSI overbought (if shorts enabled)
            elif enable_shorts and row['RSI'] > rsi_sell:
                # Only short in downtrend
                if row['downtrend']:
                    if enable_compounding:
                        position_size = balance
                    else:
                        position_size = starting_balance
                    
                    stop_distance = row['ATR'] * atr_multiplier
                    
                    position = {
                        'type': 'short',
                        'entry': price,
                        'time': row['time'],
                        'size': position_size,
                        'stop_loss': price + stop_distance,
                        'take_profit': price - (price * profit_target_pct)
                    }
        else:
            entry = position['entry']
            
            # Calculate PnL based on position type
            if position['type'] == 'long':
                change = (price - entry) / entry
            else:  # short
                change = (entry - price) / entry
            
            pnl = change * position['size']
            
            # EXIT LOGIC
            should_exit = False
            exit_reason = ''
            
            if position['type'] == 'long':
                # Long exit conditions
                if row['RSI'] > rsi_sell:
                    should_exit = True
                    exit_reason = f'RSI > {rsi_sell}'
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = f'{profit_target_pct*100:.1f}% profit'
                elif price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
                elif row['downtrend']:  # Trend reversal
                    if change < 0:
                        should_exit = True
                        exit_reason = 'Trend reversal'
            
            else:  # short position
                # Short exit conditions
                if row['RSI'] < rsi_buy:
                    should_exit = True
                    exit_reason = f'RSI < {rsi_buy}'
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = f'{profit_target_pct*100:.1f}% profit'
                elif price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
                elif row['uptrend']:  # Trend reversal
                    if change < 0:
                        should_exit = True
                        exit_reason = 'Trend reversal'
            
            if should_exit:
                balance += pnl
                trades.append({
                    'type': position['type'],
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
    
    return balance, trades, equity_curve

def calculate_metrics(balance, trades, equity_curve, capital=1000):
    """Calculate performance metrics"""
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
    
    # Count long vs short trades
    long_trades = trades_df[trades_df['type'] == 'long']
    short_trades = trades_df[trades_df['type'] == 'short']
    
    long_wins = long_trades[long_trades['pnl'] > 0]
    short_wins = short_trades[short_trades['pnl'] > 0]
    
    return {
        'balance': balance,
        'return': return_pct,
        'trades': len(trades),
        'long_trades': len(long_trades),
        'short_trades': len(short_trades),
        'win_rate': win_rate * 100,
        'long_win_rate': len(long_wins) / len(long_trades) * 100 if len(long_trades) > 0 else 0,
        'short_win_rate': len(short_wins) / len(short_trades) * 100 if len(short_trades) > 0 else 0,
        'max_dd': max_dd * 100,
        'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
        'avg_loss': losing['pnl'].mean() if len(losing) > 0 else 0,
        'score': return_pct * (1 + win_rate) * (1 - abs(max_dd))
    }

def optimize_bidirectional(df, capital=1000):
    """Optimize bidirectional strategy"""
    
    print("Optimizing bidirectional strategy...")
    print("Testing both long-only and long+short configurations\n")
    
    param_grid = {
        'fast_ema': [15, 20],
        'slow_ema': [25, 30],
        'rsi_period': [10],
        'rsi_buy': [30, 35],
        'rsi_sell': [70, 75],
        'atr_multiplier': [2.5, 3.0],
        'profit_target_pct': [0.025, 0.03],
        'enable_shorts': [True, False]
    }
    
    keys = param_grid.keys()
    values = param_grid.values()
    combinations = [dict(zip(keys, v)) for v in product(*values)]
    
    print(f"Testing {len(combinations)} combinations...")
    
    results = []
    
    for i, params in enumerate(combinations):
        if (i + 1) % 20 == 0:
            print(f"Progress: {i+1}/{len(combinations)}")
        
        if params['fast_ema'] >= params['slow_ema']:
            continue
        
        balance, trades, equity = run_bidirectional_backtest(
            df, capital=capital,
            enable_compounding=True,
            **params
        )
        
        metrics = calculate_metrics(balance, trades, equity, capital)
        
        if metrics:
            result = {**params, **metrics}
            results.append(result)
    
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
    results = optimize_bidirectional(data, capital=1000)
    
    # Display results
    print("\n" + "="*110)
    print("TOP 10 CONFIGURATIONS")
    print("="*110)
    print(f"{'#':<3} {'FastEMA':<8} {'SlowEMA':<8} {'RSI':<4} {'Buy':<4} {'Sell':<5} {'ATR':<5} "
          f"{'Profit%':<8} {'Shorts':<7} {'Return%':<9} {'Win%':<7} {'MaxDD%':<8} {'Score':<8}")
    print("-"*110)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<3} {r['fast_ema']:<8} {r['slow_ema']:<8} {r['rsi_period']:<4} "
              f"{r['rsi_buy']:<4} {r['rsi_sell']:<5} {r['atr_multiplier']:<5.1f} "
              f"{r['profit_target_pct']*100:<8.1f} {'YES' if r['enable_shorts'] else 'NO':<7} "
              f"{r['return']:<9.2f} {r['win_rate']:<7.1f} {abs(r['max_dd']):<8.2f} {r['score']:<8.2f}")
    
    # Compare best long-only vs best bidirectional
    best_overall = results[0]
    best_long_only = next((r for r in results if not r['enable_shorts']), None)
    best_bidirectional = next((r for r in results if r['enable_shorts']), None)
    
    print("\n" + "="*110)
    print("COMPARISON: LONG-ONLY vs BIDIRECTIONAL")
    print("="*110)
    
    if best_long_only:
        print("\nBEST LONG-ONLY STRATEGY:")
        print(f"  Return: {best_long_only['return']:.2f}%")
        print(f"  Max Drawdown: {abs(best_long_only['max_dd']):.2f}%")
        print(f"  Win Rate: {best_long_only['win_rate']:.2f}%")
        print(f"  Total Trades: {best_long_only['trades']}")
    
    if best_bidirectional:
        print("\nBEST BIDIRECTIONAL STRATEGY:")
        print(f"  Return: {best_bidirectional['return']:.2f}%")
        print(f"  Max Drawdown: {abs(best_bidirectional['max_dd']):.2f}%")
        print(f"  Win Rate: {best_bidirectional['win_rate']:.2f}%")
        print(f"  Total Trades: {best_bidirectional['trades']}")
        print(f"  Long Trades: {best_bidirectional['long_trades']} (Win rate: {best_bidirectional['long_win_rate']:.1f}%)")
        print(f"  Short Trades: {best_bidirectional['short_trades']} (Win rate: {best_bidirectional['short_win_rate']:.1f}%)")
        
        if best_bidirectional['short_trades'] > 0:
            improvement = best_bidirectional['return'] - best_long_only['return']
            print(f"\n  Improvement from shorts: {improvement:.2f}% additional return")
    
    # Test best configuration
    best = best_overall
    
    print("\n" + "="*110)
    print("BEST OVERALL CONFIGURATION")
    print("="*110)
    print(f"Parameters:")
    print(f"  Fast EMA: {best['fast_ema']}")
    print(f"  Slow EMA: {best['slow_ema']}")
    print(f"  RSI Period: {best['rsi_period']}")
    print(f"  RSI Buy: {best['rsi_buy']}")
    print(f"  RSI Sell: {best['rsi_sell']}")
    print(f"  ATR Multiplier: {best['atr_multiplier']}")
    print(f"  Profit Target: {best['profit_target_pct']*100:.1f}%")
    print(f"  Enable Shorts: {best['enable_shorts']}")
    
    print(f"\nPerformance:")
    print(f"  Final Balance: ${best['balance']:.2f}")
    print(f"  Return: {best['return']:.2f}%")
    print(f"  Total Trades: {best['trades']}")
    if best['enable_shorts']:
        print(f"  Long Trades: {best['long_trades']} (Win rate: {best['long_win_rate']:.1f}%)")
        print(f"  Short Trades: {best['short_trades']} (Win rate: {best['short_win_rate']:.1f}%)")
    print(f"  Overall Win Rate: {best['win_rate']:.2f}%")
    print(f"  Max Drawdown: {abs(best['max_dd']):.2f}%")
    print(f"  Avg Win: ${best['avg_win']:.2f}")
    print(f"  Avg Loss: ${best['avg_loss']:.2f}")
    
    # Run detailed backtest
    balance, trades, equity = run_bidirectional_backtest(
        data, capital=1000,
        fast_ema=best['fast_ema'],
        slow_ema=best['slow_ema'],
        rsi_period=best['rsi_period'],
        rsi_buy=best['rsi_buy'],
        rsi_sell=best['rsi_sell'],
        atr_multiplier=best['atr_multiplier'],
        profit_target_pct=best['profit_target_pct'],
        enable_shorts=best['enable_shorts'],
        enable_compounding=True
    )
    
    # Save configuration
    config = {
        'strategy': 'bidirectional',
        'fast_ema': best['fast_ema'],
        'slow_ema': best['slow_ema'],
        'rsi_period': best['rsi_period'],
        'rsi_buy': best['rsi_buy'],
        'rsi_sell': best['rsi_sell'],
        'atr_multiplier': best['atr_multiplier'],
        'profit_target_pct': best['profit_target_pct'],
        'enable_shorts': best['enable_shorts'],
        'enable_compounding': True
    }
    
    with open('config/bidirectional_strategy_params.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nConfiguration saved to: config/bidirectional_strategy_params.json")
    
    # Plot results
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curve
    ax = axes[0, 0]
    ax.plot(equity, linewidth=2, color='blue')
    ax.set_title('Equity Curve - Best Strategy', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='red', linestyle='--', alpha=0.5, label='Starting Capital')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Trade analysis
    if trades:
        trades_df = pd.DataFrame(trades)
        
        # PnL by trade type
        ax = axes[0, 1]
        if best['enable_shorts']:
            long_pnl = trades_df[trades_df['type'] == 'long']['pnl']
            short_pnl = trades_df[trades_df['type'] == 'short']['pnl']
            ax.hist([long_pnl, short_pnl], bins=20, label=['Long', 'Short'], 
                   alpha=0.7, color=['green', 'red'])
            ax.legend()
        else:
            ax.hist(trades_df['pnl'], bins=30, alpha=0.7, color='green')
        ax.set_title('Trade PnL Distribution', fontsize=14, fontweight='bold')
        ax.set_xlabel('PnL ($)')
        ax.set_ylabel('Frequency')
        ax.axvline(x=0, color='black', linestyle='--', alpha=0.5)
        ax.grid(True, alpha=0.3)
        
        # Cumulative PnL
        ax = axes[1, 0]
        ax.plot(trades_df['pnl'].cumsum(), linewidth=2, color='purple')
        ax.set_title('Cumulative PnL', fontsize=14, fontweight='bold')
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('Cumulative PnL ($)')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    
    # Comparison: Long-only vs Bidirectional
    ax = axes[1, 1]
    if best_long_only and best_bidirectional:
        categories = ['Return %', 'Win Rate %', 'Max DD %\n(inverted)']
        long_only_vals = [best_long_only['return'], best_long_only['win_rate'], -abs(best_long_only['max_dd'])]
        bidirectional_vals = [best_bidirectional['return'], best_bidirectional['win_rate'], -abs(best_bidirectional['max_dd'])]
        
        x = np.arange(len(categories))
        width = 0.35
        ax.bar(x - width/2, long_only_vals, width, label='Long-Only', alpha=0.7, color='green')
        ax.bar(x + width/2, bidirectional_vals, width, label='Bidirectional', alpha=0.7, color='blue')
        ax.set_xticks(x)
        ax.set_xticklabels(categories)
        ax.legend()
        ax.set_title('Long-Only vs Bidirectional', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    
    plt.tight_layout()
    plt.savefig('results/bidirectional_strategy.png', dpi=150)
    print(f"Chart saved to: results/bidirectional_strategy.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
