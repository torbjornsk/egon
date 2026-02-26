import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

def compute_indicators(df, ema_span=50, rsi_period=10):
    df = df.copy()
    
    # Core indicators
    df['EMA'] = df['close'].ewm(span=ema_span).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Long-term trend (for safety only)
    df['EMA_200'] = df['close'].ewm(span=200).mean()
    df['severe_downtrend'] = (df['close'] < df['EMA_200']) & (df['EMA'] < df['EMA_200'])
    
    # Price momentum
    df['momentum_5'] = df['close'].pct_change(5) * 100
    df['momentum_20'] = df['close'].pct_change(20) * 100
    
    return df

def run_optimized_backtest(df, capital=1000, 
                           rsi_buy=30, rsi_sell=70,
                           profit_target=0.03, stop_loss=0.02,
                           enable_safety=True,
                           enable_compounding=True):
    """
    Optimized strategy:
    - Your original logic (works great!)
    - Compounding for exponential growth
    - Safety: pause trading only in SEVERE downtrends
    - Adjustable parameters for optimization
    """
    position = None
    balance = capital
    starting_balance = capital
    trades = []
    equity_curve = [balance]
    skipped_trades = 0
    
    EMA_SPAN = 50
    RSI_PERIOD = 10
    
    for i in range(max(EMA_SPAN, RSI_PERIOD, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        ema = row['EMA']
        rsi = row['RSI']
        
        if position is None:
            # Entry: RSI oversold
            if rsi < rsi_buy:
                # Safety check: skip if in severe downtrend
                if enable_safety and row['severe_downtrend']:
                    skipped_trades += 1
                    equity_curve.append(balance)
                    continue
                
                # Position sizing with compounding
                if enable_compounding:
                    position_size = balance
                else:
                    position_size = starting_balance
                
                position = {
                    'entry': price,
                    'time': row['time'],
                    'size': position_size
                }
        else:
            entry = position['entry']
            change = (price - entry) / entry
            pnl = change * position['size']
            
            # Exit conditions
            should_exit = False
            exit_reason = ''
            
            if rsi > rsi_sell:
                should_exit = True
                exit_reason = f'RSI > {rsi_sell}'
            elif change >= profit_target:
                should_exit = True
                exit_reason = f'{profit_target*100:.0f}% profit target'
            elif change <= -stop_loss and price < ema:
                should_exit = True
                exit_reason = f'-{stop_loss*100:.0f}% loss + below EMA'
            
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
                print("Account blown!")
                break
        
        equity_curve.append(balance)
    
    return balance, trades, equity_curve, skipped_trades

def optimize_parameters(df):
    """Test different parameter combinations"""
    
    best_result = None
    best_return = -float('inf')
    
    # Parameter ranges to test
    rsi_buy_range = [25, 30, 35]
    rsi_sell_range = [65, 70, 75]
    profit_target_range = [0.025, 0.03, 0.035, 0.04]
    stop_loss_range = [0.015, 0.02, 0.025]
    
    results = []
    
    print("Optimizing parameters...")
    print(f"Testing {len(rsi_buy_range) * len(rsi_sell_range) * len(profit_target_range) * len(stop_loss_range)} combinations...\n")
    
    for rsi_buy in rsi_buy_range:
        for rsi_sell in rsi_sell_range:
            for profit_target in profit_target_range:
                for stop_loss in stop_loss_range:
                    balance, trades, equity, skipped = run_optimized_backtest(
                        df, capital=1000,
                        rsi_buy=rsi_buy,
                        rsi_sell=rsi_sell,
                        profit_target=profit_target,
                        stop_loss=stop_loss,
                        enable_safety=True,
                        enable_compounding=True
                    )
                    
                    if trades:
                        trades_df = pd.DataFrame(trades)
                        winning = trades_df[trades_df['pnl'] > 0]
                        win_rate = len(winning) / len(trades)
                        
                        equity_series = pd.Series(equity)
                        running_max = equity_series.expanding().max()
                        drawdown = (equity_series - running_max) / running_max
                        max_dd = drawdown.min()
                        
                        return_pct = (balance / 1000 - 1) * 100
                        
                        # Score: balance return and risk-adjusted
                        score = return_pct * (1 + win_rate) * (1 - abs(max_dd))
                        
                        result = {
                            'rsi_buy': rsi_buy,
                            'rsi_sell': rsi_sell,
                            'profit_target': profit_target,
                            'stop_loss': stop_loss,
                            'balance': balance,
                            'return': return_pct,
                            'trades': len(trades),
                            'win_rate': win_rate * 100,
                            'max_dd': max_dd * 100,
                            'score': score
                        }
                        
                        results.append(result)
                        
                        if score > best_return:
                            best_return = score
                            best_result = result
    
    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # Print top 10
    print("="*80)
    print("TOP 10 PARAMETER COMBINATIONS")
    print("="*80)
    print(f"{'Rank':<5} {'RSI Buy':<8} {'RSI Sell':<9} {'Profit%':<8} {'Stop%':<7} {'Return%':<9} {'Win%':<7} {'MaxDD%':<8} {'Score':<8}")
    print("-"*80)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<5} {r['rsi_buy']:<8} {r['rsi_sell']:<9} {r['profit_target']*100:<8.1f} "
              f"{r['stop_loss']*100:<7.1f} {r['return']:<9.2f} {r['win_rate']:<7.1f} "
              f"{abs(r['max_dd']):<8.2f} {r['score']:<8.2f}")
    
    return best_result, results

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
    
    # Compute indicators
    df = compute_indicators(data)
    
    # Optimize parameters
    best_params, all_results = optimize_parameters(df)
    
    # Run with best parameters
    print(f"\n{'='*80}")
    print("TESTING BEST PARAMETERS")
    print(f"{'='*80}")
    
    balance, trades, equity, skipped = run_optimized_backtest(
        df, capital=1000,
        rsi_buy=best_params['rsi_buy'],
        rsi_sell=best_params['rsi_sell'],
        profit_target=best_params['profit_target'],
        stop_loss=best_params['stop_loss'],
        enable_safety=True,
        enable_compounding=True
    )
    
    print(f"Parameters:")
    print(f"  RSI Buy: {best_params['rsi_buy']}")
    print(f"  RSI Sell: {best_params['rsi_sell']}")
    print(f"  Profit Target: {best_params['profit_target']*100:.1f}%")
    print(f"  Stop Loss: {best_params['stop_loss']*100:.1f}%")
    print(f"\nResults:")
    print(f"  Final Balance: ${balance:.2f}")
    print(f"  Return: {(balance/1000-1)*100:.2f}%")
    print(f"  Total Trades: {len(trades)}")
    print(f"  Skipped (safety): {skipped}")
    
    if trades:
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        print(f"  Win Rate: {len(winning)/len(trades)*100:.2f}%")
        print(f"  Avg Win: ${winning['pnl'].mean():.2f}")
        losing = trades_df[trades_df['pnl'] < 0]
        if len(losing) > 0:
            print(f"  Avg Loss: ${losing['pnl'].mean():.2f}")
    
    # Save best parameters
    config = {
        'rsi_buy': best_params['rsi_buy'],
        'rsi_sell': best_params['rsi_sell'],
        'profit_target_pct': best_params['profit_target'],
        'stop_loss_pct': best_params['stop_loss'],
        'ema_period': 50,
        'rsi_period': 10,
        'enable_safety': True,
        'enable_compounding': True
    }
    
    with open('config/optimized_strategy_params.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nOptimized parameters saved to: config/optimized_strategy_params.json")
    
    # Plot
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curve
    ax = axes[0, 0]
    ax.plot(equity, linewidth=2, color='green')
    ax.set_title('Equity Curve (Optimized Parameters)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='red', linestyle='--', alpha=0.5, label='Starting Capital')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Trade PnL
    ax = axes[0, 1]
    ax.plot(trades_df['pnl'].cumsum(), linewidth=2, color='blue')
    ax.set_title('Cumulative PnL', fontsize=14, fontweight='bold')
    ax.set_xlabel('Trade Number')
    ax.set_ylabel('Cumulative PnL ($)')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    
    # Parameter sensitivity - Return vs RSI Buy
    ax = axes[1, 0]
    rsi_buy_results = {}
    for r in all_results:
        if r['rsi_buy'] not in rsi_buy_results:
            rsi_buy_results[r['rsi_buy']] = []
        rsi_buy_results[r['rsi_buy']].append(r['return'])
    
    for rsi_buy, returns in sorted(rsi_buy_results.items()):
        ax.scatter([rsi_buy]*len(returns), returns, alpha=0.5, s=50)
    ax.set_title('Return vs RSI Buy Level', fontsize=14, fontweight='bold')
    ax.set_xlabel('RSI Buy Level')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3)
    
    # Top 10 comparison
    ax = axes[1, 1]
    top_10 = all_results[:10]
    labels = [f"#{i+1}" for i in range(len(top_10))]
    returns = [r['return'] for r in top_10]
    ax.barh(labels, returns, color='green', alpha=0.7)
    ax.set_title('Top 10 Configurations', fontsize=14, fontweight='bold')
    ax.set_xlabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    plt.savefig('results/final_optimized_strategy.png', dpi=150)
    print(f"Chart saved to: results/final_optimized_strategy.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
