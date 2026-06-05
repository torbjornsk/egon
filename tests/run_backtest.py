"""
Simple backtest runner -- single strategy, single period, detailed report.

Usage:
    python -m tests.run_backtest --bot m5 --days 90
    python -m tests.run_backtest --bot m1 --days 30 --config config/m1_params.json
    python -m tests.run_backtest --bot m5 --start 2025-06-01 --end 2025-09-01
"""

import argparse
import logging
import sys
from datetime import datetime

from src.core.config import TradingConfig, load_config
from src.strategy.m1_scalping import M1ScalpingStrategy
from src.strategy.m5_scalping import M5ScalpingStrategy

from tests.data_cache import (
    fetch_and_cache,
    generate_tick_prices,
    precompute_indicators,
    slice_window,
)
from tests.simulator_v2 import SimulatorV2 as Simulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_report(result):
    """Print a detailed backtest report."""
    s = result.summary()
    trades = result.trades

    print()
    print("=" * 80)
    print(f"BACKTEST REPORT: {s['strategy']}")
    print("=" * 80)
    print(f"Period: {s['period_days']} days")
    print(f"Starting balance: ${s['starting_balance']:,.2f}")
    print(f"Final balance:    ${s['final_balance']:,.2f}")
    print(f"Return:           {s['return_pct']:+.2f}%")
    print(f"Max drawdown:     {s['max_drawdown_pct']:.2f}%")
    if s["paused"]:
        print(f"*** PAUSED: {result.pause_reason}")
    print()

    print(f"Trades:           {s['trades']}")
    print(f"Win rate:         {s['win_rate']:.1f}%")
    print(f"Avg win:          ${s['avg_win']:.2f}")
    print(f"Avg loss:         ${s['avg_loss']:.2f}")
    print(f"Profit factor:    {s['profit_factor']:.2f}")
    print(f"Sharpe ratio:     {s['sharpe']:.2f}")
    print(f"Avg duration:     {s['avg_duration_min']:.1f} min")
    print()

    # Exit reason breakdown
    if trades:
        reasons = {}
        for t in trades:
            r = t.exit_reason.split("(")[0].strip()
            if r not in reasons:
                reasons[r] = {"count": 0, "profit": 0.0}
            reasons[r]["count"] += 1
            reasons[r]["profit"] += t.profit

        print("EXIT REASONS:")
        for reason, data in sorted(reasons.items(), key=lambda x: -x[1]["count"]):
            pct = data["count"] / len(trades) * 100
            print(
                f"  {reason:<40} {data['count']:>4} ({pct:>5.1f}%)  "
                f"P/L: ${data['profit']:>+10.2f}"
            )
        print()

    # Last 20 trades
    if trades:
        print("LAST 20 TRADES:")
        print(
            f"{'Time':<18} {'Dir':<6} {'Entry':>9} {'Exit':>9} "
            f"{'P/L':>10} {'Dur':>6} {'Reason'}"
        )
        print("-" * 80)
        for t in trades[-20:]:
            print(
                f"{t.entry_time.strftime('%m-%d %H:%M'):<18} "
                f"{t.direction:<6} "
                f"${t.entry_price:>8.2f} ${t.exit_price:>8.2f} "
                f"${t.profit:>+9.2f} "
                f"{t.duration_minutes:>5.0f}m "
                f"{t.exit_reason}"
            )
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Egon Backtester")
    parser.add_argument(
        "--bot", choices=["m1", "m5"], required=True, help="Bot to test"
    )
    parser.add_argument(
        "--config", default=None, help="Config file (default: config/<bot>_params.json)"
    )
    parser.add_argument("--days", type=int, default=90, help="Days of data (default: 90)")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--balance", type=float, default=10000.0, help="Starting balance (default: 10000)"
    )
    parser.add_argument("--force-fetch", action="store_true", help="Force re-fetch from MT5")
    parser.add_argument("--no-ticks", action="store_true", help="Skip tick simulation")
    args = parser.parse_args()

    # Config
    config_path = args.config or f"config/{args.bot}_params.json"
    config = load_config(config_path)

    # Strategy
    if args.bot == "m1":
        strategy = M1ScalpingStrategy(config)
    else:
        strategy = M5ScalpingStrategy(config)

    # Date range
    start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else None
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else None

    # Fetch data
    logger.info("Fetching data...")
    data = fetch_and_cache(days=args.days, force=args.force_fetch)

    # Select candle data for the strategy's timeframe
    tf_key = "m1" if args.bot == "m1" else "m5"
    candle_df = data[tf_key]

    # Optionally slice to requested window
    if start and end:
        candle_df = slice_window(candle_df, start, end)

    # Generate tick data from M1 candles (unless disabled)
    tick_df = None
    if not args.no_ticks:
        logger.info("Generating tick prices from M1 data...")
        tick_df = generate_tick_prices(data["m1"])
        if start and end:
            mask = (tick_df["timestamp"] >= start) & (tick_df["timestamp"] < end)
            tick_df = tick_df.loc[mask].reset_index(drop=True)

    logger.info(
        f"Running backtest: {strategy.bot_label}, "
        f"{len(candle_df)} candles, balance=${args.balance:,.0f}"
    )

    # Run
    sim = Simulator(
        strategy=strategy,
        config=config,
        candle_df=candle_df,
        tick_df=tick_df,
        starting_balance=args.balance,
    )
    result = sim.run()

    print_report(result)


if __name__ == "__main__":
    main()
