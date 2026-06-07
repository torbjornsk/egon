"""
Technical indicator computation  --  single source of truth.

All indicator logic lives here. Both bots, the GUI, and backtesting
import from this module instead of computing their own.
"""

import pandas as pd
import numpy as np
from src.core.config import TradingConfig


def compute_indicators(df: pd.DataFrame, config: TradingConfig) -> pd.DataFrame:
    """
    Compute all technical indicators on OHLCV data.

    Expects columns: open, high, low, close, volume, time.
    Returns a copy with added indicator columns.
    """
    df = df.copy()

    # EMAs
    df['ema_fast'] = df['close'].ewm(span=config.fast_ema).mean()
    df['ema_slow'] = df['close'].ewm(span=config.slow_ema).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(config.rsi_period).mean()
    loss = -delta.clip(upper=0).rolling(config.rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Slow RSI (for dual-RSI filter, always computed at period 14)
    slow_period = 14
    if config.rsi_period != slow_period:
        gain_slow = delta.clip(lower=0).rolling(slow_period).mean()
        loss_slow = -delta.clip(upper=0).rolling(slow_period).mean()
        rs_slow = gain_slow / loss_slow
        df['RSI_slow'] = 100 - (100 / (1 + rs_slow))
    else:
        df['RSI_slow'] = df['RSI']

    # ATR (14-period)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    # Trend
    df['uptrend'] = df['ema_fast'] > df['ema_slow']
    df['downtrend'] = df['ema_fast'] < df['ema_slow']

    return df


def get_adaptive_atr_multiplier(
    df: pd.DataFrame,
    base_multiplier: float,
    high_vol_multiplier: float | None = None,
) -> float:
    """
    Adaptive ATR multiplier based on volatility regime.

    Returns a reduced multiplier when current ATR is in the top 20th percentile
    of the last 100 candles, limiting stop-loss distance in high volatility.

    If high_vol_multiplier is provided, uses it directly. Otherwise falls back
    to 75% of base_multiplier.
    """
    current_atr = df.iloc[-1]['ATR']
    recent_atrs = df['ATR'].tail(100)
    atr_80th = recent_atrs.quantile(0.80)

    if current_atr > atr_80th:
        if high_vol_multiplier is not None:
            return high_vol_multiplier
        return base_multiplier * 0.75

    return base_multiplier
