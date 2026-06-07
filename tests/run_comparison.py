"""
Comparison test -- run two configs side by side on the same data windows.

Usage:
    python -m tests.run_comparison --bot m5 --config-a config/m5_params.json --config-b config/experimental/m5_wider_rsi.json
    python -m tests.run_comparison --bot m1 --config-a config/m1_params.json --config-b config/m1_params.json --override-b rsi_buy=30 rsi_sell=70
"""

import argparse
import logging
import random
from datetime import datetime, timedelta

import numpy as np

from src.core.config import TradingConfig, load_config
from src.strategy.m1_scalping import M1ScalpingStrategy
from src.strategy.m5_scalping import M5ScalpingStrategy

from tests.data_cache import fetch_and_cache, generate_tick_prices, slice_window
from tests.simulator_v2 import SimulatorV2 as Simulator, BacktestResult

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def apply_overrides(config: TradingConfig, overrides: list[str]) -> TradingConfig:
    """Apply key=value overrides to a config."""
    for override in overrides:
        key, value = override.split("=", 1)
        if not hasattr(config, key):
            print(f"Warning: unknown config key '{key}'")
            continue
        field_type = type(getattr(config, key))
        if field_type == bool:
            setattr(config, key, value.lower() in ("true", "1", "yes"))
        elif field_type == int:
            setattr(config, key, int(value))
        elif field_type == float:
            setattr(config, key, float(value))
        else:
            setattr(config, key, value)
    return config


def run_window(strategy_cls, config, candle_df, tick_df, start, end, balance, use_ticks):
    """Run a single backtest window."""
    window = slice_window(candle_df, start, end)
    if len(window) < 250:
        return None

    tick_window = None
    if use_ticks and tick_df is not None:
        mask = (tick_df["timestamp"] >= start) & (tick_df["timestamp"] < end)
        tick_window = tick_df.loc[mask].reset_index(drop=True)
        if len(tick_window) == 0:
            tick_window = None

    strategy = strategy_cls(config)
    sim = Simulator(
        strategy=strategy, config=config, candle_df=window,
        tick_df=tick_window, starting_balance=balance,
    )
    return sim.run()


def main():
    parser = argparse.ArgumentParser(description="Egon A/B Comparison")
    parser.add_argument("--bot", choices=["m1", "m5"], required=True)
    parser.add_argument("--config-a", required=True, help="Config A (baseline)")
    parser.add_argument("--config-b", required=True, help="Config B (experimental)")
    parser.add_argument("--override-a", nargs="*", default=[], help="Overrides for A")
    parser.add_argument("--override-b", nargs="*", default=[], help="Overrides for B")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--window-min", type=int, default=7)
    parser.add_argument("--window-max", type=int, default=30)
    parser.add_argument("--balance", type=float, default=10000.0)
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--no-ticks", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config_a = apply_overrides(load_config(args.config_a), args.override_a)
    config_b = apply_overrides(load_config(args.config_b), args.override_b)
    strategy_cls = M1ScalpingStrategy if args.bot == "m1" else M5ScalpingStrategy

    print(f"Fetching {args.days} days of data...")
    data = fetch_and_cache(days=args.days, force=args.force_fetch)

    tf_key = "m1" if args.bot == "m1" else "m5"
    candle_df = data[tf_key]

    tick_df = None
    if not args.no_ticks:
        print("Generating tick prices...")
        tick_df = generate_tick_prices(data["m1"])

    data_start = candle_df["time"].min()
    data_end = candle_df["time"].max()
    total_days = (data_end - data_start).days

    # Generate same windows for both
    random.seed(args.seed)
    windows = []
    for _ in range(args.runs):
        window_days = random.randint(args.window_min, args.window_max)
        max_offset = total_days - window_days
        if max_offset <= 0:
            continue
        offset = random.randint(0, max_offset)
        ws = data_start + timedelta(days=offset)
        we = ws + timedelta(days=window_days)
        windows.append((
            ws.to_pydatetime() if hasattr(ws, 'to_pydatetime') else ws,
            we.to_pydatetime() if hasattr(we, 'to_pydatetime') else we,
        ))

    print(f"Running {len(windows)} windows for A and B...")

    results_a, results_b = [], []
    a_wins, b_wins, ties = 0, 0, 0

    for i, (ws, we) in enumerate(windows, 1):
        ra = run_window(strategy_cls, config_a, candle_df, tick_df, ws, we, args.balance, not args.no_ticks)
        rb = run_window(strategy_cls, config_b, candle_df, tick_df, ws, we, args.balance, not args.no_ticks)

        if ra and rb and ra.trades and rb.trades:
            results_a.append(ra)
            results_b.append(rb)
            if ra.total_return_pct > rb.total_return_pct:
                a_wins += 1
            elif rb.total_return_pct > ra.total_return_pct:
                b_wins += 1
            else:
                ties += 1

        if i % 50 == 0:
            print(f"  Completed {i}/{len(windows)}...")

    if not results_a:
        print("No valid results.")
        return

    # Report
    ret_a = [r.total_return_pct for r in results_a]
    ret_b = [r.total_return_pct for r in results_b]
    dd_a = [r.max_drawdown_pct for r in results_a]
    dd_b = [r.max_drawdown_pct for r in results_b]
    wr_a = [r.win_rate for r in results_a]
    wr_b = [r.win_rate for r in results_b]

    print()
    print("=" * 80)
    print(f"A/B COMPARISON: {args.bot.upper()}")
    print(f"Windows: {len(results_a)} valid out of {len(windows)}")
    print("=" * 80)

    print(f"\n{'Metric':<25} {'Config A':>15} {'Config B':>15} {'Delta':>12}")
    print("-" * 70)

    def row(label, va, vb, fmt=".2f", suffix="%"):
        delta = vb - va
        sign = "+" if delta > 0 else ""
        print(f"{label:<25} {va:>14{fmt}}{suffix} {vb:>14{fmt}}{suffix} {sign}{delta:>10{fmt}}{suffix}")

    row("Mean return", np.mean(ret_a), np.mean(ret_b))
    row("Median return", np.median(ret_a), np.median(ret_b))
    row("Std dev", np.std(ret_a), np.std(ret_b))
    row("Mean drawdown", np.mean(dd_a), np.mean(dd_b))
    row("Mean win rate", np.mean(wr_a), np.mean(wr_b))
    row("Sharpe", np.mean([r.sharpe_ratio for r in results_a]),
        np.mean([r.sharpe_ratio for r in results_b]), suffix="")

    profitable_a = sum(1 for r in ret_a if r > 0) / len(ret_a) * 100
    profitable_b = sum(1 for r in ret_b if r > 0) / len(ret_b) * 100
    row("Profitable windows", profitable_a, profitable_b)

    print()
    total = a_wins + b_wins + ties
    print(f"HEAD-TO-HEAD: A wins {a_wins} ({a_wins/total*100:.0f}%), "
          f"B wins {b_wins} ({b_wins/total*100:.0f}%), "
          f"Ties {ties}")

    mean_diff = np.mean(ret_b) - np.mean(ret_a)
    if abs(mean_diff) < 1.0:
        verdict = "No significant difference"
    elif mean_diff > 0:
        verdict = f"Config B is better by {mean_diff:+.2f}%"
    else:
        verdict = f"Config A is better by {-mean_diff:+.2f}%"
    print(f"VERDICT: {verdict}")
    print("=" * 80)


if __name__ == "__main__":
    main()
