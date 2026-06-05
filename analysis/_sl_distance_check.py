"""Check actual SL distances on V4 June 1 trades."""
import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from src.core.timezone import get_mt5_now, mt5_to_local, get_local_now

mt5.initialize()
mt5_now = get_mt5_now()
local_now = get_local_now()
days_ago = (local_now.date() - datetime(2026, 6, 1).date()).days
from_naive = (mt5_now - timedelta(days=days_ago + 1)).replace(tzinfo=None)
to_naive = (mt5_now - timedelta(days=days_ago - 1)).replace(tzinfo=None)
deals = mt5.history_deals_get(from_naive, to_naive)
tick_deals = [d for d in deals if d.magic == 234200 and 'XAUUSD' in d.symbol]

# Build trades
positions = {}
sl_trades = []
for deal in tick_deals:
    if deal.entry == mt5.DEAL_ENTRY_IN:
        positions[deal.position_id] = {
            'entry_price': deal.price,
            'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
            'volume': deal.volume,
        }
    elif deal.entry == mt5.DEAL_ENTRY_OUT and deal.position_id in positions:
        pos = positions[deal.position_id]
        if deal.reason == mt5.DEAL_REASON_SL:
            if pos['type'] == 'LONG':
                sl_distance = pos['entry_price'] - deal.price
            else:
                sl_distance = deal.price - pos['entry_price']
            sl_trades.append({
                'entry': pos['entry_price'],
                'exit': deal.price,
                'sl_distance': sl_distance,
                'profit': deal.profit,
                'volume': pos['volume'],
                'type': pos['type'],
            })
        del positions[deal.position_id]

print(f"SL trades: {len(sl_trades)}")
print()
print("SL DISTANCE (price moved against us before SL hit):")
distances = [t['sl_distance'] for t in sl_trades]
print(f"  Min: ${min(distances):.2f}")
print(f"  Max: ${max(distances):.2f}")
print(f"  Avg: ${sum(distances)/len(distances):.2f}")
print(f"  Median: ${sorted(distances)[len(distances)//2]:.2f}")
print()
print("SL PROFIT (dollar loss per trade):")
profits = [t['profit'] for t in sl_trades]
print(f"  Min: ${min(profits):.2f}")
print(f"  Max: ${max(profits):.2f}")
print(f"  Avg: ${sum(profits)/len(profits):.2f}")
print()
print("Volume on SL trades:")
vols = [t['volume'] for t in sl_trades]
print(f"  Min: {min(vols)}, Max: {max(vols)}, Avg: {sum(vols)/len(vols):.2f}")
print()
print("First 15 SL trades (detail):")
for t in sl_trades[:15]:
    typ = t['type']
    print(f"  {typ:5s} entry=${t['entry']:.2f} exit=${t['exit']:.2f} "
          f"dist=${t['sl_distance']:.2f} P/L=${t['profit']:.2f} vol={t['volume']}")

# Distribution of SL distances
print()
print("SL DISTANCE DISTRIBUTION:")
brackets = [(0, 2), (2, 4), (4, 6), (6, 10), (10, 20), (20, 50)]
for lo, hi in brackets:
    count = sum(1 for d in distances if lo <= d < hi)
    print(f"  ${lo}-${hi}: {count} trades")

# What would $30 SL look like?
print()
print(f"If SL was truly 6x M5 ATR (~$30):")
print(f"  Trades hitting $30+ distance: {sum(1 for d in distances if d >= 30)}")
print(f"  Trades hitting $20+ distance: {sum(1 for d in distances if d >= 20)}")
print(f"  Trades hitting $10+ distance: {sum(1 for d in distances if d >= 10)}")
print(f"  Trades under $5 distance: {sum(1 for d in distances if d < 5)}")

mt5.shutdown()
