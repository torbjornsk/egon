"""
Replay recent market data through the simulator and compare against actual trades.

Fetches fresh M1/M5 data directly from MT5 (no cache), runs the backtest,
then pulls your real trade history for the same period and shows a
side-by-side comparison: what the bot actually did vs what the simulator
would have done.

Usage:
    python -m tests.run_replay --bot m5 --hours 24
    python -m tests.run_replay --bot m1 --hours 48 --balance 8000
    python -m tests.run_replay --bot m5 --hours 24 --config config/experimental/m5_test.json
"""

import argparse
import logging
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

from src.core.config import load_config
from src.core.indicators import compute_indicators
from src.strategy.m1_scalping import M1ScalpingStrategy
from src.strategy.m5_scalping import M5ScalpingStrategy

from tests.data_cache import generate_tick_prices
from tests.simulator_v2 import SimulatorV2 as Simulator

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SYMBOL = "XAUUSD.p"


# ---------------------------------------------------------------------------
# MT5 data fetching (always fresh, no cache)
# ---------------------------------------------------------------------------

def fetch_fresh_candles(timeframe_const: int, hours: int) -> pd.DataFrame | None:
    """Fetch candle data from MT5 for the last N hours + warmup."""
    warmup_bars = 300
    if timeframe_const == mt5.TIMEFRAME_M1:
        total_bars = hours * 60 + warmup_bars
    else:
        total_bars = hours * 12 + warmup_bars

    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe_const, 0, total_bars)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def fetch_actual_trades(hours: int, magic_number: int) -> list[dict]:
    """Fetch completed trades from MT5 deal history."""
    from_date = datetime.now() - timedelta(hours=hours)
    to_date = datetime.now() + timedelta(hours=3)
    deals = mt5.history_deals_get(from_date, to_date)

    if not deals:
        return []

    # Group by position
    positions: dict[int, list] = {}
    for deal in deals:
        if "XAUUSD" not in deal.symbol or deal.magic != magic_number:
            continue
        pos_id = deal.position_id
        if pos_id not in positions:
            positions[pos_id] = []
        positions[pos_id].append(deal)

    trades = []
    for pos_id, deals_list in positions.items():
        if len(deals_list) < 2:
            continue

        deals_list.sort(key=lambda x: x.time)
        entry = deals_list[0]
        exit_ = deals_list[-1]

        if entry.entry != mt5.DEAL_ENTRY_IN or exit_.entry != mt5.DEAL_ENTRY_OUT:
            continue

        # SL/TP from orders
        orders = mt5.history_orders_get(position=pos_id)
        sl, tp = None, None
        if orders:
            for order in orders:
                if order.type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL):
                    sl = order.sl if order.sl > 0 else None
                    tp = order.tp if order.tp > 0 else None
                    break

        entry_time = datetime.fromtimestamp(entry.time)
        exit_time = datetime.fromtimestamp(exit_.time)
        direction = "LONG" if entry.type == mt5.DEAL_TYPE_BUY else "SHORT"

        # Exit reason
        exit_reason = "Signal exit"
        if sl and abs(exit_.price - sl) < 0.5:
            exit_reason = "Stop loss"
        elif tp and abs(exit_.price - tp) < 0.5:
            exit_reason = "Take profit"

        trades.append({
            "entry_time": entry_time,
            "exit_time": exit_time,
            "direction": direction,
            "entry_price": entry.price,
            "exit_price": exit_.price,
            "sl": sl,
            "tp": tp,
            "profit": exit_.profit,
            "duration_min": (exit_time - entry_time).total_seconds() / 60,
            "exit_reason": exit_reason,
        })

    return sorted(trades, key=lambda t: t["entry_time"])


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_trade_table(trades, label):
    """Print a formatted trade table."""
    if not trades:
        print(f"  No {label} trades")
        return

    print(
        f"  {'Time':<16} {'Dir':<6} {'Entry':>9} {'Exit':>9} "
        f"{'P/L':>10} {'Dur':>6} {'Reason'}"
    )
    print(f"  {'-'*75}")
    for t in trades:
        if isinstance(t, dict):
            time_str = t["entry_time"].strftime("%m-%d %H:%M")
            print(
                f"  {time_str:<16} {t['direction']:<6} "
                f"${t['entry_price']:>8.2f} ${t['exit_price']:>8.2f} "
                f"${t['profit']:>+9.2f} {t['duration_min']:>5.0f}m "
                f"{t['exit_reason']}"
            )
        else:
            # TradeRecord from simulator
            time_str = t.entry_time.strftime("%m-%d %H:%M")
            print(
                f"  {time_str:<16} {t.direction:<6} "
                f"${t.entry_price:>8.2f} ${t.exit_price:>8.2f} "
                f"${t.profit:>+9.2f} {t.duration_minutes:>5.0f}m "
                f"{t.exit_reason}"
            )


