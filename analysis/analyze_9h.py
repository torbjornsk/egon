"""Quick 9-hour analysis for both bots."""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

from src.core.timezone import get_mt5_now, mt5_to_local, get_local_now, MT5_TZ


MAGIC_TICK = 234200
MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'
HOURS = 9


def get_trades(magic, from_date, to_date, local_start=None):
    """Fetch trades. from_date/to_date must be in MT5 broker time (naive datetimes).
    If local_start is provided, filters out trades whose exit is before that time."""
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None or len(deals) == 0:
        return []
    relevant = [d for d in deals if d.magic == magic and SYMBOL in d.symbol]
    positions = {}
    trades = []
    for deal in relevant:
        if deal.entry == mt5.DEAL_ENTRY_IN:
            positions[deal.position_id] = {
                'entry_time': mt5_to_local(deal.time),
                'entry_price': deal.price,
                'volume': deal.volume,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'position_id': deal.position_id,
            }
        elif deal.entry == mt5.DEAL_ENTRY_OUT:
            pos = positions.get(deal.position_id)
            if pos is None:
                continue
            exit_time = mt5_to_local(deal.time)
            profit = deal.profit + deal.commission + deal.swap
            if pos['type'] == 'LONG':
                price_change = deal.price - pos['entry_price']
            else:
                price_change = pos['entry_price'] - deal.price
            hold_min = (exit_time - pos['entry_time']).total_seconds() / 60
            trades.append({
                'entry_time': pos['entry_time'], 'exit_time': exit_time,
                'type': pos['type'], 'entry_price': pos['entry_price'],
                'exit_price': deal.price, 'price_change': price_change,
                'profit': profit, 'volume': pos['volume'],
                'hold_min': hold_min, 'position_id': pos['position_id'],
                'is_sl': deal.reason == mt5.DEAL_REASON_SL,
            })
            del positions[deal.position_id]
    trades.sort(key=lambda t: t['exit_time'])
    # Filter: only include trades whose exit is within the requested window
    if local_start:
        trades = [t for t in trades if t['exit_time'] >= local_start]
    return trades


def load_exit_reasons(bot_key):
    import json, os
    filename = f'data/exit_reasons_{bot_key}.json'
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r') as f:
        return json.load(f)


def analyze(label, trades, exit_reasons):
    if not trades:
        print(f"\n  {label}: No trades")
        return

    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] <= 0]
    total = sum(t['profit'] for t in trades)
    wr = len(wins) / len(trades) * 100

    print(f"\n  {label}")
    print(f"  {'─'*70}")
    print(f"  Trades: {len(trades)} | Wins: {len(wins)} ({wr:.0f}%) | P/L: ${total:+.2f}")
    if wins:
        print(f"  Avg win: ${sum(t['profit'] for t in wins)/len(wins):.2f} | Best: ${max(t['profit'] for t in wins):.2f}")
    if losses:
        print(f"  Avg loss: ${sum(t['profit'] for t in losses)/len(losses):.2f} | Worst: ${min(t['profit'] for t in losses):.2f}")
    if wins and losses:
        rr = (sum(t['profit'] for t in wins)/len(wins)) / abs(sum(t['profit'] for t in losses)/len(losses))
        print(f"  R:R: {rr:.2f}")

    longs = [t for t in trades if t['type'] == 'LONG']
    shorts = [t for t in trades if t['type'] == 'SHORT']
    print(f"  Direction: {len(longs)} LONG (${sum(t['profit'] for t in longs):+.2f}) | "
          f"{len(shorts)} SHORT (${sum(t['profit'] for t in shorts):+.2f})")
    print(f"  Avg hold: {sum(t['hold_min'] for t in trades)/len(trades):.1f} min")

    # Exit reasons
    reason_stats = defaultdict(lambda: {'count': 0, 'profit': 0.0})
    for t in trades:
        pid = str(t['position_id'])
        rd = exit_reasons.get(pid)
        if rd:
            fr = rd.get('full_reason', '?')
            if 'Stop loss' in fr:
                b = 'Stop loss'
            elif 'MT5 close' in fr:
                b = 'MT5 close'
            elif 'Mean revert' in fr:
                b = 'Mean revert'
            elif 'Profit protection' in fr:
                b = 'Profit prot.'
            elif 'Exit score' in fr:
                if 'structure' in fr: b = 'Exit (structure)'
                elif 'velocity' in fr: b = 'Exit (velocity)'
                elif 'opposite' in fr: b = 'Exit (opposite)'
                else: b = 'Exit (other)'
            else:
                b = fr[:25]
        else:
            b = '?'
        reason_stats[b]['count'] += 1
        reason_stats[b]['profit'] += t['profit']

    print(f"\n  Exit reasons:")
    for r, s in sorted(reason_stats.items(), key=lambda x: -x[1]['count']):
        avg = s['profit'] / s['count']
        print(f"    {r:<20} {s['count']:>3}x  ${s['profit']:>+7.2f}  (avg ${avg:>+5.2f})")

    # Trade list
    print(f"\n  Trades:")
    print(f"  {'Time':<6} {'Dir':<5} {'Entry':>8} {'Exit':>8} {'P/L':>7} {'Hold':>5} {'Reason':<25}")
    print(f"  {'─'*6} {'─'*5} {'─'*8} {'─'*8} {'─'*7} {'─'*5} {'─'*25}")
    for t in trades:
        pid = str(t['position_id'])
        rd = exit_reasons.get(pid)
        reason = rd['reason'][:25] if rd else '?'
        print(f"  {t['exit_time'].strftime('%H:%M'):<6} {t['type']:<5} "
              f"${t['entry_price']:>6.2f} ${t['exit_price']:>6.2f} "
              f"${t['profit']:>+5.2f} {t['hold_min']:>4.0f}m {reason}")


