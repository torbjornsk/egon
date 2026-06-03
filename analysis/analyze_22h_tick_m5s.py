"""
Analyze last 22 hours of trades for TICK and M5 Sniper bots.

Fetches deal history from MT5, groups into trades, and reports:
- Win rate, total P/L, avg win/loss
- Exit reason breakdown
- Hourly distribution
- Consecutive loss streaks
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from collections import defaultdict


MAGIC_TICK = 234200
MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'
LOOKBACK_HOURS = 22


def get_trades(magic: int, from_date: datetime, to_date: datetime) -> list[dict]:
    """Fetch deals from MT5 and group into completed trades."""
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None or len(deals) == 0:
        return []

    # Filter by magic number and symbol
    relevant = [d for d in deals if d.magic == magic and SYMBOL in d.symbol]
    if not relevant:
        return []

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
                # Exit without matching entry in this window -- skip
                continue

            exit_time = datetime.fromtimestamp(deal.time)
            exit_price = deal.price
            profit = deal.profit + deal.commission + deal.swap

            if pos['type'] == 'LONG':
                price_change = exit_price - pos['entry_price']
            else:
                price_change = pos['entry_price'] - exit_price

            hold_minutes = (exit_time - pos['entry_time']).total_seconds() / 60

            trades.append({
                'entry_time': pos['entry_time'],
                'exit_time': exit_time,
                'type': pos['type'],
                'entry_price': pos['entry_price'],
                'exit_price': exit_price,
                'price_change': price_change,
                'profit': profit,
                'volume': pos['volume'],
                'hold_min': hold_minutes,
                'position_id': pos['position_id'],
            })

            del positions[deal.position_id]

    # Sort by exit time
    trades.sort(key=lambda t: t['exit_time'])
    return trades


def load_exit_reasons(bot_key: str) -> dict:
    """Load exit reasons from the JSON file."""
    import json
    import os

    filename = f'data/exit_reasons_{bot_key}.json'
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r') as f:
        return json.load(f)


def analyze_bot(bot_name: str, trades: list[dict], exit_reasons: dict):
    """Print analysis for one bot."""
    print()
    print("=" * 80)
    print(f"  {bot_name} BOT -- Last {LOOKBACK_HOURS} hours")
    print("=" * 80)

    if not trades:
        print("  No completed trades found.")
        return

    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] <= 0]
    total_profit = sum(t['profit'] for t in trades)

    print(f"\n  Total trades: {len(trades)}")
    print(f"  Wins: {len(wins)}  |  Losses: {len(losses)}")
    win_rate = len(wins) / len(trades) * 100
    print(f"  Win rate: {win_rate:.1f}%")
    print(f"  Total P/L: ${total_profit:+.2f}")

    if wins:
        avg_win = sum(t['profit'] for t in wins) / len(wins)
        max_win = max(t['profit'] for t in wins)
        print(f"  Avg win: ${avg_win:.2f}  |  Best: ${max_win:.2f}")

    if losses:
        avg_loss = sum(t['profit'] for t in losses) / len(losses)
        worst_loss = min(t['profit'] for t in losses)
        print(f"  Avg loss: ${avg_loss:.2f}  |  Worst: ${worst_loss:.2f}")

    if wins and losses:
        avg_win = sum(t['profit'] for t in wins) / len(wins)
        avg_loss_abs = abs(sum(t['profit'] for t in losses) / len(losses))
        rr = avg_win / avg_loss_abs if avg_loss_abs > 0 else 999
        print(f"  Risk/Reward: {rr:.2f}")

    # Hold time stats
    avg_hold = sum(t['hold_min'] for t in trades) / len(trades)
    print(f"  Avg hold time: {avg_hold:.1f} min")

    # Price movement analysis
    avg_price_change_wins = 0
    avg_price_change_losses = 0
    if wins:
        avg_price_change_wins = sum(t['price_change'] for t in wins) / len(wins)
    if losses:
        avg_price_change_losses = sum(t['price_change'] for t in losses) / len(losses)
    print(f"  Avg price move (wins): ${avg_price_change_wins:+.2f}")
    print(f"  Avg price move (losses): ${avg_price_change_losses:+.2f}")

    # ── Exit Reason Breakdown ────────────────────────────────────────
    print(f"\n  {'EXIT REASON BREAKDOWN':─^50}")
    reason_stats = defaultdict(lambda: {'count': 0, 'profit': 0.0})

    for trade in trades:
        pos_id = str(trade['position_id'])
        reason_data = exit_reasons.get(pos_id)
        if reason_data:
            # Categorize into buckets
            full_reason = reason_data.get('full_reason', 'Unknown')
            if 'Stop loss' in full_reason:
                bucket = 'Stop loss'
            elif 'MT5 close' in full_reason:
                bucket = 'MT5 close'
            elif 'Profit protection' in full_reason:
                bucket = 'Profit protection'
            elif 'Mean revert' in full_reason:
                bucket = 'Mean revert exit'
            elif 'RSI exit' in full_reason:
                bucket = 'RSI exit'
            elif 'Exit score' in full_reason:
                # Extract the primary driver
                if 'structure_pressure' in full_reason:
                    bucket = 'Exit score (structure)'
                elif 'velocity_exhaustion' in full_reason:
                    bucket = 'Exit score (velocity)'
                elif 'opposite_pressure' in full_reason:
                    bucket = 'Exit score (opposite)'
                elif 'profit_stall' in full_reason:
                    bucket = 'Exit score (stall)'
                elif 'exhaustion' in full_reason:
                    bucket = 'Exit score (exhaustion)'
                else:
                    bucket = 'Exit score (other)'
            else:
                bucket = full_reason[:30]
        else:
            bucket = 'Unknown'

        reason_stats[bucket]['count'] += 1
        reason_stats[bucket]['profit'] += trade['profit']

    # Sort by count
    sorted_reasons = sorted(reason_stats.items(), key=lambda x: -x[1]['count'])
    print(f"  {'Reason':<28} {'Count':>5} {'P/L':>10} {'Avg':>8}")
    print(f"  {'─'*28} {'─'*5} {'─'*10} {'─'*8}")
    for reason, stats in sorted_reasons:
        avg = stats['profit'] / stats['count'] if stats['count'] > 0 else 0
        print(f"  {reason:<28} {stats['count']:>5} ${stats['profit']:>+8.2f} ${avg:>+6.2f}")

    # ── Hourly Distribution ──────────────────────────────────────────
    print(f"\n  {'HOURLY P/L DISTRIBUTION':─^50}")
    hourly = defaultdict(lambda: {'count': 0, 'profit': 0.0, 'wins': 0})
    for trade in trades:
        hour = trade['exit_time'].hour
        hourly[hour]['count'] += 1
        hourly[hour]['profit'] += trade['profit']
        if trade['profit'] > 0:
            hourly[hour]['wins'] += 1

    print(f"  {'Hour':<6} {'Trades':>6} {'P/L':>10} {'WR':>6}")
    print(f"  {'─'*6} {'─'*6} {'─'*10} {'─'*6}")
    for hour in sorted(hourly.keys()):
        h = hourly[hour]
        wr = h['wins'] / h['count'] * 100 if h['count'] > 0 else 0
        print(f"  {hour:02d}:00  {h['count']:>5} ${h['profit']:>+8.2f} {wr:>5.0f}%")

    # ── Consecutive Loss Streaks ─────────────────────────────────────
    print(f"\n  {'STREAK ANALYSIS':─^50}")
    max_loss_streak = 0
    current_streak = 0
    max_win_streak = 0
    current_win_streak = 0

    for trade in trades:
        if trade['profit'] <= 0:
            current_streak += 1
            max_loss_streak = max(max_loss_streak, current_streak)
            current_win_streak = 0
        else:
            current_win_streak += 1
            max_win_streak = max(max_win_streak, current_win_streak)
            current_streak = 0

    print(f"  Max consecutive losses: {max_loss_streak}")
    print(f"  Max consecutive wins: {max_win_streak}")

    # ── Direction Analysis ───────────────────────────────────────────
    print(f"\n  {'DIRECTION ANALYSIS':─^50}")
    longs = [t for t in trades if t['type'] == 'LONG']
    shorts = [t for t in trades if t['type'] == 'SHORT']

    long_profit = sum(t['profit'] for t in longs)
    short_profit = sum(t['profit'] for t in shorts)
    long_wr = len([t for t in longs if t['profit'] > 0]) / len(longs) * 100 if longs else 0
    short_wr = len([t for t in shorts if t['profit'] > 0]) / len(shorts) * 100 if shorts else 0

    print(f"  LONG:  {len(longs)} trades, ${long_profit:+.2f}, WR {long_wr:.0f}%")
    print(f"  SHORT: {len(shorts)} trades, ${short_profit:+.2f}, WR {short_wr:.0f}%")

    # ── Last 10 Trades ───────────────────────────────────────────────
    print(f"\n  {'LAST 10 TRADES':─^50}")
    for trade in trades[-10:]:
        status = "W" if trade['profit'] > 0 else "L"
        pos_id = str(trade['position_id'])
        reason_data = exit_reasons.get(pos_id)
        reason_str = reason_data['reason'][:25] if reason_data else '?'
        print(
            f"  {trade['exit_time'].strftime('%H:%M')} "
            f"{trade['type']:<5} "
            f"${trade['profit']:>+6.2f} "
            f"({trade['hold_min']:.0f}m) "
            f"{reason_str}"
        )


def main():
    print("\n" + "=" * 80)
    print("  TRADE ANALYSIS -- Last 22 Hours")
    print("  TICK Scalper (magic 234200) & M5 Sniper (magic 234050)")
    print("=" * 80)

    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        # Account info
        account = mt5.account_info()
        if account:
            print(f"\n  Account: {account.login}")
            print(f"  Balance: ${account.balance:.2f}  |  Equity: ${account.equity:.2f}")

        # Time window
        to_date = datetime.now()
        from_date = to_date - timedelta(hours=LOOKBACK_HOURS)
        print(f"  Window: {from_date.strftime('%Y-%m-%d %H:%M')} -> {to_date.strftime('%Y-%m-%d %H:%M')}")

        # Fetch trades
        tick_trades = get_trades(MAGIC_TICK, from_date, to_date)
        m5s_trades = get_trades(MAGIC_M5S, from_date, to_date)

        # Load exit reasons
        tick_reasons = load_exit_reasons('tick')
        m5s_reasons = load_exit_reasons('m5s')

        # Analyze each bot
        analyze_bot("TICK SCALPER", tick_trades, tick_reasons)
        analyze_bot("M5 SNIPER", m5s_trades, m5s_reasons)

        # ── Combined Summary ─────────────────────────────────────────
        all_trades = tick_trades + m5s_trades
        if all_trades:
            total = sum(t['profit'] for t in all_trades)
            print("\n" + "=" * 80)
            print(f"  COMBINED: {len(all_trades)} trades, ${total:+.2f}")
            print(f"  TICK: {len(tick_trades)} trades (${sum(t['profit'] for t in tick_trades):+.2f})")
            print(f"  M5S:  {len(m5s_trades)} trades (${sum(t['profit'] for t in m5s_trades):+.2f})")
            print("=" * 80)

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
