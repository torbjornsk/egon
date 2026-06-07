"""
M5 Sniper: Long vs Short performance over last 48 hours.
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from collections import defaultdict


MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'


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
                'position_id': deal.position_id,
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
            hold_min = (exit_time - pos['entry_time']).total_seconds() / 60

            # Check peak price during trade
            rates = mt5.copy_rates_range(
                SYMBOL, mt5.TIMEFRAME_M1,
                pos['entry_time'] - timedelta(minutes=1),
                exit_time + timedelta(minutes=1),
            )
            peak_move = 0.0
            if rates is not None and len(rates) > 0:
                if pos['type'] == 'LONG':
                    peak_price = max(r[2] for r in rates)  # high
                    peak_move = peak_price - pos['entry_price']
                else:
                    peak_price = min(r[3] for r in rates)  # low
                    peak_move = pos['entry_price'] - peak_price

            is_sl = (deal.reason == mt5.DEAL_REASON_SL)

            trades.append({
                'entry_time': pos['entry_time'],
                'exit_time': exit_time,
                'type': pos['type'],
                'entry_price': pos['entry_price'],
                'exit_price': deal.price,
                'price_change': price_change,
                'profit': profit,
                'volume': pos['volume'],
                'hold_min': hold_min,
                'position_id': pos['position_id'],
                'peak_move': peak_move,
                'is_sl': is_sl,
            })
            del positions[deal.position_id]

    trades.sort(key=lambda t: t['exit_time'])
    return trades


def analyze_direction(label: str, trades: list):
    if not trades:
        print(f"\n  {label}: No trades")
        return

    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] <= 0]
    total_profit = sum(t['profit'] for t in trades)
    win_rate = len(wins) / len(trades) * 100

    print(f"\n  {label}")
    print(f"  {'─' * 60}")
    print(f"  Trades: {len(trades)} | Wins: {len(wins)} ({win_rate:.0f}%) | P/L: ${total_profit:+.2f}")

    if wins:
        avg_win = sum(t['profit'] for t in wins) / len(wins)
        best = max(t['profit'] for t in wins)
        avg_peak_wins = sum(t['peak_move'] for t in wins) / len(wins)
        avg_hold_wins = sum(t['hold_min'] for t in wins) / len(wins)
        print(f"  Avg win: ${avg_win:.2f} | Best: ${best:.2f} | Avg peak: ${avg_peak_wins:.2f} | Avg hold: {avg_hold_wins:.0f}min")

    if losses:
        avg_loss = sum(t['profit'] for t in losses) / len(losses)
        worst = min(t['profit'] for t in losses)
        avg_peak_losses = sum(t['peak_move'] for t in losses) / len(losses)
        avg_hold_losses = sum(t['hold_min'] for t in losses) / len(losses)
        print(f"  Avg loss: ${avg_loss:.2f} | Worst: ${worst:.2f} | Avg peak: ${avg_peak_losses:.2f} | Avg hold: {avg_hold_losses:.0f}min")

    if wins and losses:
        rr = (sum(t['profit'] for t in wins) / len(wins)) / abs(sum(t['profit'] for t in losses) / len(losses))
        print(f"  R:R: {rr:.2f}")

    # SL breakdown
    sl_trades = [t for t in trades if t['is_sl']]
    trailed = [t for t in sl_trades if t['peak_move'] > 1.5]
    initial = [t for t in sl_trades if t['peak_move'] <= 1.5]
    non_sl = [t for t in trades if not t['is_sl']]

    print(f"\n  Exit breakdown:")
    if initial:
        print(f"    Initial SL: {len(initial)}x, ${sum(t['profit'] for t in initial):+.2f} (avg ${sum(t['profit'] for t in initial)/len(initial):.2f})")
    if trailed:
        print(f"    Trailed SL: {len(trailed)}x, ${sum(t['profit'] for t in trailed):+.2f} (avg ${sum(t['profit'] for t in trailed)/len(trailed):.2f})")
    if non_sl:
        print(f"    Bot exit:   {len(non_sl)}x, ${sum(t['profit'] for t in non_sl):+.2f} (avg ${sum(t['profit'] for t in non_sl)/len(non_sl):.2f})")

    # Hourly breakdown
    print(f"\n  Hourly:")
    hourly = defaultdict(lambda: {'count': 0, 'profit': 0.0, 'wins': 0})
    for t in trades:
        h = t['entry_time'].hour
        hourly[h]['count'] += 1
        hourly[h]['profit'] += t['profit']
        if t['profit'] > 0:
            hourly[h]['wins'] += 1

    for h in sorted(hourly.keys()):
        s = hourly[h]
        wr = s['wins'] / s['count'] * 100 if s['count'] > 0 else 0
        print(f"    {h:02d}:00  {s['count']:>2} trades  ${s['profit']:>+7.2f}  WR {wr:.0f}%")

    # Individual trades
    print(f"\n  All trades:")
    print(f"  {'Time':<12} {'Entry':>9} {'Exit':>9} {'Peak':>7} {'P/L':>8} {'Hold':>5} {'Exit':<8}")
    print(f"  {'─'*12} {'─'*9} {'─'*9} {'─'*7} {'─'*8} {'─'*5} {'─'*8}")
    for t in trades:
        exit_type = "InitSL" if t['is_sl'] and t['peak_move'] <= 1.5 else "Trail" if t['is_sl'] else "MeanRev"
        print(
            f"  {t['entry_time'].strftime('%m-%d %H:%M')} "
            f"${t['entry_price']:>7.2f} "
            f"${t['exit_price']:>7.2f} "
            f"${t['peak_move']:>+5.2f} "
            f"${t['profit']:>+6.2f} "
            f"{t['hold_min']:>4.0f}m "
            f"{exit_type:<8}"
        )


def main():
    print("\n" + "=" * 80)
    print("  M5 SNIPER: LONG vs SHORT -- Last 48 Hours")
    print("=" * 80)

    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        now = datetime.now()
        from_date = now - timedelta(hours=48)

        trades = get_trades(MAGIC_M5S, from_date, now)
        if not trades:
            print("  No trades found.")
            return

        longs = [t for t in trades if t['type'] == 'LONG']
        shorts = [t for t in trades if t['type'] == 'SHORT']

        total = sum(t['profit'] for t in trades)
        print(f"\n  Total: {len(trades)} trades, ${total:+.2f}")
        print(f"  LONGs: {len(longs)} | SHORTs: {len(shorts)}")

        analyze_direction("LONG TRADES", longs)
        analyze_direction("SHORT TRADES", shorts)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