def main():
    print(f"\n{'='*80}")
    print(f"  LAST {HOURS} HOURS ANALYSIS")
    print(f"{'='*80}")

    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    try:
        # Use MT5 broker time for API queries (add 3h buffer to end to catch recent deals)
        mt5_now = get_mt5_now()
        mt5_start = mt5_now - timedelta(hours=HOURS)
        mt5_end_buffered = mt5_now + timedelta(hours=3)
        # Use local time for display
        local_now = get_local_now()
        local_start = local_now - timedelta(hours=HOURS)
        print(f"  Window: {local_start.strftime('%Y-%m-%d %H:%M')} -> {local_now.strftime('%Y-%m-%d %H:%M')} (local)")

        # MT5 API needs naive datetimes in broker time
        from_naive = mt5_start.replace(tzinfo=None)
        to_naive = mt5_end_buffered.replace(tzinfo=None)

        # Market context
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, from_naive, to_naive)
        if rates is not None and len(rates) > 10:
            closes = [r[4] for r in rates]
            highs = [r[2] for r in rates]
            lows = [r[3] for r in rates]
            net = closes[-1] - closes[0]
            rng = max(highs) - min(lows)
            tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(rates))]
            atr = np.mean(tr[-14:])
            print(f"  Market: ${closes[0]:.2f} -> ${closes[-1]:.2f} (net ${net:+.2f}, range ${rng:.2f}, ATR ${atr:.2f})")

        tick_trades = get_trades(MAGIC_TICK, from_naive, to_naive, local_start=local_start)
        m5s_trades = get_trades(MAGIC_M5S, from_naive, to_naive, local_start=local_start)

        tick_reasons = load_exit_reasons('tick')
        m5s_reasons = load_exit_reasons('m5s')

        analyze("TICK SCALPER", tick_trades, tick_reasons)
        analyze("M5 SNIPER", m5s_trades, m5s_reasons)

        # Combined
        all_p = sum(t['profit'] for t in tick_trades) + sum(t['profit'] for t in m5s_trades)
        print(f"\n  {'='*70}")
        print(f"  COMBINED: ${all_p:+.2f}")
        print(f"  TICK: {len(tick_trades)}t ${sum(t['profit'] for t in tick_trades):+.2f} | "
              f"M5S: {len(m5s_trades)}t ${sum(t['profit'] for t in m5s_trades):+.2f}")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
