"""Analyze last 9 hours of live trades from all bots."""
import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import timedelta
from collections import defaultdict

from src.core.timezone import get_mt5_now, mt5_to_local, get_local_now

MAGIC_MAP = {
    234000: 'M5',
    234001: 'M1',
    234015: 'M15',
    234050: 'M5S',
    234100: 'LZ',
    234200: 'TICK',
    234300: 'MOM',
}

HOURS = 9


def main():
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    try:
        mt5_now = get_mt5_now()
        local_now = get_local_now()
        local_start = local_now - timedelta(hours=HOURS)

        # Query with buffer
        from_naive = (mt5_now - timedelta(hours=HOURS + 1)).replace(tzinfo=None)
        to_naive = (mt5_now + timedelta(hours=3)).replace(tzinfo=None)

        deals = mt5.history_deals_get(from_naive, to_naive)
        if deals is None:
            print("No deals found")
            return

        # Filter our bots + XAUUSD
        our_deals = [d for d in deals if d.magic in MAGIC_MAP and 'XAUUSD' in d.symbol]

        # Build trades
        positions = {}
        trades = []
        for deal in our_deals:
            if deal.entry == mt5.DEAL_ENTRY_IN:
                positions[deal.position_id] = {
                    'entry_time': mt5_to_local(deal.time),
                    'entry_price': deal.price,
                    'volume': deal.volume,
                    'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                    'bot': MAGIC_MAP[deal.magic],
                }
            elif deal.entry == mt5.DEAL_ENTRY_OUT and deal.position_id in positions:
                pos = positions[deal.position_id]
                exit_time = mt5_to_local(deal.time)

                # Post-filter by local time
                if exit_time < local_start:
                    del positions[deal.position_id]
                    continue

                hold_seconds = (exit_time - pos['entry_time']).total_seconds()

                if deal.reason == mt5.DEAL_REASON_SL:
                    reason = "Stop loss"
                elif deal.reason == mt5.DEAL_REASON_TP:
                    reason = "Take profit"
                else:
                    reason = "Bot exit"

                trades.append({
                    'entry_time': pos['entry_time'],
                    'exit_time': exit_time,
                    'type': pos['type'],
                    'entry_price': pos['entry_price'],
                    'exit_price': deal.price,
                    'profit': deal.profit + deal.commission + deal.swap,
                    'profit_gross': deal.profit,
                    'commission': deal.commission,
                    'volume': pos['volume'],
                    'hold_seconds': hold_seconds,
                    'reason': reason,
                    'bot': pos['bot'],
                })
                del positions[deal.position_id]

        trades.sort(key=lambda t: t['exit_time'])

        print("=" * 80)
        print(f"LIVE TRADE ANALYSIS -- Last {HOURS} hours")
        print(f"Period: {local_start.strftime('%Y-%m-%d %H:%M')} to {local_now.strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)
        print(f"\nTotal trades: {len(trades)}")
        print()

        if not trades:
            print("No trades in this period.")
            return

        # ── Per-bot breakdown ────────────────────────────────────────
        bots_seen = sorted(set(t['bot'] for t in trades))
        print(f"{'Bot':<6} {'Trades':>7} {'Win%':>7} {'P/L':>10} {'Avg Win':>9} {'Avg Loss':>10} {'Avg Hold':>9}")
        print("-" * 70)

        for bot in bots_seen:
            bt = [t for t in trades if t['bot'] == bot]
            wins = [t for t in bt if t['profit'] > 0]
            losses = [t for t in bt if t['profit'] < 0]
            wr = len(wins) / len(bt) * 100 if bt else 0
            pnl = sum(t['profit'] for t in bt)
            avg_w = sum(t['profit'] for t in wins) / len(wins) if wins else 0
            avg_l = sum(t['profit'] for t in losses) / len(losses) if losses else 0
            avg_hold = sum(t['hold_seconds'] for t in bt) / len(bt)
            print(f"{bot:<6} {len(bt):>7} {wr:>6.1f}% ${pnl:>8.2f} ${avg_w:>7.2f} ${avg_l:>8.2f} {avg_hold:>7.0f}s")

        total_pnl = sum(t['profit'] for t in trades)
        print("-" * 70)
        print(f"{'TOTAL':<6} {len(trades):>7} {'':>7} ${total_pnl:>8.2f}")
        print()

        # ── Per-bot detail ───────────────────────────────────────────
        for bot in bots_seen:
            bt = [t for t in trades if t['bot'] == bot]
            if not bt:
                continue

            wins = [t for t in bt if t['profit'] > 0]
            losses = [t for t in bt if t['profit'] < 0]
            pnl = sum(t['profit'] for t in bt)

            print("=" * 80)
            print(f"  {bot} BOT DETAIL  ({len(bt)} trades, ${pnl:+.2f})")
            print("=" * 80)

            # Exit reasons
            reason_stats = defaultdict(lambda: {'count': 0, 'pnl': 0, 'wins': 0})
            for t in bt:
                reason_stats[t['reason']]['count'] += 1
                reason_stats[t['reason']]['pnl'] += t['profit']
                if t['profit'] > 0:
                    reason_stats[t['reason']]['wins'] += 1

            print(f"\n  Exit reasons:")
            for reason, stats in sorted(reason_stats.items(), key=lambda x: -x[1]['count']):
                wr_r = stats['wins'] / stats['count'] * 100
                print(f"    {reason:20s}: {stats['count']:3d} trades, "
                      f"WR {wr_r:4.0f}%, P/L ${stats['pnl']:+.2f}")

            # Direction
            longs = [t for t in bt if t['type'] == 'LONG']
            shorts = [t for t in bt if t['type'] == 'SHORT']
            print(f"\n  Direction:")
            for label, group in [('LONG', longs), ('SHORT', shorts)]:
                if not group:
                    continue
                g_wr = sum(1 for t in group if t['profit'] > 0) / len(group) * 100
                g_pnl = sum(t['profit'] for t in group)
                print(f"    {label:5s}: {len(group):3d} trades, WR {g_wr:.0f}%, P/L ${g_pnl:+.2f}")

            # Hold time distribution
            holds = [t['hold_seconds'] for t in bt]
            print(f"\n  Hold times: avg {sum(holds)/len(holds):.0f}s, "
                  f"min {min(holds):.0f}s, max {max(holds):.0f}s")

            brackets = [(0, 15), (15, 30), (30, 60), (60, 120), (120, 300), (300, 99999)]
            names = ["<15s", "15-30s", "30-60s", "1-2min", "2-5min", ">5min"]
            for (lo, hi), name in zip(brackets, names):
                group = [t for t in bt if lo <= t['hold_seconds'] < hi]
                if not group:
                    continue
                g_pnl = sum(t['profit'] for t in group)
                g_wr = sum(1 for t in group if t['profit'] > 0) / len(group) * 100
                print(f"    {name:>7}: {len(group):3d} trades, WR {g_wr:.0f}%, P/L ${g_pnl:+.2f}")

            # Last 10 trades
            print(f"\n  Last 10 trades:")
            for t in bt[-10:]:
                status = "W" if t['profit'] > 0 else "L"
                print(f"    {t['exit_time'].strftime('%H:%M')} {t['type']:5s} "
                      f"${t['profit']:+6.2f} [{status}] hold={t['hold_seconds']:.0f}s "
                      f"({t['reason']})")
            print()

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