def stats_from_trades(trades) -> dict:
    """Compute stats from a list of trades (dicts or TradeRecords)."""
    if not trades:
        return {"count": 0, "profit": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0}

    profits = []
    for t in trades:
        profits.append(t["profit"] if isinstance(t, dict) else t.profit)

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]

    return {
        "count": len(profits),
        "profit": sum(profits),
        "win_rate": len(wins) / len(profits) * 100 if profits else 0,
        "avg_win": sum(wins) / len(wins) if wins else 0,
        "avg_loss": sum(losses) / len(losses) if losses else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Egon Replay Evaluator")
    parser.add_argument("--bot", choices=["m1", "m5"], required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--balance", type=float, default=None,
                        help="Starting balance (default: current MT5 balance)")
    parser.add_argument("--no-ticks", action="store_true")
    args = parser.parse_args()

    # Connect
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    # Get balance
    account = mt5.account_info()
    if not account:
        print("Not logged in to MT5")
        mt5.shutdown()
        return

    balance = args.balance or account.balance

    # Config + strategy
    config_path = args.config or f"config/{args.bot}_params.json"
    config = load_config(config_path)

    if args.bot == "m1":
        strategy = M1ScalpingStrategy(config)
        tf_const = mt5.TIMEFRAME_M1
    else:
        strategy = M5ScalpingStrategy(config)
        tf_const = mt5.TIMEFRAME_M5

    # Fetch fresh candle data
    print(f"Fetching fresh {args.bot.upper()} data ({args.hours}h)...")
    candle_df = fetch_fresh_candles(tf_const, args.hours)
    if candle_df is None or len(candle_df) < 250:
        print("Insufficient candle data")
        mt5.shutdown()
        return

    # Fetch M1 data for tick generation
    tick_df = None
    if not args.no_ticks:
        print("Fetching M1 data for tick simulation...")
        m1_df = fetch_fresh_candles(mt5.TIMEFRAME_M1, args.hours)
        if m1_df is not None and len(m1_df) > 0:
            tick_df = generate_tick_prices(m1_df)

    # Fetch actual trades
    print("Fetching actual trade history...")
    actual_trades = fetch_actual_trades(args.hours, strategy.magic_number)

    mt5.shutdown()

    # Run simulator
    print(f"Running simulator: {strategy.bot_label}, {len(candle_df)} candles, ${balance:,.0f}...")
    sim = Simulator(
        strategy=strategy,
        config=config,
        candle_df=candle_df,
        tick_df=tick_df,
        starting_balance=balance,
    )
    result = sim.run()

    # Report
    actual_stats = stats_from_trades(actual_trades)
    sim_stats = stats_from_trades(result.trades)

    print()
    print("=" * 80)
    print(f"REPLAY EVALUATION: {args.bot.upper()} -- Last {args.hours} hours")
    print("=" * 80)

    print(f"\n{'Metric':<25} {'Actual':>15} {'Simulated':>15}")
    print("-" * 58)
    print(f"{'Trades':<25} {actual_stats['count']:>15} {sim_stats['count']:>15}")
    print(f"{'Total P/L':<25} ${actual_stats['profit']:>13.2f} ${sim_stats['profit']:>13.2f}")
    print(f"{'Win rate':<25} {actual_stats['win_rate']:>14.1f}% {sim_stats['win_rate']:>14.1f}%")
    print(f"{'Avg win':<25} ${actual_stats['avg_win']:>13.2f} ${sim_stats['avg_win']:>13.2f}")
    print(f"{'Avg loss':<25} ${actual_stats['avg_loss']:>13.2f} ${sim_stats['avg_loss']:>13.2f}")

    if result.trades:
        print(f"{'Max drawdown':<25} {'':>15} {result.max_drawdown_pct:>14.1f}%")
        print(f"{'Sharpe':<25} {'':>15} {result.sharpe_ratio:>14.2f}")

    # Actual trades
    print(f"\nACTUAL TRADES ({actual_stats['count']}):")
    print_trade_table(actual_trades, "actual")

    # Simulated trades
    print(f"\nSIMULATED TRADES ({sim_stats['count']}):")
    print_trade_table(result.trades, "simulated")

    # Divergence analysis
    if actual_trades and result.trades:
        print(f"\nDIVERGENCE ANALYSIS:")
        diff = sim_stats["profit"] - actual_stats["profit"]
        print(f"  P/L difference: ${diff:+.2f} (sim - actual)")
        if abs(actual_stats["count"] - sim_stats["count"]) > 2:
            print(
                f"  Trade count mismatch: {actual_stats['count']} actual vs "
                f"{sim_stats['count']} simulated"
            )
            print("  Possible causes: slippage, spread, tick timing, MT5 execution delays")
        if abs(diff) > 50:
            print("  Significant P/L divergence -- check spread/slippage assumptions")
        else:
            print("  Simulator tracking actual performance reasonably well")

    print("=" * 80)


if __name__ == "__main__":
    main()
