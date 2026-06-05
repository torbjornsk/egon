"""
M15 Sniper Strategy -- RSI scalping with limit order pre-placement on M15 timeframe.

Same principles as M5 Sniper but on 15-minute candles:
- Fewer trades, larger moves, wider stops
- Places limit orders at RSI trigger levels
- Falls back to market orders on candle close
"""

import logging

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M15
from src.core.rsi_levels import calculate_rsi_buy_price, calculate_rsi_sell_price
from src.strategy.m5_sniper import M5SniperStrategy, SniperOrder

logger = logging.getLogger(__name__)


class M15SniperStrategy(M5SniperStrategy):
    """
    M15 RSI sniper -- identical logic to M5 sniper but on 15-minute candles.

    Differences from M5:
    - Timeframe: M15 (slower signals, bigger moves)
    - Magic number: 234115
    - Wider sniper offset (RSI -12 for deeper entries on bigger swings)
    """

    @property
    def timeframe_minutes(self) -> int:
        return 15

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M15

    @property
    def magic_number(self) -> int:
        return 234115

    @property
    def bot_label(self) -> str:
        return "M15S"

    @property
    def order_comment(self) -> str:
        return "m15_sniper"

    def calculate_sniper_levels(self, df: pd.DataFrame) -> dict:
        """
        Calculate limit order prices for M15 RSI thresholds.

        Uses wider offset than M5 (RSI -12 instead of -10) because M15
        swings are larger and we want to catch deeper wicks.
        """
        sniper_buy_rsi = max(15, self.config.rsi_buy - 12)
        sniper_sell_rsi = min(85, self.config.rsi_sell + 12)

        buy_price = calculate_rsi_buy_price(df, sniper_buy_rsi, self.config.rsi_period)
        sell_price = calculate_rsi_sell_price(df, sniper_sell_rsi, self.config.rsi_period)

        return {
            'buy_price': buy_price,
            'sell_price': sell_price,
        }
