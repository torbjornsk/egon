"""
Breakout Strategy -- price breakout of N-candle high/low with EMA trend filter.

Entry: tick-based. Breakout levels are recalculated each candle. Between candles,
live price is checked every second -- the moment it crosses the level, entry fires.

Exit: trailing stop only (no RSI exit). Positions are managed entirely by SL/TP
and the trailing mechanism in the bot layer.

Inspired by "Pip Scalper" concept: high-frequency breakout entries with tight
trailing stops, capturing momentum moves while cutting losers quickly.
"""

import logging

import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import (
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    TIMEFRAME_MAP, TIMEFRAME_MINUTES,
)

logger = logging.getLogger(__name__)


class BreakoutStrategy:
    """
    N-candle breakout with EMA trend filter and tick-based entry.

    On each candle close:
    - Compute breakout high/low from last N candles
    - Check trend direction (EMA 9/21)
    - Arm levels if conditions are met

    Every second (tick check):
    - If bid crosses breakout high -> LONG entry
    - If ask crosses breakout low -> SHORT entry

    Config fields:
    - breakout_bars: N candles for high/low lookback
    - breakout_min_atr: minimum ATR filter to avoid dead markets
    - fast_ema, slow_ema: trend filter (9/21 default)
    - enable_shorts: direction control
    - breakout_re_entry_bars: cooldown bars after signal before allowing re-entry
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{config.bot_label}")

        # Track bar count for re-entry cooldown
        self._last_breakout_bar: int = -999
        self._bars_processed: int = 0

        # Armed breakout levels (recalculated each candle)
        self._breakout_high: float | None = None
        self._breakout_low: float | None = None
        self._trend_up: bool = False
        self._trend_down: bool = False
        self._levels_armed: bool = False

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

    # -- Candle-based: recalculate levels each candle -------------------------

    def update_levels(self, df: pd.DataFrame):
        """
        Recalculate breakout levels on each new candle.

        Called by the bot's trading_logic() on candle close.
        Sets _breakout_high/_breakout_low for tick-based fill checks.
        """
        self._bars_processed += 1

        n = self.config.breakout_bars
        if len(df) < n + 3:
            self._levels_armed = False
            return

        # Use last closed candle for trend/ATR, lookback is N candles before it
        signal_candle = df.iloc[-2]
        lookback = df.iloc[-(n + 2):-2]

        # ATR filter
        current_atr = signal_candle.get('ATR', 0)
        if current_atr < self.config.breakout_min_atr:
            self._levels_armed = False
            self.logger.info(
                f"[BREAKOUT] Levels disarmed: ATR ${current_atr:.2f} "
                f"< min ${self.config.breakout_min_atr:.2f}"
            )
            return

        # Re-entry cooldown
        bars_since_last = self._bars_processed - self._last_breakout_bar
        if bars_since_last <= self.config.breakout_re_entry_bars:
            self._levels_armed = False
            return

        # Calculate levels
        self._breakout_high = float(lookback['high'].max())
        self._breakout_low = float(lookback['low'].min())
        self._trend_up = bool(signal_candle.get('uptrend', False))
        self._trend_down = bool(signal_candle.get('downtrend', False))
        self._levels_armed = True

        self.logger.info(
            f"[BREAKOUT] Levels armed: high=${self._breakout_high:.2f}, "
            f"low=${self._breakout_low:.2f}, "
            f"trend={'UP' if self._trend_up else 'DOWN' if self._trend_down else 'FLAT'}, "
            f"lookback={n} bars (iloc[-{n+2}:-2])"
        )

    # -- Tick-based: check live price against armed levels --------------------

    def check_tick_entry(self, bid: float, ask: float, has_long: bool, has_short: bool) -> dict | None:
        """
        Check if live price has crossed a breakout level.

        Called every second by the bot's main loop.
        Returns {'direction': 'LONG'/'SHORT'} or None.

        For longs: bid must cross above breakout_high (in an uptrend)
        For shorts: ask must cross below breakout_low (in a downtrend)
        """
        if not self._levels_armed:
            return None

        # Long breakout: price crosses above N-bar high
        if (self._breakout_high is not None
                and bid > self._breakout_high
                and self._trend_up
                and not has_long):
            self._last_breakout_bar = self._bars_processed
            self._levels_armed = False  # One signal per level set
            self.logger.info(
                f"[BREAKOUT FILL] LONG: bid ${bid:.2f} > "
                f"{self.config.breakout_bars}-bar high ${self._breakout_high:.2f}"
            )
            return {'direction': 'LONG'}

        # Short breakout: price crosses below N-bar low
        if (self.config.enable_shorts
                and self._breakout_low is not None
                and ask < self._breakout_low
                and self._trend_down
                and not has_short):
            self._last_breakout_bar = self._bars_processed
            self._levels_armed = False  # One signal per level set
            self.logger.info(
                f"[BREAKOUT FILL] SHORT: ask ${ask:.2f} < "
                f"{self.config.breakout_bars}-bar low ${self._breakout_low:.2f}"
            )
            return {'direction': 'SHORT'}

        return None

    # -- Candle-based entry (kept as fallback, but no longer primary) ----------

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        """
        Candle-close fallback entry -- only fires if tick-based didn't trigger.

        This handles the case where the breakout happened during the candle
        but check_tick_entry wasn't called (e.g., bot just started).
        """
        # If levels are still armed, the tick check hasn't fired yet
        # Don't double-enter from candle logic
        if self._levels_armed:
            return None

        # This is intentionally a no-op now -- tick-based is primary.
        # The candle logic only recalculates levels via update_levels().
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

        All exits are handled by trailing stop + SL/TP in the bot layer.
        """
        return False, ""

    # -- State for GUI --------------------------------------------------------

    def get_strategy_state(self, df: pd.DataFrame) -> dict:
        """Return breakout-specific state for GUI display."""
        n = self.config.breakout_bars
        if df is None or len(df) < n + 3:
            return {}

        signal_candle = df.iloc[-2]
        current_close = float(df.iloc[-1]['close'])
        current_atr = float(signal_candle.get('ATR', 0))

        breakout_high = self._breakout_high or 0
        breakout_low = self._breakout_low or 0

        dist_to_high = breakout_high - current_close if breakout_high else 0
        dist_to_low = current_close - breakout_low if breakout_low else 0

        return {
            'breakout_high': breakout_high,
            'breakout_low': breakout_low,
            'close': current_close,
            'atr': current_atr,
            'uptrend': self._trend_up,
            'downtrend': self._trend_down,
            'dist_to_high': dist_to_high,
            'dist_to_low': dist_to_low,
            'atr_filter_ok': current_atr >= self.config.breakout_min_atr,
            'bars_since_signal': self._bars_processed - self._last_breakout_bar,
            'levels_armed': self._levels_armed,
        }
