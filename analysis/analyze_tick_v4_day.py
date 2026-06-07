"""
Analyze Tick Bot V4's best day (Mon Jun 1, 2026).

V4 was the only profitable tick bot version: 175 trades/day, 53% WR,
$6.06 avg win, $5.67 avg loss = +$97.89/day.

This script pulls all TICK magic (234200) trades from Jun 1 and analyzes:
- Win/loss distribution
- Hold times
- Exit reasons (from exit_reasons_tick.json)
- Price movement after exit (missed profit)
- Session breakdown
- Consecutive win/loss streaks
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from collections import defaultdict
import json

from src.core.timezone import get_mt5_now, mt5_to_local, get_local_now

TICK_MAGIC = 234200
SYMBOL = 'XAUUSD.p'


def load_exit_reasons() -> dict:
    """Load exit reasons from data file."""
    try:
        with open('data/exit_reasons_tick.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def get_trades_for_date(target_date: datetime.date) -> list[dict]:
    """
    Get all TICK bot trades for a specific local date.

    Follows the MT5 quirks pattern:
    - Query with buffer on both sides
    - Post-filter by local time
    """
    # We need to query MT5 in its timezone (EET)
    # Target: full day in local time (Europe/Berlin)
    # Local midnight = MT5 midnight + 1 hour (summer: Berlin=GMT+2, Athens=GMT+3)

    # Build the MT5 query range with generous buffer
    mt5_now = get_mt5_now()

    # How many days ago was target_date?
    local_now = get_local_now()
    days_ago = (local_now.date() - target_date).days

    # Query range: target day with buffer
    from_naive = (mt5_now - timedelta(days=days_ago + 1)).replace(tzinfo=None)
    to_naive = (mt5_now - timedelta(days=days_ago - 1)).replace(tzinfo=None)

    deals = mt5.history_deals_get(from_naive, to_naive)
    if deals is None:
        return []

    # Filter: TICK magic + XAUUSD
    tick_deals = [d for d in deals if d.magic == TICK_MAGIC and SYMBOL in d.symbol]

    # Group into trades (entry + exit pairs)
    positions = {}
    trades = []

    for deal in tick_deals:
        if deal.entry == mt5.DEAL_ENTRY_IN:
            positions[deal.position_id] = {
                'entry_time': mt5_to_local(deal.time),
                'entry_price': deal.price,
                'volume': deal.volume,
                'type': 'LONG' if deal.type == mt5.DEAL_TYPE_BUY else 'SHORT',
                'position_id': deal.position_id,
            }
        elif deal.entry == mt5.DEAL_ENTRY_OUT and deal.position_id in positions:
            pos = positions[deal.position_id]
            exit_time = mt5_to_local(deal.time)

            # Post-filter: only trades that exited on our target date (local time)
            if exit_time.date() != target_date:
                continue

            profit = deal.profit + deal.commission + deal.swap
            hold_seconds = (exit_time - pos['entry_time']).total_seconds()

            if pos['type'] == 'LONG':
                price_move = deal.price - pos['entry_price']
            else:
                price_move = pos['entry_price'] - deal.price

            # Determine exit reason from MT5 deal reason
            if deal.reason == mt5.DEAL_REASON_SL:
                exit_reason = "Stop loss"
            elif deal.reason == mt5.DEAL_REASON_TP:
                exit_reason = "Take profit"
            else:
                exit_reason = "Bot exit"

            trades.append({
                'entry_time': pos['entry_time'],
                'exit_time': exit_time,
                'type': pos['type'],
                'entry_price': pos['entry_price'],
                'exit_price': deal.price,
                'price_move': price_move,
                'profit': profit,
                'profit_gross': deal.profit,
                'commission': deal.commission,
                'volume': pos['volume'],
                'hold_seconds': hold_seconds,
                'exit_reason': exit_reason,
                'position_id': deal.position_id,
                'ticket': deal.ticket,
            })

            del positions[deal.position_id]

    trades.sort(key=lambda t: t['exit_time'])
    return trades


def analyze_trades(trades: list[dict]):
    """Print comprehensive analysis of trades."""
    if not trades:
        print("No trades found for this date.")
        return

    # Load exit reasons file for more detail
    exit_reasons = load_exit_reasons()

    print(f"\nTotal trades: {len(trades)}")
    print()

    # ── Overview ─────────────────────────────────────────────────────
    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] < 0]
    breakeven = [t for t in trades if t['profit'] == 0]

    total_pnl = sum(t['profit'] for t in trades)
    total_gross = sum(t['profit_gross'] for t in trades)
    total_commission = sum(t['commission'] for t in trades)
    wr = len(wins) / len(trades) * 100

    print("=" * 70)
    print("OVERVIEW")
    print("=" * 70)
    print(f"  Wins: {len(wins)} ({wr:.1f}%)")
    print(f"  Losses: {len(losses)} ({100-wr:.1f}%)")
    print(f"  Breakeven: {len(breakeven)}")
    print(f"  Total P/L: ${total_pnl:.2f} (gross: ${total_gross:.2f}, commission: ${total_commission:.2f})")
    print()

    if wins:
        avg_win = sum(t['profit'] for t in wins) / len(wins)
        max_win = max(t['profit'] for t in wins)
        median_win = sorted([t['profit'] for t in wins])[len(wins) // 2]
        print(f"  Avg win: ${avg_win:.2f}, Median: ${median_win:.2f}, Max: ${max_win:.2f}")

    if losses:
        avg_loss = sum(t['profit'] for t in losses) / len(losses)
        max_loss = min(t['profit'] for t in losses)
        median_loss = sorted([t['profit'] for t in losses])[len(losses) // 2]
        print(f"  Avg loss: ${avg_loss:.2f}, Median: ${median_loss:.2f}, Max: ${max_loss:.2f}")

    print()

    # ── Hold Times ───────────────────────────────────────────────────
    print("=" * 70)
    print("HOLD TIMES")
    print("=" * 70)

    hold_times = [t['hold_seconds'] for t in trades]
    avg_hold = sum(hold_times) / len(hold_times)
    min_hold = min(hold_times)
    max_hold = max(hold_times)

    win_holds = [t['hold_seconds'] for t in wins] if wins else [0]
    loss_holds = [t['hold_seconds'] for t in losses] if losses else [0]

    print(f"  Overall: avg {avg_hold:.0f}s, min {min_hold:.0f}s, max {max_hold:.0f}s")
    print(f"  Winners: avg {sum(win_holds)/len(win_holds):.0f}s")
    print(f"  Losers:  avg {sum(loss_holds)/len(loss_holds):.0f}s")
    print()

    # Distribution
    brackets = [(0, 30), (30, 60), (60, 120), (120, 300), (300, 600), (600, 99999)]
    bracket_names = ["<30s", "30-60s", "1-2min", "2-5min", "5-10min", ">10min"]
    print("  Hold time distribution:")
    for (lo, hi), name in zip(brackets, bracket_names):
        count = sum(1 for h in hold_times if lo <= h < hi)
        pnl = sum(t['profit'] for t in trades if lo <= t['hold_seconds'] < hi)
        wr_bracket = 0
        bracket_trades = [t for t in trades if lo <= t['hold_seconds'] < hi]
        if bracket_trades:
            wr_bracket = sum(1 for t in bracket_trades if t['profit'] > 0) / len(bracket_trades) * 100
        print(f"    {name:>8}: {count:3d} trades, WR {wr_bracket:4.0f}%, P/L ${pnl:+7.2f}")
    print()

    # ── Exit Reasons ─────────────────────────────────────────────────
    print("=" * 70)
    print("EXIT REASONS")
    print("=" * 70)

    reason_stats = defaultdict(lambda: {'count': 0, 'pnl': 0, 'wins': 0})
    for t in trades:
        # Try to get detailed reason from exit_reasons file
        ticket_str = str(t['ticket'])
        if ticket_str in exit_reasons:
            reason = exit_reasons[ticket_str].get('reason', t['exit_reason'])
        else:
            reason = t['exit_reason']

        # Categorize
        if 'Stop loss' in reason:
            category = 'Stop loss'
        elif 'Exit score' in reason:
            category = 'Exit score'
        elif 'Velocity' in reason or 'partial' in reason.lower():
            category = 'Velocity/Partial'
        elif 'Take profit' in reason:
            category = 'Take profit'
        else:
            category = reason

        reason_stats[category]['count'] += 1
        reason_stats[category]['pnl'] += t['profit']
        if t['profit'] > 0:
            reason_stats[category]['wins'] += 1

    for reason, stats in sorted(reason_stats.items(), key=lambda x: -x[1]['count']):
        wr_r = stats['wins'] / stats['count'] * 100 if stats['count'] > 0 else 0
        print(f"  {reason:25s}: {stats['count']:3d} trades, WR {wr_r:4.0f}%, P/L ${stats['pnl']:+7.2f}")
    print()

    # ── Direction ────────────────────────────────────────────────────
    print("=" * 70)
    print("DIRECTION ANALYSIS")
    print("=" * 70)

    longs = [t for t in trades if t['type'] == 'LONG']
    shorts = [t for t in trades if t['type'] == 'SHORT']

    for label, group in [('LONG', longs), ('SHORT', shorts)]:
        if not group:
            continue
        g_wins = [t for t in group if t['profit'] > 0]
        g_wr = len(g_wins) / len(group) * 100
        g_pnl = sum(t['profit'] for t in group)
        g_avg_win = sum(t['profit'] for t in g_wins) / len(g_wins) if g_wins else 0
        g_losses = [t for t in group if t['profit'] < 0]
        g_avg_loss = sum(t['profit'] for t in g_losses) / len(g_losses) if g_losses else 0
        print(f"  {label:5s}: {len(group):3d} trades, WR {g_wr:.0f}%, "
              f"P/L ${g_pnl:+.2f}, Avg W ${g_avg_win:.2f} / L ${g_avg_loss:.2f}")
    print()

    # ── Session Breakdown ────────────────────────────────────────────
    print("=" * 70)
    print("SESSION BREAKDOWN (local time)")
    print("=" * 70)

    sessions = [
        ("00-04 Asian", 0, 4),
        ("04-08 Asian/London", 4, 8),
        ("08-12 London", 8, 12),
        ("12-16 London/NY", 12, 16),
        ("16-20 NY", 16, 20),
        ("20-24 NY/Asian", 20, 24),
    ]

    for name, start_h, end_h in sessions:
        session_trades = [t for t in trades if start_h <= t['exit_time'].hour < end_h]
        if not session_trades:
            print(f"  {name:20s}: no trades")
            continue
        s_pnl = sum(t['profit'] for t in session_trades)
        s_wins = sum(1 for t in session_trades if t['profit'] > 0)
        s_wr = s_wins / len(session_trades) * 100
        print(f"  {name:20s}: {len(session_trades):3d} trades, WR {s_wr:.0f}%, P/L ${s_pnl:+7.2f}")
    print()

    # ── Price Movement After Exit ────────────────────────────────────
    print("=" * 70)
    print("PRICE MOVEMENT AFTER EXIT (missed profit analysis)")
    print("=" * 70)
    print()

    # For each winning trade, check how much further price went in our direction
    # within 60 seconds after exit
    missed_profits = []
    correct_exits = 0
    premature_exits = 0

    for t in wins[:50]:  # Limit to first 50 wins for speed
        exit_time_naive = t['exit_time'].replace(tzinfo=None)
        # Get 1-minute candles for 5 minutes after exit
        rates = mt5.copy_rates_from(SYMBOL, mt5.TIMEFRAME_M1, exit_time_naive, 5)
        if rates is None or len(rates) == 0:
            continue

        if t['type'] == 'LONG':
            # How high did price go after we exited?
            peak_after = max(r[2] for r in rates)  # high column
            missed = peak_after - t['exit_price']
        else:
            trough_after = min(r[3] for r in rates)  # low column
            missed = t['exit_price'] - trough_after

        if missed > 1.0:  # More than $1 of continued movement
            premature_exits += 1
            missed_profits.append(missed)
        else:
            correct_exits += 1

    total_analyzed = premature_exits + correct_exits
    if total_analyzed > 0:
        print(f"  Analyzed {total_analyzed} winning trades (5-min after exit):")
        print(f"  Correct exits (price reversed within $1): {correct_exits} ({correct_exits/total_analyzed*100:.0f}%)")
        print(f"  Premature exits (price continued $1+): {premature_exits} ({premature_exits/total_analyzed*100:.0f}%)")
        if missed_profits:
            avg_missed = sum(missed_profits) / len(missed_profits)
            max_missed = max(missed_profits)
            print(f"  Avg missed move: ${avg_missed:.2f}, Max: ${max_missed:.2f}")
            total_missed_est = avg_missed * premature_exits
            print(f"  Estimated total missed profit: ${total_missed_est:.2f} (across {premature_exits} trades)")
    print()

    # ── Streaks ──────────────────────────────────────────────────────
    print("=" * 70)
    print("CONSECUTIVE STREAKS")
    print("=" * 70)

    max_win_streak = 0
    max_loss_streak = 0
    current_streak = 0
    current_type = None

    for t in trades:
        is_win = t['profit'] > 0
        if current_type is None:
            current_type = is_win
            current_streak = 1
        elif is_win == current_type:
            current_streak += 1
        else:
            if current_type:
                max_win_streak = max(max_win_streak, current_streak)
            else:
                max_loss_streak = max(max_loss_streak, current_streak)
            current_type = is_win
            current_streak = 1

    # Don't forget the last streak
    if current_type is not None:
        if current_type:
            max_win_streak = max(max_win_streak, current_streak)
        else:
            max_loss_streak = max(max_loss_streak, current_streak)

    print(f"  Max winning streak: {max_win_streak}")
    print(f"  Max losing streak: {max_loss_streak}")
    print()

    # ── Top 10 Best and Worst ────────────────────────────────────────
    print("=" * 70)
    print("TOP 10 BEST TRADES")
    print("=" * 70)
    for t in sorted(trades, key=lambda x: x['profit'], reverse=True)[:10]:
        print(f"  {t['exit_time'].strftime('%H:%M')} {t['type']:5s} "
              f"${t['profit']:+6.2f} | hold {t['hold_seconds']:4.0f}s | "
              f"entry ${t['entry_price']:.2f} -> ${t['exit_price']:.2f}")

    print()
    print("=" * 70)
    print("TOP 10 WORST TRADES")
    print("=" * 70)
    for t in sorted(trades, key=lambda x: x['profit'])[:10]:
        print(f"  {t['exit_time'].strftime('%H:%M')} {t['type']:5s} "
              f"${t['profit']:+6.2f} | hold {t['hold_seconds']:4.0f}s | "
              f"entry ${t['entry_price']:.2f} -> ${t['exit_price']:.2f}")
    print()


def main():
    print("=" * 70)
    print("TICK BOT V4 ANALYSIS -- Monday June 1, 2026")
    print("(V4 was the only profitable version: +$98/day)")
    print("=" * 70)

    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        # V4's best day: Mon Jun 1, 2026
        target_date = datetime(2026, 6, 1).date()
        print(f"\nFetching TICK trades for {target_date}...")

        trades = get_trades_for_date(target_date)
        analyze_trades(trades)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
