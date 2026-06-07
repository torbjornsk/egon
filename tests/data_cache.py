"""
Data caching layer -- fetches OHLCV data from MT5 and caches to disk.

Caches both M1 and M5 candles. M1 candles serve double duty: they provide
the M1 strategy's candle data AND act as second-by-second price simulation
for profit protection testing (interpolated within each M1 bar).

Indicators are pre-computed and stored alongside the raw data.
"""

import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

from src.core.config import TradingConfig, load_config
from src.core.indicators import compute_indicators

logger = logging.getLogger(__name__)

CACHE_DIR = Path("tests/cache")
SYMBOL = "XAUUSD.p"


def _fetch_mt5_data(
    symbol: str, timeframe_const: int, days: int
) -> pd.DataFrame | None:
    """Fetch OHLCV data from MT5 using copy_rates_from_pos with chunking.

    MT5 caps at 99999 bars per request, so we fetch in chunks using
    increasing offsets to get as much history as possible.
    """
    if timeframe_const == mt5.TIMEFRAME_M1:
        bars_needed = days * 24 * 60
    elif timeframe_const == mt5.TIMEFRAME_M5:
        bars_needed = days * 24 * 12
    else:
        bars_needed = days * 24 * 60

    max_chunk = 99_999
    all_dfs = []
    offset = 0

    while offset < bars_needed:
        chunk_size = min(max_chunk, bars_needed - offset)
        rates = mt5.copy_rates_from_pos(symbol, timeframe_const, offset, chunk_size)
        if rates is None or len(rates) == 0:
            break
        all_dfs.append(pd.DataFrame(rates))
        fetched = len(rates)
        offset += fetched
        if fetched < chunk_size:
            break  # No more data available

    if not all_dfs:
        logger.error(f"No data for {symbol}: {mt5.last_error()}")
        return None

    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def fetch_and_cache(
    symbol: str = SYMBOL,
    days: int = 365,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """
    Fetch M1 and M5 candle data, cache to disk, return both.

    Returns dict with keys 'm1' and 'm5', each a DataFrame with
    columns: time, open, high, low, close, tick_volume, spread, real_volume.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Cache key based on days requested
    cache_label = f"{symbol}_{days}d"
    m1_path = CACHE_DIR / f"{cache_label}_m1.pkl"
    m5_path = CACHE_DIR / f"{cache_label}_m5.pkl"

    result = {}

    if not force and m1_path.exists() and m5_path.exists():
        logger.info("Loading cached data...")
        with open(m1_path, "rb") as f:
            result["m1"] = pickle.load(f)
        with open(m5_path, "rb") as f:
            result["m5"] = pickle.load(f)
        logger.info(
            f"Cached: M1={len(result['m1'])} bars, M5={len(result['m5'])} bars"
        )
        return result

    # Connect to MT5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        mt5.shutdown()
        raise RuntimeError(f"Symbol {symbol} not found")
    if not sym_info.visible:
        mt5.symbol_select(symbol, True)

    logger.info(f"Fetching M1 data ({days} days)...")
    m1_df = _fetch_mt5_data(symbol, mt5.TIMEFRAME_M1, days)

    logger.info(f"Fetching M5 data ({days} days)...")
    m5_df = _fetch_mt5_data(symbol, mt5.TIMEFRAME_M5, days)

    mt5.shutdown()

    if m1_df is None or m5_df is None:
        raise RuntimeError("Failed to fetch data from MT5")

    # Cache
    with open(m1_path, "wb") as f:
        pickle.dump(m1_df, f)
    with open(m5_path, "wb") as f:
        pickle.dump(m5_df, f)

    logger.info(
        f"Cached: M1={len(m1_df)} bars ({m1_df['time'].min()} to {m1_df['time'].max()}), "
        f"M5={len(m5_df)} bars"
    )

    result["m1"] = m1_df
    result["m5"] = m5_df
    return result


def precompute_indicators(
    df: pd.DataFrame, config: TradingConfig
) -> pd.DataFrame:
    """Compute indicators once and return enriched DataFrame."""
    return compute_indicators(df, config)


def generate_tick_prices(m1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate second-by-second price series from M1 candles.

    For each M1 bar, interpolates 60 price points following the
    open -> high/low -> close path. This simulates intra-candle
    price movement for profit protection testing.

    Returns DataFrame with columns: timestamp, price
    """
    rows = []
    for _, bar in m1_df.iterrows():
        bar_start = bar["time"]
        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

        # Determine path: if close > open, go low first then high
        if c >= o:
            # Bullish: open -> low -> high -> close
            path = [o, l, h, c]
        else:
            # Bearish: open -> high -> low -> close
            path = [o, h, l, c]

        # Distribute across 60 seconds
        for sec in range(60):
            t = bar_start + pd.Timedelta(seconds=sec)
            # Linear interpolation across 4 waypoints
            frac = sec / 59 if sec < 59 else 1.0
            segment = frac * 3  # 0..3 across the 4 waypoints
            idx = min(int(segment), 2)
            local_frac = segment - idx
            price = path[idx] + (path[idx + 1] - path[idx]) * local_frac
            rows.append({"timestamp": t, "price": price})

    return pd.DataFrame(rows)


def slice_window(
    df: pd.DataFrame, start: datetime, end: datetime
) -> pd.DataFrame:
    """Slice a DataFrame by time range."""
    mask = (df["time"] >= start) & (df["time"] < end)
    return df.loc[mask].copy().reset_index(drop=True)
