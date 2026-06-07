"""
A/B/C comparison test -- run three configs side by side on identical windows.

Usage:
    python -m tests.run_abc_comparison --bot m1 --runs 100 --no-ticks
"""

import argparse
import logging
import random
from datetime import timedelta

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


def apply_overrides(config: TradingConfig, overrides: dict) -> TradingConfig:
    """Apply dict overrides to a config."""
    for key, value in overrides.items():
        if hasattr(config, key):
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


def print_report(all_results: dict[str, list[BacktestResult]], labels: dict[str, str]):
    """Print comparison report for N configs."""
    names = list(all_results.keys())

    print()
    print("=" * 90)
    print("PROFIT PROTECTION SCALING COMPARISON")
    print("=" * 90)

    for name in names:
        results = all_results[name]
        print(f"\n  {name}: {labels[name]}")
        print(f"    Valid runs: {len(results)}")

    # Build stats
    stats = {}
    for name in names:
        results = all_results[name]
        ret = [r.total_return_pct for r in results]
        dd = [r.max_drawdown_pct for r in results]
        wr = [r.win_rate for r in results]
        trades = [len(r.trades) for r in results]
        sharpe = [r.sharpe_ratio for r in results]
        paused = sum(1 for r in results if r.paused)

        # Profit protection exit stats
        pp_exits = []
        rsi_exits = []
        other_exits = []
        for r in results:
            for t in r.trades:
                if "profit protection" in t.exit_reason.lower():
                    pp_exits.append(t.profit)
                elif "rsi" in t.exit_reason.lower():
                    rsi_exits.append(t.profit)
                else:
                    other_exits.append(t.profit)

        stats[name] = {
            "mean_return": np.mean(ret),
            "median_return": np.median(ret),
            "std_return": np.std(ret),
            "mean_dd": np.mean(dd),
            "mean_wr": np.mean(wr),
            "mean_sharpe": np.mean(sharpe),
            "mean_trades": np.mean(trades),
            "profitable_pct": sum(1 for r in ret if r > 0) / len(ret) * 100,
            "paused": paused,
            "pp_count": len(pp_exits),
            "pp_avg": np.mean(pp_exits) if pp_exits else 0,
            "rsi_count": len(rsi_exits),
            "rsi_avg": np.mean(rsi_exits) if rsi_exits else 0,
        }

    # Table
    header = f"{'Metric':<30}"
    for name in names:
        header += f" {name:>15}"
    print(f"\n{header}")
    print("-" * (30 + 16 * len(names)))

    def row(label, key, fmt=".2f", suffix="%"):
        line = f"{label:<30}"
        for name in names:
            val = stats[name][key]
            line += f" {val:>14{fmt}}{suffix}"
        print(line)

    row("Mean return", "mean_return")
    row("Median return", "median_return")
    row("Std dev", "std_return")
    row("Mean drawdown", "mean_dd")
    row("Mean win rate", "mean_wr")
    row("Mean Sharpe", "mean_sharpe", suffix="")
    row("Profitable windows", "profitable_pct")
    row("Mean trades/window", "mean_trades", ".1f", suffix="")
    row("Risk pauses", "paused", ".0f", suffix="")

    # Exit reason breakdown
    print(f"\n{'EXIT BREAKDOWN':<30}")
    print("-" * (30 + 16 * len(names)))

    def row2(label, key, fmt=".0f", suffix=""):
        line = f"{label:<30}"
        for name in names:
            val = stats[name][key]
            line += f" {val:>14{fmt}}{suffix}"
        print(line)

    row2("Profit protection exits", "pp_count")
    row2("Avg PP exit profit", "pp_avg", ".2f", "$")
    row2("RSI exits", "rsi_count")
    row2("Avg RSI exit profit", "rsi_avg", ".2f", "$")

    # Head-to-head
    print(f"\nHEAD-TO-HEAD (by return per window):")
    for i, n1 in enumerate(names):
        for n2 in names[i + 1:]:
            r1 = all_results[n1]
            r2 = all_results[n2]
            wins_1 = sum(
                1 for a, b in zip(r1, r2)
                if a.total_return_pct > b.total_return_pct
            )
            wins_2 = sum(
                1 for a, b in zip(r1, r2)
                if b.total_return_pct > a.total_return_pct
            )
            ties = len(r1) - wins_1 - wins_2
            total = len(r1)
            print(
                f"  {n1} vs {n2}: "
                f"{n1} wins {wins_1} ({wins_1/total*100:.0f}%), "
                f"{n2} wins {wins_2} ({wins_2/total*100:.0f}%), "
                f"ties {ties}"
            )

    # Verdict
    print()
    best = max(names, key=lambda n: stats[n]["mean_return"])
    best_ret = stats[best]["mean_return"]
    print(f"BEST MEAN RETURN: {best} ({best_ret:+.2f}%)")

    best_sharpe = max(names, key=lambda n: stats[n]["mean_sharpe"])
    print(f"BEST SHARPE:      {best_sharpe} ({stats[best_sharpe]['mean_sharpe']:.2f})")

    best_pp_avg = max(names, key=lambda n: stats[n]["pp_avg"])
    print(f"BEST PP AVG:      {best_pp_avg} (${stats[best_pp_avg]['pp_avg']:.2f})")

    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Egon A/B/C Profit Protection Comparison")
    parser.add_argument("--bot", choices=["m1", "m5"], default="m1")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--window-min", type=int, default=7)
    parser.add_argument("--window-max", type=int, default=14)
    parser.add_argument("--balance", type=float, default=10000.0)
    parser.add_argument("--force-fetch", action="store_true")
    parser.add_argument("--no-ticks", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    config_path = f"config/{args.bot}_params.json"
    base_config = load_config(config_path)
    strategy_cls = M1ScalpingStrategy if args.bot == "m1" else M5ScalpingStrategy

    # === Define the three configs ===

    # A: Current (flat drawdown limit)
    config_a = load_config(config_path)
    label_a = (
        f"Flat {config_a.profit_protection_drawdown_limit_pct*100:.0f}% drawdown "
        f"at {config_a.profit_protection_threshold_pct*100:.0f}% threshold"
    )

    # B: User's tiered proposal
    config_b = load_config(config_path)
    config_b.profit_protection_scaling = "tiered"
    config_b.profit_protection_tiers = [
        [1.0, 0.25],   # 1x threshold -> 25% drawdown
        [1.5, 0.50],   # 1.5x threshold -> 50% drawdown
        [2.0, 0.75],   # 2x threshold -> 75% drawdown
    ]
    label_b = "Tiered: 25% at 1x, 50% at 1.5x, 75% at 2x threshold"

    # C: Kiro's continuous scaling proposal
    config_c = load_config(config_path)
    config_c.profit_protection_scaling = "continuous"
    config_c.profit_protection_continuous_base = 0.20
    config_c.profit_protection_continuous_rate = 0.15
    config_c.profit_protection_continuous_max = 0.75
    label_c = "Continuous: 20% base, +15% per threshold multiple, max 75%"

    configs = {
        "A-Current": (config_a, label_a),
        "B-Tiered": (config_b, label_b),
        "C-Continuous": (config_c, label_c),
    }

    # === Fetch data ===
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

    print(f"Data: {data_start.date()} to {data_end.date()} ({total_days} days)")

    # Generate windows
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
            ws.to_pydatetime() if hasattr(ws, "to_pydatetime") else ws,
            we.to_pydatetime() if hasattr(we, "to_pydatetime") else we,
        ))

    print(f"Running {len(windows)} windows x {len(configs)} configs...")
    print()

    # === Run all configs on same windows ===
    all_results = {name: [] for name in configs}
    skipped = 0

    for i, (ws, we) in enumerate(windows, 1):
        run_results = {}
        valid = True

        for name, (cfg, _) in configs.items():
            result = run_window(
                strategy_cls, cfg, candle_df, tick_df,
                ws, we, args.balance, not args.no_ticks,
            )
            if result and result.trades:
                run_results[name] = result
            else:
                valid = False
                break

        if valid and len(run_results) == len(configs):
            for name, result in run_results.items():
                all_results[name].append(result)
        else:
            skipped += 1

        if i % 25 == 0:
            print(f"  Completed {i}/{len(windows)}...")

    if skipped:
        print(f"  ({skipped} windows skipped)")

    if not all(all_results.values()):
        print("No valid results.")
        return

    labels = {name: label for name, (_, label) in configs.items()}
    print_report(all_results, labels)


if __name__ == "__main__":
    main()
