"""
Backtest for the Liquidity Zone strategy.

Runs the ZoneBot against SimBroker with M5 data.
The ZoneBot places limit orders at detected zones and manages fills.

Usage:
    python -m tests.run_lz_backtest
    python -m tests.run_lz_backtest --days 30
    python -m tests.run_lz_backtest --no-spread
"""

import argparse
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.core.config import load_config
from src.core.indicators import compute_indicators
from src.core.broker import ORDER_TYPE_BUY, DEAL_ENTRY_OUT, DEAL_REASON_SL, DEAL_REASON_TP
from src.strategy.liquidity_zones import LiquidityZoneStrategy
from src.bot.zone_bot import ZoneBot
from tests.sim_broker import SimBroker

logging.basicConfig(level=logging.WARNING)


@dataclass
class LZTradeRecord:
    """Trade record for LZ backtest."""
    ticket: int
    direction: str
    entry_price: float
    exit_price: float
    profit: float
    exit_reason: str
    duration_minutes: float


@dataclass
class LZBacktestResult:
    """Backtest result for LZ strategy."""
    trades: list[LZTradeRecord] = field(default_factory=list)
    starting_balance: float = 10000.0
    final_balance: float = 10000.0
    peak_balance: float = 10000.0
    max_drawdown_pct: float = 0.0
    period_days: int = 0
    total_orders_placed: int = 0
    orders_filled: int = 0
    orders_cancelled: int = 0

    @property
    def total_return_pct(self) -> float:
        return (self.final_balance / self.starting_balance - 1) * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.profit > 0) / len(self.trades) * 100

    @property
    def sharpe_ratio(self) -> float:
        if len(self.trades) < 2:
            return 0.0
        returns = [t.profit for t in self.trades]
        return np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.profit for t in self.trades if t.profit > 0)
        gross_loss = abs(sum(t.profit for t in self.trades if t.profit < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def fill_rate(self) -> float:
        if self.total_orders_placed == 0:
            return 0.0
        return self.orders_filled / self.total_orders_placed * 100


def run_lz_backtest(
    config_path: str = "config/lz_params.json",
    m5_df: pd.DataFrame | None = None,
    days: int = 160,
    starting_balance: float = 10000.0,
    spread: float = 0.15,
    slippage: float = 0.05,
) -> LZBacktestResult:
    """Run a full LZ backtest."""

    config = load_config(config_path)

    # Fetch data if not provided
    if m5_df is None:
        from tests.run_m15_grid import fetch_m15_data
        import MetaTrader5 as mt5
        import pickle
        from pathlib import Path

        cache_path = Path("tests/cache/XAUUSD.p_160d_m5.pkl")
        if cache_path.exists():
            with open(cache_path, "rb") as f:
                m5_df = pickle.load(f)
        else:
            if not mt5.initialize():
                raise RuntimeError("MT5 not available")
            rates = mt5.copy_rates_from_pos("XAUUSD.p", mt5.TIMEFRAME_M5, 0, days * 24 * 12)
            mt5.shutdown()
            if rates is None:
                raise RuntimeError("Failed to fetch M5 data")
            m5_df = pd.DataFrame(rates)
            m5_df["time"] = pd.to_datetime(m5_df["time"], unit="s")
            cache_path.parent.mkdir(exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(m5_df, f)

    # Pre-compute indicators
    m5_df = compute_indicators(m5_df, config)

    # Create broker and bot
    broker = SimBroker(m5_df, starting_balance, spread_points=spread, slippage_points=slippage)
    strategy = LiquidityZoneStrategy(config)
    bot = ZoneBot(strategy, config, broker=broker)
    bot.positions.exit_reasons_file = ""
    bot.logger.setLevel(logging.WARNING)

    # Patch get_local_now
    import src.core.timezone as tz_mod
    import src.core.position as pos_mod
    import src.core.risk as risk_mod

    original_get_local_now = tz_mod.get_local_now
    sim_time_fn = lambda: broker.sim_time
    tz_mod.get_local_now = sim_time_fn
    pos_mod.get_local_now = sim_time_fn
    risk_mod.get_local_now = sim_time_fn

    # Override get_minutes_held
    def _sim_get_minutes_held(ticket: int) -> float:
        if ticket not in bot.positions.position_open_times:
            return 0
        delta = broker.sim_time - bot.positions.position_open_times[ticket]
        return max(0, delta.total_seconds() / 60)
    bot.positions.get_minutes_held = _sim_get_minutes_held

    # Disable safety pauses for full-period view
    bot.risk.max_drawdown_limit = 0.99
    bot.risk.daily_loss_limit_pct = 0.99
    bot.risk.rapid_loss_threshold_pct = 0.99
    bot.risk.max_consecutive_losses = 999

    # Track ALL trades by monitoring balance changes each bar
    trade_records = []
    original_close = bot.close_position

    def intercepted_close(position, reason, emergency=False):
        entry_price = position.price_open
        entry_time = datetime.fromtimestamp(position.time)
        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"
        balance_before = broker.balance
        original_close(position, reason, emergency)
        profit = broker.balance - balance_before
        exit_time = broker.sim_time
        duration = (exit_time - entry_time).total_seconds() / 60
        trade_records.append(LZTradeRecord(
            ticket=position.ticket, direction=direction,
            entry_price=entry_price, exit_price=position.price_current,
            profit=profit, exit_reason=reason, duration_minutes=duration,
        ))

    bot.close_position = intercepted_close

    # Run simulation
    warmup = 200
    peak_balance = starting_balance
    max_dd = 0.0
    seen_sl_tp_tickets = set()

    bot.connect()

    try:
        for i in range(warmup, len(m5_df)):
            broker.advance(i)

            # Capture SL/TP trades that happened during advance()
            for ticket, info in broker._sl_tp_info.items():
                if ticket not in seen_sl_tp_tickets:
                    seen_sl_tp_tickets.add(ticket)
                    direction = "LONG" if info.get('type', 0) == ORDER_TYPE_BUY else "SHORT"
                    profit = info.get('profit', 0)
                    reason = "Stop loss" if profit < 0 else "Take profit"
                    trade_records.append(LZTradeRecord(
                        ticket=ticket, direction=direction,
                        entry_price=info.get('price_open', 0),
                        exit_price=info.get('exit_price', 0),
                        profit=profit, exit_reason=reason,
                        duration_minutes=0,
                    ))

            # Track drawdown
            balance = broker.balance
            if balance > peak_balance:
                peak_balance = balance
            if peak_balance > 0:
                dd = (peak_balance - balance) / peak_balance * 100
                if dd > max_dd:
                    max_dd = dd

            # Check SL/TP closes (ZoneBot handles its own tracking)
            bot.check_mt5_closed_positions()

            # Run trading logic
            bot.last_processed_candle = m5_df.iloc[i]["time"]
            bot.trading_logic()

            # PP continuous
            if bot.is_profit_protection_active():
                bot.check_profit_protection_continuous()

    finally:
        tz_mod.get_local_now = original_get_local_now
        pos_mod.get_local_now = original_get_local_now
        risk_mod.get_local_now = original_get_local_now

    # Close remaining positions
    positions = broker.get_open_positions(strategy.magic_number)
    for pos in positions:
        bot.close_position(pos, "End of backtest")

    final_info = broker.get_account_info()

    # Calculate period
    start_time = m5_df.iloc[warmup]["time"]
    end_time = m5_df.iloc[min(len(m5_df) - 1, broker._current_bar_idx)]["time"]
    period_days = (end_time - start_time).days if hasattr(end_time - start_time, 'days') else 0

    return LZBacktestResult(
        trades=trade_records,
        starting_balance=starting_balance,
        final_balance=final_info["balance"],
        peak_balance=peak_balance,
        max_drawdown_pct=max_dd,
        period_days=period_days,
        total_orders_placed=bot._next_order_id - 5000,
        orders_filled=len([o for o in bot.pending_orders if o.filled]) + len(trade_records),
        orders_cancelled=len([o for o in bot.pending_orders if o.cancelled]),
    )


def main():
    parser = argparse.ArgumentParser(description="LZ Strategy Backtest")
    parser.add_argument("--days", type=int, default=160)
    parser.add_argument("--no-spread", action="store_true")
    parser.add_argument("--config", default="config/lz_params.json")
    args = parser.parse_args()

    spread = 0.0 if args.no_spread else 0.15
    slippage = 0.0 if args.no_spread else 0.05

    print(f"Running LZ backtest...")
    print(f"  Spread: ${spread*2:.2f}, Slippage: ${slippage:.2f}")

    t0 = time.time()
    result = run_lz_backtest(
        config_path=args.config,
        days=args.days,
        spread=spread,
        slippage=slippage,
    )
    elapsed = time.time() - t0

    wins = [t for t in result.trades if t.profit > 0]
    losses = [t for t in result.trades if t.profit < 0]

    print(f"\n{'='*70}")
    print(f"  LIQUIDITY ZONE BACKTEST RESULTS")
    print(f"{'='*70}")
    print(f"  Period:          {result.period_days} days")
    print(f"  Return:          {result.total_return_pct:+.2f}%")
    print(f"  Final balance:   ${result.final_balance:.2f}")
    print(f"  Max drawdown:    {result.max_drawdown_pct:.1f}%")
    print(f"  Trades:          {len(result.trades)}")
    print(f"  Win rate:        {result.win_rate:.1f}%")
    print(f"  Sharpe:          {result.sharpe_ratio:.3f}")
    print(f"  Profit factor:   {result.profit_factor:.2f}")
    print(f"  Avg win:         ${np.mean([t.profit for t in wins]):.2f}" if wins else "  Avg win:         N/A")
    print(f"  Avg loss:        ${np.mean([t.profit for t in losses]):.2f}" if losses else "  Avg loss:        N/A")
    print(f"  Orders placed:   {result.total_orders_placed}")
    print(f"  Fill rate:       {result.fill_rate:.0f}%")
    print(f"  Time:            {elapsed:.1f}s")

    # Exit breakdown
    from collections import Counter
    reasons = Counter(t.exit_reason for t in result.trades)
    print(f"\n  Exit breakdown:")
    for reason, count in reasons.most_common():
        print(f"    {reason}: {count}")

    # Direction breakdown
    longs = [t for t in result.trades if t.direction == "LONG"]
    shorts = [t for t in result.trades if t.direction == "SHORT"]
    print(f"\n  Direction:")
    print(f"    LONG:  {len(longs)} trades, ${sum(t.profit for t in longs):.2f}")
    print(f"    SHORT: {len(shorts)} trades, ${sum(t.profit for t in shorts):.2f}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
