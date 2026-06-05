"""
M15 strategy parameter grid search.

Fetches M15 data from MT5, tests various parameter combinations
with realistic spread/slippage, finds what actually works.

Tests:
- RSI periods: 5, 7, 10, 14
- RSI entry thresholds: tight (25/75), medium (30/70), wide (35/65)
- ATR stop multipliers: 2.0, 3.0, 4.0, 5.0
- Position sizing: conservative (5%), moderate (10%), aggressive (15%)
- Leverage: 10x, 15x, 20x

Usage:
    python -m tests.run_m15_grid
"""

import copy
import logging
import pickle
import time
from datetime import timedelta
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from src.core.config import TradingConfig, load_config
from src.core.broker import TIMEFRAME_M1
from src.strategy.m1_scalping import M1ScalpingStrategy
from tests.simulator_v2 import SimulatorV2

logging.basicConfig(level=logging.WARNING)

CACHE_DIR = Path("tests/cache")
SYMBOL = "XAUUSD.p"
BALANCE = 10000.0
SPREAD = 0.15       # half-spread ($0.30 total)
SLIPPAGE = 0.05     # max random slippage


def fetch_m15_data(days: int = 160, force: bool = False) -> pd.DataFrame:
    """Fetch and cache M15 data."""
    cache_path = CACHE_DIR / f"{SYMBOL}_{days}d_m15.pkl"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and cache_path.exists():
        with open(cache_path, "rb") as f:
            df = pickle.load(f)
        print(f"Cached M15: {len(df)} bars, {df['time'].min().date()} to {df['time'].max().date()}")
        return df

    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    sym_info = mt5.symbol_info(SYMBOL)
    if sym_info is None:
        mt5.shutdown()
        raise RuntimeError(f"Symbol {SYMBOL} not found")
    if not sym_info.visible:
        mt5.symbol_select(SYMBOL, True)

    # M15: 96 bars/day
    bars_needed = days * 96
    print(f"Fetching M15 data ({days} days, {bars_needed} bars)...")

    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, min(bars_needed, 99999))
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise RuntimeError("Failed to fetch M15 data")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    with open(cache_path, "wb") as f:
        pickle.dump(df, f)

    print(f"M15: {len(df)} bars, {df['time'].min().date()} to {df['time'].max().date()}")
    return df


class M15Strategy(M1ScalpingStrategy):
    """M15 strategy -- reuses M1 logic but on 15-minute timeframe."""

    @property
    def timeframe_minutes(self) -> int:
        return 15

    @property
    def mt5_timeframe(self) -> int:
        return 15  # MT5 TIMEFRAME_M15

    @property
    def magic_number(self) -> int:
        return 234015

    @property
    def bot_label(self) -> str:
        return "M15"

    @property
    def order_comment(self) -> str:
        return "m15_scalping"


def make_config(
    rsi_period: int = 10,
    rsi_buy: float = 30,
    rsi_sell: float = 70,
    rsi_exit_long: float = 65,
    rsi_exit_short: float = 35,
    atr_multiplier: float = 3.0,
    position_size_pct: float = 0.10,
    leverage: int = 15,
    profit_target_pct: float = 0.015,
) -> TradingConfig:
    """Create an M15 config with given parameters."""
    return TradingConfig(
        strategy="m15_scalping",
        position_size_pct=position_size_pct,
        leverage=leverage,
        max_positions=1,
        max_drawdown_limit=0.35,
        fast_ema=9,
        slow_ema=21,
        rsi_period=rsi_period,
        rsi_buy=rsi_buy,
        rsi_sell=rsi_sell,
        rsi_exit_long=rsi_exit_long,
        rsi_exit_short=rsi_exit_short,
        rsi_exit_confirmation=False,
        atr_multiplier=atr_multiplier,
        atr_high_volatility_multiplier=atr_multiplier * 0.6,
        profit_target_pct=profit_target_pct,
        enable_shorts=True,
        short_requires_downtrend=False,
        long_requires_uptrend=False,
        use_smart_cooldown=False,
        entry_signal_confirmations=0,
        use_profit_protection=True,
        profit_protection_auto_volatility=True,
        profit_protection_threshold_pct=0.04,
        profit_protection_drawdown_limit_pct=0.50,
        profit_protection_time_based_tightening=True,
        profit_protection_tightening_start_minutes=60,
        profit_protection_tightening_interval_minutes=30,
        profit_protection_tightening_step_pct=0.05,
        profit_protection_minimum_drawdown_pct=0.20,
        use_loss_backoff=True,
        loss_backoff_sl_only=True,
        loss_backoff_sl_threshold=2,
        loss_backoff_sl_candles=2,
        sl_tightening_factor=1.0,
        block_second_when_underwater=False,
        trading_mode="both",
        trend_filter="none",
    )


