"""
RSI level calculator -- reverse-engineers what price would produce a target RSI.

Given the current RSI state (average gains/losses), calculates the exact
price that would make RSI equal a target value. Used to place limit orders
at RSI trigger levels before the signal actually fires.
"""

import numpy as np
import pandas as pd


def calculate_rsi_price(
    df: pd.DataFrame,
    target_rsi: float,
    rsi_period: int = 14,
) -> float | None:
    """
    Calculate what close price would produce the target RSI value.

    Uses the current state of the RSI calculation (avg gain/loss from
    the last N periods) and solves for the price that would give the
    target RSI on the NEXT tick/close.

    Args:
        df: DataFrame with 'close' column (needs at least rsi_period + 1 rows)
        target_rsi: The RSI value we want to hit (e.g. 35 for buy, 65 for sell)
        rsi_period: RSI period (must match the bot's config)

    Returns:
        The price that would produce target_rsi, or None if impossible.
    """
    if len(df) < rsi_period + 2:
        return None

    closes = df['close'].values

    # Calculate current avg gain and avg loss using Wilder's smoothing
    # (same method as our indicators.py RSI calculation)
    deltas = np.diff(closes[-(rsi_period + 1):])

    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Use simple average for the initial window (matches pandas rolling.mean)
    avg_gain = gains[:-1].mean()  # Average of first N-1 changes
    avg_loss = losses[:-1].mean()

    # Apply Wilder's smoothing for the last value
    last_gain = gains[-1]
    last_loss = losses[-1]
    avg_gain = (avg_gain * (rsi_period - 1) + last_gain) / rsi_period
    avg_loss = (avg_loss * (rsi_period - 1) + last_loss) / rsi_period

    # Now solve: what change from current close gives target_rsi?
    current_close = closes[-1]

    # Target RS from target RSI
    if target_rsi >= 100 or target_rsi <= 0:
        return None

    target_rs = target_rsi / (100 - target_rsi)

    # Case 1: price goes DOWN (loss) to hit a low RSI (buy signal)
    # new_avg_gain = avg_gain * (N-1) / N  (no new gain)
    # new_avg_loss = (avg_loss * (N-1) + abs(change)) / N
    # RS = new_avg_gain / new_avg_loss = target_rs
    if target_rsi < 50:
        new_avg_gain = avg_gain * (rsi_period - 1) / rsi_period
        # Solve: new_avg_gain / new_avg_loss = target_rs
        # new_avg_loss = new_avg_gain / target_rs
        required_avg_loss = new_avg_gain / target_rs if target_rs > 0 else float('inf')
        # (avg_loss * (N-1) + abs_change) / N = required_avg_loss
        # abs_change = required_avg_loss * N - avg_loss * (N-1)
        abs_change = required_avg_loss * rsi_period - avg_loss * (rsi_period - 1)

        if abs_change < 0:
            # RSI is already below target without any price change
            return current_close

        target_price = current_close - abs_change
        return target_price

    # Case 2: price goes UP (gain) to hit a high RSI (sell signal)
    # new_avg_loss = avg_loss * (N-1) / N  (no new loss)
    # new_avg_gain = (avg_gain * (N-1) + change) / N
    # RS = new_avg_gain / new_avg_loss = target_rs
    else:
        new_avg_loss = avg_loss * (rsi_period - 1) / rsi_period
        if new_avg_loss <= 0:
            # No losses means RSI is already very high
            return current_close

        required_avg_gain = target_rs * new_avg_loss
        change = required_avg_gain * rsi_period - avg_gain * (rsi_period - 1)

        if change < 0:
            # RSI is already above target
            return current_close

        target_price = current_close + change
        return target_price


def calculate_rsi_buy_price(
    df: pd.DataFrame,
    rsi_buy: float,
    rsi_period: int = 14,
) -> float | None:
    """Calculate the price where RSI would hit the buy threshold (below current price)."""
    price = calculate_rsi_price(df, rsi_buy, rsi_period)
    if price is None:
        return None
    current = df['close'].iloc[-1]
    # Buy price should be below current price
    if price >= current:
        return None  # RSI is already in buy zone
    return price


def calculate_rsi_sell_price(
    df: pd.DataFrame,
    rsi_sell: float,
    rsi_period: int = 14,
) -> float | None:
    """Calculate the price where RSI would hit the sell threshold (above current price)."""
    price = calculate_rsi_price(df, rsi_sell, rsi_period)
    if price is None:
        return None
    current = df['close'].iloc[-1]
    # Sell price should be above current price
    if price <= current:
        return None  # RSI is already in sell zone
    return price
