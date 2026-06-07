"""
Unified Sniper Strategy -- configurable RSI scalping with limit order pre-placement.

Replaces the separate M1/M5/M15 sniper strategies with a single class
that reads all parameters from config. Timeframe, RSI levels, sniper offsets,
exit RSI behavior -- everything is configurable.

Usage: create different config JSON files for different variants:
  - M1 sniper: timeframe=M1, sniper_rsi_offset=7, magic_number=234101
  - M5 sniper: timeframe=M5, sniper_rsi_offset=10, magic_number=234050
  - M15 sniper: timeframe=M15, sniper_rsi_offset=12, magic_number=234115
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import (
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    TIMEFRAME_MAP, TIMEFRAME_MINUTES,
)
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


class SniperStrategy:
    """
    Configurable RSI scalping with limit order pre-placement.

    All behavior driven by TradingConfig fields:
    - timeframe, magic_number, bot_label, order_comment (identity)
    - rsi_buy, rsi_sell, sniper_rsi_offset (entry levels)
    - rsi_exit_long, rsi_exit_short (exit levels)
    - exit_rsi_trend_threshold, exit_rsi_trend_shift (adaptive exit)
    - enable_shorts, short_requires_downtrend (direction control)
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{config.bot_label}")

        # Pending sniper orders (managed by the bot, not MT5 pending orders)
        self.pending_buy: SniperOrder | None = None
        self.pending_sell: SniperOrder | None = None

    @property
    def timeframe_minutes(self) -> int:
        return TIMEFRAME_MINUTES.get(self.config.timeframe, 5)

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_MAP.get(self.config.timeframe, 5)

    @property
    def magic_number(self) -> int:
        return self.config.magic_number

    @property
    def bot_label(self) -> str:
        return self.config.bot_label

    @property
    def order_comment(self) -> str:
        return self.config.order_comment

    # ── RSI level calculation ───────────────────────────────────────

    def calculate_sniper_levels(self, df: pd.DataFrame) -> dict:
        """
        Calculate limit order prices for RSI buy/sell thresholds.

        Uses sniper_rsi_offset to place orders deeper than the standard
        entry threshold, catching intra-candle wicks.
        """
        offset = self.config.sniper_rsi_offset
        # Clamp to valid RSI range (0-100)
        sniper_buy_rsi = max(0, self.config.rsi_buy - offset)
        sniper_sell_rsi = min(100, self.config.rsi_sell + offset)

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

        For buys: fills when bid drops to entry price.
        For sells: fills when ask rises to entry price.
        """
        if ask <= 0:
            ask = bid

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
            self.logger.info(
                f"[FALLBACK] LONG SIGNAL: RSI={latest['RSI']:.2f} < {self.config.rsi_buy}"
            )
            return {'direction': 'LONG'}

        if self.config.enable_shorts and latest['RSI'] > self.config.rsi_sell:
            if has_long:
                return None
            if latest.get('downtrend', False) or not self.config.short_requires_downtrend:
                self.logger.info(
                    f"[FALLBACK] SHORT SIGNAL: RSI={latest['RSI']:.2f} > {self.config.rsi_sell}"
                )
                return {'direction': 'SHORT'}

        return None

    # ── Exit (wave-based: exit when RSI returns to neutral) ───────

    def get_exit_rsi(self, df: pd.DataFrame, direction: str) -> float:
        """
        Calculate the exit RSI target.

        If adaptive_exit_enabled: shifts the base exit_rsi based on trend strength.
        Otherwise: returns the fixed exit_rsi value.
        """
        base_exit = self.config.exit_rsi

        if not self.config.adaptive_exit_enabled:
            return base_exit

        latest = df.iloc[-1]
        ema_fast = latest.get('ema_fast', 0)
        ema_slow = latest.get('ema_slow', 0)
        atr = latest.get('ATR', 1)

        if atr <= 0:
            return base_exit

        # Normalized EMA divergence: positive = uptrend, negative = downtrend
        divergence = (ema_fast - ema_slow) / atr
        threshold = self.config.exit_rsi_trend_threshold
        shift = self.config.exit_rsi_trend_shift

        if direction == 'LONG':
            if divergence < -threshold:
                # Strong downtrend: counter-trend long, exit earlier
                return base_exit - shift
            elif divergence > threshold:
                # Strong uptrend: with-trend long, let it run
                return base_exit + shift
            else:
                return base_exit
        else:  # SHORT
            if divergence > threshold:
                # Strong uptrend: counter-trend short, exit earlier
                return base_exit + shift
            elif divergence < -threshold:
                # Strong downtrend: with-trend short, let it run
                return base_exit - shift
            else:
                return base_exit

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        """Check for exit signals on a position using mean-revert logic."""
        latest = df.iloc[-1]

        if position.type == ORDER_TYPE_BUY:
            exit_rsi = self.get_exit_rsi(df, 'LONG')
            if latest['RSI'] >= exit_rsi:
                return True, f"Mean revert exit (RSI {latest['RSI']:.1f} >= {exit_rsi:.0f})"
        else:
            exit_rsi = self.get_exit_rsi(df, 'SHORT')
            if latest['RSI'] <= exit_rsi:
                return True, f"Mean revert exit (RSI {latest['RSI']:.1f} <= {exit_rsi:.0f})"

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
