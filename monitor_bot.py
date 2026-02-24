"""
Simple monitoring dashboard for the trading bot
Shows real-time stats and recent trades
"""

import MetaTrader5 as mt5
import time
import os
from datetime import datetime, timedelta

def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_account_stats():
    """Get current account statistics"""
    account_info = mt5.account_info()
    if not account_info:
        return None
    
    return {
        'balance': account_info.balance,
        'equity': account_info.equity,
        'margin': account_info.margin,
        'free_margin': account_info.margin_free,
        'profit': account_info.profit,
        'leverage': account_info.leverage
    }

def get_open_positions():
    """Get all open positions"""
    positions = mt5.positions_get(symbol='XAUUSD')
    return list(positions) if positions else []

def get_recent_deals(hours=24):
    """Get recent closed deals"""
    from_date = datetime.now() - timedelta(hours=hours)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if deals:
        # Filter for XAUUSD
        xau_deals = [d for d in deals if d.symbol == 'XAUUSD' and d.entry == mt5.DEAL_ENTRY_OUT]
        return xau_deals
    return []

def display_dashboard():
    """Display the monitoring dashboard"""
    clear_screen()
    
    print("="*80)
    print(" "*25 + "GOLD TRADING BOT MONITOR")
    print("="*80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Account Stats
    stats = get_account_stats()
    if stats:
        print("ACCOUNT STATUS")
        print("-"*80)
        print(f"Balance:      ${stats['balance']:>12,.2f}")
        print(f"Equity:       ${stats['equity']:>12,.2f}")
        print(f"Profit:       ${stats['profit']:>12,.2f}  ({stats['profit']/stats['balance']*100:+.2f}%)")
        print(f"Free Margin:  ${stats['free_margin']:>12,.2f}")
        print(f"Leverage:     1:{stats['leverage']}")
        print()
    
    # Open Positions
    positions = get_open_positions()
    print(f"OPEN POSITIONS ({len(positions)})")
    print("-"*80)
    
    if positions:
        for pos in positions:
            pos_type = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
            print(f"Ticket: {pos.ticket}")
            print(f"  Type: {pos_type}")
            print(f"  Volume: {pos.volume}")
            print(f"  Entry: {pos.price_open:.2f}")
            print(f"  Current: {pos.price_current:.2f}")
            print(f"  SL: {pos.sl:.2f}")
            print(f"  TP: {pos.tp:.2f}")
            print(f"  Profit: ${pos.profit:.2f}")
            print()
    else:
        print("No open positions")
        print()
    
    # Recent Trades
    deals = get_recent_deals(hours=24)
    print(f"RECENT TRADES (Last 24 hours: {len(deals)})")
    print("-"*80)
    
    if deals:
        total_profit = sum(d.profit for d in deals)
        winning = [d for d in deals if d.profit > 0]
        
        print(f"Total Trades: {len(deals)}")
        print(f"Winning: {len(winning)} ({len(winning)/len(deals)*100:.1f}%)")
        print(f"Total P/L: ${total_profit:.2f}")
        print()
        
        print("Last 5 trades:")
        for deal in deals[-5:]:
            time_str = datetime.fromtimestamp(deal.time).strftime('%H:%M:%S')
            profit_str = f"${deal.profit:+.2f}"
            print(f"  {time_str} - Ticket {deal.position_id} - {profit_str}")
    else:
        print("No trades in last 24 hours")
    
    print()
    print("="*80)
    print("Press Ctrl+C to exit")

def main():
    """Main monitoring loop"""
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
    
    try:
        while True:
            display_dashboard()
            time.sleep(5)  # Update every 5 seconds
    except KeyboardInterrupt:
        print("\nMonitor stopped")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()
