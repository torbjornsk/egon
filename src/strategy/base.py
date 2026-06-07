"""
Trading strategy Protocol.

Strategies define ONLY entry and exit logic. Everything else
(MT5 connection, risk, position tracking) lives in the bot/core layers.
"""

from typing import Protocol, runtime_checkable

import pandas as pd

from src.core.config import TradingConfig


@runtime_checkable
class TradingStrategy(Protocol):
    """Protocol for trading strategies."""

    @property
    def timeframe_minutes(self) -> int:
        """Candle timeframe in minutes (1 for M1, 5 for M5)."""
        ...

    @property
    def mt5_timeframe(self) -> int:
        """MT5 timeframe constant."""
        ...

    @property
    def magic_number(self) -> int:
        """Unique magic number for this strategy's orders."""
        ...

    @property
    def bot_label(self) -> str:
        """Short label for logging and exit reasons (e.g. 'M1', 'M5')."""
        ...

    @property
    def order_comment(self) -> str:
        """Comment string for MT5 orders."""
        ...

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        """
        Check for entry signals.

        Args:
            df: OHLCV data with indicators computed
            open_positions: currently open positions (MT5 objects)
            context: dict with 'can_enter', 'has_long', 'has_short', etc.

        Returns:
            dict with 'direction' ('LONG'/'SHORT'), or None if no signal.
        """
        ...

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        """
        Check for exit signals on a single position.

        Args:
            df: OHLCV data with indicators
            position: MT5 position object
            context: dict with 'current_profit', 'minutes_held', etc.

        Returns:
            (should_close, reason)
        """
        ...
