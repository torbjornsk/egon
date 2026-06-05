"""
Liquidity zone detection for XAUUSD.

Identifies price levels where orders cluster and price is likely to react:
- Swing highs/lows (where stops and take-profits accumulate)
- High-volume areas (where institutional activity happened)
- Order blocks (last candle before a strong impulsive move)

Zones have a strength score based on:
- Number of times price has reacted at this level
- Recency (newer zones are stronger)
- Volume at the zone
- Whether the zone is "fresh" (untested since creation)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class LiquidityZone:
    """A price zone where liquidity clusters."""
    price_low: float          # Bottom of the zone
    price_high: float         # Top of the zone
    zone_type: str            # "demand" (buy zone) or "supply" (sell zone)
    strength: float           # 0-1 score
    created_at: datetime      # When the zone was identified
    touches: int = 0          # Times price has visited this zone
    fresh: bool = True        # Never been tested since creation
    origin: str = ""          # How it was detected (swing, volume, order_block)

    @property
    def mid_price(self) -> float:
        return (self.price_low + self.price_high) / 2

    @property
    def width(self) -> float:
        return self.price_high - self.price_low

    def contains(self, price: float) -> bool:
        return self.price_low <= price <= self.price_high

    def distance_from(self, price: float) -> float:
        """Distance from price to nearest edge of zone."""
        if price < self.price_low:
            return self.price_low - price
        elif price > self.price_high:
            return price - self.price_high
        return 0.0


def detect_swing_points(
    df: pd.DataFrame,
    left_bars: int = 5,
    right_bars: int = 2,
) -> tuple[list[int], list[int]]:
    """
    Detect swing highs and swing lows using left/right bar comparison.

    A swing high is a bar whose high is higher than the `left_bars` bars
    before it AND the `right_bars` bars after it.

    Returns: (swing_high_indices, swing_low_indices)
    """
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(left_bars, n - right_bars):
        # Swing high
        is_high = True
        for j in range(1, left_bars + 1):
            if highs[i] <= highs[i - j]:
                is_high = False
                break
        if is_high:
            for j in range(1, right_bars + 1):
                if highs[i] <= highs[i + j]:
                    is_high = False
                    break
        if is_high:
            swing_highs.append(i)

        # Swing low
        is_low = True
        for j in range(1, left_bars + 1):
            if lows[i] >= lows[i - j]:
                is_low = False
                break
        if is_low:
            for j in range(1, right_bars + 1):
                if lows[i] >= lows[i + j]:
                    is_low = False
                    break
        if is_low:
            swing_lows.append(i)

    return swing_highs, swing_lows


def detect_order_blocks(
    df: pd.DataFrame,
    min_impulse_atr: float = 1.5,
) -> list[tuple[int, str]]:
    """
    Detect order blocks: the last opposing candle before a strong move.

    Bullish OB: last bearish candle before a strong bullish impulse
    Bearish OB: last bullish candle before a strong bearish impulse

    Returns: list of (bar_index, "demand" or "supply")
    """
    if 'ATR' not in df.columns or len(df) < 10:
        return []

    opens = df['open'].values
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = df['ATR'].values

    blocks = []

    for i in range(2, len(df) - 1):
        atr = atrs[i]
        if atr <= 0:
            continue

        # Current candle is the impulse
        body = abs(closes[i] - opens[i])
        if body < atr * min_impulse_atr:
            continue

        # Bullish impulse (big green candle)
        if closes[i] > opens[i]:
            # Look for the last bearish candle before this
            if closes[i - 1] < opens[i - 1]:  # Previous was bearish
                blocks.append((i - 1, "demand"))

        # Bearish impulse (big red candle)
        elif closes[i] < opens[i]:
            if closes[i - 1] > opens[i - 1]:  # Previous was bullish
                blocks.append((i - 1, "supply"))

    return blocks


def find_liquidity_zones(
    df: pd.DataFrame,
    lookback: int = 100,
    zone_width_atr: float = 0.3,
    max_zones: int = 10,
    swing_left: int = 5,
    swing_right: int = 2,
    min_impulse_atr: float = 1.5,
) -> list[LiquidityZone]:
    """
    Find active liquidity zones from recent price action.

    Combines swing points and order blocks into a unified zone list,
    merges overlapping zones, and scores them by strength.

    Args:
        df: OHLCV DataFrame with ATR column
        lookback: How many bars back to look for zones
        zone_width_atr: Zone width as fraction of ATR
        max_zones: Maximum zones to return
        swing_left: Bars to the left for swing detection
        swing_right: Bars to the right for swing detection
        min_impulse_atr: Minimum impulse size (in ATR) for order blocks

    Returns: List of LiquidityZone sorted by distance from current price
    """
    if len(df) < lookback or 'ATR' not in df.columns:
        return []

    # Work with the last `lookback` bars
    window = df.iloc[-lookback:].copy().reset_index(drop=True)
    current_price = window['close'].iloc[-1]
    current_atr = window['ATR'].iloc[-1]
    zone_half_width = current_atr * zone_width_atr

    if current_atr <= 0:
        return []

    zones: list[LiquidityZone] = []
    times = window['time'].values

    # 1. Swing-based zones
    swing_highs, swing_lows = detect_swing_points(window, swing_left, swing_right)

    for idx in swing_lows:
        low = window['low'].iloc[idx]
        zone_time = pd.Timestamp(times[idx]).to_pydatetime() if isinstance(times[idx], np.datetime64) else times[idx]
        # Recency score: newer = stronger
        bars_ago = len(window) - idx
        recency = max(0.3, 1.0 - bars_ago / lookback)

        zones.append(LiquidityZone(
            price_low=low - zone_half_width * 0.3,
            price_high=low + zone_half_width * 0.7,
            zone_type="demand",
            strength=0.6 * recency,
            created_at=zone_time,
            origin="swing_low",
        ))

    for idx in swing_highs:
        high = window['high'].iloc[idx]
        zone_time = pd.Timestamp(times[idx]).to_pydatetime() if isinstance(times[idx], np.datetime64) else times[idx]
        bars_ago = len(window) - idx
        recency = max(0.3, 1.0 - bars_ago / lookback)

        zones.append(LiquidityZone(
            price_low=high - zone_half_width * 0.7,
            price_high=high + zone_half_width * 0.3,
            zone_type="supply",
            strength=0.6 * recency,
            created_at=zone_time,
            origin="swing_high",
        ))

    # 2. Order block zones
    blocks = detect_order_blocks(window, min_impulse_atr)
    for idx, block_type in blocks:
        if block_type == "demand":
            low = window['low'].iloc[idx]
            high = window['high'].iloc[idx]
        else:
            low = window['low'].iloc[idx]
            high = window['high'].iloc[idx]

        zone_time = pd.Timestamp(times[idx]).to_pydatetime() if isinstance(times[idx], np.datetime64) else times[idx]
        bars_ago = len(window) - idx
        recency = max(0.3, 1.0 - bars_ago / lookback)

        zones.append(LiquidityZone(
            price_low=low,
            price_high=high,
            zone_type=block_type,
            strength=0.8 * recency,  # Order blocks are stronger
            created_at=zone_time,
            origin="order_block",
        ))

    # 3. Merge overlapping zones of the same type
    zones = _merge_overlapping(zones)

    # 4. Mark zones that have been tested (price has visited since creation)
    for zone in zones:
        # Check if any bar after zone creation touched the zone
        zone_bar_idx = None
        for i, t in enumerate(times):
            t_dt = pd.Timestamp(t).to_pydatetime() if isinstance(t, np.datetime64) else t
            if t_dt >= zone.created_at:
                zone_bar_idx = i
                break

        if zone_bar_idx is not None:
            for i in range(zone_bar_idx + 1, len(window)):
                if window['low'].iloc[i] <= zone.price_high and window['high'].iloc[i] >= zone.price_low:
                    zone.touches += 1
                    zone.fresh = False

    # 5. Filter: remove zones that current price is already inside
    zones = [z for z in zones if not z.contains(current_price)]

    # 6. Filter: demand zones below price, supply zones above price
    valid_zones = []
    for z in zones:
        if z.zone_type == "demand" and z.mid_price < current_price:
            valid_zones.append(z)
        elif z.zone_type == "supply" and z.mid_price > current_price:
            valid_zones.append(z)
    zones = valid_zones

    # 7. Score adjustment: fresh zones are stronger, heavily tested zones weaken
    for z in zones:
        if z.fresh:
            z.strength *= 1.3
        elif z.touches >= 3:
            z.strength *= 0.5  # Zone is "used up"
        z.strength = min(1.0, z.strength)

    # 8. Sort by distance from current price (closest first) and limit
    zones.sort(key=lambda z: z.distance_from(current_price))
    return zones[:max_zones]


def _merge_overlapping(zones: list[LiquidityZone]) -> list[LiquidityZone]:
    """Merge zones of the same type that overlap."""
    if not zones:
        return []

    # Group by type
    demand = [z for z in zones if z.zone_type == "demand"]
    supply = [z for z in zones if z.zone_type == "supply"]

    merged = []
    for group in [demand, supply]:
        group.sort(key=lambda z: z.price_low)
        i = 0
        while i < len(group):
            current = group[i]
            # Merge with subsequent overlapping zones
            while i + 1 < len(group) and group[i + 1].price_low <= current.price_high:
                next_zone = group[i + 1]
                current = LiquidityZone(
                    price_low=min(current.price_low, next_zone.price_low),
                    price_high=max(current.price_high, next_zone.price_high),
                    zone_type=current.zone_type,
                    strength=max(current.strength, next_zone.strength) * 1.1,  # Confluence bonus
                    created_at=max(current.created_at, next_zone.created_at),
                    origin=f"{current.origin}+{next_zone.origin}",
                )
                i += 1
            merged.append(current)
            i += 1

    return merged
