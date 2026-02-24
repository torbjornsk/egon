import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def compute_indicators(df, ema_span=50, rsi_period=10):
    df = df.copy()
    
    # Your original indicators
    df['EMA'] = df['close'].ewm(span=ema_span).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Additional trend detection
    df['EMA_long'] = df['close'].ewm(span=200).mean()  # Long-term trend
    df['price_above_ema'] = df['close'] > df['EMA']
    df['price_above_ema_long'] = df['close'] > df['EMA_long']
    
    # Trend strength (how far above/below EMA)
    df['trend_strength'] = (df['close'] - df['EMA']) / df['EMA'] * 100
    
    # Volatility (ATR)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # Market regime detection
    # Uptrend: price above both EMAs and rising
    df['uptrend'] = (df['price_above_ema'] & df['price_above_ema_long'] & 
                     (df['EMA'] > df['EMA'].shift(5)))
    
    # Strong uptrend: even more aggressive
    df['strong_uptrend'] = (df['uptrend'] & (df['trend_strength'] > 1))
    
    return df

def run_enhanced_backtest(df, capital=1000, leverage=100, 
                          enable_trend_filter=True,
                          enable_compounding=True,
                          max_risk_per_trade=0.05):
    """
    Enhanced version with:
    - Trend filter (only trade in uptrends)
    - Compounding (reinvest profits)
    - Adjustable position sizing
    """
    position = None
    balance = capital
    starting_balance = capital
    trades = []
    equity_curve = [balance]
    
    EMA_SPAN = 50
    RSI_PERIOD = 10
    
    for i in range(max(EMA_SPAN, RSI_PERIOD, 200), len(df)):
        row = df.iloc[i]
        price = row['close']
        ema = row['EMA']
        rsi = row['RSI']
        
        if position is None:
            # Entry conditions
            entry_signal = rsi < 30
            
            # Trend filter: only enter if in uptrend
            if enable_trend_filter:
                entry_signal = entry_signal and row['uptrend']
            
            if entry_signal:
                # Position sizing
                if enable_compounding:
                    position_size = balance  # Use current balance
                else:
                    position_size = starting_balance  # Fixed position
                
                # Limit risk per trade
                max_position = balance * (1 / max_risk_per_trade)
                position_size = min(position_size, max_position)
                
                position = {
                    'entry': price,
                    'time': row['time'],
                    'index': i,
                    'size': position_size,
                    'in_strong_uptrend': row['strong_uptrend']
                }
        else:
            entry = position['entry']
            change = (price - entry) / entry
            pnl = change * position['size']
            
            # Exit conditions
            should_exit = False
            exit_reason = ''
            
            # Standard exits (your original logic)
            if rsi > 70:
                should_exit = True
                exit_reason = 'RSI > 70'
            elif change >= 0.03:
                should_exit = True
                exit_reason = '3% profit target'
            elif change <= -0.02 and price < ema:
                should_exit = True
                exit_reason = '-2% loss + below EMA'
            
            # Additional safety: exit if trend breaks
            if enable_trend_filter and not row['uptrend']:
                if change < 0:  # Only exit on trend break if losing
                    should_exit = True
                    exit_reason = 'Trend break (safety)'
            
            # Aggressive profit taking in strong uptrends
            if position['in_strong_uptrend'] and change >= 0.05:
                should_exit = True
                exit_reason = '5% profit (strong trend)'
            
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
    
    return balance, trades, equity_curve

def compare_strategies(df):
    """Compare different strategy configurations"""
    
    configs = {
        "Original (No Filter)": {
            'enable_trend_filter': False,
            'enable_compounding': False,
            'max_risk_per_trade': 1.0
        },
        "With Trend Filter": {
            'enable_trend_filter': True,
            'enable_compounding': False,
            'max_risk_per_trade': 1.0
        },
        "With Compounding": {
            'enable_trend_filter': False,
            'enable_compounding': True,
            'max_risk_per_trade': 0.05
        },
        "Full Enhanced": {
            'enable_trend_filter': True,
            'enable_compounding': True,
            'max_risk_per_trade': 0.05
        }
    }
    
    results = {}
    
    for name, config in configs.items():
        print(f"\n{'='*60}")
        print(f"Testing: {name}")
        print(f"{'='*60}")
        
        final_balance, trades, equity_curve = run_enhanced_backtest(
            df, capital=1000, **config
        )
        
        results[name] = {
            'balance': final_balance,
            'trades': trades,
            'equity': equity_curve
        }
        
        if trades:
            trades_df = pd.DataFrame(trades)
            winning = trades_df[trades_df['pnl'] > 0]
            losing = trades_df[trades_df['pnl'] < 0]
            
            equity_series = pd.Series(equity_curve)
            running_max = equity_series.expanding().max()
            drawdown = (equity_series - running_max) / running_max
            max_dd = drawdown.min()
            
            print(f"Final balance:   ${final_balance:.2f}")
            print(f"Return:          {(final_balance/1000 - 1)*100:.2f}%")
            print(f"Total trades:    {len(trades)}")
            print(f"Win rate:        {len(winning)/len(trades)*100:.2f}%")
            print(f"Max drawdown:    {max_dd*100:.2f}%")
            print(f"Avg win:         ${winning['pnl'].mean():.2f}" if len(winning) > 0 else "Avg win:         N/A")
            print(f"Avg loss:        ${losing['pnl'].mean():.2f}" if len(losing) > 0 else "Avg loss:        N/A")
    
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
    print(f"Time span: {days_span} days")
    
    # Compute indicators
    df = compute_indicators(data)
    
    # Compare strategies
    results = compare_strategies(df)
    
    # Plot comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # Equity curves
    ax = axes[0, 0]
    colors = ['blue', 'green', 'orange', 'red']
    for (name, result), color in zip(results.items(), colors):
        ax.plot(result['equity'], label=name, linewidth=2, color=color, alpha=0.8)
    ax.set_title('Equity Curves Comparison', fontsize=14, fontweight='bold')
    ax.set_xlabel('Bar Number')
    ax.set_ylabel('Balance ($)')
    ax.axhline(y=1000, color='black', linestyle='--', alpha=0.3, label='Starting Capital')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')  # Log scale to see all curves
    
    # Returns comparison
    ax = axes[0, 1]
    names = list(results.keys())
    returns = [(results[name]['balance']/1000 - 1)*100 for name in names]
    ax.bar(range(len(names)), returns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Return Comparison', fontsize=14, fontweight='bold')
    ax.set_ylabel('Return (%)')
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    
    # Trade count comparison
    ax = axes[1, 0]
    trade_counts = [len(results[name]['trades']) for name in names]
    ax.bar(range(len(names)), trade_counts, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Number of Trades', fontsize=14, fontweight='bold')
    ax.set_ylabel('Trades')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Max drawdown comparison
    ax = axes[1, 1]
    drawdowns = []
    for name in names:
        equity_series = pd.Series(results[name]['equity'])
        running_max = equity_series.expanding().max()
        dd = (equity_series - running_max) / running_max
        drawdowns.append(abs(dd.min()) * 100)
    
    ax.bar(range(len(names)), drawdowns, color=colors, alpha=0.7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha='right')
    ax.set_title('Max Drawdown (Lower is Better)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Max Drawdown (%)')
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('results/enhanced_strategy_comparison.png', dpi=150)
    print(f"\n{'='*60}")
    print("Chart saved to: results/enhanced_strategy_comparison.png")
    print(f"{'='*60}")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
