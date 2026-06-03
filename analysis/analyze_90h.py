"""
90-hour rolling analysis for TICK and M5S bots.
Splits into 6-hour windows to show when each bot did well/badly.
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np


MAGIC_TICK = 234200
MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'
LOOKBACK_HOURS = 90
WINDOW_HOURS = 6


def get_trades(magic: int, from_date: datetime, to_date: datetime) -> list[dict]:
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None or len(deals) == 0:
        return []

    relevant = [d for d in deals if d.magic == magic and SYMBOL in d.symbol]
    positions = {}
    trades = []

    for deal in relevant:
        if deal.entry == mt5.DEAL_ENTRY_IN:
            positions[deal.position_id] = {
                'entry_time': datetime.fromtimestamp(deal.time),
                'entry_price': deal.price,
                'volume': deal.volume,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
            }
        elif deal.entry == mt5.DEAL_ENTRY_OUT:
            pos = positions.get(deal.position_id)
            if pos is None:
                continue
            exit_time = datetime.fromtimestamp(deal.time)
            profit = deal.profit + deal.commission + deal.swap
            if pos['type'] == 'LONG':
                price_change = deal.price - pos['entry_price']
            else:
                price_change = pos['entry_price'] - deal.price

            trades.append({
                'entry_time': pos['entry_time'],
                'exit_time': exit_time,
                'type': pos['type'],
                'entry_price': pos['entry_price'],
                'exit_price': deal.price,
                'price_change': price_change,
                'profit': profit,
                'volume': pos['volume'],
            })
            del positions[deal.position_id]

    trades.sort(key=lambda t: t['exit_time'])
    return trades


def get_price_at(from_date: datetime, to_date: datetime) -> tuple[float, float, float]:
    """Get start price, end price, and ATR for a window."""
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, from_date, to_date)
    if rates is None or len(rates) < 5:
        return 0, 0, 0
    closes = [r[4] for r in rates]
    highs = [r[2] for r in rates]
    lows = [r[3] for r in rates]
    tr_vals = []
    for i in range(1, len(rates)):
        tr_vals.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    avg_atr = np.mean(tr_vals[-14:]) if len(tr_vals) >= 14 else np.mean(tr_vals) if tr_vals else 0
    return closes[0], closes[-1], avg_atr


def print_window_row(window_start, window_end, tick_trades, m5s_trades, start_price, end_price, atr):
    """Print one row of the rolling window analysis."""
    tick_count = len(tick_trades)
    tick_profit = sum(t['profit'] for t in tick_trades)
    tick_wins = sum(1 for t in tick_trades if t['profit'] > 0)
    tick_wr = tick_wins / tick_count * 100 if tick_count > 0 else 0

    m5s_count = len(m5s_trades)
    m5s_profit = sum(t['profit'] for t in m5s_trades)
    m5s_wins = sum(1 for t in m5s_trades if t['profit'] > 0)
    m5s_wr = m5s_wins / m5s_count * 100 if m5s_count > 0 else 0

    price_move = end_price - start_price if start_price > 0 else 0
    combined = tick_profit + m5s_profit

    # Visual indicator
    tick_bar = "+" * min(10, int(tick_profit / 5)) if tick_profit > 0 else "-" * min(10, int(-tick_profit / 5))
    m5s_bar = "+" * min(10, int(m5s_profit / 5)) if m5s_profit > 0 else "-" * min(10, int(-m5s_profit / 5))

    day = window_start.strftime('%a')
    print(
        f"  {window_start.strftime('%m-%d %H:%M')} "
        f"{day} "
        f"${price_move:>+6.1f} "
        f"ATR${atr:>4.1f} | "
        f"TICK: {tick_count:>2}t ${tick_profit:>+7.2f} {tick_wr:>3.0f}% {tick_bar:<10} | "
        f"M5S: {m5s_count:>2}t ${m5s_profit:>+7.2f} {m5s_wr:>3.0f}% {m5s_bar:<10} | "
        f"${combined:>+7.2f}"
    )


def main():
    print("\n" + "=" * 120)
    print(f"  90-HOUR ROLLING ANALYSIS ({WINDOW_HOURS}h windows) -- TICK + M5 SNIPER")
    print("=" * 120)

    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        now = datetime.now()
        start = now - timedelta(hours=LOOKBACK_HOURS)

        # Fetch all trades for the entire period
        tick_all = get_trades(MAGIC_TICK, start, now)
        m5s_all = get_trades(MAGIC_M5S, start, now)

        print(f"\n  Period: {start.strftime('%Y-%m-%d %H:%M')} -> {now.strftime('%Y-%m-%d %H:%M')}")
        print(f"  TICK total: {len(tick_all)} trades, ${sum(t['profit'] for t in tick_all):+.2f}")
        print(f"  M5S total:  {len(m5s_all)} trades, ${sum(t['profit'] for t in m5s_all):+.2f}")
        print(f"  Combined:   ${sum(t['profit'] for t in tick_all) + sum(t['profit'] for t in m5s_all):+.2f}")

        print(f"\n  {'Window':<16} {'Day':<4} {'Price':>7} {'ATR':>6} | "
              f"{'TICK':^30} | {'M5S':^30} | {'Total':>8}")
        print(f"  {'─'*16} {'─'*4} {'─'*7} {'─'*6}─┼─{'─'*30}─┼─{'─'*30}─┼─{'─'*8}")

        # Rolling windows
        window_start = start
        cumulative_tick = 0.0
        cumulative_m5s = 0.0

        while window_start < now:
            window_end = window_start + timedelta(hours=WINDOW_HOURS)
            if window_end > now:
                window_end = now

            # Filter trades by exit time within this window
            tick_window = [t for t in tick_all if window_start <= t['exit_time'] < window_end]
            m5s_window = [t for t in m5s_all if window_start <= t['exit_time'] < window_end]

            # Get price context
            start_price, end_price, atr = get_price_at(window_start, window_end)

            print_window_row(window_start, window_end, tick_window, m5s_window, start_price, end_price, atr)

            cumulative_tick += sum(t['profit'] for t in tick_window)
            cumulative_m5s += sum(t['profit'] for t in m5s_window)

            window_start = window_end

        # Summary by time-of-day
        print(f"\n\n  {'─'*80}")
        print(f"  TIME-OF-DAY BREAKDOWN (all 90 hours aggregated)")
        print(f"  {'─'*80}")

        # 4-hour blocks
        blocks = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
        block_labels = ["00-04 (Asian)", "04-08 (Asian/London)", "08-12 (London)",
                       "12-16 (London/NY)", "16-20 (NY)", "20-24 (NY/Asian)"]

        print(f"\n  {'Session':<22} | {'TICK trades':>6} {'TICK P/L':>10} {'WR':>4} | "
              f"{'M5S trades':>6} {'M5S P/L':>10} {'WR':>4} | {'Combined':>9}")
        print(f"  {'─'*22}─┼─{'─'*6}─{'─'*10}─{'─'*4}─┼─{'─'*6}─{'─'*10}─{'─'*4}─┼─{'─'*9}")

        for (h_start, h_end), label in zip(blocks, block_labels):
            tick_block = [t for t in tick_all if h_start <= t['exit_time'].hour < h_end]
            m5s_block = [t for t in m5s_all if h_start <= t['exit_time'].hour < h_end]

            tick_p = sum(t['profit'] for t in tick_block)
            m5s_p = sum(t['profit'] for t in m5s_block)
            tick_wr = sum(1 for t in tick_block if t['profit'] > 0) / len(tick_block) * 100 if tick_block else 0
            m5s_wr = sum(1 for t in m5s_block if t['profit'] > 0) / len(m5s_block) * 100 if m5s_block else 0

            print(
                f"  {label:<22} | "
                f"{len(tick_block):>6} ${tick_p:>+8.2f} {tick_wr:>3.0f}% | "
                f"{len(m5s_block):>6} ${m5s_p:>+8.2f} {m5s_wr:>3.0f}% | "
                f"${tick_p + m5s_p:>+8.2f}"
            )

        # Best and worst windows
        print(f"\n\n  {'─'*80}")
        print(f"  NOTABLE PERIODS")
        print(f"  {'─'*80}")

        # Recalculate windows to find best/worst
        window_results = []
        window_start = start
        while window_start < now:
            window_end = min(window_start + timedelta(hours=WINDOW_HOURS), now)
            tick_window = [t for t in tick_all if window_start <= t['exit_time'] < window_end]
            m5s_window = [t for t in m5s_all if window_start <= t['exit_time'] < window_end]
            tick_p = sum(t['profit'] for t in tick_window)
            m5s_p = sum(t['profit'] for t in m5s_window)
            start_price, end_price, atr = get_price_at(window_start, window_end)
            price_move = end_price - start_price if start_price > 0 else 0

            window_results.append({
                'start': window_start, 'end': window_end,
                'tick_profit': tick_p, 'm5s_profit': m5s_p,
                'combined': tick_p + m5s_p,
                'tick_count': len(tick_window), 'm5s_count': len(m5s_window),
                'price_move': price_move, 'atr': atr,
            })
            window_start = window_end

        # Sort by combined
        best = sorted(window_results, key=lambda w: w['combined'], reverse=True)[:3]
        worst = sorted(window_results, key=lambda w: w['combined'])[:3]

        print(f"\n  Best {WINDOW_HOURS}h windows:")
        for w in best:
            if w['combined'] <= 0:
                break
            print(f"    {w['start'].strftime('%m-%d %H:%M')} {w['start'].strftime('%a')}: "
                  f"${w['combined']:+.2f} (TICK ${w['tick_profit']:+.2f}/{w['tick_count']}t, "
                  f"M5S ${w['m5s_profit']:+.2f}/{w['m5s_count']}t) "
                  f"Price ${w['price_move']:+.1f}, ATR ${w['atr']:.1f}")

        print(f"\n  Worst {WINDOW_HOURS}h windows:")
        for w in worst:
            if w['combined'] >= 0:
                break
            print(f"    {w['start'].strftime('%m-%d %H:%M')} {w['start'].strftime('%a')}: "
                  f"${w['combined']:+.2f} (TICK ${w['tick_profit']:+.2f}/{w['tick_count']}t, "
                  f"M5S ${w['m5s_profit']:+.2f}/{w['m5s_count']}t) "
                  f"Price ${w['price_move']:+.1f}, ATR ${w['atr']:.1f}")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
