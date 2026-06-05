"""Quick analysis: midnight local -> now."""
import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime
import numpy as np
import json, os
import pytz
from src.core.timezone import get_mt5_now, mt5_to_local, get_local_now, MT5_TZ, LOCAL_TZ

mt5.initialize()

SYMBOL = 'XAUUSD.p'
MAGIC_TICK = 234200
MAGIC_M5S = 234050

local_now = get_local_now()
local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
mt5_start = local_start.astimezone(MT5_TZ).replace(tzinfo=None)
mt5_end = local_now.astimezone(MT5_TZ).replace(tzinfo=None)

print(f"Window: {local_start.strftime('%H:%M')} -> {local_now.strftime('%H:%M')} local")
print()

rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, mt5_start, mt5_end)
if rates is not None and len(rates) > 5:
    closes = [r[4] for r in rates]
    highs = [r[2] for r in rates]
    lows = [r[3] for r in rates]
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(rates))]
    atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
    print(f"Market: ${closes[0]:.2f} -> ${closes[-1]:.2f} (net ${closes[-1]-closes[0]:+.2f}, range ${max(highs)-min(lows):.2f}, ATR ${atr:.2f})")
    print()


def get_trades(magic):
    deals = mt5.history_deals_get(mt5_start, mt5_end)
    if not deals:
        return []
    relevant = [d for d in deals if d.magic == magic and SYMBOL in d.symbol]
    positions = {}
    trades = []
    for deal in relevant:
        if deal.entry == mt5.DEAL_ENTRY_IN:
            positions[deal.position_id] = {
                'entry_time': mt5_to_local(deal.time),
                'entry_price': deal.price,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'pid': deal.position_id,
            }
        elif deal.entry == mt5.DEAL_ENTRY_OUT:
            pos = positions.get(deal.position_id)
            if not pos:
                continue
            exit_time = mt5_to_local(deal.time)
            profit = deal.profit + deal.commission + deal.swap
            hold_min = (exit_time - pos['entry_time']).total_seconds() / 60
            trades.append({
                'exit_time': exit_time, 'entry_time': pos['entry_time'],
                'type': pos['type'], 'entry_price': pos['entry_price'],
                'exit_price': deal.price, 'profit': profit,
                'hold_min': hold_min, 'pid': pos['pid'],
            })
            del positions[deal.position_id]
    trades.sort(key=lambda t: t['exit_time'])
    return trades


def load_reasons(key):
    f = f'data/exit_reasons_{key}.json'
    if not os.path.exists(f):
        return {}
    with open(f) as fh:
        return json.load(fh)


tick_reasons = load_reasons('tick')
m5s_reasons = load_reasons('m5s')

for label, magic, reasons in [('TICK SCALPER', MAGIC_TICK, tick_reasons), ('M5 SNIPER', MAGIC_M5S, m5s_reasons)]:
    trades = get_trades(magic)
    if not trades:
        print(f"{label}: No trades")
        print()
        continue
    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] <= 0]
    total = sum(t['profit'] for t in trades)
    wr = len(wins) / len(trades) * 100

    print(f"{label}: {len(trades)} trades, {wr:.0f}% WR, ${total:+.2f}")
    if wins:
        print(f"  Avg win: ${sum(t['profit'] for t in wins)/len(wins):.2f} | Best: ${max(t['profit'] for t in wins):.2f}")
    if losses:
        print(f"  Avg loss: ${sum(t['profit'] for t in losses)/len(losses):.2f} | Worst: ${min(t['profit'] for t in losses):.2f}")
    if wins and losses:
        rr = (sum(t['profit'] for t in wins)/len(wins)) / abs(sum(t['profit'] for t in losses)/len(losses))
        print(f"  R:R: {rr:.2f}")
    longs = [t for t in trades if t['type'] == 'LONG']
    shorts = [t for t in trades if t['type'] == 'SHORT']
    print(f"  {len(longs)} LONG (${sum(t['profit'] for t in longs):+.2f}) | {len(shorts)} SHORT (${sum(t['profit'] for t in shorts):+.2f})")
    print()
    print(f"  {'Time':<6} {'Dir':<5} {'Entry':>8} {'Exit':>8} {'P/L':>7} {'Hold':>5} Reason")
    print(f"  {'---':<6} {'---':<5} {'---':>8} {'---':>8} {'---':>7} {'---':>5} {'---':<25}")
    for t in trades:
        rd = reasons.get(str(t['pid']))
        reason = rd['reason'][:25] if rd else '?'
        print(f"  {t['exit_time'].strftime('%H:%M'):<6} {t['type']:<5} ${t['entry_price']:>6.2f} ${t['exit_price']:>6.2f} ${t['profit']:>+5.2f} {t['hold_min']:>4.0f}m {reason}")
    print()

tick_t = get_trades(MAGIC_TICK)
m5s_t = get_trades(MAGIC_M5S)
print(f"COMBINED: ${sum(t['profit'] for t in tick_t) + sum(t['profit'] for t in m5s_t):+.2f}")

mt5.shutdown()
