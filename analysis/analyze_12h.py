"""
Analyze the last 12 hours: backtest replay + trade-by-trade breakdown.

Runs the real bot logic on the last 12h of M1 data, then analyzes:
- Win/loss streaks and their cost
- Stop loss vs RSI exit performance
- Entry timing quality (how far price moved in our favor before exit)
- Missed profit (peak unrealized vs actual exit)
- Consecutive loss patterns and backoff impact
- Directional bias (LONG vs SHORT performance)
- Volatility regime analysis (high ATR vs low ATR trades)

Usage:
    python -m analysis.analyze_12h
"""

import sys
sys.path.append(".")

import copy
import logging
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

from src.core.config import load_config
from src.core.indicators import compute_indicators
from src.strategy.m1_scalping import M1ScalpingStrategy
from tests.data_cache import fetch_and_cache, slice_window
from tests.simulator_v2 import SimulatorV2 as Simulator, BacktestResult, TradeRecord

logging.basicConfig(level=logging.ERROR)

BALANCE = 10000.0
HOURS = 12


def run_backtest(config, candle_df, balance, start, end) -> BacktestResult | None:
    window = slice_window(candle_df, start, end)
    if len(window) < 250:
        print(f"  Only {len(window)} candles in window (need 250+)")
        return None
    strategy = M1ScalpingStrategy(config)
    sim = Simulator(strategy, config, window, None, balance)
    return sim.run()


