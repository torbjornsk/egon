"""
Breakout Strategy -- price breakout of N-candle high/low with EMA trend filter.

Entry: when price breaks above last N candles' high (long) or below last N candles'
low (short), filtered by EMA 9/21 trend direction. No RSI involved.

Exit: trailing stop only (no RSI exit). Positions are managed entirely by SL/TP
and the trailing mechanism in the bot layer.

Inspired by "Pip Scalper" concept: high-frequency breakout entries with tight
trailing stops, capturing momentum moves while cutting losers quickly.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import (
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    TIMEFRAME_MAP, TIMEFRAME_MINUTES,
)

logger = logging.getLogger(__name__)


class BreakoutStrategy:
    """
    N-candle breakout with EMA trend filter.

    All behavior driven by TradingConfig fields:
    - timeframe, magic_number, bot_label, order_comment (identity)
    - breakout_bars (N candles for high/low lookback)
    - breakout_min_atr (minimum ATR filter to avoid dead markets)
    - fast_ema, slow_ema (trend filter: 9/21 default)
    - enable_shorts (direction control)
    - breakout_re_entry_bars (cooldown bars after exit before allowing re-entry)
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{config.bot_label}")

        # Track last breakout direction to prevent immediate re-entries
        self._last_breakout_bar: int = -999
        self._bars_processed: int = 0

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

    # -- Entry logic ----------------------------------------------------------

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        """
        Check for breakout entry signals.

        Long: last closed candle breaks above highest high of N candles before it
        Short: last closed candle breaks below lowest low of N candles before it

        Uses df.iloc[-2] (last closed candle) as the signal candle, since
        df.iloc[-1] is the current forming candle at evaluation time.
        """
        self._bars_processed += 1

        n = self.config.breakout_bars
        if len(df) < n + 3:
            return None

        # Signal candle = last CLOSED candle (iloc[-2])
        # Current forming candle is iloc[-1] and not reliable for close-based signals
        signal_candle = df.iloc[-2]
        lookback = df.iloc[-(n + 2):-2]  # N candles BEFORE the signal candle

        # ATR filter: skip dead markets (use signal candle's ATR)
        current_atr = signal_candle.get('ATR', 0)
        if current_atr < self.config.breakout_min_atr:
            return None

        # Re-entry cooldown: wait N bars after last breakout signal
        bars_since_last = self._bars_processed - self._last_breakout_bar
        if bars_since_last <= self.config.breakout_re_entry_bars:
            return None

        has_long = context.get('has_long', False)
        has_short = context.get('has_short', False)

        highest_high = lookback['high'].max()
        lowest_low = lookback['low'].min()

        close = signal_candle['close']
        is_uptrend = signal_candle.get('uptrend', False)
        is_downtrend = signal_candle.get('downtrend', False)

        # Long breakout: signal candle closed above N-bar high, with uptrend
        if close > highest_high and is_uptrend and not has_long:
            self._last_breakout_bar = self._bars_processed
            self.logger.info(
                f"[BREAKOUT] LONG: close ${close:.2f} > {n}-bar high ${highest_high:.2f}, "
                f"ATR=${current_atr:.2f}, EMA trend=UP"
            )
            return {'direction': 'LONG'}

        # Short breakout: signal candle closed below N-bar low, with downtrend
        if self.config.enable_shorts and close < lowest_low and is_downtrend and not has_short:
            self._last_breakout_bar = self._bars_processed
            self.logger.info(
                f"[BREAKOUT] SHORT: close ${close:.2f} < {n}-bar low ${lowest_low:.2f}, "
                f"ATR=${current_atr:.2f}, EMA trend=DOWN"
            )
            return {'direction': 'SHORT'}

        return None

    # -- Exit logic -----------------------------------------------------------

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        """
        Breakout strategy has NO candle-based exit logic.

        All exits are handled by:
        - Stop loss (placed at entry)
        - Trailing stop (managed by the bot's trailing logic)
        - Take profit (if configured)

        This method always returns False. The BaseTradingBot's trailing
        mechanism handles the exit.
        """
        return False, ""

    # -- State for GUI --------------------------------------------------------

    def get_strategy_state(self, df: pd.DataFrame) -> dict:
        """
        Return breakout-specific state for GUI display.

        Shows: N-bar high/low levels, current ATR, trend direction,
        and whether conditions are met for entry.
        """
        n = self.config.breakout_bars
        if df is None or len(df) < n + 3:
            return {}

        # Use last closed candle as reference (same as check_entry)
        signal_candle = df.iloc[-2]
        lookback = df.iloc[-(n + 2):-2]

        highest_high = float(lookback['high'].max())
        lowest_low = float(lookback['low'].min())
        current_atr = float(signal_candle.get('ATR', 0))
        close = float(signal_candle['close'])
        is_uptrend = bool(signal_candle.get('uptrend', False))
        is_downtrend = bool(signal_candle.get('downtrend', False))

        # Distance to breakout levels (from current forming candle's close)
        current_close = float(df.iloc[-1]['close'])
        dist_to_high = highest_high - current_close
        dist_to_low = current_close - lowest_low

        return {
            'breakout_high': highest_high,
            'breakout_low': lowest_low,
            'close': current_close,
            'atr': current_atr,
            'uptrend': is_uptrend,
            'downtrend': is_downtrend,
            'dist_to_high': dist_to_high,
            'dist_to_low': dist_to_low,
            'atr_filter_ok': current_atr >= self.config.breakout_min_atr,
            'bars_since_signal': self._bars_processed - self._last_breakout_bar,
        }
