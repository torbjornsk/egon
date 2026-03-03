"""
Comprehensive trade reporting tool
Shows all trades with entry/exit details, SL/TP levels, and statistics
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import argparse

def get_position_details(position_id):
    """Get full position details including SL/TP from history"""
    # Get all deals for this position
    deals = mt5.history_deals_get(position=position_id)
    if not deals or len(deals) < 2:
        return None
    
    entry_deal = deals[0]
    exit_deal = deals[-1]
    
    # Get the order that created the position to find SL/TP
    orders = mt5.history_orders_get(position=position_id)
    sl = None
    tp = None
    
    if orders:
        for order in orders:
            if order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
                sl = order.sl
                tp = order.tp
                break
    
    return {
        'entry_deal': entry_deal,
        'exit_deal': exit_deal,
        'sl': sl,
        'tp': tp
    }

def analyze_trades(hours=24, magic_number=None):
    """Analyze trades from the last N hours"""
    from_date = datetime.now() - timedelta(hours=hours)
    
    # Get all deals
    deals = mt5.history_deals_get(from_date, datetime.now() + timedelta(hours=3))
    
    if not deals:
        return []
    
    # Filter by symbol and magic number
    filtered_deals = [d for d in deals if 'XAUUSD' in d.symbol]
    if magic_number is not None:
        filtered_deals = [d for d in filtered_deals if d.magic == magic_number]
    
    # Group by position ID
    positions = {}
    for deal in filtered_deals:
        pos_id = deal.position_id
        if pos_id not in positions:
            positions[pos_id] = []
        positions[pos_id].append(deal)
    
    # Analyze each position
    trades = []
    for pos_id, deals_list in positions.items():
        if len(deals_list) < 2:
            continue
        
        deals_list.sort(key=lambda x: x.time)
        entry_deal = deals_list[0]
        exit_deal = deals_list[-1]
        
        if entry_deal.entry != mt5.DEAL_ENTRY_IN or exit_deal.entry != mt5.DEAL_ENTRY_OUT:
            continue
        
        # Get SL/TP from orders
        orders = mt5.history_orders_get(position=pos_id)
        sl = None
        tp = None
        
        if orders:
            for order in orders:
                if order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
                    sl = order.sl if order.sl > 0 else None
                    tp = order.tp if order.tp > 0 else None
                    break
        
        entry_time = datetime.fromtimestamp(entry_deal.time)
        exit_time = datetime.fromtimestamp(exit_deal.time)
        duration_min = (exit_time - entry_time).total_seconds() / 60
        
        trade_type = "LONG" if entry_deal.type == mt5.DEAL_TYPE_BUY else "SHORT"
        
        # Determine exit reason
        exit_reason = "RSI Exit"
        if sl and abs(exit_deal.price - sl) < 0.5:
            exit_reason = "Stop Loss"
        elif tp and abs(exit_deal.price - tp) < 0.5:
            exit_reason = "Take Profit"
        
        # Calculate distances
        entry_price = entry_deal.price
        exit_price = exit_deal.price
        
        if trade_type == "LONG":
            price_change = exit_price - entry_price
            sl_distance = (entry_price - sl) if sl else None
            tp_distance = (tp - entry_price) if tp else None
        else:
            price_change = entry_price - exit_price
            sl_distance = (sl - entry_price) if sl else None
            tp_distance = (entry_price - tp) if tp else None
        
        price_change_pct = (price_change / entry_price) * 100
        
        trades.append({
            'pos_id': pos_id,
            'magic': entry_deal.magic,
            'type': trade_type,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'sl': sl,
            'tp': tp,
            'sl_distance': sl_distance,
            'tp_distance': tp_distance,
            'volume': entry_deal.volume,
            'profit': exit_deal.profit,
            'price_change': price_change,
            'price_change_pct': price_change_pct,
            'duration_min': duration_min,
            'exit_reason': exit_reason
        })
    
    return sorted(trades, key=lambda x: x['entry_time'])

def print_report(trades, bot_name="ALL"):
    """Print formatted trade report"""
    if not trades:
        print(f"No trades found for {bot_name}")
        return
    
    # Statistics
    winning = [t for t in trades if t['profit'] > 0]
    losing = [t for t in trades if t['profit'] < 0]
    
    total_profit = sum(t['profit'] for t in trades)
    win_rate = len(winning) / len(trades) * 100 if trades else 0
    
    sl_exits = [t for t in trades if t['exit_reason'] == "Stop Loss"]
    tp_exits = [t for t in trades if t['exit_reason'] == "Take Profit"]
    rsi_exits = [t for t in trades if t['exit_reason'] == "RSI Exit"]
    
    print(f"\n{'='*120}")
    print(f"{bot_name} TRADE REPORT")
    print(f"{'='*120}")
    print(f"\nSUMMARY:")
    print(f"  Total Trades: {len(trades)}")
    print(f"  Winning: {len(winning)} ({win_rate:.1f}%)")
    print(f"  Losing: {len(losing)} ({100-win_rate:.1f}%)")
    print(f"  Total P/L: ${total_profit:.2f}")
    
    if winning:
        avg_win = sum(t['profit'] for t in winning) / len(winning)
        print(f"  Avg Win: ${avg_win:.2f}")
    
    if losing:
        avg_loss = sum(t['profit'] for t in losing) / len(losing)
        print(f"  Avg Loss: ${avg_loss:.2f}")
    
    avg_duration = sum(t['duration_min'] for t in trades) / len(trades)
    print(f"  Avg Duration: {avg_duration:.1f} minutes")
    
    print(f"\nEXIT REASONS:")
    print(f"  Stop Loss: {len(sl_exits)} ({len(sl_exits)/len(trades)*100:.1f}%)")
    print(f"  Take Profit: {len(tp_exits)} ({len(tp_exits)/len(trades)*100:.1f}%)")
    print(f"  RSI Exit: {len(rsi_exits)} ({len(rsi_exits)/len(trades)*100:.1f}%)")
    
    # Detailed trades
    print(f"\n{'='*120}")
    print("DETAILED TRADES:")
    print(f"{'='*120}")
    print(f"{'Time':<8} | {'Type':<5} | {'Entry':>8} | {'Exit':>8} | {'SL':>8} | {'TP':>8} | {'Dur':>5} | {'Exit Reason':<12} | {'P/L':>9}")
    print(f"{'='*120}")
    
    for t in trades:
        time_str = t['entry_time'].strftime('%H:%M')
        sl_str = f"${t['sl']:.2f}" if t['sl'] else "N/A"
        tp_str = f"${t['tp']:.2f}" if t['tp'] else "N/A"
        dur_str = f"{t['duration_min']:.0f}m"
        pnl_str = f"${t['profit']:+.2f}"
        
        # Color code by result
        marker = "+" if t['profit'] > 0 else "-"
        
        print(f"{time_str:<8} | {t['type']:<5} | ${t['entry_price']:>7.2f} | ${t['exit_price']:>7.2f} | {sl_str:>8} | {tp_str:>8} | {dur_str:>5} | {t['exit_reason']:<12} | {pnl_str:>9} {marker}")
    
    print(f"{'='*120}")

def main():
    parser = argparse.ArgumentParser(description='Generate comprehensive trade report')
    parser.add_argument('--hours', type=int, default=24, help='Number of hours to analyze (default: 24)')
    parser.add_argument('--bot', choices=['m5', 'm1', 'all'], default='all', help='Which bot to analyze')
    args = parser.parse_args()
    
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
    
    print(f"\n{'='*120}")
    print(f"TRADE REPORT - Last {args.hours} hours")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*120}")
    
    if args.bot == 'all':
        # Get all trades
        all_trades = analyze_trades(hours=args.hours)
        
        # Separate by bot
        m5_trades = [t for t in all_trades if t['magic'] == 234000]
        m1_trades = [t for t in all_trades if t['magic'] == 234001]
        
        # Print reports
        if m5_trades:
            print_report(m5_trades, "M5 BOT (Magic: 234000)")
        
        if m1_trades:
            print_report(m1_trades, "M1 BOT (Magic: 234001)")
        
        # Combined summary
        if all_trades:
            print(f"\n{'='*120}")
            print("COMBINED SUMMARY")
            print(f"{'='*120}")
            total_profit = sum(t['profit'] for t in all_trades)
            m5_profit = sum(t['profit'] for t in m5_trades)
            m1_profit = sum(t['profit'] for t in m1_trades)
            
            print(f"  M5 Bot: {len(m5_trades)} trades, ${m5_profit:.2f}")
            print(f"  M1 Bot: {len(m1_trades)} trades, ${m1_profit:.2f}")
            print(f"  Total: {len(all_trades)} trades, ${total_profit:.2f}")
            print(f"{'='*120}")
    
    elif args.bot == 'm5':
        trades = analyze_trades(hours=args.hours, magic_number=234000)
        print_report(trades, "M5 BOT (Magic: 234000)")
    
    elif args.bot == 'm1':
        trades = analyze_trades(hours=args.hours, magic_number=234001)
        print_report(trades, "M1 BOT (Magic: 234001)")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
