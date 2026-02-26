import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

def compute_indicators(df, fast_ema=20, slow_ema=30, rsi_period=10):
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=slow_ema).mean()
    
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
    
    df['ema_200'] = df['close'].ewm(span=200).mean()
    df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
    df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
    
    return df

def run_safe_leveraged_backtest(df, capital=1000,
                                position_size_pct=0.10,  # Use 10% of balance per trade
                                leverage=100,
                                fast_ema=20, slow_ema=30, rsi_period=10,
                                rsi_buy=30, rsi_sell=75,
                                atr_multiplier=3.0,
                                profit_target_pct=0.03,
                                max_drawdown_limit=0.30,  # Stop trading if 30% drawdown
                                enable_shorts=True,
                                warmup_candles=3):  # Wait after gaps
    """
    Safe leveraged strategy with gap detection:
    - Only use X% of balance per trade (e.g., 10%)
    - Apply leverage to that percentage
    - Stop trading if drawdown exceeds limit
    - Proper risk management with ATR-based stops
    - Detect market gaps and wait for warm-up period
    """
    
    df = compute_indicators(df, fast_ema, slow_ema, rsi_period)
    
    position = None
    balance = capital
    starting_balance = capital
    peak_balance = capital
    trades = []
    equity_curve = [balance]
    trading_paused = False
    last_close_time = None
    warmup_until_bar = -1  # Bar index until which we're in warm-up
    
    for i in range(max(fast_ema, slow_ema, rsi_period, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        
        # Detect market gap (time gap > 15 minutes for M5 data)
        if i > 0:
            prev_row = df.iloc[i-1]
            time_gap_minutes = (row['time'] - prev_row['time']).total_seconds() / 60
            
            if time_gap_minutes > 15:
                # Market gap detected - enter warm-up period
                warmup_until_bar = i + warmup_candles
                # Close any open position at gap (simulates stop loss/take profit hitting during gap)
                if position is not None:
                    # Assume we exit at the open price after gap
                    exit_price = row['open']
                    
                    if position['type'] == 'long':
                        price_change = exit_price - position['entry']
                        pnl = (price_change / position['entry']) * position['leveraged_position']
                    else:
                        price_change = position['entry'] - exit_price
                        pnl = (price_change / position['entry']) * position['leveraged_position']
                    
                    balance += pnl
                    
                    trades.append({
                        'entry': position['entry'],
                        'exit': exit_price,
                        'type': position['type'],
                        'pnl': pnl,
                        'entry_time': position['time'],
                        'exit_time': row['time'],
                        'exit_reason': 'market_gap'
                    })
                    
                    position = None
        
        # Update peak balance
        if balance > peak_balance:
            peak_balance = balance
        
        # Check drawdown
        current_drawdown = (peak_balance - balance) / peak_balance
        if current_drawdown >= max_drawdown_limit:
            if not trading_paused:
                trading_paused = True
        
        # Check if we're in warm-up period
        in_warmup = i < warmup_until_bar
        
        # Check cooldown after closing position
        in_cooldown = False
        if last_close_time is not None and i < last_close_time + 2:  # 2 candle cooldown
            in_cooldown = True
    
    for i in range(max(fast_ema, slow_ema, rsi_period, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        
        # Update peak balance
        if balance > peak_balance:
            peak_balance = balance
        
        # Check drawdown
        current_drawdown = (peak_balance - balance) / peak_balance
        if current_drawdown >= max_drawdown_limit:
            if not trading_paused:
                print(f"Trading paused at bar {i}: Drawdown {current_drawdown*100:.2f}% exceeds limit")
                trading_paused = True
        
        if position is None and not trading_paused and not in_warmup and not in_cooldown:
            # LONG ENTRY
            if row['RSI'] < rsi_buy:
                # Position size: X% of balance, leveraged
                base_position = balance * position_size_pct
                leveraged_position = base_position * leverage
                
                # Calculate stop loss
                stop_distance = row['ATR'] * atr_multiplier
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'time': row['time'],
                    'base_position': base_position,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * profit_target_pct)
                }
            
            # SHORT ENTRY
            elif enable_shorts and row['RSI'] > rsi_sell and row['downtrend']:
                base_position = balance * position_size_pct
                leveraged_position = base_position * leverage
                stop_distance = row['ATR'] * atr_multiplier
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'time': row['time'],
                    'base_position': base_position,
                    'leveraged_position': leveraged_position,
                    'stop_loss': price + stop_distance,
                    'take_profit': price - (price * profit_target_pct)
                }
        
        elif position is not None:
            entry = position['entry']
            
            # Calculate price change percentage
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            
            # PnL on the leveraged position
            pnl = price_change_pct * position['leveraged_position']
            
            # EXIT LOGIC
            should_exit = False
            exit_reason = ''
            
            if position['type'] == 'long':
                if row['RSI'] > rsi_sell:
                    should_exit = True
                    exit_reason = f'RSI > {rsi_sell}'
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Profit target'
                elif price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
            else:  # short
                if row['RSI'] < rsi_buy:
                    should_exit = True
                    exit_reason = f'RSI < {rsi_buy}'
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Profit target'
                elif price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop loss'
            
            # Safety: Force exit if loss would exceed base position (margin call simulation)
            if pnl < -position['base_position']:
                should_exit = True
                exit_reason = 'Margin call (loss > position size)'
                pnl = -position['base_position']  # Cap loss at position size
            
            if should_exit:
                balance += pnl
                trades.append({
                    'type': position['type'],
                    'entry_time': position['time'],
                    'exit_time': row['time'],
                    'entry_price': entry,
                    'exit_price': price,
                    'base_position': position['base_position'],
                    'leveraged_position': position['leveraged_position'],
                    'pnl': pnl,
                    'pnl_pct': price_change_pct * 100,
                    'reason': exit_reason,
                    'balance_after': balance
                })
                position = None
                last_close_time = i  # Track when we closed for cooldown
            
            if balance <= 0:
                print("Account blown!")
                break
        
        equity_curve.append(balance)
    
    return balance, trades, equity_curve, trading_paused

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
    
    # Test different combinations of position size and leverage
    configs = {
        "Conservative (10% @ 10x)": {
            'position_size_pct': 0.10,
            'leverage': 10,
            'max_drawdown_limit': 0.25
        },
        "Moderate (10% @ 25x)": {
            'position_size_pct': 0.10,
            'leverage': 25,
            'max_drawdown_limit': 0.30
        },
        "Aggressive (15% @ 25x)": {
            'position_size_pct': 0.15,
            'leverage': 25,
            'max_drawdown_limit': 0.35
        },
        "Very Aggressive (10% @ 50x)": {
            'position_size_pct': 0.10,
            'leverage': 50,
            'max_drawdown_limit': 0.40
        },
        "Maximum (15% @ 50x)": {
            'position_size_pct': 0.15,
            'leverage': 50,
            'max_drawdown_limit': 0.45
        }
    }
    
    results = {}
    
    for name, config in configs.items():
        print(f"\n{'='*80}")
        print(f"Testing: {name}")
        print(f"  Position Size: {config['position_size_pct']*100}% of balance")
        print(f"  Leverage: {config['leverage']}x")
        print(f"  Effective Position: {config['position_size_pct']*config['leverage']*100}% of balance")
        print(f"  Max Drawdown Limit: {config['max_drawdown_limit']*100}%")
        print(f"{'='*80}")
        
        balance, trades, equity, paused = run_safe_leveraged_backtest(
            data, capital=1000,
            position_size_pct=config['position_size_pct'],
            leverage=config['leverage'],
            fast_ema=20, slow_ema=30, rsi_period=10,
            rsi_buy=30, rsi_sell=75,
            atr_multiplier=3.0,
            profit_target_pct=0.03,
            max_drawdown_limit=config['max_drawdown_limit'],
            enable_shorts=True
        )
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            losing = trades_df[trades_df['pnl'] < 0]
            
            equity_series = pd.Series(equity)
            running_max = equity_series.expanding().max()
            drawdown = (equity_series - running_max) / running_max
            max_dd = drawdown.min()
            
            return_pct = (balance / 1000 - 1) * 100
            
            long_trades = trades_df[trades_df['type'] == 'long']
            short_trades = trades_df[trades_df['type'] == 'short']
            
            results[name] = {
                'config': config,
                'balance': balance,
                'return': return_pct,
                'trades': len(trades),
                'win_rate': len(winning) / len(trades) * 100,
                'max_dd': max_dd * 100,
                'equity': equity,
                'paused': paused
            }
            
            print(f"\nResults:")
            print(f"  Final Balance: ${balance:.2f}")
            print(f"  Return: {return_pct:.2f}%")
            print(f"  Total Trades: {len(trades)}")
            print(f"  Long Trades: {len(long_trades)}")
            print(f"  Short Trades: {len(short_trades)}")
            print(f"  Win Rate: {len(winning)/len(trades)*100:.2f}%")
            print(f"  Max Drawdown: {max_dd*100:.2f}%")
            print(f"  Avg Win: ${winning['pnl'].mean():.2f}")
            print(f"  Avg Loss: ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "  Avg Loss: N/A")
            print(f"  Trading Paused: {'Yes' if paused else 'No'}")
    
    # Summary
    print("\n" + "="*100)
    print("SAFE LEVERAGED STRATEGY COMPARISON")
    print("="*100)
    print(f"{'Strategy':<30} {'Pos%':<6} {'Eff%':<8} {'Return':<12} {'Max DD':<10} {'R/R':<8} {'Paused':<8}")
    print("-"*100)
    
    for name, r in results.items():
        eff_pos = r['config']['position_size_pct'] * r['config']['leverage'] * 100
        rr = r['return'] / abs(r['max_dd']) if r['max_dd'] != 0 else 0
        print(f"{name:<30} {r['config']['position_size_pct']*100:>5.0f}% {eff_pos:>7.0f}% "
              f"{r['return']:>10.2f}%  {abs(r['max_dd']):>8.2f}%  {rr:>6.2f}  {'Yes' if r['paused'] else 'No':<8}")
    
    # Find best by risk/reward
    best_name = max(results.keys(), key=lambda k: results[k]['return'] / abs(results[k]['max_dd']))
    best = results[best_name]
    
    print("\n" + "="*100)
    print(f"RECOMMENDED: {best_name}")
    print("="*100)
    print(f"This configuration provides the best risk/reward balance")
    print(f"Return: {best['return']:.2f}%")
    print(f"Max Drawdown: {abs(best['max_dd']):.2f}%")
    print(f"Risk/Reward Ratio: {best['return'] / abs(best['max_dd']):.2f}")
    
    # Save best configuration
    config_to_save = {
        'strategy': 'safe_leveraged',
        'position_size_pct': best['config']['position_size_pct'],
        'leverage': best['config']['leverage'],
        'max_drawdown_limit': best['config']['max_drawdown_limit'],
        'fast_ema': 20,
        'slow_ema': 30,
        'rsi_period': 10,
        'rsi_buy': 30,
        'rsi_sell': 75,
        'atr_multiplier': 3.0,
        'profit_target_pct': 0.03,
        'enable_shorts': True
    }
    
    with open('config/safe_leveraged_params.json', 'w') as f:
        json.dump(config_to_save, f, indent=2)
    
    print(f"\nConfiguration saved to: config/safe_leveraged_params.json")
    
    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curves
    ax = axes[0, 0]
    colors = ['green', 'blue', 'orange', 'red']
    for (name, result), color in zip(results.items(), colors):
        ax.plot(result['equity'], label=name, linewidth=2, color=color, alpha=0.8)
    ax.set_title('Equity Curves - Safe Leveraged Strategies', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='black', linestyle='--', alpha=0.3)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')
    
    # Returns
    ax = axes[0, 1]
    names = list(results.keys())
    returns = [results[name]['return'] for name in names]
    bars = ax.bar(range(len(names)), returns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.split('(')[0].strip() for n in names], rotation=45, ha='right')
    ax.set_title('Return Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    for bar, ret in zip(bars, returns):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{ret:.0f}%', ha='center', va='bottom', fontweight='bold')
    
    # Max Drawdown
    ax = axes[1, 0]
    drawdowns = [abs(results[name]['max_dd']) for name in names]
    ax.bar(range(len(names)), drawdowns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.split('(')[0].strip() for n in names], rotation=45, ha='right')
    ax.set_title('Max Drawdown', fontsize=14, fontweight='bold')
    ax.set_ylabel('Max Drawdown (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Risk/Reward scatter
    ax = axes[1, 1]
    for (name, result), color in zip(results.items(), colors):
        rr = result['return'] / abs(result['max_dd'])
        ax.scatter([abs(result['max_dd'])], [result['return']],
                  s=300, color=color, alpha=0.7, label=name.split('(')[0].strip(),
                  edgecolors='black', linewidths=2)
    ax.set_title('Return vs Risk', fontsize=14, fontweight='bold')
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('Return (%)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Add diagonal lines for risk/reward ratios
    max_dd = max(drawdowns)
    max_ret = max(returns)
    for ratio in [2, 5, 10, 15]:
        x = np.linspace(0, max_dd, 100)
        y = x * ratio
        ax.plot(x, y, 'k--', alpha=0.2, linewidth=0.5)
        if max_dd * ratio < max_ret * 1.2:
            ax.text(max_dd * 0.8, max_dd * ratio * 0.8, f'{ratio}:1', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('results/safe_leveraged_comparison.png', dpi=150)
    print(f"Chart saved to: results/safe_leveraged_comparison.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
