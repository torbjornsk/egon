"""
Deep 48-hour analysis: comparing M5 Sniper performance between
the last 22 hours vs the 24 hours before that.

Also analyzes what went wrong with the tick bot.

Fetches actual price data to understand market conditions that
drove the different outcomes.
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
import pandas as pd


MAGIC_TICK = 234200
MAGIC_M5S = 234050
SYMBOL = 'XAUUSD.p'


def get_trades(magic: int, from_date: datetime, to_date: datetime) -> list[dict]:
    """Fetch deals from MT5 and group into completed trades."""
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None or len(deals) == 0:
        return []

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

    trades.sort(key=lambda t: t['exit_time'])
    return trades


def load_exit_reasons(bot_key: str) -> dict:
    import json, os
    filename = f'data/exit_reasons_{bot_key}.json'
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r') as f:
        return json.load(f)


def get_market_context(from_date: datetime, to_date: datetime) -> dict:
    """Get M5 price data for the period to understand market conditions."""
    # Need to convert to naive datetime for MT5 API
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, from_date, to_date)
    if rates is None or len(rates) == 0:
        return {}

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Compute basic stats
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values

    # ATR
    tr = []
    for i in range(1, len(df)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        ))
    avg_atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr) if tr else 0

    # RSI
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Rolling RSI values at each point
    rsi_values = []
    period = 14
    if len(deltas) > period:
        avg_gain = gains[:period].mean()
        avg_loss = losses[:period].mean()
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))

    # How many times RSI crossed buy/sell thresholds
    rsi_buy_crosses = 0
    rsi_sell_crosses = 0
    for i in range(1, len(rsi_values)):
        if rsi_values[i] < 35 and rsi_values[i-1] >= 35:
            rsi_buy_crosses += 1
        if rsi_values[i] > 65 and rsi_values[i-1] <= 65:
            rsi_sell_crosses += 1

    # Price range and trend
    total_range = max(highs) - min(lows)
    net_move = closes[-1] - closes[0]
    max_drawdown_from_start = min(lows) - closes[0]
    max_rally_from_start = max(highs) - closes[0]

    # Directional bias
    up_candles = sum(1 for i in range(len(df)) if df.iloc[i]['close'] > df.iloc[i]['open'])
    down_candles = len(df) - up_candles

    # Volatility profile (ATR over time)
    hourly_atr = {}
    for i in range(14, len(df)):
        hour = df.iloc[i]['time'].hour
        local_tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        )
        if hour not in hourly_atr:
            hourly_atr[hour] = []
        hourly_atr[hour].append(local_tr)

    avg_hourly_atr = {h: np.mean(v) for h, v in hourly_atr.items()}

    return {
        'start_price': closes[0],
        'end_price': closes[-1],
        'net_move': net_move,
        'total_range': total_range,
        'avg_atr': avg_atr,
        'rsi_buy_crosses': rsi_buy_crosses,
        'rsi_sell_crosses': rsi_sell_crosses,
        'up_candles': up_candles,
        'down_candles': down_candles,
        'candle_count': len(df),
        'max_rally': max_rally_from_start,
        'max_drawdown': max_drawdown_from_start,
        'hourly_atr': avg_hourly_atr,
        'rsi_min': min(rsi_values) if rsi_values else 50,
        'rsi_max': max(rsi_values) if rsi_values else 50,
        'rsi_mean': np.mean(rsi_values) if rsi_values else 50,
    }


def print_period_analysis(label: str, trades: list, exit_reasons: dict, market: dict):
    """Detailed analysis for one period."""
    print(f"\n{'=' * 80}")
    print(f"  {label}")
    print(f"{'=' * 80}")

    if not trades:
        print("  No trades.")
        return

    wins = [t for t in trades if t['profit'] > 0]
    losses = [t for t in trades if t['profit'] <= 0]
    total_profit = sum(t['profit'] for t in trades)
    win_rate = len(wins) / len(trades) * 100

    print(f"\n  Trades: {len(trades)} | Wins: {len(wins)} ({win_rate:.0f}%) | P/L: ${total_profit:+.2f}")
    if wins:
        print(f"  Avg win: ${sum(t['profit'] for t in wins)/len(wins):.2f} | Best: ${max(t['profit'] for t in wins):.2f}")
    if losses:
        print(f"  Avg loss: ${sum(t['profit'] for t in losses)/len(losses):.2f} | Worst: ${min(t['profit'] for t in losses):.2f}")
    if wins and losses:
        avg_w = sum(t['profit'] for t in wins) / len(wins)
        avg_l = abs(sum(t['profit'] for t in losses) / len(losses))
        print(f"  R:R ratio: {avg_w/avg_l:.2f}")

    print(f"  Avg hold: {sum(t['hold_min'] for t in trades)/len(trades):.1f} min")
    print(f"  Direction: {sum(1 for t in trades if t['type']=='LONG')} LONG / {sum(1 for t in trades if t['type']=='SHORT')} SHORT")

    # Exit reasons
    print(f"\n  Exit Reasons:")
    reason_stats = defaultdict(lambda: {'count': 0, 'profit': 0.0})
    for trade in trades:
        pos_id = str(trade['position_id'])
        reason_data = exit_reasons.get(pos_id)
        if reason_data:
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
                if 'structure_pressure' in full_reason:
                    bucket = 'Exit score (structure)'
                elif 'velocity_exhaustion' in full_reason:
                    bucket = 'Exit score (velocity)'
                elif 'opposite_pressure' in full_reason:
                    bucket = 'Exit score (opposite)'
                else:
                    bucket = 'Exit score (other)'
            else:
                bucket = full_reason[:30]
        else:
            bucket = 'Unknown'
        reason_stats[bucket]['count'] += 1
        reason_stats[bucket]['profit'] += trade['profit']

    for reason, stats in sorted(reason_stats.items(), key=lambda x: -x[1]['count']):
        avg = stats['profit'] / stats['count']
        print(f"    {reason:<28} {stats['count']:>3}x  ${stats['profit']:>+7.2f}  (avg ${avg:>+5.2f})")

    # Market context
    if market:
        print(f"\n  Market Context:")
        print(f"    Price: ${market['start_price']:.2f} -> ${market['end_price']:.2f} (net ${market['net_move']:+.2f})")
        print(f"    Range: ${market['total_range']:.2f} | Avg M5 ATR: ${market['avg_atr']:.2f}")
        print(f"    RSI buy crosses: {market['rsi_buy_crosses']} | RSI sell crosses: {market['rsi_sell_crosses']}")
        print(f"    RSI range: {market['rsi_min']:.0f} - {market['rsi_max']:.0f} (mean {market['rsi_mean']:.0f})")
        print(f"    Candles: {market['up_candles']} up / {market['down_candles']} down")
        print(f"    Max rally: ${market['max_rally']:+.2f} | Max drawdown: ${market['max_drawdown']:+.2f}")

    # Winning trades analysis: what did they capture?
    if wins:
        print(f"\n  Winning Trades Analysis:")
        long_wins = [t for t in wins if t['type'] == 'LONG']
        short_wins = [t for t in wins if t['type'] == 'SHORT']
        print(f"    LONG wins: {len(long_wins)}, avg ${sum(t['profit'] for t in long_wins)/len(long_wins):.2f}" if long_wins else "    LONG wins: 0")
        print(f"    SHORT wins: {len(short_wins)}, avg ${sum(t['profit'] for t in short_wins)/len(short_wins):.2f}" if short_wins else "    SHORT wins: 0")
        print(f"    Avg price move (wins): ${sum(t['price_change'] for t in wins)/len(wins):.2f}")
        print(f"    Avg hold time (wins): {sum(t['hold_min'] for t in wins)/len(wins):.1f} min")

    # Losing trades analysis
    if losses:
        print(f"\n  Losing Trades Analysis:")
        long_losses = [t for t in losses if t['type'] == 'LONG']
        short_losses = [t for t in losses if t['type'] == 'SHORT']
        print(f"    LONG losses: {len(long_losses)}, avg ${sum(t['profit'] for t in long_losses)/len(long_losses):.2f}" if long_losses else "    LONG losses: 0")
        print(f"    SHORT losses: {len(short_losses)}, avg ${sum(t['profit'] for t in short_losses)/len(short_losses):.2f}" if short_losses else "    SHORT losses: 0")
        print(f"    Avg price move (losses): ${sum(t['price_change'] for t in losses)/len(losses):.2f}")
        print(f"    Avg hold time (losses): {sum(t['hold_min'] for t in losses)/len(losses):.1f} min")


def main():
    print("\n" + "=" * 80)
    print("  DEEP 48-HOUR ANALYSIS")
    print("  Comparing periods: last 22h (Period A) vs preceding 24h (Period B)")
    print("=" * 80)

    if not mt5.initialize():
        print(f"MT5 initialization failed: {mt5.last_error()}")
        return

    try:
        now = datetime.now()

        # Period A: last 22 hours (today's session)
        period_a_end = now
        period_a_start = now - timedelta(hours=22)

        # Period B: the 24 hours before that
        period_b_end = period_a_start
        period_b_start = period_b_end - timedelta(hours=24)

        print(f"\n  Period A: {period_a_start.strftime('%Y-%m-%d %H:%M')} -> {period_a_end.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Period B: {period_b_start.strftime('%Y-%m-%d %H:%M')} -> {period_b_end.strftime('%Y-%m-%d %H:%M')}")

        # Load exit reasons
        m5s_reasons = load_exit_reasons('m5s')
        tick_reasons = load_exit_reasons('tick')

        # ═══════════════════════════════════════════════════════════════
        # M5 SNIPER COMPARISON
        # ═══════════════════════════════════════════════════════════════
        print("\n\n" + "#" * 80)
        print("#  M5 SNIPER: Period A (last 22h) vs Period B (preceding 24h)")
        print("#" * 80)

        m5s_a = get_trades(MAGIC_M5S, period_a_start, period_a_end)
        m5s_b = get_trades(MAGIC_M5S, period_b_start, period_b_end)

        market_a = get_market_context(period_a_start, period_a_end)
        market_b = get_market_context(period_b_start, period_b_end)

        print_period_analysis("M5 SNIPER -- Period A (last 22h)", m5s_a, m5s_reasons, market_a)
        print_period_analysis("M5 SNIPER -- Period B (preceding 24h)", m5s_b, m5s_reasons, market_b)

        # Comparative insights
        if m5s_a and m5s_b and market_a and market_b:
            print(f"\n{'=' * 80}")
            print(f"  M5 SNIPER COMPARISON INSIGHTS")
            print(f"{'=' * 80}")

            profit_a = sum(t['profit'] for t in m5s_a)
            profit_b = sum(t['profit'] for t in m5s_b)
            print(f"\n  P/L: A=${profit_a:+.2f} vs B=${profit_b:+.2f} (delta ${profit_a-profit_b:+.2f})")

            wr_a = len([t for t in m5s_a if t['profit'] > 0]) / len(m5s_a) * 100
            wr_b = len([t for t in m5s_b if t['profit'] > 0]) / len(m5s_b) * 100
            print(f"  Win rate: A={wr_a:.0f}% vs B={wr_b:.0f}%")

            print(f"\n  Market conditions:")
            print(f"    Net move: A=${market_a['net_move']:+.2f} vs B=${market_b['net_move']:+.2f}")
            print(f"    ATR: A=${market_a['avg_atr']:.2f} vs B=${market_b['avg_atr']:.2f}")
            print(f"    RSI buy signals: A={market_a['rsi_buy_crosses']} vs B={market_b['rsi_buy_crosses']}")
            print(f"    RSI sell signals: A={market_a['rsi_sell_crosses']} vs B={market_b['rsi_sell_crosses']}")
            print(f"    RSI mean: A={market_a['rsi_mean']:.0f} vs B={market_b['rsi_mean']:.0f}")
            print(f"    Range: A=${market_a['total_range']:.2f} vs B=${market_b['total_range']:.2f}")

            # Key hypothesis: when market has clear directional moves that pull RSI
            # to extremes and then revert, the mean-revert exit works perfectly.
            # When market chops, entries hit SL before RSI can mean-revert.
            mean_revert_wins_a = [t for t in m5s_a if t['profit'] > 10]
            mean_revert_wins_b = [t for t in m5s_b if t['profit'] > 10]
            print(f"\n  Big wins (> $10): A={len(mean_revert_wins_a)} vs B={len(mean_revert_wins_b)}")
            if mean_revert_wins_a:
                print(f"    A avg: ${sum(t['profit'] for t in mean_revert_wins_a)/len(mean_revert_wins_a):.2f}, "
                      f"avg hold: {sum(t['hold_min'] for t in mean_revert_wins_a)/len(mean_revert_wins_a):.0f}min")
            if mean_revert_wins_b:
                print(f"    B avg: ${sum(t['profit'] for t in mean_revert_wins_b)/len(mean_revert_wins_b):.2f}, "
                      f"avg hold: {sum(t['hold_min'] for t in mean_revert_wins_b)/len(mean_revert_wins_b):.0f}min")

        # ═══════════════════════════════════════════════════════════════
        # TICK SCALPER ANALYSIS
        # ═══════════════════════════════════════════════════════════════
        print("\n\n" + "#" * 80)
        print("#  TICK SCALPER: Period A (last 22h)")
        print("#" * 80)

        tick_a = get_trades(MAGIC_TICK, period_a_start, period_a_end)
        print_period_analysis("TICK SCALPER -- Period A (last 22h)", tick_a, tick_reasons, market_a)

        # Tick bot specific: analyze the damage pattern
        if tick_a:
            print(f"\n  TICK BOT DAMAGE ANALYSIS:")
            sl_trades = [t for t in tick_a if t['profit'] < -5]
            small_wins = [t for t in tick_a if 0 < t['profit'] < 2]
            good_wins = [t for t in tick_a if t['profit'] >= 5]

            print(f"    SL hits (> -$5 loss): {len(sl_trades)}, total ${sum(t['profit'] for t in sl_trades):.2f}")
            print(f"    Tiny wins (< $2): {len(small_wins)}, total ${sum(t['profit'] for t in small_wins):.2f}")
            print(f"    Good wins (>= $5): {len(good_wins)}, total ${sum(t['profit'] for t in good_wins):.2f}")

            # Time analysis: when did the SL hits happen?
            if sl_trades:
                print(f"\n    SL hit timing:")
                for t in sl_trades:
                    print(f"      {t['exit_time'].strftime('%H:%M')} {t['type']:<5} ${t['profit']:+.2f} "
                          f"(held {t['hold_min']:.0f}min, entry ${t['entry_price']:.2f})")

            # Hold time comparison
            if small_wins and good_wins:
                print(f"\n    Hold time: tiny wins avg {sum(t['hold_min'] for t in small_wins)/len(small_wins):.1f}min "
                      f"vs good wins avg {sum(t['hold_min'] for t in good_wins)/len(good_wins):.1f}min")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
