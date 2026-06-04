"""
M5 Sniper Strategy -- RSI scalping with limit order pre-placement.

Instead of waiting for candle close to detect RSI signals, this strategy:
1. Calculates what price would trigger RSI buy/sell thresholds
2. Places limit orders at those levels to catch intra-candle wicks
3. Falls back to market orders on candle close if RSI signal fires normally

Benefits over standard M5:
- No spread cost when limit order fills (providing liquidity)
- Catches intra-candle dips/spikes that close-only RSI misses
- Better entry prices (buying the wick, not the close)
- Same signal logic as fallback (never misses a valid signal)
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M5
from src.core.rsi_levels import calculate_rsi_buy_price, calculate_rsi_sell_price

logger = logging.getLogger(__name__)


@dataclass
class SniperOrder:
    """A pending limit order targeting an RSI level."""
    direction: str          # "LONG" or "SHORT"
    entry_price: float
    sl: float
    tp: float
    placed_at: datetime
    filled: bool = False
    cancelled: bool = False


class M5SniperStrategy:
    """
    M5 RSI scalping with limit order pre-placement.

    Each candle:
    1. Calculate RSI trigger prices for buy and sell
    2. Place limit orders at those levels
    3. On candle close: if not filled, check RSI normally (market order fallback)
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger("src.bot.M5S")

        # Pending sniper orders (managed by the bot, not MT5 pending orders)
        self.pending_buy: SniperOrder | None = None
        self.pending_sell: SniperOrder | None = None

    @property
    def timeframe_minutes(self) -> int:
        return 5

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M5

    @property
    def magic_number(self) -> int:
        return 234050

    @property
    def bot_label(self) -> str:
        return "M5S"

    @property
    def order_comment(self) -> str:
        return "m5_sniper"

    # ── RSI level calculation ───────────────────────────────────────

    def calculate_sniper_levels(self, df: pd.DataFrame) -> dict:
        """
        Calculate limit order prices for RSI buy/sell thresholds.

        Uses a MORE EXTREME RSI level than the config threshold for the
        limit order. This places the order deeper (closer to actual bottoms)
        while the fallback market order still uses the config threshold.
        """
        # Sniper aims deeper than the standard threshold
        # Config rsi_buy=35 -> sniper targets RSI 25 (deeper bottom)
        # Config rsi_sell=65 -> sniper targets RSI 75 (higher top)
        sniper_buy_rsi = max(15, self.config.rsi_buy - 10)
        sniper_sell_rsi = min(85, self.config.rsi_sell + 10)

        buy_price = calculate_rsi_buy_price(df, sniper_buy_rsi, self.config.rsi_period)
        sell_price = calculate_rsi_sell_price(df, sniper_sell_rsi, self.config.rsi_period)

        return {
            'buy_price': buy_price,
            'sell_price': sell_price,
        }

    # ── Check if limit orders filled (called by bot each second) ────

    def check_sniper_fills(self, bid: float, ask: float = 0) -> SniperOrder | None:
        """
        Check if current price has reached a sniper level.

        For buys: fills when bid drops to entry (we buy at ask, but the
        signal is based on mid/bid reaching the level).
        For sells: fills when ask rises to entry.
        """
        if ask <= 0:
            ask = bid  # Fallback if only one price provided

        if self.pending_buy and not self.pending_buy.filled and not self.pending_buy.cancelled:
            if bid <= self.pending_buy.entry_price:
                self.pending_buy.filled = True
                self.logger.info(
                    f"[SNIPER FILL] LONG @ ${self.pending_buy.entry_price:.2f} "
                    f"(bid touched ${bid:.2f})"
                )
                return self.pending_buy

        if self.pending_sell and not self.pending_sell.filled and not self.pending_sell.cancelled:
            if ask >= self.pending_sell.entry_price:
                self.pending_sell.filled = True
                self.logger.info(
                    f"[SNIPER FILL] SHORT @ ${self.pending_sell.entry_price:.2f} "
                    f"(ask touched ${ask:.2f})"
                )
                return self.pending_sell

        return None

    # ── Standard entry (fallback on candle close) ───────────────────

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        """
        Standard RSI entry check (candle close fallback).

        Only fires if the sniper limit order didn't fill during the candle.
        """
        latest = df.iloc[-1]
        has_long = context.get('has_long', False)
        has_short = context.get('has_short', False)

        # If sniper already filled this candle, don't double-enter
        if self.pending_buy and self.pending_buy.filled:
            return None
        if self.pending_sell and self.pending_sell.filled:
            return None

        # Standard RSI check
        if latest['RSI'] < self.config.rsi_buy:
            if has_short:
                return None
            self.logger.info(f"[FALLBACK] LONG SIGNAL: RSI={latest['RSI']:.2f} < {self.config.rsi_buy}")
            return {'direction': 'LONG'}

        if self.config.enable_shorts and latest['RSI'] > self.config.rsi_sell:
            if has_long:
                return None
            if latest.get('downtrend', False) or not self.config.short_requires_downtrend:
                self.logger.info(f"[FALLBACK] SHORT SIGNAL: RSI={latest['RSI']:.2f} > {self.config.rsi_sell}")
                return {'direction': 'SHORT'}

        return None

    # ── Exit (wave-based: exit when RSI returns to neutral) ───────

    def get_exit_rsi(self, df: pd.DataFrame, direction: str) -> float:
        """
        Calculate the adaptive RSI exit threshold based on trend strength.

        Uses EMA divergence (fast - slow) normalized by ATR to gauge trend strength.
        Only shifts from 50 when there's a meaningful trend (> 0.5 ATR divergence).

        Mild/sideways: exit at RSI 50 (standard mean revert)
        Strong trend (> 0.5 ATR divergence): shift to 45 or 55
        """
        latest = df.iloc[-1]
        ema_fast = latest.get('ema_fast', 0)
        ema_slow = latest.get('ema_slow', 0)
        atr = latest.get('ATR', 1)

        if atr <= 0:
            return 50.0

        # Normalized EMA divergence: positive = uptrend, negative = downtrend
        # Typical range: -2 to +2 ATR
        divergence = (ema_fast - ema_slow) / atr

        if direction == 'LONG':
            if divergence < -0.5:
                # Strong downtrend: counter-trend long, exit earlier
                return 45.0
            elif divergence > 0.5:
                # Strong uptrend: with-trend long, let it run
                return 55.0
            else:
                return 50.0
        else:  # SHORT
            if divergence > 0.5:
                # Strong uptrend: counter-trend short, exit earlier
                return 55.0
            elif divergence < -0.5:
                # Strong downtrend: with-trend short, let it run
                return 45.0
            else:
                return 50.0

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        latest = df.iloc[-1]
        profit = context.get('current_profit', 0)

        if position.type == ORDER_TYPE_BUY:
            # Trend-adaptive mean revert exit
            exit_rsi = self.get_exit_rsi(df, 'LONG')
            if latest['RSI'] >= exit_rsi:
                return True, f"Mean revert exit (RSI {latest['RSI']:.1f} >= {exit_rsi:.0f})"

            # Safety: RSI extreme exit
            threshold = self.config.rsi_exit_long
            if latest['RSI'] > threshold:
                return True, f"RSI exit ({latest['RSI']:.2f} > {threshold})"
        else:
            # Trend-adaptive mean revert exit
            exit_rsi = self.get_exit_rsi(df, 'SHORT')
            if latest['RSI'] <= exit_rsi:
                return True, f"Mean revert exit (RSI {latest['RSI']:.1f} <= {exit_rsi:.0f})"

            # Safety: RSI extreme exit
            threshold = self.config.rsi_exit_short
            if latest['RSI'] < threshold:
                return True, f"RSI exit ({latest['RSI']:.2f} < {threshold})"

        return False, ""

    # ── Order lifecycle ─────────────────────────────────────────────

    def cancel_pending(self):
        """Cancel all pending sniper orders (called on new candle)."""
        if self.pending_buy and not self.pending_buy.filled:
            self.pending_buy.cancelled = True
        if self.pending_sell and not self.pending_sell.filled:
            self.pending_sell.cancelled = True
        self.pending_buy = None
        self.pending_sell = None
