"""
M5 Scalping Strategy -- entry and exit logic only.

Features:
- RSI-based entries (oversold buy, overbought + downtrend sell)
- Simple RSI exits (no confirmation)
- Profit protection with hardcoded time-based tightening
- Standard cooldown (no smart skip)
"""

import logging

import pandas as pd

from src.core.config import TradingConfig
from src.core.mt5_client import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M5

logger = logging.getLogger(__name__)


class M5ScalpingStrategy:
    """M5 scalping: wider RSI bands, longer holds, simpler exits."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger("src.bot.M5")

    @property
    def timeframe_minutes(self) -> int:
        return 5

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M5

    @property
    def magic_number(self) -> int:
        return 234000

    @property
    def bot_label(self) -> str:
        return "M5"

    @property
    def order_comment(self) -> str:
        return "m5_strategy"

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        latest = df.iloc[-1]
        has_long = context.get('has_long', False)
        has_short = context.get('has_short', False)

        # LONG
        if latest['RSI'] < self.config.rsi_buy:
            if has_short:
                self.logger.info("LONG signal detected but skipping -- already have SHORT position(s)")
                return None
            self.logger.info(f"LONG SIGNAL: RSI={latest['RSI']:.2f}")
            return {'direction': 'LONG'}

        # SHORT
        if (self.config.enable_shorts
                and latest['RSI'] > self.config.rsi_sell
                and latest['downtrend']):
            if has_long:
                self.logger.info("SHORT signal detected but skipping -- already have LONG position(s)")
                return None
            self.logger.info(f"SHORT SIGNAL: RSI={latest['RSI']:.2f}")
            return {'direction': 'SHORT'}

        return None

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        latest = df.iloc[-1]

        # Simple RSI exits (no confirmation for M5)
        if position.type == ORDER_TYPE_BUY:
            if latest['RSI'] > self.config.rsi_sell:
                return True, f"RSI overbought ({latest['RSI']:.2f} > {self.config.rsi_sell})"
        else:
            if latest['RSI'] < self.config.rsi_buy:
                return True, f"RSI oversold ({latest['RSI']:.2f} < {self.config.rsi_buy})"

        return False, ""
