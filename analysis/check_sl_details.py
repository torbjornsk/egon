"""
Analyze the M5 Sniper "Stop loss" exits in Period B to determine
if they were initial SL hits or trailed SL hits.

If entry -> price went up -> trailed SL moved up -> price reversed -> trailed SL hit,
that's a very different situation from entry -> price immediately went against us -> initial SL hit.
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import numpy as np


MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'


def main():
    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        now = datetime.now()
        # Period B: 24h before the last 22h
        period_b_end = now - timedelta(hours=22)
        period_b_start = period_b_end - timedelta(hours=24)

        # Also check Period A for comparison
        period_a_start = now - timedelta(hours=22)
        period_a_end = now

        for period_label, from_date, to_date in [
            ("Period A (last 22h)", period_a_start, period_a_end),
            ("Period B (preceding 24h)", period_b_start, period_b_end),
        ]:
            print(f"\n{'='*80}")
            print(f"  M5 SNIPER STOP LOSS DETAIL -- {period_label}")
            print(f"{'='*80}\n")

            deals = mt5.history_deals_get(from_date, to_date)
            if deals is None:
                print("  No deals found.")
                continue

            relevant = [d for d in deals if d.magic == MAGIC_M5S and SYMBOL in d.symbol]

            # Group into trades
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

                    # Check if this was a stop loss
                    is_sl = (deal.reason == mt5.DEAL_REASON_SL)

                    if pos['type'] == 'LONG':
                        price_change = deal.price - pos['entry_price']
                    else:
                        price_change = pos['entry_price'] - deal.price

                    hold_min = (exit_time - pos['entry_time']).total_seconds() / 60

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
                        'is_sl': is_sl,
                        'position_id': pos['position_id'],
                    })
                    del positions[deal.position_id]

            # Filter to SL exits only
            sl_trades = [t for t in trades if t['is_sl']]
            if not sl_trades:
                print("  No SL exits found.")
                continue

            # For each SL trade, check what the peak favorable price was
            # to determine if SL was trailed (peak > entry = was in profit)
            print(f"  {'Time':<6} {'Dir':<5} {'Entry':>9} {'Exit':>9} {'Peak':>9} "
                  f"{'PeakMove':>9} {'ExitMove':>9} {'P/L':>8} {'Hold':>5} {'Type':<12}")
            print(f"  {'─'*6} {'─'*5} {'─'*9} {'─'*9} {'─'*9} "
                  f"{'─'*9} {'─'*9} {'─'*8} {'─'*5} {'─'*12}")

            initial_sl_count = 0
            trailed_sl_count = 0
            initial_sl_profit = 0.0
            trailed_sl_profit = 0.0

            for t in sorted(sl_trades, key=lambda x: x['exit_time']):
                # Fetch M1 data for this trade to find peak price
                rates = mt5.copy_rates_range(
                    SYMBOL, mt5.TIMEFRAME_M1,
                    t['entry_time'] - timedelta(minutes=1),
                    t['exit_time'] + timedelta(minutes=1),
                )

                peak_move = 0.0
                if rates is not None and len(rates) > 0:
                    if t['type'] == 'LONG':
                        peak_price = max(r[2] for r in rates)  # high
                        peak_move = peak_price - t['entry_price']
                    else:
                        peak_price = min(r[3] for r in rates)  # low
                        peak_move = t['entry_price'] - peak_price
                else:
                    peak_price = t['entry_price']

                # Classify: if peak move > 0.5 ATR (~$1.5), it was likely trailed
                # ATR for this period is ~$3.33-$4.13
                is_trailed = peak_move > 1.5  # went at least $1.50 in our favor

                if is_trailed:
                    sl_type = "TRAILED"
                    trailed_sl_count += 1
                    trailed_sl_profit += t['profit']
                else:
                    sl_type = "INITIAL"
                    initial_sl_count += 1
                    initial_sl_profit += t['profit']

                print(
                    f"  {t['exit_time'].strftime('%H:%M'):<6} "
                    f"{t['type']:<5} "
                    f"${t['entry_price']:>7.2f} "
                    f"${t['exit_price']:>7.2f} "
                    f"${peak_price:>7.2f} "
                    f"${peak_move:>+7.2f} "
                    f"${t['price_change']:>+7.2f} "
                    f"${t['profit']:>+6.2f} "
                    f"{t['hold_min']:>4.0f}m "
                    f"{sl_type:<12}"
                )

            print(f"\n  Summary:")
            print(f"    Initial SL hits: {initial_sl_count}, total ${initial_sl_profit:+.2f}"
                  f" (avg ${initial_sl_profit/initial_sl_count:.2f})" if initial_sl_count else "    Initial SL: 0")
            print(f"    Trailed SL hits: {trailed_sl_count}, total ${trailed_sl_profit:+.2f}"
                  f" (avg ${trailed_sl_profit/trailed_sl_count:.2f})" if trailed_sl_count else "    Trailed SL: 0")
            print(f"    Total SL exits: {len(sl_trades)}, total ${sum(t['profit'] for t in sl_trades):+.2f}")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