def analyze_trades(result: BacktestResult, candle_df: pd.DataFrame):
    """Deep analysis of all trades in the result."""
    trades = result.trades
    if not trades:
        print("No trades to analyze.")
        return

    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit < 0]
    sl_trades = [t for t in trades if "stop loss" in t.exit_reason.lower()]
    rsi_trades = [t for t in trades if "rsi" in t.exit_reason.lower()]
    pp_trades = [t for t in trades if "profit protection" in t.exit_reason.lower()]
    tp_trades = [t for t in trades if "take profit" in t.exit_reason.lower()]

    total_pnl = sum(t.profit for t in trades)
    avg_win = np.mean([t.profit for t in wins]) if wins else 0
    avg_loss = np.mean([t.profit for t in losses]) if losses else 0
    win_rate = len(wins) / len(trades) * 100

    # ── Overview ────────────────────────────────────────────────────────
    print()
    print("=" * 90)
    print(f"  LAST {HOURS}H TRADE ANALYSIS  ({len(trades)} trades)")
    print("=" * 90)

    print(f"\n  P/L: ${total_pnl:+.2f}  |  Win rate: {win_rate:.1f}%  |  "
          f"Avg win: ${avg_win:.2f}  |  Avg loss: ${avg_loss:.2f}")
    print(f"  Return: {result.total_return_pct:+.2f}%  |  Max DD: {result.max_drawdown_pct:.2f}%  |  "
          f"Sharpe: {result.sharpe_ratio:.2f}  |  PF: {result.profit_factor:.2f}")

    # ── Exit reason breakdown ───────────────────────────────────────────
    print(f"\n{'EXIT REASON':<25} {'Count':>6} {'Win%':>7} {'Avg P/L':>10} {'Total P/L':>11} {'Avg Dur':>9}")
    print("-" * 70)

    for label, group in [("Stop loss", sl_trades), ("RSI exit", rsi_trades),
                          ("Profit protection", pp_trades), ("Take profit", tp_trades)]:
        if not group:
            continue
        g_wins = sum(1 for t in group if t.profit > 0)
        g_wr = g_wins / len(group) * 100 if group else 0
        g_avg = np.mean([t.profit for t in group])
        g_total = sum(t.profit for t in group)
        g_dur = np.mean([t.duration_minutes for t in group])
        print(f"  {label:<23} {len(group):>6} {g_wr:>6.1f}% ${g_avg:>8.2f} ${g_total:>9.2f} {g_dur:>7.1f}m")

    # ── Direction breakdown ─────────────────────────────────────────────
    print(f"\n{'DIRECTION':<25} {'Count':>6} {'Win%':>7} {'Avg P/L':>10} {'Total P/L':>11} {'SL Rate':>9}")
    print("-" * 70)

    for direction in ["LONG", "SHORT"]:
        d_trades = [t for t in trades if t.direction == direction]
        if not d_trades:
            continue
        d_wins = sum(1 for t in d_trades if t.profit > 0)
        d_wr = d_wins / len(d_trades) * 100
        d_avg = np.mean([t.profit for t in d_trades])
        d_total = sum(t.profit for t in d_trades)
        d_sl = sum(1 for t in d_trades if "stop loss" in t.exit_reason.lower())
        d_sl_rate = d_sl / len(d_trades) * 100
        print(f"  {direction:<23} {len(d_trades):>6} {d_wr:>6.1f}% ${d_avg:>8.2f} ${d_total:>9.2f} {d_sl_rate:>7.1f}%")

    # ── Missed profit analysis ──────────────────────────────────────────
    print(f"\nMISSED PROFIT ANALYSIS (peak unrealized vs actual exit)")
    print("-" * 70)

    missed_profits = []
    for t in trades:
        if t.peak_profit > 0:
            missed = t.peak_profit - t.profit
            missed_profits.append((t, missed))

    if missed_profits:
        missed_profits.sort(key=lambda x: x[1], reverse=True)
        total_missed = sum(m for _, m in missed_profits if m > 0)
        avg_missed = np.mean([m for _, m in missed_profits if m > 0]) if any(m > 0 for _, m in missed_profits) else 0

        print(f"  Total missed profit: ${total_missed:.2f}")
        print(f"  Avg missed per trade (when peak > exit): ${avg_missed:.2f}")
        print(f"  Trades that went green then red: {sum(1 for t, m in missed_profits if t.profit < 0 and t.peak_profit > 0)}")

        # Top 5 biggest missed profits
        print(f"\n  Top 5 biggest missed profits:")
        for i, (t, missed) in enumerate(missed_profits[:5], 1):
            print(f"    {i}. {t.entry_time.strftime('%H:%M')} {t.direction} "
                  f"peak=${t.peak_profit:.2f} exit=${t.profit:.2f} "
                  f"missed=${missed:.2f} ({t.exit_reason})")

    # ── Green-to-red trades ─────────────────────────────────────────────
    green_to_red = [t for t in trades if t.peak_profit > 0 and t.profit < 0]
    if green_to_red:
        print(f"\nGREEN-TO-RED TRADES ({len(green_to_red)} trades went profitable then lost)")
        print("-" * 70)
        g2r_total_loss = sum(t.profit for t in green_to_red)
        g2r_total_peak = sum(t.peak_profit for t in green_to_red)
        print(f"  Total loss from green-to-red: ${g2r_total_loss:.2f}")
        print(f"  Total peak profit that was lost: ${g2r_total_peak:.2f}")
        print(f"  If PP caught all at peak: would have saved ${abs(g2r_total_loss) + g2r_total_peak:.2f}")

        for t in green_to_red[:10]:
            print(f"    {t.entry_time.strftime('%H:%M')} {t.direction} "
                  f"peak=${t.peak_profit:.2f} -> exit=${t.profit:.2f} "
                  f"held {t.duration_minutes:.0f}m ({t.exit_reason})")


    # ── Streak analysis ─────────────────────────────────────────────────
    print(f"\nSTREAK ANALYSIS")
    print("-" * 70)

    streaks = []
    current_streak = 0
    current_type = None
    streak_pnl = 0

    for t in trades:
        is_win = t.profit > 0
        if current_type is None:
            current_type = is_win
            current_streak = 1
            streak_pnl = t.profit
        elif is_win == current_type:
            current_streak += 1
            streak_pnl += t.profit
        else:
            streaks.append((current_type, current_streak, streak_pnl))
            current_type = is_win
            current_streak = 1
            streak_pnl = t.profit
    if current_streak > 0:
        streaks.append((current_type, current_streak, streak_pnl))

    win_streaks = [(s, pnl) for is_win, s, pnl in streaks if is_win]
    loss_streaks = [(s, pnl) for is_win, s, pnl in streaks if not is_win]

    if win_streaks:
        max_ws = max(win_streaks, key=lambda x: x[0])
        avg_ws = np.mean([s for s, _ in win_streaks])
        print(f"  Win streaks:  max={max_ws[0]} (${max_ws[1]:.2f}), avg={avg_ws:.1f}, count={len(win_streaks)}")

    if loss_streaks:
        max_ls = max(loss_streaks, key=lambda x: x[0])
        avg_ls = np.mean([s for s, _ in loss_streaks])
        total_loss_streak_cost = sum(pnl for _, pnl in loss_streaks)
        print(f"  Loss streaks: max={max_ls[0]} (${max_ls[1]:.2f}), avg={avg_ls:.1f}, count={len(loss_streaks)}")
        print(f"  Total cost of all loss streaks: ${total_loss_streak_cost:.2f}")

        # Show the worst loss streaks
        worst_streaks = sorted(loss_streaks, key=lambda x: x[1])[:3]
        for i, (length, pnl) in enumerate(worst_streaks, 1):
            print(f"    Worst #{i}: {length} consecutive losses, ${pnl:.2f}")

    # ── Hourly performance ──────────────────────────────────────────────
    print(f"\nHOURLY PERFORMANCE")
    print("-" * 70)

    hourly = defaultdict(lambda: {"trades": 0, "pnl": 0, "wins": 0, "sl": 0})
    for t in trades:
        h = t.entry_time.hour
        hourly[h]["trades"] += 1
        hourly[h]["pnl"] += t.profit
        if t.profit > 0:
            hourly[h]["wins"] += 1
        if "stop loss" in t.exit_reason.lower():
            hourly[h]["sl"] += 1

    print(f"  {'Hour':<6} {'Trades':>7} {'Win%':>7} {'P/L':>10} {'Avg P/L':>10} {'SL%':>7}")
    for h in sorted(hourly.keys()):
        d = hourly[h]
        wr = d["wins"] / d["trades"] * 100 if d["trades"] else 0
        avg = d["pnl"] / d["trades"] if d["trades"] else 0
        sl_pct = d["sl"] / d["trades"] * 100 if d["trades"] else 0
        flag = " <<<" if d["pnl"] < -50 else (" ***" if d["pnl"] > 50 else "")
        print(f"  {h:02d}:00 {d['trades']:>7} {wr:>6.1f}% ${d['pnl']:>8.2f} ${avg:>8.2f} {sl_pct:>6.1f}%{flag}")

    # ── Stop loss distance analysis ─────────────────────────────────────
    print(f"\nSTOP LOSS ANALYSIS")
    print("-" * 70)

    if sl_trades:
        sl_losses = [abs(t.profit) for t in sl_trades]
        sl_durations = [t.duration_minutes for t in sl_trades]
        print(f"  SL trades: {len(sl_trades)} ({len(sl_trades)/len(trades)*100:.1f}% of all trades)")
        print(f"  Avg SL loss: ${np.mean(sl_losses):.2f}")
        print(f"  Median SL loss: ${np.median(sl_losses):.2f}")
        print(f"  Max SL loss: ${max(sl_losses):.2f}")
        print(f"  Avg time to SL: {np.mean(sl_durations):.1f}min")
        print(f"  Total SL cost: ${sum(t.profit for t in sl_trades):.2f}")

        # SL trades that were profitable at some point
        sl_was_green = [t for t in sl_trades if t.peak_profit > 0]
        if sl_was_green:
            print(f"\n  SL trades that were green first: {len(sl_was_green)}")
            print(f"  Avg peak before SL: ${np.mean([t.peak_profit for t in sl_was_green]):.2f}")
            print(f"  These could have been saved by tighter profit protection")

        # Quick SL (< 3 min)
        quick_sl = [t for t in sl_trades if t.duration_minutes < 3]
        if quick_sl:
            print(f"\n  Quick SL (<3min): {len(quick_sl)} trades, ${sum(t.profit for t in quick_sl):.2f}")
            print(f"  These suggest bad entry timing or too-tight stops")

    # ── Trade duration analysis ─────────────────────────────────────────
    print(f"\nTRADE DURATION ANALYSIS")
    print("-" * 70)

    durations = [t.duration_minutes for t in trades]
    win_durations = [t.duration_minutes for t in wins]
    loss_durations = [t.duration_minutes for t in losses]

    print(f"  Overall: avg={np.mean(durations):.1f}m, median={np.median(durations):.1f}m")
    if win_durations:
        print(f"  Winners: avg={np.mean(win_durations):.1f}m, median={np.median(win_durations):.1f}m")
    if loss_durations:
        print(f"  Losers:  avg={np.mean(loss_durations):.1f}m, median={np.median(loss_durations):.1f}m")

    # Long-held losers
    long_losers = [t for t in losses if t.duration_minutes > 20]
    if long_losers:
        print(f"\n  Long-held losers (>20min): {len(long_losers)}, total ${sum(t.profit for t in long_losers):.2f}")
        for t in sorted(long_losers, key=lambda x: x.profit)[:5]:
            print(f"    {t.entry_time.strftime('%H:%M')} {t.direction} held {t.duration_minutes:.0f}m "
                  f"P/L=${t.profit:.2f} peak=${t.peak_profit:.2f} ({t.exit_reason})")


