"""Quick test to compare with/without gap protection"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.mt5_connector import MT5Connector
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json

# Import the backtest function
exec(open('safe_leveraged_strategy.py').read().split('def main()')[0])

def main():
    mt5 = MT5Connector()
    if not mt5.connect():
        print("Failed to connect to MT5")
        return
    
    print("Fetching data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    if data is None:
        print("Failed to fetch data")
        mt5.disconnect()
        return
    
    print(f"Data: {len(data)} bars\n")
    
    # Load configuration
    with open('config/safe_leveraged_params.json', 'r') as f:
        config = json.load(f)
    
    print("Testing full 8-month period with gap protection...")
    print("="*60)
    
    balance, trades, equity, paused = run_safe_leveraged_backtest(
        data,
        capital=1000,
        position_size_pct=config['position_size_pct'],
        leverage=config['leverage'],
        fast_ema=config['fast_ema'],
        slow_ema=config['slow_ema'],
        rsi_period=config['rsi_period'],
        rsi_buy=config['rsi_buy'],
        rsi_sell=config['rsi_sell'],
        atr_multiplier=config['atr_multiplier'],
        profit_target_pct=config['profit_target_pct'],
        max_drawdown_limit=config['max_drawdown_limit'],
        enable_shorts=config['enable_shorts'],
        warmup_candles=3
    )
    
    if trades:
        trades_df = pd.DataFrame(trades)
        winning = trades_df[trades_df['pnl'] > 0]
        
        equity_series = pd.Series(equity)
        running_max = equity_series.expanding().max()
        drawdown = (equity_series - running_max) / running_max
        max_dd = drawdown.min()
        
        return_pct = (balance / 1000 - 1) * 100
        
        # Count gap-related exits
        gap_exits = len(trades_df[trades_df['reason'] == 'market_gap'])
        
        print(f"\nRESULTS WITH GAP PROTECTION:")
        print(f"  Final Balance: ${balance:.2f}")
        print(f"  Return: {return_pct:.2f}%")
        print(f"  Total Trades: {len(trades)}")
        print(f"  Gap Exits: {gap_exits}")
        print(f"  Win Rate: {len(winning)/len(trades)*100:.1f}%")
        print(f"  Max Drawdown: {abs(max_dd)*100:.2f}%")
        print(f"  Trading Paused: {'Yes' if paused else 'No'}")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
