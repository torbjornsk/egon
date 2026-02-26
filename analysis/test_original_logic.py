import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def compute_indicators(df, ema_span=50, rsi_period=10):
    df = df.copy()
    df['EMA'] = df['close'].ewm(span=ema_span).mean()
    
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

def run_backtest(df, capital=1000, leverage=100):
    """Your original backtest logic"""
    position = None
    balance = capital
    trades = []
    equity_curve = [balance]
    
    EMA_SPAN = 50
    RSI_PERIOD = 10
    
    for i in range(max(EMA_SPAN, RSI_PERIOD), len(df)):
        row = df.iloc[i]
        price = row['close']
        ema = row['EMA']
        rsi = row['RSI']
        
        if position is None:
            # Entry: RSI < 30
            if rsi < 30:
                position = {'entry': price, 'time': row['time'], 'index': i}
        else:
            entry = position['entry']
            change = (price - entry) / entry
            pnl = change * balance  # Full position with leverage
            
            # Exit conditions (your original logic)
            should_exit = False
            exit_reason = ''
            
            if rsi > 70:
                should_exit = True
                exit_reason = 'RSI > 70'
            elif change >= 0.03:
                should_exit = True
                exit_reason = '3% profit target'
            elif change <= -0.02 and price < ema:
                should_exit = True
                exit_reason = '-2% loss + below EMA'
            
            if should_exit:
                balance += pnl
                trades.append({
                    'entry_time': position['time'],
                    'exit_time': row['time'],
                    'entry_price': entry,
                    'exit_price': price,
                    'pnl': pnl,
                    'pnl_pct': change * 100,
                    'reason': exit_reason
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
    
    # Compute indicators
    df = compute_indicators(data)
    
    # Run backtest
    final_balance, trades, equity_curve = run_backtest(df, capital=1000)
    
    # Print results
    print("="*60)
    print("BACKTEST RESULTS - YOUR ORIGINAL LOGIC")
    print("="*60)
    print(f"Initial capital: $1,000.00")
    print(f"Final balance:   ${final_balance:.2f}")
    print(f"Total trades:    {len(trades)}")
    print(f"Net PnL:         ${final_balance - 1000:.2f}")
    print(f"Return:          {(final_balance/1000 - 1)*100:.2f}%")
    
    if trades:
        trades_df = pd.DataFrame(trades)
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        print(f"\nWinning trades:  {len(winning_trades)}")
        print(f"Losing trades:   {len(losing_trades)}")
        print(f"Win rate:        {100 * len(winning_trades) / len(trades):.2f}%")
        print(f"Average PnL:     ${trades_df['pnl'].mean():.2f}")
        print(f"Average win:     ${winning_trades['pnl'].mean():.2f}" if len(winning_trades) > 0 else "Average win:     N/A")
        print(f"Average loss:    ${losing_trades['pnl'].mean():.2f}" if len(losing_trades) > 0 else "Average loss:    N/A")
        
        # Calculate max drawdown
        equity_series = pd.Series(equity_curve)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = drawdown.min()
        print(f"Max drawdown:    {max_drawdown*100:.2f}%")
        
        # Exit reasons breakdown
        print(f"\nExit reasons:")
        for reason in trades_df['reason'].unique():
            count = len(trades_df[trades_df['reason'] == reason])
            print(f"  {reason}: {count} ({count/len(trades)*100:.1f}%)")
        
        # Plot results
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        
        # Equity curve
        ax = axes[0, 0]
        ax.plot(equity_curve, linewidth=2, color='blue')
        ax.set_title('Equity Curve', fontsize=14, fontweight='bold')
        ax.set_xlabel('Bar Number')
        ax.set_ylabel('Balance ($)')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=1000, color='red', linestyle='--', alpha=0.5, label='Starting Capital')
        ax.legend()
        
        # Trade PnL distribution
        ax = axes[0, 1]
        ax.hist(trades_df['pnl'], bins=30, alpha=0.7, color='green', edgecolor='black')
        ax.set_title('Trade PnL Distribution', fontsize=14, fontweight='bold')
        ax.set_xlabel('PnL ($)')
        ax.set_ylabel('Frequency')
        ax.axvline(x=0, color='red', linestyle='--', alpha=0.5)
        ax.grid(True, alpha=0.3)
        
        # Cumulative PnL
        ax = axes[1, 0]
        cumulative_pnl = trades_df['pnl'].cumsum()
        ax.plot(cumulative_pnl, linewidth=2, color='purple')
        ax.set_title('Cumulative PnL', fontsize=14, fontweight='bold')
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('Cumulative PnL ($)')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
        
        # Exit reasons pie chart
        ax = axes[1, 1]
        reason_counts = trades_df['reason'].value_counts()
        ax.pie(reason_counts.values, labels=reason_counts.index, autopct='%1.1f%%', startangle=90)
        ax.set_title('Exit Reasons', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig('results/original_logic_analysis.png', dpi=150)
        print(f"\nChart saved to: results/original_logic_analysis.png")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
