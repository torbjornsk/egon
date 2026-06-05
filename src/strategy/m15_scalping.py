"""
M15 Scalping Strategy -- entry and exit logic.

Slower than M1/M5: RSI-14 with tight 25/75 entry thresholds.
Fewer trades (~2/day), wider stops, lets winners run.
Designed to survive transaction costs ($0.30 spread).
"""

import logging

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL

logger = logging.getLogger(__name__)

# MT5 TIMEFRAME_M15 constant
TIMEFRAME_M15 = 15


class M15ScalpingStrategy:
    """M15 scalping: selective RSI-14 entries, wide exits, ATR stops."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger("src.bot.M15")

    @property
    def timeframe_minutes(self) -> int:
        return 15

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M15

    @property
    def magic_number(self) -> int:
        return 234015

    @property
    def bot_label(self) -> str:
        return "M15"

    @property
    def order_comment(self) -> str:
        return "m15_scalping"

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        latest = df.iloc[-1]
        has_long = context.get('has_long', False)
        has_short = context.get('has_short', False)

        # LONG: RSI below buy threshold
        if latest['RSI'] < self.config.rsi_buy:
            if has_short:
                self.logger.info("LONG signal skipped -- already have SHORT")
                return None
            self.logger.info(f"LONG SIGNAL: RSI={latest['RSI']:.2f} < {self.config.rsi_buy}")
            return {'direction': 'LONG'}

        # SHORT: RSI above sell threshold
        if self.config.enable_shorts and latest['RSI'] > self.config.rsi_sell:
            if has_long:
                self.logger.info("SHORT signal skipped -- already have LONG")
                return None
            self.logger.info(f"SHORT SIGNAL: RSI={latest['RSI']:.2f} > {self.config.rsi_sell}")
            return {'direction': 'SHORT'}

        return None

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        latest = df.iloc[-1]

        if position.type == ORDER_TYPE_BUY:
            threshold = self.config.rsi_exit_long
            if latest['RSI'] > threshold:
                return True, f"RSI exit ({latest['RSI']:.2f} > {threshold})"
        else:
            threshold = self.config.rsi_exit_short
            if latest['RSI'] < threshold:
                return True, f"RSI exit ({latest['RSI']:.2f} < {threshold})"

        return False, ""