def suggest_improvements(result: BacktestResult, config):
    """Generate specific improvement suggestions based on the analysis."""
    trades = result.trades
    if not trades:
        return

    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit < 0]
    sl_trades = [t for t in trades if "stop loss" in t.exit_reason.lower()]
    rsi_trades = [t for t in trades if "rsi" in t.exit_reason.lower()]
    pp_trades = [t for t in trades if "profit protection" in t.exit_reason.lower()]

    total_pnl = sum(t.profit for t in trades)
    win_rate = len(wins) / len(trades) * 100
    sl_rate = len(sl_trades) / len(trades) * 100
    avg_win = np.mean([t.profit for t in wins]) if wins else 0
    avg_loss = np.mean([t.profit for t in losses]) if losses else 0
    rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    green_to_red = [t for t in trades if t.peak_profit > 0 and t.profit < 0]
    quick_sl = [t for t in sl_trades if t.duration_minutes < 3]

    print()
    print("=" * 90)
    print("  IMPROVEMENT SUGGESTIONS")
    print("=" * 90)

    suggestions = []

    # 1. Risk/reward
    if rr < 1.0:
        suggestions.append(
            f"RISK/REWARD is {rr:.2f}:1 (avg win ${avg_win:.2f} vs avg loss ${avg_loss:.2f}).\n"
            f"    Wins are smaller than losses. Options:\n"
            f"    - Widen profit target (current: {config.profit_target_pct*100:.1f}%)\n"
            f"    - Tighten RSI exit thresholds to let winners run longer\n"
            f"    - Lower ATR multiplier to tighten stops (current: {config.atr_multiplier}x)"
        )

    # 2. Stop loss rate
    if sl_rate > 35:
        sl_cost = sum(t.profit for t in sl_trades)
        suggestions.append(
            f"HIGH STOP LOSS RATE: {sl_rate:.1f}% of trades hit SL (${sl_cost:.2f} total).\n"
            f"    Current ATR multiplier: {config.atr_multiplier}x (high vol: {config.atr_high_volatility_multiplier}x)\n"
            f"    Options:\n"
            f"    - Increase ATR multiplier to give trades more room\n"
            f"    - Add volatility filter to skip entries in choppy conditions\n"
            f"    - Tighten RSI entry bands (current: buy<{config.rsi_buy}, sell>{config.rsi_sell})"
        )

    # 3. Quick stop losses
    if quick_sl and len(quick_sl) > 3:
        qs_cost = sum(t.profit for t in quick_sl)
        suggestions.append(
            f"QUICK STOP LOSSES: {len(quick_sl)} trades hit SL within 3 minutes (${qs_cost:.2f}).\n"
            f"    This suggests entering against momentum or during high volatility.\n"
            f"    Options:\n"
            f"    - Add momentum confirmation before entry\n"
            f"    - Skip entries when ATR is above a threshold\n"
            f"    - Require entry_signal_confirmations > 0 (current: {config.entry_signal_confirmations})"
        )

    # 4. Green-to-red
    if green_to_red and len(green_to_red) > 5:
        g2r_loss = sum(t.profit for t in green_to_red)
        g2r_peak = sum(t.peak_profit for t in green_to_red)
        suggestions.append(
            f"GREEN-TO-RED: {len(green_to_red)} trades were profitable then turned to losses (${g2r_loss:.2f}).\n"
            f"    Peak profit that was lost: ${g2r_peak:.2f}\n"
            f"    Current PP threshold: {config.profit_protection_threshold_pct*100:.1f}% of invested\n"
            f"    Options:\n"
            f"    - Lower PP threshold to activate earlier\n"
            f"    - Tighten PP drawdown limit (current: {config.profit_protection_drawdown_limit_pct*100:.0f}%)\n"
            f"    - Enable PP always-on instead of auto-volatility"
        )

    # 5. Directional bias
    longs = [t for t in trades if t.direction == "LONG"]
    shorts = [t for t in trades if t.direction == "SHORT"]
    if longs and shorts:
        long_pnl = sum(t.profit for t in longs)
        short_pnl = sum(t.profit for t in shorts)
        long_wr = sum(1 for t in longs if t.profit > 0) / len(longs) * 100
        short_wr = sum(1 for t in shorts if t.profit > 0) / len(shorts) * 100

        if short_pnl < -50 and long_pnl > 0:
            suggestions.append(
                f"SHORTS UNDERPERFORMING: LONG ${long_pnl:+.2f} ({long_wr:.0f}% WR) vs SHORT ${short_pnl:+.2f} ({short_wr:.0f}% WR).\n"
                f"    Consider disabling shorts or tightening short entry conditions.\n"
                f"    Current short entry: RSI > {config.rsi_sell} AND downtrend"
            )
        elif long_pnl < -50 and short_pnl > 0:
            suggestions.append(
                f"LONGS UNDERPERFORMING: LONG ${long_pnl:+.2f} ({long_wr:.0f}% WR) vs SHORT ${short_pnl:+.2f} ({short_wr:.0f}% WR).\n"
                f"    Market may be in a downtrend. Consider:\n"
                f"    - Adding trend filter to skip longs in downtrend\n"
                f"    - Tightening long entry RSI (current: < {config.rsi_buy})"
            )

    # 6. Win rate
    if win_rate < 50:
        suggestions.append(
            f"LOW WIN RATE: {win_rate:.1f}%. More than half of trades are losers.\n"
            f"    Options:\n"
            f"    - Tighten entry conditions (lower RSI buy, higher RSI sell)\n"
            f"    - Add trend confirmation (only trade in trend direction)\n"
            f"    - Increase entry_signal_confirmations to filter noise"
        )

    # 7. Profit protection effectiveness
    if pp_trades:
        pp_wins = sum(1 for t in pp_trades if t.profit > 0)
        pp_avg = np.mean([t.profit for t in pp_trades])
        if pp_avg < 5:
            suggestions.append(
                f"PP EXITS TOO EARLY: Avg PP exit profit is only ${pp_avg:.2f}.\n"
                f"    PP is triggering but not capturing enough profit.\n"
                f"    Options:\n"
                f"    - Increase PP threshold (current: {config.profit_protection_threshold_pct*100:.1f}%)\n"
                f"    - Widen initial drawdown limit (current: {config.profit_protection_drawdown_limit_pct*100:.0f}%)"
            )

    # 8. Loss backoff impact
    if config.use_loss_backoff:
        # Check if there were periods where backoff would have helped
        consecutive = 0
        max_consecutive = 0
        for t in trades:
            if t.profit < 0:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        if max_consecutive >= 4:
            backoff_multipliers = config.loss_backoff_multipliers
            idx = min(max_consecutive - 1, len(backoff_multipliers) - 1)
            suggestions.append(
                f"LOSS STREAKS: Max {max_consecutive} consecutive losses detected.\n"
                f"    Backoff is ON with multipliers {backoff_multipliers}.\n"
                f"    At {max_consecutive} losses, cooldown is {backoff_multipliers[idx]}x normal.\n"
                f"    This is working as designed -- backoff prevents deeper damage."
            )

    # Print suggestions
    if suggestions:
        for i, s in enumerate(suggestions, 1):
            print(f"\n  {i}. {s}")
    else:
        print("\n  No major issues detected. Strategy is performing well for this period.")

    print()
    print("=" * 90)


def main():
    config = load_config("config/m1_params.json")

    print("Fetching data...")
    data = fetch_and_cache(days=105)
    candle_df = data["m1"]

    data_end = candle_df["time"].max()
    start_12h = data_end - timedelta(hours=HOURS)

    print(f"Analyzing: {start_12h} to {data_end} ({HOURS}h)")

    result = run_backtest(
        config, candle_df, BALANCE,
        start_12h.to_pydatetime() if hasattr(start_12h, "to_pydatetime") else start_12h,
        data_end.to_pydatetime() if hasattr(data_end, "to_pydatetime") else data_end,
    )

    if not result:
        print("Backtest returned no result.")
        return

    if not result.trades:
        print("No trades in the last 12 hours.")
        return

    analyze_trades(result, candle_df)
    suggest_improvements(result, config)


if __name__ == "__main__":
    main()
