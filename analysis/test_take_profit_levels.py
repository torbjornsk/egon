"""Test different take profit levels"""

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

def test_tp_level(data, config, tp_pct):
    """Test a specific take profit level"""
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
        profit_target_pct=tp_pct,
        max_drawdown_limit=config['max_drawdown_limit'],
        enable_shorts=config['enable_shorts'],
        warmup_candles=3
    )
    
    if not trades:
        return None
    
    trades_df = pd.DataFrame(trades)
    winning = trades_df[trades_df['pnl'] > 0]
    
    equity_series = pd.Series(equity)
    running_max = equity_series.expanding().max()
    drawdown = (equity_series - running_max) / running_max
    max_dd = drawdown.min()
    
    return_pct = (balance / 1000 - 1) * 100
    
    # Count exits by reason
    tp_exits = len(trades_df[trades_df['reason'] == 'Profit target'])
    rsi_exits = len(trades_df[trades_df['reason'].str.contains('RSI', na=False)])
    sl_exits = len(trades_df[trades_df['reason'] == 'Stop loss'])
    
    return {
        'tp_pct': tp_pct * 100,
        'balance': balance,
        'return': return_pct,
        'trades': len(trades),
        'win_rate': len(winning) / len(trades) * 100,
        'max_dd': abs(max_dd) * 100,
        'avg_win': winning['pnl'].mean() if len(winning) > 0 else 0,
        'avg_loss': trades_df[trades_df['pnl'] < 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0,
        'tp_exits': tp_exits,
        'rsi_exits': rsi_exits,
        'sl_exits': sl_exits,
        'paused': paused
    }

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
    
    print(f"Data: {len(data)} bars from {data['time'].min()} to {data['time'].max()}")
    print()
    
    # Load configuration
    with open('config/safe_leveraged_params.json', 'r') as f:
        config = json.load(f)
    
    # Test different take profit levels
    tp_levels = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]
    
    print("Testing different take profit levels...")
    print("="*100)
    print(f"{'TP %':>6} | {'Return':>8} | {'Trades':>6} | {'Win%':>5} | {'MaxDD':>6} | {'TP Exits':>8} | {'RSI Exits':>9} | {'SL Exits':>8} | {'Avg Win':>8} | {'Avg Loss':>9}")
    print("="*100)
    
    results = []
    for tp in tp_levels:
        result = test_tp_level(data, config, tp)
        if result:
            results.append(result)
            print(f"{result['tp_pct']:>6.1f} | {result['return']:>7.2f}% | {result['trades']:>6} | "
                  f"{result['win_rate']:>5.1f} | {result['max_dd']:>5.1f}% | "
                  f"{result['tp_exits']:>8} | {result['rsi_exits']:>9} | {result['sl_exits']:>8} | "
                  f"${result['avg_win']:>7.2f} | ${result['avg_loss']:>8.2f}")
    
    print("="*100)
    
    # Find best by return
    best_return = max(results, key=lambda x: x['return'])
    print(f"\nBest Return: {best_return['tp_pct']:.1f}% TP → {best_return['return']:.2f}% return")
    
    # Find best risk-adjusted (return / max_dd)
    best_risk_adj = max(results, key=lambda x: x['return'] / x['max_dd'] if x['max_dd'] > 0 else 0)
    print(f"Best Risk-Adjusted: {best_risk_adj['tp_pct']:.1f}% TP → {best_risk_adj['return']:.2f}% return, {best_risk_adj['max_dd']:.2f}% DD")
    
    # Find best win rate
    best_wr = max(results, key=lambda x: x['win_rate'])
    print(f"Best Win Rate: {best_wr['tp_pct']:.1f}% TP → {best_wr['win_rate']:.1f}% win rate")
    
    mt5.disconnect()

if __name__ == "__main__":
    main()
