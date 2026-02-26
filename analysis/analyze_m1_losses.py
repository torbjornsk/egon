"""
Detailed analysis of M1 bot losses
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
    
    print("="*100)
    print("M1 BOT DETAILED TRADE ANALYSIS (Last 8 Hours)")
    print("="*100)
    print()
    
    # Get M1 trades
    from_date = datetime.now() - timedelta(hours=8)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if not deals:
        print("No trades found")
        mt5.shutdown()
        return
    
    # Filter M1 bot trades (magic 234001)
    m1_deals = [d for d in deals if d.symbol == 'XAUUSD' and d.magic == 234001]
    
    # Group by position ID
    positions = {}
    for deal in m1_deals:
        pos_id = deal.position_id
        if pos_id not in positions:
            positions[pos_id] = []
        positions[pos_id].append(deal)
    
    print(f"Total M1 Positions: {len(positions)}")
    print()
    
    # Analyze each position
    trades = []
    for pos_id, deals_list in positions.items():
        if len(deals_list) < 2:
            continue
        
        # Sort by time
        deals_list.sort(key=lambda x: x.time)
        
        entry_deal = deals_list[0]
        exit_deal = deals_list[-1]
        
        if entry_deal.entry != mt5.DEAL_ENTRY_IN or exit_deal.entry != mt5.DEAL_ENTRY_OUT:
            continue
        
        entry_time = datetime.fromtimestamp(entry_deal.time)
        exit_time = datetime.fromtimestamp(exit_deal.time)
        duration_min = (exit_time - entry_time).total_seconds() / 60
        
        trade_type = "LONG" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SHORT"
        
        trades.append({
            'pos_id': pos_id,
            'type': trade_type,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_deal.price,
            'exit_price': exit_deal.price,
            'volume': entry_deal.volume,
            'profit': exit_deal.profit,
            'duration_min': duration_min,
            'comment': exit_deal.comment
        })
    
    # Sort by time
    trades.sort(key=lambda x: x['entry_time'])
    
    # Statistics
    winning = [t for t in trades if t['profit'] > 0]
    losing = [t for t in trades if t['profit'] < 0]
    
    total_profit = sum(t['profit'] for t in trades)
    
    print(f"STATISTICS:")
    print(f"  Total Trades: {len(trades)}")
    print(f"  Winning: {len(winning)} ({len(winning)/len(trades)*100:.1f}%)")
    print(f"  Losing: {len(losing)} ({len(losing)/len(trades)*100:.1f}%)")
    print(f"  Total P/L: ${total_profit:.2f}")
    print(f"  Avg Win: ${sum(t['profit'] for t in winning)/len(winning):.2f}" if winning else "  Avg Win: N/A")
    print(f"  Avg Loss: ${sum(t['profit'] for t in losing)/len(losing):.2f}" if losing else "  Avg Loss: N/A")
    print(f"  Avg Duration: {sum(t['duration_min'] for t in trades)/len(trades):.1f} minutes")
    print()
    
    # Show all trades
    print("ALL TRADES:")
    print(f"{'Time':<12} | {'Type':<5} | {'Entry':>8} | {'Exit':>8} | {'Change':>7} | {'Duration':>8} | {'P/L':>9} | {'Comment':<20}")
    print("="*100)
    
    for t in trades:
        time_str = t['entry_time'].strftime('%H:%M')
        price_change = t['exit_price'] - t['entry_price'] if t['type'] == 'LONG' else t['entry_price'] - t['exit_price']
        price_change_pct = (price_change / t['entry_price']) * 100
        duration_str = f"{t['duration_min']:.0f}m"
        pnl_str = f"${t['profit']:+.2f}"
        comment = t['comment'][:20]
        
        print(f"{time_str:<12} | {t['type']:<5} | ${t['entry_price']:>7.2f} | ${t['exit_price']:>7.2f} | {price_change_pct:>6.2f}% | {duration_str:>8} | {pnl_str:>9} | {comment:<20}")
    
    print("="*100)
    
    # Identify problems
    print()
    print("PROBLEM ANALYSIS:")
    
    # Check for stop losses
    sl_trades = [t for t in losing if 'close' in t['comment'].lower() or t['duration_min'] < 5]
    if sl_trades:
        print(f"⚠ {len(sl_trades)} trades appear to be stop losses (quick losses)")
        avg_sl_loss = sum(t['profit'] for t in sl_trades) / len(sl_trades)
        print(f"  Average SL loss: ${avg_sl_loss:.2f}")
    
    # Check win rate
    if len(winning) / len(trades) < 0.55:
        print(f"⚠ Win rate is low ({len(winning)/len(trades)*100:.1f}%)")
        print(f"  Expected: ~60-65% based on backtests")
    
    # Check if losses are bigger than wins
    if winning and losing:
        avg_win = sum(t['profit'] for t in winning) / len(winning)
        avg_loss = abs(sum(t['profit'] for t in losing) / len(losing))
        if avg_loss > avg_win * 2:
            print(f"⚠ Average loss (${avg_loss:.2f}) is much larger than average win (${avg_win:.2f})")
            print(f"  This suggests stops are too tight or entries are poor")
    
    # Check for consecutive losses
    consecutive_losses = 0
    max_consecutive = 0
    for t in trades:
        if t['profit'] < 0:
            consecutive_losses += 1
            max_consecutive = max(max_consecutive, consecutive_losses)
        else:
            consecutive_losses = 0
    
    if max_consecutive >= 3:
        print(f"⚠ Max consecutive losses: {max_consecutive}")
        print(f"  Consider pausing bot during strong trends")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
