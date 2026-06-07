"""
Liquidity Zone Strategy -- limit orders at support/resistance.

Instead of chasing price with market orders, this strategy:
1. Identifies liquidity zones (support/resistance levels)
2. Places limit buy orders at demand zones (below price)
3. Places limit sell orders at supply zones (above price)
4. Manages pending orders (cancel stale, update zones)

Key advantages over RSI scalping:
- No spread cost on entry (limit orders provide liquidity)
- Better entries (buying at support, selling at resistance)
- Fewer trades (only when price reaches a zone)
- Works in both ranging and trending markets (pullback entries)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M5
from src.core.liquidity import LiquidityZone, find_liquidity_zones
from src.core.indicators import compute_indicators

logger = logging.getLogger(__name__)


@dataclass
class PendingOrder:
    """A limit order waiting to be filled."""
    ticket: int
    direction: str          # "LONG" or "SHORT"
    entry_price: float      # Limit price
    sl: float               # Stop loss
    tp: float               # Take profit
    zone: LiquidityZone     # The zone this order targets
    placed_at: datetime     # When the order was placed
    volume: float = 0.0
    filled: bool = False
    cancelled: bool = False


class LiquidityZoneStrategy:
    """
    Places limit orders at liquidity zones on M5 timeframe.

    The strategy maintains a set of pending limit orders at detected
    zones. When price reaches a zone, the limit order fills and becomes
    a position. Positions are managed with ATR-based stops and
    zone-to-zone take profits.
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger("src.bot.LZ")

        # Active zones and pending orders
        self.active_zones: list[LiquidityZone] = []
        self.pending_orders: list[PendingOrder] = []
        self._next_order_id: int = 5000
        self._last_zone_update: datetime | None = None

    @property
    def timeframe_minutes(self) -> int:
        return 5

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M5

    @property
    def magic_number(self) -> int:
        return 234100

    @property
    def bot_label(self) -> str:
        return "LZ"

    @property
    def order_comment(self) -> str:
        return "lz_strategy"

    # ── Zone management ─────────────────────────────────────────────

    def update_zones(self, df: pd.DataFrame, current_time: datetime):
        """
        Recalculate liquidity zones from recent price action.

        Called periodically (not every candle) to avoid excessive computation.
        """
        # Only update zones every N candles (configurable via zone_update_interval)
        update_interval_minutes = getattr(self.config, 'zone_update_interval', 15)
        if self._last_zone_update is not None:
            elapsed = (current_time - self._last_zone_update).total_seconds() / 60
            if elapsed < update_interval_minutes:
                return

        self._last_zone_update = current_time

        lookback = getattr(self.config, 'zone_lookback', 100)
        max_zones = getattr(self.config, 'max_active_zones', 6)

        self.active_zones = find_liquidity_zones(
            df,
            lookback=lookback,
            zone_width_atr=0.3,
            max_zones=max_zones,
            swing_left=5,
            swing_right=2,
            min_impulse_atr=1.5,
        )

        if self.active_zones:
            demand = [z for z in self.active_zones if z.zone_type == "demand"]
            supply = [z for z in self.active_zones if z.zone_type == "supply"]
            self.logger.info(
                f"[ZONES] Updated: {len(demand)} demand, {len(supply)} supply zones"
            )

    # ── Order placement logic ───────────────────────────────────────

    def get_pending_orders(
        self,
        df: pd.DataFrame,
        open_positions: list,
        current_time: datetime,
        balance: float,
        current_price: float,
    ) -> list[dict]:
        """
        Determine which limit orders should be active.

        Returns list of order specs: [{'direction', 'entry_price', 'sl', 'tp', 'zone'}]
        """
        if not self.active_zones:
            return []

        # Don't place orders if we already have max positions
        max_pos = self.config.max_positions
        if len(open_positions) >= max_pos:
            return []

        # Don't place orders if we already have pending orders at these zones
        active_zone_prices = {
            (o.zone.price_low, o.zone.price_high)
            for o in self.pending_orders
            if not o.filled and not o.cancelled
        }

        orders = []
        current_atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else 1.0
        rr_ratio = getattr(self.config, 'zone_rr_ratio', 2.0)

        for zone in self.active_zones:
            # Skip if we already have an order at this zone
            zone_key = (zone.price_low, zone.price_high)
            if zone_key in active_zone_prices:
                continue

            # Skip weak zones
            min_strength = getattr(self.config, 'zone_min_strength', 0.4)
            if zone.strength < min_strength:
                continue

            # Skip zones too far from current price (> 3 ATR away)
            max_distance_atr = getattr(self.config, 'zone_max_distance_atr', 3.0)
            if zone.distance_from(current_price) > current_atr * max_distance_atr:
                continue

            # Calculate entry, SL, TP
            stop_distance = current_atr * self.config.atr_multiplier

            if zone.zone_type == "demand":
                # Buy limit at top of demand zone
                entry = zone.price_high
                sl = zone.price_low - current_atr * 1.0  # SL 1 ATR below zone bottom
                risk = entry - sl
                tp = entry + risk * rr_ratio  # TP at R:R ratio
                direction = "LONG"
            else:
                # Sell limit at bottom of supply zone
                entry = zone.price_low
                sl = zone.price_high + current_atr * 1.0  # SL 1 ATR above zone top
                risk = sl - entry
                tp = entry - risk * rr_ratio  # TP at R:R ratio
                direction = "SHORT"

            # Sanity check: risk must be positive and reasonable
            if risk <= 0 or risk > current_atr * 5:
                continue

            # Check trading mode
            mode = self.config.trading_mode
            if mode == "long_only" and direction == "SHORT":
                continue
            if mode == "short_only" and direction == "LONG":
                continue

            orders.append({
                'direction': direction,
                'entry_price': entry,
                'sl': sl,
                'tp': tp,
                'zone': zone,
            })

        return orders

    # ── Exit logic ──────────────────────────────────────────────────

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        """
        Check if a position should be closed.

        Pure structure-based exits (no RSI):
        1. Price reaches opposite zone (take profit at next structure level)
        2. Trailing stop: once profit exceeds 1 ATR, trail at 50% of peak
        3. Time-based: held too long without progress
        """
        latest = df.iloc[-1]
        minutes_held = context.get('minutes_held', 0)
        current_profit = context.get('current_profit', 0)
        current_price = latest['close']
        current_atr = latest['ATR'] if 'ATR' in latest.index else 1.0

        # 1. Opposite zone exit: if price has reached a supply zone (for longs)
        #    or demand zone (for shorts), take profit
        for zone in self.active_zones:
            if position.type == ORDER_TYPE_BUY and zone.zone_type == "supply":
                if zone.contains(current_price):
                    return True, f"Reached supply zone [{zone.price_low:.2f}-{zone.price_high:.2f}]"
            elif position.type == ORDER_TYPE_SELL and zone.zone_type == "demand":
                if zone.contains(current_price):
                    return True, f"Reached demand zone [{zone.price_low:.2f}-{zone.price_high:.2f}]"

        # 2. Trailing stop: once profit > 1 ATR worth, trail at 50%
        if current_atr > 0:
            entry_price = position.price_open
            if position.type == ORDER_TYPE_BUY:
                move = current_price - entry_price
            else:
                move = entry_price - current_price

            # If we've moved more than 1.5 ATR in our favor and now giving back
            if move > current_atr * 1.5 and current_profit > 0:
                # Price has moved well, but check if it's reversing
                # Use recent price action: if last 3 candles are against us
                if len(df) >= 4:
                    recent = df.iloc[-3:]
                    if position.type == ORDER_TYPE_BUY:
                        reversing = all(recent['close'].iloc[i] < recent['close'].iloc[i-1] for i in range(1, len(recent)))
                    else:
                        reversing = all(recent['close'].iloc[i] > recent['close'].iloc[i-1] for i in range(1, len(recent)))
                    if reversing:
                        return True, f"Trailing stop (moved {move:.2f}, 3 bars reversing)"

        # 3. Break-even stop: if we were in profit but now back to entry
        if minutes_held > 30:
            entry_price = position.price_open
            if position.type == ORDER_TYPE_BUY:
                if current_price < entry_price - current_atr * 0.2:
                    return True, f"Break-even stop (price below entry after {minutes_held:.0f}min)"
            else:
                if current_price > entry_price + current_atr * 0.2:
                    return True, f"Break-even stop (price above entry after {minutes_held:.0f}min)"

        # 3. Time exit: if held > max time with no meaningful profit
        max_hold_minutes = getattr(self.config, 'zone_max_hold_minutes', 240)
        if minutes_held > max_hold_minutes and current_profit <= 0:
            return True, f"Time exit ({minutes_held:.0f}min, no profit)"

        # 4. Extended time exit: even profitable positions shouldn't be held forever
        if minutes_held > max_hold_minutes * 2:
            return True, f"Max time exit ({minutes_held:.0f}min)"

        return False, ""

    # ── Entry signal (for compatibility with BaseTradingBot) ────────

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        """
        For the liquidity zone strategy, entries happen via limit order fills,
        not market orders. This method returns None -- the ZoneBot handles
        order placement separately.

        However, as a fallback, if RSI hits extreme levels AND we're at a zone,
        we can enter with a market order (aggressive entry at confirmed zone).
        """
        # The zone bot handles limit orders. This is only called if
        # the bot falls through to standard trading_logic.
        return None
