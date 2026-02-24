import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from itertools import product

def compute_indicators(df, fast_ema=15, slow_ema=25, rsi_period=10):
    df = df.copy()
    
    # EMAs for trend
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Trend
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def run_aggressive_backtest(df, capital=1000,
                            fast_ema=15, slow_ema=25, rsi_period=10,
                            rsi_buy=35, rsi_sell=70,
                            atr_multiplier=3.0,
                            profit_target_pct=0.04,
                            trailing_stop_pct=0.015,
                            enable_shorts=True,
                            enable_compounding=True,
                            position_multiplier=1.0):
    """
    Aggressive strategy with:
    - Higher profit targets
    - Trailing stops to lock in gains
    - Position multiplier for leverage
    - More aggressive entry/exit
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
            # LONG ENTRY: More aggressive (higher RSI threshold)
            if row['RSI'] < rsi_buy:
                if enable_compounding:
                    position_size = balance * position_multiplier
                else:
                    position_size = starting_balance * position_multiplier
                
                stop_distance = row['ATR'] * atr_multiplier
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'time': row['time'],
                    'size': position_size,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * profit_target_pct),
                    'highest_price': price,
                    'trailing_stop': None
                }
            
            # SHORT ENTRY: More aggressive
            elif enable_shorts and row['RSI'] > rsi_sell:
                if row['downtrend']:
                    if enable_compounding:
                        position_size = balance * position_multiplier
                    else:
                        position_size = starting_balance * position_multiplier
                    
                    stop_distance = row['ATR'] * atr_multiplier
                    
                    position = {
                        'type': 'short',
                        'entry': price,
                        'time': row['time'],
                        'size': position_size,
                        'stop_loss': price + stop_distance,
                        'take_profit': price - (price * profit_target_pct),
                        'lowest_price': price,
                        'trailing_stop': None
                    }
        else:
            entry = position['entry']
            
            # Calculate PnL
            if position['type'] == 'long':
                change = (price - entry) / entry
                
                # Update trailing stop
                if price > position['highest_price']:
                    position['highest_price'] = price
                    # Activate trailing stop once in profit
                    if change > trailing_stop_pct:
                        position['trailing_stop'] = price * (1 - trailing_stop_pct)
            else:  # short
                change = (entry - price) / entry
                
                # Update trailing stop
                if price < position['lowest_price']:
                    position['lowest_price'] = price
                    if change > trailing_stop_pct:
                        position['trailing_stop'] = price * (1 + trailing_stop_pct)
            
            pnl = change * position['size']
            
            # EXIT LOGIC
            should_exit = False
            exit_reason = ''
            
            if position['type'] == 'long':
                # Trailing stop hit
                if position['trailing_stop'] and price <= position['trailing_stop']:
                    should_exit = True
                    exit_reason = 'Trailing stop'
                # Profit target
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = f'{profit_target_pct*100:.1f}% profit'
                # Hard stop loss
                elif price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
                # RSI overbought
                elif row['RSI'] > rsi_sell:
                    should_exit = True
                    exit_reason = f'RSI > {rsi_sell}'
            
            else:  # short
                # Trailing stop hit
                if position['trailing_stop'] and price >= position['trailing_stop']:
                    should_exit = True
                    exit_reason = 'Trailing stop'
                # Profit target
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = f'{profit_target_pct*100:.1f}% profit'
                # Hard stop loss
                elif price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
                # RSI oversold
                elif row['RSI'] < rsi_buy:
                    should_exit = True
                    exit_reason = f'RSI < {rsi_buy}'
            
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
    """Calculate performance metrics with focus on returns"""
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
    
    long_trades = trades_df[trades_df['type'] == 'long']
    short_trades = trades_df[trades_df['type'] == 'short']
    long_wins = long_trades[long_trades['pnl'] > 0]
    short_wins = short_trades[short_trades['pnl'] > 0]
    
    # Aggressive score: prioritize returns (80%) over risk (20%)
    score = return_pct * 0.8 + (return_pct * (1 - abs(max_dd))) * 0.2
    
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
        'score': score
    }

def optimize_aggressive(df, capital=1000):
    """Optimize for maximum returns"""
    
    print("Optimizing aggressive strategy for maximum returns...")
    print("Focus: High returns with acceptable risk\n")
    
    param_grid = {
        'fast_ema': [15, 20],
        'slow_ema': [25, 30],
        'rsi_period': [10],
        'rsi_buy': [35, 40],
        'rsi_sell': [65, 70],
        'atr_multiplier': [3.0, 3.5],
        'profit_target_pct': [0.04, 0.05],
        'trailing_stop_pct': [0.015, 0.02],
        'enable_shorts': [True],
        'position_multiplier': [1.0, 1.5, 2.0]  # Test higher leverage
    }
    
    keys = param_grid.keys()
    values = param_grid.values()
    combinations = [dict(zip(keys, v)) for v in product(*values)]
    
    print(f"Testing {len(combinations)} combinations...")
    
    results = []
    
    for i, params in enumerate(combinations):
        if (i + 1) % 50 == 0:
            print(f"Progress: {i+1}/{len(combinations)}")
        
        if params['fast_ema'] >= params['slow_ema']:
            continue
        
        balance, trades, equity = run_aggressive_backtest(
            df, capital=capital,
            enable_compounding=True,
            **params
        )
        
        metrics = calculate_metrics(balance, trades, equity, capital)
        
        if metrics and metrics['balance'] > 0:  # Only keep profitable strategies
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
    results = optimize_aggressive(data, capital=1000)
    
    if not results:
        print("No profitable strategies found!")
        mt5.disconnect()
        return
    
    # Display results
    print("\n" + "="*120)
    print("TOP 10 AGGRESSIVE CONFIGURATIONS (Sorted by Return-Focused Score)")
    print("="*120)
    print(f"{'#':<3} {'FastEMA':<8} {'SlowEMA':<8} {'Buy':<4} {'Sell':<5} {'ATR':<5} "
          f"{'Profit%':<8} {'Trail%':<7} {'Mult':<5} {'Return%':<10} {'Win%':<7} {'MaxDD%':<8} {'Score':<8}")
    print("-"*120)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<3} {r['fast_ema']:<8} {r['slow_ema']:<8} {r['rsi_buy']:<4} {r['rsi_sell']:<5} "
              f"{r['atr_multiplier']:<5.1f} {r['profit_target_pct']*100:<8.1f} "
              f"{r['trailing_stop_pct']*100:<7.1f} {r['position_multiplier']:<5.1f} "
              f"{r['return']:<10.2f} {r['win_rate']:<7.1f} {abs(r['max_dd']):<8.2f} {r['score']:<8.2f}")
    
    # Best configuration
    best = results[0]
    
    print("\n" + "="*120)
    print("BEST AGGRESSIVE CONFIGURATION")
    print("="*120)
    print(f"Parameters:")
    print(f"  Fast EMA: {best['fast_ema']}")
    print(f"  Slow EMA: {best['slow_ema']}")
    print(f"  RSI Period: {best['rsi_period']}")
    print(f"  RSI Buy: {best['rsi_buy']}")
    print(f"  RSI Sell: {best['rsi_sell']}")
    print(f"  ATR Multiplier: {best['atr_multiplier']}")
    print(f"  Profit Target: {best['profit_target_pct']*100:.1f}%")
    print(f"  Trailing Stop: {best['trailing_stop_pct']*100:.1f}%")
    print(f"  Position Multiplier: {best['position_multiplier']}x")
    print(f"  Enable Shorts: {best['enable_shorts']}")
    
    print(f"\nPerformance:")
    print(f"  Final Balance: ${best['balance']:.2f}")
    print(f"  Return: {best['return']:.2f}%")
    print(f"  Total Trades: {best['trades']}")
    print(f"  Long Trades: {best['long_trades']} (Win rate: {best['long_win_rate']:.1f}%)")
    print(f"  Short Trades: {best['short_trades']} (Win rate: {best['short_win_rate']:.1f}%)")
    print(f"  Overall Win Rate: {best['win_rate']:.2f}%")
    print(f"  Max Drawdown: {abs(best['max_dd']):.2f}%")
    print(f"  Avg Win: ${best['avg_win']:.2f}")
    print(f"  Avg Loss: ${best['avg_loss']:.2f}")
    
    # Compare with conservative strategy
    print("\n" + "="*120)
    print("RISK COMPARISON")
    print("="*120)
    
    # Find most conservative (lowest drawdown)
    conservative = min(results, key=lambda x: abs(x['max_dd']))
    
    print(f"\nMost Conservative Strategy:")
    print(f"  Return: {conservative['return']:.2f}%")
    print(f"  Max Drawdown: {abs(conservative['max_dd']):.2f}%")
    print(f"  Position Multiplier: {conservative['position_multiplier']}x")
    
    print(f"\nMost Aggressive Strategy (Best Return):")
    print(f"  Return: {best['return']:.2f}%")
    print(f"  Max Drawdown: {abs(best['max_dd']):.2f}%")
    print(f"  Position Multiplier: {best['position_multiplier']}x")
    
    print(f"\nRisk/Reward Trade-off:")
    print(f"  Additional Return: {best['return'] - conservative['return']:.2f}%")
    print(f"  Additional Risk: {abs(best['max_dd']) - abs(conservative['max_dd']):.2f}%")
    
    # Run detailed backtest
    balance, trades, equity = run_aggressive_backtest(
        data, capital=1000,
        fast_ema=best['fast_ema'],
        slow_ema=best['slow_ema'],
        rsi_period=best['rsi_period'],
        rsi_buy=best['rsi_buy'],
        rsi_sell=best['rsi_sell'],
        atr_multiplier=best['atr_multiplier'],
        profit_target_pct=best['profit_target_pct'],
        trailing_stop_pct=best['trailing_stop_pct'],
        enable_shorts=best['enable_shorts'],
        enable_compounding=True,
        position_multiplier=best['position_multiplier']
    )
    
    # Save configuration
    config = {
        'strategy': 'aggressive',
        'fast_ema': best['fast_ema'],
        'slow_ema': best['slow_ema'],
        'rsi_period': best['rsi_period'],
        'rsi_buy': best['rsi_buy'],
        'rsi_sell': best['rsi_sell'],
        'atr_multiplier': best['atr_multiplier'],
        'profit_target_pct': best['profit_target_pct'],
        'trailing_stop_pct': best['trailing_stop_pct'],
        'enable_shorts': best['enable_shorts'],
        'enable_compounding': True,
        'position_multiplier': best['position_multiplier']
    }
    
    with open('config/aggressive_strategy_params.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nConfiguration saved to: config/aggressive_strategy_params.json")
    
    # Plot results
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curve
    ax = axes[0, 0]
    ax.plot(equity, linewidth=2, color='red')
    ax.set_title('Equity Curve - Aggressive Strategy', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='black', linestyle='--', alpha=0.5, label='Starting Capital')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Drawdown
    if trades:
        equity_series = pd.Series(equity)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max * 100
        
        ax = axes[0, 1]
        ax.fill_between(range(len(drawdown)), drawdown, 0, color='red', alpha=0.3)
        ax.plot(drawdown, color='red', linewidth=1)
        ax.set_title('Drawdown Over Time', fontsize=14, fontweight='bold')
        ax.set_xlabel('Bar Number')
        ax.set_ylabel('Drawdown (%)')
        ax.grid(True, alpha=0.3)
        
        # Trade distribution
        trades_df = pd.DataFrame(trades)
        ax = axes[1, 0]
        long_pnl = trades_df[trades_df['type'] == 'long']['pnl']
        short_pnl = trades_df[trades_df['type'] == 'short']['pnl']
        ax.hist([long_pnl, short_pnl], bins=30, label=['Long', 'Short'], 
               alpha=0.7, color=['green', 'red'])
        ax.set_title('Trade PnL Distribution', fontsize=14, fontweight='bold')
        ax.set_xlabel('PnL ($)')
        ax.set_ylabel('Frequency')
        ax.axvline(x=0, color='black', linestyle='--', alpha=0.5)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Return vs Drawdown scatter (top 20)
        ax = axes[1, 1]
        returns = [r['return'] for r in results[:20]]
        drawdowns = [abs(r['max_dd']) for r in results[:20]]
        multipliers = [r['position_multiplier'] for r in results[:20]]
        scatter = ax.scatter(drawdowns, returns, c=multipliers, cmap='RdYlGn', s=100, alpha=0.6)
        ax.scatter([abs(best['max_dd'])], [best['return']], color='red', s=300, marker='*',
                  edgecolors='black', linewidths=2, label='Best', zorder=5)
        ax.set_title('Return vs Risk (Top 20)', fontsize=14, fontweight='bold')
        ax.set_xlabel('Max Drawdown (%)')
        ax.set_ylabel('Return (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax, label='Position Multiplier')
    
    plt.tight_layout()
    plt.savefig('results/aggressive_strategy.png', dpi=150)
    print(f"Chart saved to: results/aggressive_strategy.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
