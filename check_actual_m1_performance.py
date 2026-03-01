"""
Check what the M1 bot actually did during the gap period
Look at real trades from MT5 history
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

def check_actual_trades():
    """Check actual M1 bot trades during gap period"""
    
    print("="*70)
    print("ACTUAL M1 BOT PERFORMANCE CHECK")
    print("="*70)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    # Get deals from the last 24 hours
    now = datetime.now()
    from_date = now - timedelta(hours=24)
    
    deals = mt5.history_deals_get(from_date, now)
    
    if deals is None or len(deals) == 0:
        print("\nNo deals found in last 24 hours")
        print("This means:")
        print("  - M1 bot didn't trade during the gap period")
        print("  - Or bot wasn't running")
        print("  - Or using different account")
        mt5.shutdown()
        return
    
    # Filter for M1 bot (magic number 234001) and XAUUSD.p
    m1_deals = [d for d in deals if d.magic == 234001 and d.symbol == 'XAUUSD.p']
    
    if len(m1_deals) == 0:
        print("\nNo M1 bot trades found (magic 234001)")
        print(f"Total deals in period: {len(deals)}")
        
        # Show what magic numbers we do have
        magic_numbers = set(d.magic for d in deals)
        print(f"Magic numbers found: {magic_numbers}")
        
        # Check if any XAUUSD.p trades
        xau_deals = [d for d in deals if 'XAUUSD' in d.symbol]
        if xau_deals:
            print(f"\nFound {len(xau_deals)} XAUUSD trades with other magic numbers:")
            for d in xau_deals[:5]:
                print(f"  Magic {d.magic}: {d.symbol} at {datetime.fromtimestamp(d.time)}")
        
        mt5.shutdown()
        return
    
    # Analyze M1 bot trades
    print(f"\nFound {len(m1_deals)} M1 bot deals")
    print("-" * 70)
    
    # Group deals into trades (entry + exit)
    trades = []
    positions = {}
    
    for deal in sorted(m1_deals, key=lambda x: x.time):
        pos_id = deal.position_id
        
        if pos_id not in positions:
            # Opening trade
            positions[pos_id] = {
                'entry_time': datetime.fromtimestamp(deal.time),
                'entry_price': deal.price,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'volume': deal.volume
            }
        else:
            # Closing trade
            entry = positions[pos_id]
            exit_time = datetime.fromtimestamp(deal.time)
            exit_price = deal.price
            
            # Calculate profit
            if entry['type'] == 'LONG':
                price_change = exit_price - entry['entry_price']
            else:
                price_change = entry['entry_price'] - exit_price
            
            profit = deal.profit
            
            trades.append({
                'entry_time': entry['entry_time'],
                'exit_time': exit_time,
                'type': entry['type'],
                'entry_price': entry['entry_price'],
                'exit_price': exit_price,
                'volume': entry['volume'],
                'profit': profit,
                'duration': (exit_time - entry['entry_time']).total_seconds() / 60
            })
            
            del positions[pos_id]
    
    # Show trades
    if trades:
        print(f"\nCompleted Trades: {len(trades)}")
        print("-" * 70)
        
        total_profit = 0
        winning = 0
        
        for i, t in enumerate(trades, 1):
            duration_str = f"{t['duration']:.1f}min"
            profit_str = f"${t['profit']:+.2f}"
            
            print(f"\n{i}. {t['type']} Trade")
            print(f"   Entry:  {t['entry_time'].strftime('%Y-%m-%d %H:%M:%S')} @ ${t['entry_price']:.2f}")
            print(f"   Exit:   {t['exit_time'].strftime('%Y-%m-%d %H:%M:%S')} @ ${t['exit_price']:.2f}")
            print(f"   Volume: {t['volume']} lots")
            print(f"   Duration: {duration_str}")
            print(f"   Profit: {profit_str}")
            
            total_profit += t['profit']
            if t['profit'] > 0:
                winning += 1
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Total Trades: {len(trades)}")
        print(f"Winning: {winning}/{len(trades)} ({winning/len(trades)*100:.0f}%)")
        print(f"Total Profit: ${total_profit:+.2f}")
        
        if total_profit < 100:
            print(f"\n⚠️  Performance was modest during gap period")
            print(f"   Possible reasons:")
            print(f"   - Gap warmup period (bot waits 2 candles after gaps)")
            print(f"   - RSI too high for entry (gap up = overbought)")
            print(f"   - Cooldown periods between trades")
            print(f"   - Conservative exit strategy")
    
    # Check for open positions
    if positions:
        print(f"\n\nOpen Positions: {len(positions)}")
        print("-" * 70)
        for pos_id, pos in positions.items():
            print(f"Position {pos_id}:")
            print(f"  Type: {pos['type']}")
            print(f"  Entry: {pos['entry_time'].strftime('%Y-%m-%d %H:%M:%S')} @ ${pos['entry_price']:.2f}")
            print(f"  Volume: {pos['volume']} lots")
    
    mt5.shutdown()
    print("\n" + "="*70)

if __name__ == "__main__":
    check_actual_trades()
