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

def run_leveraged_backtest(df, capital=1000, leverage=100,
                           fast_ema=20, slow_ema=30, rsi_period=10,
                           rsi_buy=30, rsi_sell=75,
                           atr_multiplier=3.0,
                           profit_target_pct=0.03,
                           enable_shorts=True,
                           risk_per_trade=0.02):
    """
    Proper leverage implementation:
    - Use leverage to control larger positions
    - Risk management: only risk X% of capital per trade
    - Position size based on stop loss distance
    """
    
    df = compute_indicators(df, fast_ema, slow_ema, rsi_period)
    
    position = None
    balance = capital
    trades = []
    equity_curve = [balance]
    
    for i in range(max(fast_ema, slow_ema, rsi_period, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        
        if position is None:
            # LONG ENTRY
            if row['RSI'] < rsi_buy:
                # Calculate position size based on risk
                stop_distance = row['ATR'] * atr_multiplier
                stop_distance_pct = stop_distance / price
                
                # Risk amount
                risk_amount = balance * risk_per_trade
                
                # Position size: risk_amount / stop_distance_pct
                # This is how much we can control with our risk
                position_value = risk_amount / stop_distance_pct
                
                # Apply leverage limit
                max_position_value = balance * leverage
                position_value = min(position_value, max_position_value)
                
                position = {
                    'type': 'long',
                    'entry': price,
                    'time': row['time'],
                    'position_value': position_value,
                    'stop_loss': price - stop_distance,
                    'take_profit': price + (price * profit_target_pct)
                }
            
            # SHORT ENTRY
            elif enable_shorts and row['RSI'] > rsi_sell and row['downtrend']:
                stop_distance = row['ATR'] * atr_multiplier
                stop_distance_pct = stop_distance / price
                
                risk_amount = balance * risk_per_trade
                position_value = risk_amount / stop_distance_pct
                max_position_value = balance * leverage
                position_value = min(position_value, max_position_value)
                
                position = {
                    'type': 'short',
                    'entry': price,
                    'time': row['time'],
                    'position_value': position_value,
                    'stop_loss': price + stop_distance,
                    'take_profit': price - (price * profit_target_pct)
                }
        else:
            entry = position['entry']
            
            # Calculate PnL based on position value and price change
            if position['type'] == 'long':
                price_change_pct = (price - entry) / entry
            else:
                price_change_pct = (entry - price) / entry
            
            pnl = price_change_pct * position['position_value']
            
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
            
            if should_exit:
                balance += pnl
                trades.append({
                    'type': position['type'],
                    'entry_time': position['time'],
                    'exit_time': row['time'],
                    'entry_price': entry,
                    'exit_price': price,
                    'position_value': position['position_value'],
                    'pnl': pnl,
                    'pnl_pct': price_change_pct * 100,
                    'reason': exit_reason,
                    'balance_after': balance
                })
                position = None
            
            if balance <= 0:
                print("Account blown!")
                break
        
        equity_curve.append(balance)
    
    return balance, trades, equity_curve

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
    
    # Test different leverage levels
    leverage_levels = [1, 10, 25, 50, 100]
    
    results = {}
    
    for leverage in leverage_levels:
        print(f"\n{'='*80}")
        print(f"Testing with {leverage}x Leverage")
        print(f"{'='*80}")
        
        balance, trades, equity = run_leveraged_backtest(
            data, capital=1000, leverage=leverage,
            fast_ema=20, slow_ema=30, rsi_period=10,
            rsi_buy=30, rsi_sell=75,
            atr_multiplier=3.0,
            profit_target_pct=0.03,
            enable_shorts=True,
            risk_per_trade=0.02  # Risk 2% per trade
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
            
            results[leverage] = {
                'balance': balance,
                'return': return_pct,
                'trades': len(trades),
                'win_rate': len(winning) / len(trades) * 100,
                'max_dd': max_dd * 100,
                'equity': equity
            }
            
            print(f"Final Balance: ${balance:.2f}")
            print(f"Return: {return_pct:.2f}%")
            print(f"Total Trades: {len(trades)}")
            print(f"Win Rate: {len(winning)/len(trades)*100:.2f}%")
            print(f"Max Drawdown: {max_dd*100:.2f}%")
            print(f"Avg Position Value: ${trades_df['position_value'].mean():.2f}")
    
    # Summary
    print("\n" + "="*80)
    print("LEVERAGE COMPARISON SUMMARY")
    print("="*80)
    print(f"{'Leverage':<10} {'Return':<12} {'Max DD':<12} {'Risk/Reward':<12} {'Final Balance':<15}")
    print("-"*80)
    
    for lev in leverage_levels:
        if lev in results:
            r = results[lev]
            rr = r['return'] / abs(r['max_dd']) if r['max_dd'] != 0 else 0
            print(f"{lev}x{'':<7} {r['return']:>10.2f}%  {abs(r['max_dd']):>10.2f}%  {rr:>10.2f}    ${r['balance']:>12.2f}")
    
    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curves
    ax = axes[0, 0]
    colors = ['green', 'blue', 'orange', 'red', 'purple']
    for (lev, result), color in zip(results.items(), colors):
        ax.plot(result['equity'], label=f'{lev}x Leverage', linewidth=2, color=color, alpha=0.8)
    ax.set_title('Equity Curves by Leverage', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='black', linestyle='--', alpha=0.3)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')
    
    # Returns
    ax = axes[0, 1]
    leverages = list(results.keys())
    returns = [results[lev]['return'] for lev in leverages]
    bars = ax.bar(range(len(leverages)), returns, color=colors[:len(leverages)], alpha=0.7)
    ax.set_xticks(range(len(leverages)))
    ax.set_xticklabels([f'{lev}x' for lev in leverages])
    ax.set_title('Return by Leverage', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    for bar, ret in zip(bars, returns):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{ret:.0f}%', ha='center', va='bottom', fontweight='bold')
    
    # Max Drawdown
    ax = axes[1, 0]
    drawdowns = [abs(results[lev]['max_dd']) for lev in leverages]
    ax.bar(range(len(leverages)), drawdowns, color=colors[:len(leverages)], alpha=0.7)
    ax.set_xticks(range(len(leverages)))
    ax.set_xticklabels([f'{lev}x' for lev in leverages])
    ax.set_title('Max Drawdown by Leverage', fontsize=14, fontweight='bold')
    ax.set_ylabel('Max Drawdown (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Risk/Reward
    ax = axes[1, 1]
    risk_rewards = [results[lev]['return'] / abs(results[lev]['max_dd']) for lev in leverages]
    ax.bar(range(len(leverages)), risk_rewards, color=colors[:len(leverages)], alpha=0.7)
    ax.set_xticks(range(len(leverages)))
    ax.set_xticklabels([f'{lev}x' for lev in leverages])
    ax.set_title('Risk/Reward Ratio by Leverage', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return / Max Drawdown')
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('results/leverage_comparison.png', dpi=150)
    print(f"\nChart saved to: results/leverage_comparison.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
