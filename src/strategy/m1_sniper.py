"""
M1 Sniper Strategy -- RSI scalping with limit order pre-placement on M1 timeframe.

Same principles as M5 Sniper but on 1-minute candles:
- Faster signals, more trades, tighter stops
- Places limit orders at RSI trigger levels
- Falls back to market orders on candle close
"""

import logging

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M1
from src.core.rsi_levels import calculate_rsi_buy_price, calculate_rsi_sell_price
from src.strategy.m5_sniper import M5SniperStrategy, SniperOrder

logger = logging.getLogger(__name__)


class M1SniperStrategy(M5SniperStrategy):
    """
    M1 RSI sniper -- identical logic to M5 sniper but on 1-minute candles.

    Differences from M5:
    - Timeframe: M1 (faster signals)
    - Magic number: 234101
    - Tighter sniper offset (RSI -7 instead of -10 for less extreme entries)
    """

    @property
    def timeframe_minutes(self) -> int:
        return 1

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M1

    @property
    def magic_number(self) -> int:
        return 234101

    @property
    def bot_label(self) -> str:
        return "M1S"

    @property
    def order_comment(self) -> str:
        return "m1_sniper"

    def calculate_sniper_levels(self, df: pd.DataFrame) -> dict:
        """
        Calculate limit order prices for M1 RSI thresholds.

        Uses slightly less extreme offset than M5 (RSI -7 instead of -10)
        because M1 moves are smaller and we don't want to miss fills.
        """
        sniper_buy_rsi = max(15, self.config.rsi_buy - 7)
        sniper_sell_rsi = min(85, self.config.rsi_sell + 7)

        buy_price = calculate_rsi_buy_price(df, sniper_buy_rsi, self.config.rsi_period)
        sell_price = calculate_rsi_sell_price(df, sniper_sell_rsi, self.config.rsi_period)

        return {
            'buy_price': buy_price,
            'sell_price': sell_price,
        }
