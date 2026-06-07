"""
Monte Carlo backtest -- tests strategy across many random time windows.

Usage:
    python -m tests.run_monte_carlo --bot m5 --runs 200 --days 365
    python -m tests.run_monte_carlo --bot m1 --runs 100 --window-min 7 --window-max 30
    python -m tests.run_monte_carlo --bot m5 --config experimental.json --runs 500
"""

import argparse
import logging
import random
import sys
from datetime import datetime, timedelta

import numpy as np

from src.core.config import TradingConfig, load_config
from src.strategy.m1_scalping import M1ScalpingStrategy
from src.strategy.m5_scalping import M5ScalpingStrategy

from tests.data_cache import (
    fetch_and_cache,
    generate_tick_prices,
    slice_window,
)
from tests.simulator_v2 import SimulatorV2 as Simulator, BacktestResult

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_single(
    strategy_cls,
    config: TradingConfig,
    candle_df,
    tick_df,
    start: datetime,
    end: datetime,
    balance: float,
    use_ticks: bool,
) -> BacktestResult | None:
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
        strategy=strategy,
        config=config,
        candle_df=window,
        tick_df=tick_window,
        starting_balance=balance,
    )
    return sim.run()


def print_monte_carlo_report(results: list[BacktestResult], label: str):
    """Print aggregate Monte Carlo statistics."""
    returns = [r.total_return_pct for r in results]
    drawdowns = [r.max_drawdown_pct for r in results]
    win_rates = [r.win_rate for r in results]
    trade_counts = [len(r.trades) for r in results]
    sharpes = [r.sharpe_ratio for r in results]
    paused_count = sum(1 for r in results if r.paused)

    print()
    print("=" * 80)
    print(f"MONTE CARLO RESULTS: {label}")
    print(f"Completed runs: {len(results)}")
    print("=" * 80)

    print(f"\nRETURNS:")
    print(f"  Mean:       {np.mean(returns):>+8.2f}%")
    print(f"  Median:     {np.median(returns):>+8.2f}%")
    print(f"  Std Dev:    {np.std(returns):>8.2f}%")
    print(f"  Best:       {np.max(returns):>+8.2f}%")
    print(f"  Worst:      {np.min(returns):>+8.2f}%")
    print(f"  25th pctl:  {np.percentile(returns, 25):>+8.2f}%")
    print(f"  75th pctl:  {np.percentile(returns, 75):>+8.2f}%")
    profitable = sum(1 for r in returns if r > 0)
    print(f"  Profitable: {profitable}/{len(returns)} ({profitable/len(returns)*100:.1f}%)")

    print(f"\nDRAWDOWN:")
    print(f"  Mean:       {np.mean(drawdowns):>8.2f}%")
    print(f"  Median:     {np.median(drawdowns):>8.2f}%")
    print(f"  Worst:      {np.max(drawdowns):>8.2f}%")
    print(f"  95th pctl:  {np.percentile(drawdowns, 95):>8.2f}%")

    print(f"\nWIN RATE:")
    print(f"  Mean:       {np.mean(win_rates):>8.1f}%")
    print(f"  Range:      {np.min(win_rates):.1f}% - {np.max(win_rates):.1f}%")

    print(f"\nSHARPE RATIO:")
    print(f"  Mean:       {np.mean(sharpes):>8.2f}")
    print(f"  Median:     {np.median(sharpes):>8.2f}")

    print(f"\nTRADES PER WINDOW:")
    print(f"  Mean:       {np.mean(trade_counts):>8.1f}")
    print(f"  Range:      {np.min(trade_counts)} - {np.max(trade_counts)}")

    if paused_count:
        print(f"\nRISK PAUSES:  {paused_count}/{len(results)} ({paused_count/len(results)*100:.1f}%)")

    # Worst 5
    worst = sorted(results, key=lambda r: r.total_return_pct)[:5]
    print(f"\nWORST 5 WINDOWS:")
    for r in worst:
        ec = r.equity_curve
        if ec:
            start_t = ec[0]["time"].strftime("%Y-%m-%d")
            end_t = ec[-1]["time"].strftime("%Y-%m-%d")
        else:
            start_t = end_t = "?"
        print(
            f"  {start_t} to {end_t}: "
            f"{r.total_return_pct:>+7.2f}%, "
            f"DD {r.max_drawdown_pct:.1f}%, "
            f"{len(r.trades)} trades, "
            f"WR {r.win_rate:.0f}%"
        )

    # Best 5
    best = sorted(results, key=lambda r: r.total_return_pct, reverse=True)[:5]
    print(f"\nBEST 5 WINDOWS:")
    for r in best:
        ec = r.equity_curve
        if ec:
            start_t = ec[0]["time"].strftime("%Y-%m-%d")
            end_t = ec[-1]["time"].strftime("%Y-%m-%d")
        else:
            start_t = end_t = "?"
        print(
            f"  {start_t} to {end_t}: "
            f"{r.total_return_pct:>+7.2f}%, "
            f"DD {r.max_drawdown_pct:.1f}%, "
            f"{len(r.trades)} trades, "
            f"WR {r.win_rate:.0f}%"
        )

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Egon Monte Carlo Backtester")
    parser.add_argument(
        "--bot", choices=["m1", "m5"], required=True, help="Bot to test"
    )
    parser.add_argument("--config", default=None, help="Config file")
    parser.add_argument("--runs", type=int, default=200, help="Number of random windows")
    parser.add_argument("--days", type=int, default=365, help="Total data to fetch")
    parser.add_argument(
        "--window-min", type=int, default=7, help="Min window size in days"
    )
    parser.add_argument(
        "--window-max", type=int, default=30, help="Max window size in days"
    )
    parser.add_argument(
        "--balance", type=float, default=10000.0, help="Starting balance"
    )
    parser.add_argument("--force-fetch", action="store_true", help="Force re-fetch")
    parser.add_argument("--no-ticks", action="store_true", help="Skip tick simulation")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    # Config
    config_path = args.config or f"config/{args.bot}_params.json"
    config = load_config(config_path)

    # Strategy class
    strategy_cls = M1ScalpingStrategy if args.bot == "m1" else M5ScalpingStrategy

    # Fetch full dataset
    print(f"Fetching {args.days} days of data...")
    data = fetch_and_cache(days=args.days, force=args.force_fetch)

    tf_key = "m1" if args.bot == "m1" else "m5"
    candle_df = data[tf_key]

    tick_df = None
    if not args.no_ticks:
        print("Generating tick prices...")
        tick_df = generate_tick_prices(data["m1"])

    # Determine available date range
    data_start = candle_df["time"].min()
    data_end = candle_df["time"].max()
    total_days = (data_end - data_start).days

    print(
        f"Data range: {data_start.date()} to {data_end.date()} ({total_days} days)"
    )
    print(
        f"Running {args.runs} random windows "
        f"({args.window_min}-{args.window_max} days each)..."
    )
    print()

    results = []
    failed = 0

    for run_num in range(1, args.runs + 1):
        window_days = random.randint(args.window_min, args.window_max)
        max_start_offset = total_days - window_days
        if max_start_offset <= 0:
            continue

        start_offset = random.randint(0, max_start_offset)
        window_start = data_start + timedelta(days=start_offset)
        window_end = window_start + timedelta(days=window_days)

        result = run_single(
            strategy_cls=strategy_cls,
            config=config,
            candle_df=candle_df,
            tick_df=tick_df,
            start=window_start.to_pydatetime() if hasattr(window_start, 'to_pydatetime') else window_start,
            end=window_end.to_pydatetime() if hasattr(window_end, 'to_pydatetime') else window_end,
            balance=args.balance,
            use_ticks=not args.no_ticks,
        )

        if result and result.trades:
            results.append(result)
        else:
            failed += 1

        if run_num % 50 == 0:
            print(f"  Completed {run_num}/{args.runs} runs...")

    if not results:
        print("No valid results. Check data availability.")
        return

    if failed:
        print(f"  ({failed} windows skipped due to insufficient data)")

    print_monte_carlo_report(results, f"{args.bot.upper()} ({config.strategy})")


if __name__ == "__main__":
    main()
