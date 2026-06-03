"""
Day-by-day analysis: TICK + M5S performance vs market conditions.
Shows each trading day (Sun evening to Fri) with market context.
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


MAGIC_TICK = 234200
MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'
LOOKBACK_HOURS = 90


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


def get_market_day(from_date: datetime, to_date: datetime) -> dict:
    """Get comprehensive market stats for one day."""
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, from_date, to_date)
    if rates is None or len(rates) < 10:
        return {}

    df = pd.DataFrame(rates)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values

    # ATR
    tr_vals = []
    for i in range(1, len(df)):
        tr_vals.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    avg_atr = np.mean(tr_vals) if tr_vals else 0

    # RSI
    deltas = np.diff(closes)
    rsi_values = []
    period = 14
    if len(deltas) > period:
        gains = np.where(deltas > 0, deltas, 0)
        losses_arr = np.where(deltas < 0, -deltas, 0)
        avg_gain = gains[:period].mean()
        avg_loss = losses_arr[:period].mean()
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses_arr[i]) / period
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))

    rsi_buy_crosses = 0
    rsi_sell_crosses = 0
    for i in range(1, len(rsi_values)):
        if rsi_values[i] < 35 and rsi_values[i-1] >= 35:
            rsi_buy_crosses += 1
        if rsi_values[i] > 65 and rsi_values[i-1] <= 65:
            rsi_sell_crosses += 1

    # Trend characterization
    net_move = closes[-1] - closes[0]
    day_high = max(highs)
    day_low = min(lows)
    day_range = day_high - day_low

    # Directional consistency: how much of the range was captured as net move?
    directionality = abs(net_move) / day_range if day_range > 0 else 0

    # Choppiness: count direction changes (close > prev close alternating)
    direction_changes = 0
    for i in range(2, len(closes)):
        if (closes[i] > closes[i-1]) != (closes[i-1] > closes[i-2]):
            direction_changes += 1
    choppiness = direction_changes / len(closes) if len(closes) > 0 else 0

    # Volatility profile: how consistent is ATR throughout the day?
    if len(tr_vals) >= 20:
        atr_std = np.std(tr_vals) / avg_atr if avg_atr > 0 else 0
    else:
        atr_std = 0

    # Swing count (simple: local min/max over 6-bar windows)
    swings = 0
    for i in range(3, len(closes) - 3):
        if closes[i] == max(closes[i-3:i+4]) or closes[i] == min(closes[i-3:i+4]):
            swings += 1

    # Market type classification
    if directionality > 0.5 and choppiness < 0.4:
        market_type = "TRENDING"
    elif directionality < 0.2 and choppiness > 0.5:
        market_type = "CHOPPY"
    elif avg_atr > 5.0:
        market_type = "VOLATILE"
    else:
        market_type = "MIXED"

    return {
        'open': closes[0],
        'close': closes[-1],
        'high': day_high,
        'low': day_low,
        'net_move': net_move,
        'range': day_range,
        'avg_atr': avg_atr,
        'directionality': directionality,
        'choppiness': choppiness,
        'atr_std': atr_std,
        'rsi_buy_crosses': rsi_buy_crosses,
        'rsi_sell_crosses': rsi_sell_crosses,
        'rsi_mean': np.mean(rsi_values) if rsi_values else 50,
        'candle_count': len(df),
        'market_type': market_type,
        'swings': swings,
    }


def analyze_day(day_label: str, day_start: datetime, day_end: datetime, tick_all: list, m5s_all: list):
    """Analyze one day."""
    tick_day = [t for t in tick_all if day_start <= t['exit_time'] < day_end]
    m5s_day = [t for t in m5s_all if day_start <= t['exit_time'] < day_end]
    market = get_market_day(day_start, day_end)

    if not market:
        return

    tick_profit = sum(t['profit'] for t in tick_day)
    m5s_profit = sum(t['profit'] for t in m5s_day)
    combined = tick_profit + m5s_profit

    tick_wins = sum(1 for t in tick_day if t['profit'] > 0)
    m5s_wins = sum(1 for t in m5s_day if t['profit'] > 0)
    tick_wr = tick_wins / len(tick_day) * 100 if tick_day else 0
    m5s_wr = m5s_wins / len(m5s_day) * 100 if m5s_day else 0

    print(f"\n{'='*90}")
    print(f"  {day_label}: {day_start.strftime('%Y-%m-%d %H:%M')} -> {day_end.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*90}")

    # Market conditions
    direction = "UP" if market['net_move'] > 5 else "DOWN" if market['net_move'] < -5 else "FLAT"
    print(f"\n  MARKET: {market['market_type']} {direction}")
    print(f"  Price: ${market['open']:.2f} -> ${market['close']:.2f} (net ${market['net_move']:+.2f})")
    print(f"  Range: ${market['range']:.2f} (H:${market['high']:.2f} L:${market['low']:.2f})")
    print(f"  ATR: ${market['avg_atr']:.2f} | Directionality: {market['directionality']:.2f} | Choppiness: {market['choppiness']:.2f}")
    print(f"  RSI signals: {market['rsi_buy_crosses']} buy / {market['rsi_sell_crosses']} sell | RSI mean: {market['rsi_mean']:.0f}")

    # Bot performance
    print(f"\n  TICK SCALPER: {len(tick_day)} trades, ${tick_profit:+.2f}, WR {tick_wr:.0f}%")
    if tick_day:
        tick_longs = [t for t in tick_day if t['type'] == 'LONG']
        tick_shorts = [t for t in tick_day if t['type'] == 'SHORT']
        print(f"    Longs: {len(tick_longs)} (${sum(t['profit'] for t in tick_longs):+.2f}) | "
              f"Shorts: {len(tick_shorts)} (${sum(t['profit'] for t in tick_shorts):+.2f})")
        big_losses = [t for t in tick_day if t['profit'] < -5]
        big_wins = [t for t in tick_day if t['profit'] > 5]
        print(f"    Big wins (>$5): {len(big_wins)} (${sum(t['profit'] for t in big_wins):+.2f}) | "
              f"Big losses (<-$5): {len(big_losses)} (${sum(t['profit'] for t in big_losses):+.2f})")

    print(f"\n  M5 SNIPER: {len(m5s_day)} trades, ${m5s_profit:+.2f}, WR {m5s_wr:.0f}%")
    if m5s_day:
        m5s_longs = [t for t in m5s_day if t['type'] == 'LONG']
        m5s_shorts = [t for t in m5s_day if t['type'] == 'SHORT']
        print(f"    Longs: {len(m5s_longs)} (${sum(t['profit'] for t in m5s_longs):+.2f}) | "
              f"Shorts: {len(m5s_shorts)} (${sum(t['profit'] for t in m5s_shorts):+.2f})")
        # Exit type breakdown
        mean_reverts = [t for t in m5s_day if t['profit'] > 10]
        small_profits = [t for t in m5s_day if 0 < t['profit'] <= 5]
        losses = [t for t in m5s_day if t['profit'] < 0]
        print(f"    Mean reverts (>$10): {len(mean_reverts)} (${sum(t['profit'] for t in mean_reverts):+.2f})")
        print(f"    Small wins (0-$5): {len(small_profits)} (${sum(t['profit'] for t in small_profits):+.2f})")
        print(f"    Losses: {len(losses)} (${sum(t['profit'] for t in losses):+.2f})")

    print(f"\n  COMBINED: ${combined:+.2f}")

    # Correlation insight
    if market['directionality'] > 0.4 and m5s_profit > 20:
        print(f"  --> Trending market + M5S profits: mean-reversion catching strong pullbacks")
    if market['choppiness'] > 0.45 and m5s_profit < -10:
        print(f"  --> Choppy market + M5S losses: entries get stopped before mean-revert completes")
    if market['avg_atr'] > 5 and tick_profit < -20:
        print(f"  --> High ATR + TICK losses: volatile spikes hitting wide stops")
    if tick_wr > 70 and tick_profit < 0:
        print(f"  --> High win rate but negative: classic R:R problem (many small wins, few big losses)")


def main():
    print("\n" + "=" * 90)
    print("  DAY-BY-DAY ANALYSIS vs MARKET CONDITIONS")
    print("=" * 90)

    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        now = datetime.now()
        start = now - timedelta(hours=LOOKBACK_HOURS)

        tick_all = get_trades(MAGIC_TICK, start, now)
        m5s_all = get_trades(MAGIC_M5S, start, now)

        # Split by calendar day (using local time)
        # Find distinct dates in the data
        all_trades = tick_all + m5s_all
        if not all_trades:
            print("  No trades found.")
            return

        dates = sorted(set(t['exit_time'].date() for t in all_trades))

        for date in dates:
            day_start = datetime(date.year, date.month, date.day, 0, 0, 0)
            day_end = day_start + timedelta(days=1)

            # Skip if day is outside our lookback
            if day_end < start:
                continue

            day_label = date.strftime('%A %b %d')
            analyze_day(day_label, day_start, day_end, tick_all, m5s_all)

        # Final summary
        print(f"\n\n{'='*90}")
        print(f"  SUMMARY")
        print(f"{'='*90}")
        print(f"\n  Total TICK: {len(tick_all)} trades, ${sum(t['profit'] for t in tick_all):+.2f}")
        print(f"  Total M5S:  {len(m5s_all)} trades, ${sum(t['profit'] for t in m5s_all):+.2f}")
        print(f"  Combined:   ${sum(t['profit'] for t in tick_all) + sum(t['profit'] for t in m5s_all):+.2f}")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