def run_backtest(config: TradingConfig, m15_df: pd.DataFrame) -> dict | None:
    """Run a single backtest and return summary stats."""
    strat = M15Strategy(config)
    sim = SimulatorV2(strat, config, m15_df, None, BALANCE, spread=SPREAD, slippage=SLIPPAGE)

    # Disable safety pauses for grid search (we want to see full performance)
    sim.bot.risk.max_drawdown_limit = 0.99
    sim.bot.risk.daily_loss_limit_pct = 0.99
    sim.bot.risk.rapid_loss_threshold_pct = 0.99
    sim.bot.risk.max_consecutive_losses = 999

    r = sim.run()
    if not r.trades:
        return None

    wins = [t.profit for t in r.trades if t.profit > 0]
    losses = [t.profit for t in r.trades if t.profit < 0]

    return {
        'return_pct': r.total_return_pct,
        'trades': len(r.trades),
        'win_rate': r.win_rate,
        'sharpe': r.sharpe_ratio,
        'avg_win': np.mean(wins) if wins else 0,
        'avg_loss': np.mean(losses) if losses else 0,
        'max_dd': r.max_drawdown_pct,
        'profit_factor': r.profit_factor,
        'period_days': r.period_days,
    }


def main():
    m15_df = fetch_m15_data(days=160)

    # Parameter grid
    grid = []

    # Phase 1: RSI period + entry thresholds (with fixed sizing)
    for rsi_period in [5, 7, 10, 14]:
        for rsi_buy, rsi_sell in [(25, 75), (30, 70), (35, 65)]:
            # Exit = entry + offset toward center
            rsi_exit_long = rsi_sell - 5
            rsi_exit_short = rsi_buy + 5
            for atr_mult in [2.5, 3.5, 5.0]:
                name = f"RSI{rsi_period} {rsi_buy}/{rsi_sell} ATR{atr_mult}"
                config = make_config(
                    rsi_period=rsi_period,
                    rsi_buy=rsi_buy,
                    rsi_sell=rsi_sell,
                    rsi_exit_long=rsi_exit_long,
                    rsi_exit_short=rsi_exit_short,
                    atr_multiplier=atr_mult,
                )
                grid.append((name, config))

    print(f"\nGrid: {len(grid)} parameter combos")
    print(f"Data: {len(m15_df)} M15 bars ({m15_df['time'].min().date()} to {m15_df['time'].max().date()})")
    print(f"Spread: ${SPREAD*2:.2f} total, Slippage: ${SLIPPAGE:.2f} max")
    print(f"Sizing: 10% at 15x leverage (1.5x effective)")
    print()

    results = []
    t0 = time.time()

    for i, (name, config) in enumerate(grid, 1):
        r = run_backtest(config, m15_df)
        if r:
            r['name'] = name
            results.append(r)
        if i % 9 == 0:
            elapsed = time.time() - t0
            print(f"  {i}/{len(grid)} done ({elapsed:.0f}s)...")

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f}s")

    # Sort by return
    results.sort(key=lambda x: x['return_pct'], reverse=True)

    # Print results
    print(f"\n{'=' * 130}")
    print(f"  M15 PARAMETER GRID -- sorted by return (with ${SPREAD*2:.2f} spread)")
    print(f"{'=' * 130}")

    hdr = (f"{'#':>2} {'Profile':<28} {'Ret%':>7} {'Trades':>7} {'WinR%':>6} "
           f"{'Sharpe':>7} {'PF':>5} {'AvgW$':>7} {'AvgL$':>8} {'MaxDD%':>7} {'Days':>5}")
    print(hdr)
    print("-" * 130)

    for i, r in enumerate(results[:20], 1):
        line = (f"{i:>2} {r['name']:<28} "
                f"{r['return_pct']:>+6.2f}% {r['trades']:>7} {r['win_rate']:>5.1f}% "
                f"{r['sharpe']:>7.3f} {r['profit_factor']:>5.2f} "
                f"${r['avg_win']:>6.2f} ${r['avg_loss']:>7.2f} "
                f"{r['max_dd']:>6.1f}% {r['period_days']:>5}")
        print(line)

    if len(results) > 20:
        print(f"  ... ({len(results) - 20} more)")

    # Show worst 5
    print(f"\nWORST 5:")
    for r in results[-5:]:
        print(f"  {r['name']:<28} {r['return_pct']:>+6.2f}% {r['trades']:>5} trades  MaxDD {r['max_dd']:.1f}%")

    # Summary stats
    profitable = [r for r in results if r['return_pct'] > 0]
    print(f"\n{'=' * 130}")
    print(f"SUMMARY: {len(profitable)}/{len(results)} configs profitable after costs")
    if profitable:
        print(f"  Best: {profitable[0]['name']} at {profitable[0]['return_pct']:+.2f}%")
        print(f"  Avg profitable return: {np.mean([r['return_pct'] for r in profitable]):+.2f}%")
    print(f"{'=' * 130}")


if __name__ == "__main__":
    main()
