"""
Evaluate live trading performance using actual MT5 trade data
Analyzes what worked and identifies improvement opportunities
"""

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd

def get_trade_details(hours=10):
    """Get detailed trade information from MT5"""
    from_date = datetime.now() - timedelta(hours=hours)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if not deals:
        return {'m5': [], 'm1': []}
    
    # Group deals by position
    positions = {}
    for deal in deals:
        if deal.symbol != 'XAUUSD':
            continue
        pos_id = deal.position_id
        if pos_id not in positions:
            positions[pos_id] = []
        positions[pos_id].append(deal)
    
    # Analyze each position
    m5_trades = []
    m1_trades = []
    
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
        
        entry_price = entry_deal.price
        exit_price = exit_deal.price
        
        if trade_type == "LONG":
            price_change_pct = (exit_price - entry_price) / entry_price * 100
        else:
            price_change_pct = (entry_price - exit_price) / entry_price * 100
        
        trade = {
            'entry_time': entry_time,
            'exit_time': exit_time,
            'type': trade_type,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'sl': sl,
            'tp': tp,
            'profit': exit_deal.profit,
            'price_change_pct': price_change_pct,
            'duration_min': duration_min,
            'exit_reason': exit_reason,
            'magic': entry_deal.magic
        }
        
        if entry_deal.magic == 234000:
            m5_trades.append(trade)
        elif entry_deal.magic == 234001:
            m1_trades.append(trade)
    
    return {
        'm5': sorted(m5_trades, key=lambda x: x['entry_time']),
        'm1': sorted(m1_trades, key=lambda x: x['entry_time'])
    }

def main():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
    
    hours = 24
    print("="*100)
    print(f"LIVE TRADING EVALUATION - Last {hours} Hours")
    print("="*100)
    print()
    
    trades = get_trade_details(hours=hours)
    
    # Overall summary
    m5_profit = sum(t['profit'] for t in trades['m5'])
    m1_profit = sum(t['profit'] for t in trades['m1'])
    total_profit = m5_profit + m1_profit
    
    print(f"OVERALL PERFORMANCE:")
    print(f"  M5 Bot: {len(trades['m5'])} trades, ${m5_profit:.2f}")
    print(f"  M1 Bot: {len(trades['m1'])} trades, ${m1_profit:.2f}")
    print(f"  Total: {len(trades['m5']) + len(trades['m1'])} trades, ${total_profit:.2f}")
    print()
    
    # Analyze each bot
    for bot_name, bot_trades in [('M5', trades['m5']), ('M1', trades['m1'])]:
        if not bot_trades:
            continue
        
        print("="*100)
        print(f"{bot_name} BOT ANALYSIS")
        print("="*100)
        
        # Calculate stats
        winning = [t for t in bot_trades if t['profit'] > 0]
        losing = [t for t in bot_trades if t['profit'] < 0]
        sl_trades = [t for t in bot_trades if t['exit_reason'] == 'Stop Loss']
        rsi_trades = [t for t in bot_trades if t['exit_reason'] == 'RSI Exit']
        
        total_pnl = sum(t['profit'] for t in bot_trades)
        win_rate = len(winning) / len(bot_trades) * 100
        sl_rate = len(sl_trades) / len(bot_trades) * 100
        
        avg_win = sum(t['profit'] for t in winning) / len(winning) if winning else 0
        avg_loss = sum(t['profit'] for t in losing) / len(losing) if losing else 0
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        print(f"\nPerformance:")
        print(f"  Total P/L: ${total_pnl:.2f}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Avg Win: ${avg_win:.2f}")
        print(f"  Avg Loss: ${avg_loss:.2f}")
        print(f"  Risk/Reward: 1:{risk_reward:.2f}")
        
        print(f"\nExit Analysis:")
        print(f"  Stop Loss: {len(sl_trades)} ({sl_rate:.1f}%)")
        print(f"  RSI Exit: {len(rsi_trades)} ({len(rsi_trades)/len(bot_trades)*100:.1f}%)")
        
        print(f"\nRecommendations:")
        if sl_rate > 30:
            print(f"  - High stop loss rate ({sl_rate:.1f}%) - consider widening stops")
        if risk_reward < 1.0:
            print(f"  - Poor risk/reward ({risk_reward:.2f}) - wins smaller than losses")
            print(f"    Consider: holding winners longer or tightening stops")
        if win_rate < 50:
            print(f"  - Low win rate ({win_rate:.1f}%) - tighten entry conditions")
        if not (sl_rate > 30 or risk_reward < 1.0 or win_rate < 50):
            print(f"  - Performance looks good!")
        
        print()
    
    # Overall recommendations
    print("="*100)
    print("KEY RECOMMENDATIONS")
    print("="*100)
    
    if total_profit > 0:
        print(f"Overall profitable: ${total_profit:.2f}")
    else:
        print(f"Overall loss: ${total_profit:.2f} - review strategy parameters")
    
    # Compare bots
    if trades['m5'] and trades['m1']:
        m5_per_trade = m5_profit / len(trades['m5'])
        m1_per_trade = m1_profit / len(trades['m1'])
        
        print(f"\nPer-trade comparison:")
        print(f"  M5: ${m5_per_trade:.2f} per trade")
        print(f"  M1: ${m1_per_trade:.2f} per trade")
        
        if m5_per_trade > m1_per_trade * 2:
            print(f"  M5 significantly outperforming - consider focusing on M5")
        elif m1_per_trade > m5_per_trade * 2:
            print(f"  M1 significantly outperforming")
        else:
            print(f"  Both bots performing similarly")
    
    print("="*100)
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
