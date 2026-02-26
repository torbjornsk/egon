"""
Deep analysis of M1 bot performance
Analyze patterns in wins vs losses to identify improvement opportunities
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def connect_mt5():
    """Connect to MT5"""
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return False
    print("Connected to MT5")
    return True

def get_historical_trades(days=7):
    """Get trades from last N days"""
    start_date = datetime.now() - timedelta(days=days)
    
    deals = mt5.history_deals_get(start_date, datetime.now())
    
    if deals is None or len(deals) == 0:
        print(f"No deals found in last {days} days")
        return None
    
    df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Filter for XAUUSD M1 bot
    df = df[(df['symbol'] == 'XAUUSD') & (df['magic'] == 234001)]
    
    print(f"\nAnalyzing {len(df)} M1 deals from last {days} days")
    return df

def analyze_trade_patterns(deals):
    """Analyze patterns in winning vs losing trades"""
    if deals is None or len(deals) == 0:
        return
    
    # Group by position to get complete trades
    trades = []
    for ticket in deals['position_id'].unique():
        position_deals = deals[deals['position_id'] == ticket].sort_values('time')
        
        if len(position_deals) >= 2:
            entry = position_deals.iloc[0]
            exit_deal = position_deals.iloc[-1]
            
            profit = exit_deal['profit']
            duration = (exit_deal['time'] - entry['time']).total_seconds() / 60
            
            trades.append({
                'ticket': ticket,
                'entry_time': entry['time'],
                'exit_time': exit_deal['time'],
                'entry_price': entry['price'],
                'exit_price': exit_deal['price'],
                'profit': profit,
                'duration_min': duration,
                'type': 'LONG' if entry['type'] == 0 else 'SHORT',
                'volume': entry['volume'],
                'hour': entry['time'].hour,
                'day_of_week': entry['time'].dayofweek
            })
    
    if not trades:
        print("No completed trades found")
        return
    
    df = pd.DataFrame(trades)
    
    # Separate wins and losses
    wins = df[df['profit'] > 0].copy()
    losses = df[df['profit'] < 0].copy()
    
    print(f"\n{'='*80}")
    print(f"DEEP ANALYSIS - M1 BOT ({len(df)} trades)")
    print(f"{'='*80}")
    
    # Overall stats
    print(f"\nOverall Performance:")
    print(f"  Total Profit: ${df['profit'].sum():.2f}")
    print(f"  Win Rate: {len(wins)/len(df)*100:.1f}%")
    print(f"  Profit Factor: {abs(wins['profit'].sum() / losses['profit'].sum()):.2f}")
    print(f"  Avg Win: ${wins['profit'].mean():.2f}")
    print(f"  Avg Loss: ${losses['profit'].mean():.2f}")
    print(f"  Win/Loss Ratio: {abs(wins['profit'].mean() / losses['profit'].mean()):.2f}")
    
    # Duration analysis
    print(f"\n{'='*80}")
    print(f"DURATION ANALYSIS")
    print(f"{'='*80}")
    print(f"\nWinning Trades:")
    print(f"  Avg Duration: {wins['duration_min'].mean():.1f} min")
    print(f"  Median Duration: {wins['duration_min'].median():.1f} min")
    print(f"  Quick wins (<3min): {len(wins[wins['duration_min'] < 3])} (${wins[wins['duration_min'] < 3]['profit'].sum():.2f})")
    print(f"  Medium wins (3-10min): {len(wins[(wins['duration_min'] >= 3) & (wins['duration_min'] < 10)])} (${wins[(wins['duration_min'] >= 3) & (wins['duration_min'] < 10)]['profit'].sum():.2f})")
    print(f"  Long wins (>10min): {len(wins[wins['duration_min'] >= 10])} (${wins[wins['duration_min'] >= 10]['profit'].sum():.2f})")
    
    print(f"\nLosing Trades:")
    print(f"  Avg Duration: {losses['duration_min'].mean():.1f} min")
    print(f"  Median Duration: {losses['duration_min'].median():.1f} min")
    print(f"  Quick losses (<3min): {len(losses[losses['duration_min'] < 3])} (${losses[losses['duration_min'] < 3]['profit'].sum():.2f})")
    print(f"  Medium losses (3-10min): {len(losses[(losses['duration_min'] >= 3) & (losses['duration_min'] < 10)])} (${losses[(losses['duration_min'] >= 3) & (losses['duration_min'] < 10)]['profit'].sum():.2f})")
    print(f"  Long losses (>10min): {len(losses[losses['duration_min'] >= 10])} (${losses[losses['duration_min'] >= 10]['profit'].sum():.2f})")
    
    # Type analysis (LONG vs SHORT)
    print(f"\n{'='*80}")
    print(f"TRADE TYPE ANALYSIS")
    print(f"{'='*80}")
    
    for trade_type in ['LONG', 'SHORT']:
        type_trades = df[df['type'] == trade_type]
        type_wins = wins[wins['type'] == trade_type]
        type_losses = losses[losses['type'] == trade_type]
        
        if len(type_trades) > 0:
            print(f"\n{trade_type} Trades:")
            print(f"  Count: {len(type_trades)}")
            print(f"  Win Rate: {len(type_wins)/len(type_trades)*100:.1f}%")
            print(f"  Total Profit: ${type_trades['profit'].sum():.2f}")
            print(f"  Avg Profit: ${type_trades['profit'].mean():.2f}")
    
    # Day of week analysis
    print(f"\n{'='*80}")
    print(f"DAY OF WEEK ANALYSIS")
    print(f"{'='*80}")
    
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for day_num in range(7):
        day_trades = df[df['day_of_week'] == day_num]
        if len(day_trades) > 0:
            day_wins = wins[wins['day_of_week'] == day_num]
            print(f"\n{days[day_num]}:")
            print(f"  Trades: {len(day_trades)}")
            print(f"  Win Rate: {len(day_wins)/len(day_trades)*100:.1f}%")
            print(f"  Profit: ${day_trades['profit'].sum():.2f}")
    
    # Loss size distribution
    print(f"\n{'='*80}")
    print(f"LOSS SIZE DISTRIBUTION")
    print(f"{'='*80}")
    
    loss_bins = [
        (0, 5, "Tiny ($0-5)"),
        (5, 10, "Small ($5-10)"),
        (10, 20, "Medium ($10-20)"),
        (20, 50, "Large ($20-50)"),
        (50, 1000, "Huge (>$50)")
    ]
    
    for min_loss, max_loss, label in loss_bins:
        bin_losses = losses[(losses['profit'].abs() >= min_loss) & (losses['profit'].abs() < max_loss)]
        if len(bin_losses) > 0:
            print(f"\n{label}:")
            print(f"  Count: {len(bin_losses)}")
            print(f"  Total: ${bin_losses['profit'].sum():.2f}")
            print(f"  Avg Duration: {bin_losses['duration_min'].mean():.1f} min")
    
    # Consecutive loss analysis
    print(f"\n{'='*80}")
    print(f"CONSECUTIVE LOSS PATTERNS")
    print(f"{'='*80}")
    
    df_sorted = df.sort_values('entry_time')
    consecutive = 0
    max_consecutive = 0
    consecutive_streaks = []
    
    for idx, row in df_sorted.iterrows():
        if row['profit'] < 0:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            if consecutive > 0:
                consecutive_streaks.append(consecutive)
            consecutive = 0
    
    if consecutive > 0:
        consecutive_streaks.append(consecutive)
    
    print(f"\nMax Consecutive Losses: {max_consecutive}")
    print(f"Streaks of 3+ losses: {len([s for s in consecutive_streaks if s >= 3])}")
    print(f"Streaks of 5+ losses: {len([s for s in consecutive_streaks if s >= 5])}")
    print(f"Streaks of 8+ losses: {len([s for s in consecutive_streaks if s >= 8])}")
    
    # Recommendations
    print(f"\n{'='*80}")
    print(f"KEY INSIGHTS & RECOMMENDATIONS")
    print(f"{'='*80}")
    
    # Check if quick losses are the problem
    quick_loss_pct = len(losses[losses['duration_min'] < 3]) / len(losses) * 100
    if quick_loss_pct > 60:
        print(f"\n⚠️  {quick_loss_pct:.0f}% of losses happen in <3 minutes")
        print(f"   → Consider: Stricter entry filters (lower RSI threshold, trend confirmation)")
    
    # Check win/loss ratio
    win_loss_ratio = abs(wins['profit'].mean() / losses['profit'].mean())
    if win_loss_ratio < 1.5:
        print(f"\n⚠️  Win/Loss ratio is {win_loss_ratio:.2f} (target: >1.5)")
        print(f"   → Consider: Tighter stops OR wider profit targets")
    
    # Check if one direction is better
    long_profit = df[df['type'] == 'LONG']['profit'].sum()
    short_profit = df[df['type'] == 'SHORT']['profit'].sum()
    if abs(long_profit - short_profit) > 100:
        better = "LONG" if long_profit > short_profit else "SHORT"
        print(f"\n💡 {better} trades are significantly more profitable")
        print(f"   → Consider: Focus on {better} trades or investigate why {better} works better")
    
    # Check profit factor
    profit_factor = abs(wins['profit'].sum() / losses['profit'].sum())
    if profit_factor < 1.5:
        print(f"\n⚠️  Profit factor is {profit_factor:.2f} (target: >1.5)")
        print(f"   → Strategy is barely profitable, needs optimization")
    
    return df

def main():
    if not connect_mt5():
        return
    
    # Analyze last 7 days
    deals = get_historical_trades(days=7)
    
    if deals is not None:
        analyze_trade_patterns(deals)
    
    mt5.shutdown()
    print(f"\n{'='*80}")
    print("Analysis complete!")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
