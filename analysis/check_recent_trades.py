"""
Check Recent Trades from MT5 History

Fetches the last 50 trades and analyzes:
- Entry/exit prices
- Profit/loss
- How far price moved in our favor before exit
- TP distances vs actual movement
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

def main():
    print("="*80)
    print("RECENT TRADE HISTORY ANALYSIS")
    print("="*80)
    print()
    
    # Initialize MT5
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return
    
    try:
        # Get account info
        account_info = mt5.account_info()
        if account_info:
            print(f"Account: {account_info.login}")
            print(f"Balance: ${account_info.balance:.2f}")
            print(f"Equity: ${account_info.equity:.2f}")
            print()
        
        # Get deals from last 7 days
        from_date = datetime.now() - timedelta(days=7)
        to_date = datetime.now()
        
        deals = mt5.history_deals_get(from_date, to_date)
        
        if deals is None or len(deals) == 0:
            print("No deals found in the last 7 days")
            return
        
        print(f"Found {len(deals)} deals in last 7 days")
        print()
        
        # Filter for XAUUSD and our magic numbers
        magic_numbers = [234000, 234001]  # M5 and M1 bots
        xau_deals = [d for d in deals if 'XAUUSD' in d.symbol and d.magic in magic_numbers]
        
        if len(xau_deals) == 0:
            print("No XAUUSD deals found from our bots")
            return
        
        print(f"Found {len(xau_deals)} XAUUSD deals from our bots")
        print()
        
        # Group deals into trades (entry + exit pairs)
        trades = []
        positions = {}
        
        for deal in xau_deals:
            if deal.entry == mt5.DEAL_ENTRY_IN:
                # Opening position
                positions[deal.position_id] = {
                    'entry_deal': deal,
                    'entry_time': datetime.fromtimestamp(deal.time),
                    'entry_price': deal.price,
                    'volume': deal.volume,
                    'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                    'magic': deal.magic
                }
            elif deal.entry == mt5.DEAL_ENTRY_OUT and deal.position_id in positions:
                # Closing position
                pos = positions[deal.position_id]
                exit_time = datetime.fromtimestamp(deal.time)
                exit_price = deal.price
                
                # Calculate profit
                profit = deal.profit
                
                # Calculate price movement
                if pos['type'] == 'LONG':
                    price_change = exit_price - pos['entry_price']
                else:
                    price_change = pos['entry_price'] - exit_price
                
                price_change_pct = (price_change / pos['entry_price']) * 100
                
                # Calculate hold time
                hold_time = (exit_time - pos['entry_time']).total_seconds() / 60
                
                trades.append({
                    'entry_time': pos['entry_time'],
                    'exit_time': exit_time,
                    'type': pos['type'],
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_price,
                    'price_change': price_change,
                    'price_change_pct': price_change_pct,
                    'profit': profit,
                    'volume': pos['volume'],
                    'hold_time_min': hold_time,
                    'magic': pos['magic'],
                    'bot': 'M5' if pos['magic'] == 234000 else 'M1'
                })
                
                del positions[deal.position_id]
        
        if len(trades) == 0:
            print("No completed trades found")
            return
        
        # Sort by exit time
        trades.sort(key=lambda x: x['exit_time'], reverse=True)
        
        # Show last 20 trades
        print("="*80)
        print("LAST 20 TRADES")
        print("="*80)
        print()
        
        for i, trade in enumerate(trades[:20], 1):
            status = "WIN" if trade['profit'] > 0 else "LOSS"
            print(f"{i}. {trade['exit_time'].strftime('%Y-%m-%d %H:%M')} [{trade['bot']}] {trade['type']}")
            print(f"   Entry: ${trade['entry_price']:.2f} -> Exit: ${trade['exit_price']:.2f}")
            print(f"   Price change: ${trade['price_change']:+.2f} ({trade['price_change_pct']:+.3f}%)")
            print(f"   P/L: ${trade['profit']:+.2f} ({status})")
            print(f"   Hold time: {trade['hold_time_min']:.1f} min")
            print()
        
        # Statistics
        print("="*80)
        print("STATISTICS (Last 20 trades)")
        print("="*80)
        print()
        
        recent_20 = trades[:20]
        winning = [t for t in recent_20 if t['profit'] > 0]
        losing = [t for t in recent_20 if t['profit'] < 0]
        
        total_profit = sum(t['profit'] for t in recent_20)
        win_rate = len(winning) / len(recent_20) * 100
        
        print(f"Total trades: {len(recent_20)}")
        print(f"Winning: {len(winning)} ({win_rate:.1f}%)")
        print(f"Losing: {len(losing)} ({100-win_rate:.1f}%)")
        print(f"Total P/L: ${total_profit:+.2f}")
        print()
        
        if winning:
            avg_win = sum(t['profit'] for t in winning) / len(winning)
            print(f"Average win: ${avg_win:.2f}")
        
        if losing:
            avg_loss = sum(t['profit'] for t in losing) / len(losing)
            print(f"Average loss: ${avg_loss:.2f}")
        
        print()
        
        # Analyze green-to-red potential
        print("="*80)
        print("ANALYZING PRICE MOVEMENT")
        print("="*80)
        print()
        
        print("Checking if positions could have been more profitable...")
        print("(This requires fetching candle data for each trade)")
        print()
        
        # For a few recent trades, check peak profit potential
        for i, trade in enumerate(trades[:5], 1):
            print(f"{i}. {trade['exit_time'].strftime('%H:%M')} [{trade['bot']}] {trade['type']} - ${trade['profit']:+.2f}")
            
            # Get candle data for the trade period
            symbol = 'XAUUSD.p'
            timeframe = mt5.TIMEFRAME_M1 if trade['bot'] == 'M1' else mt5.TIMEFRAME_M5
            
            # Get candles from entry to exit + a bit after
            start_time = trade['entry_time']
            end_time = trade['exit_time'] + timedelta(minutes=30)
            
            rates = mt5.copy_rates_range(symbol, timeframe, start_time, end_time)
            
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                
                # Calculate peak profit potential
                if trade['type'] == 'LONG':
                    peak_price = df['high'].max()
                    peak_profit_potential = (peak_price - trade['entry_price']) * trade['volume'] * 100
                else:
                    peak_price = df['low'].min()
                    peak_profit_potential = (trade['entry_price'] - peak_price) * trade['volume'] * 100
                
                missed_profit = peak_profit_potential - trade['profit']
                
                print(f"   Entry: ${trade['entry_price']:.2f}, Exit: ${trade['exit_price']:.2f}")
                print(f"   Peak price: ${peak_price:.2f}")
                print(f"   Actual profit: ${trade['profit']:+.2f}")
                print(f"   Peak potential: ${peak_profit_potential:+.2f}")
                
                if missed_profit > 0:
                    print(f"   Missed profit: ${missed_profit:.2f} ⚠️")
                else:
                    print(f"   Captured peak profit ✓")
            
            print()
        
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
