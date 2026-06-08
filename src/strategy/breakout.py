"""
Breakout Strategy -- MT5 stop orders for instant breakout entry.

On each candle close:
- Compute breakout high/low from last N candles
- Place BUY STOP above the high and SELL STOP below the low
- SL placed at/near the breakout level (failed breakout = small loss)
- Cancel and replace orders each candle as levels shift

MT5 fills the stop order server-side the instant price touches it -- zero latency.
Trailing stop runs at configurable interval (default 100ms) for fast profit locking.
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
    N-candle breakout with EMA trend filter and MT5 stop order entry.

    On each candle close:
    - Compute breakout levels from last N candles
    - Cancel previous pending orders
    - Place new BUY STOP / SELL STOP at breakout level + buffer
    - SL at the breakout level itself (if it goes back through, breakout failed)

    Config fields:
    - breakout_bars: N candles for high/low lookback
    - breakout_entry_buffer_atr: offset above/below level (in ATR multiples)
    - breakout_min_atr: minimum ATR filter
    - breakout_sl_atr_mult: SL distance from entry (in ATR multiples)
    - fast_ema, slow_ema: trend filter (9/21 default)
    - enable_shorts: direction control
    - breakout_re_entry_bars: cooldown bars after signal
    """

    def __init__(self, config: TradingConfig):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{config.bot_label}")

        # Track bar count for re-entry cooldown
        self._last_breakout_bar: int = -999
        self._bars_processed: int = 0

        # Current pending order tickets (managed by the bot)
        self._pending_buy_ticket: int | None = None
        self._pending_sell_ticket: int | None = None

        # Current armed levels (for GUI display)
        self._breakout_high: float | None = None
        self._breakout_low: float | None = None
        self._buy_stop_price: float | None = None
        self._sell_stop_price: float | None = None
        self._trend_up: bool = False
        self._trend_down: bool = False
        self._current_atr: float = 0.0

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

    # -- Candle-based: recalculate levels and place stop orders ----------------

    def update_levels(self, df: pd.DataFrame) -> dict | None:
        """
        Recalculate breakout levels on each new candle.

        Returns a dict with order placement info for the bot to execute,
        or None if no orders should be placed.
        """
        self._bars_processed += 1

        n = self.config.breakout_bars
        if len(df) < n + 3:
            return None

        # Use last closed candle for trend/ATR
        signal_candle = df.iloc[-2]
        lookback = df.iloc[-(n + 2):-2]

        # ATR filter
        current_atr = float(signal_candle.get('ATR', 0))
        self._current_atr = current_atr
        if current_atr < self.config.breakout_min_atr:
            self.logger.info(
                f"[BREAKOUT] No orders: ATR ${current_atr:.2f} "
                f"< min ${self.config.breakout_min_atr:.2f}"
            )
            self._breakout_high = None
            self._breakout_low = None
            return None

        # Re-entry cooldown
        bars_since_last = self._bars_processed - self._last_breakout_bar
        if bars_since_last <= self.config.breakout_re_entry_bars:
            return None

        # Calculate levels
        self._breakout_high = float(lookback['high'].max())
        self._breakout_low = float(lookback['low'].min())
        self._trend_up = bool(signal_candle.get('uptrend', False))
        self._trend_down = bool(signal_candle.get('downtrend', False))

        # Calculate stop order prices (level + buffer)
        buffer = current_atr * self.config.breakout_entry_buffer_atr
        self._buy_stop_price = self._breakout_high + buffer
        self._sell_stop_price = self._breakout_low - buffer

        # SL based on ATR distance from entry price
        sl_distance = current_atr * self.config.breakout_sl_atr_mult
        buy_sl = self._buy_stop_price - sl_distance   # Below entry for long
        sell_sl = self._sell_stop_price + sl_distance  # Above entry for short

        self.logger.info(
            f"[BREAKOUT] Levels: high=${self._breakout_high:.2f}, low=${self._breakout_low:.2f}, "
            f"ATR=${current_atr:.2f}, "
            f"trend={'UP' if self._trend_up else 'DOWN' if self._trend_down else 'FLAT'}, "
            f"buy_stop=${self._buy_stop_price:.2f}, sell_stop=${self._sell_stop_price:.2f}, "
            f"lookback={n} bars"
        )

        return {
            'buy_stop_price': self._buy_stop_price if self._trend_up else None,
            'sell_stop_price': self._sell_stop_price if self._trend_down else None,
            'buy_sl': buy_sl,
            'sell_sl': sell_sl,
            'atr': current_atr,
        }

    def record_fill(self):
        """Record that a stop order was filled (for re-entry cooldown)."""
        self._last_breakout_bar = self._bars_processed

    # -- Tick-based entry (kept as fallback for non-stop-order mode) -----------

    def check_tick_entry(self, bid: float, ask: float, has_long: bool, has_short: bool) -> dict | None:
        """Fallback tick-based check (not used when stop orders are active)."""
        return None

    # -- Candle-based entry (disabled -- stop orders handle entry) -------------

    def check_entry(self, df, open_positions, context) -> dict | None:
        """Disabled -- MT5 stop orders handle entry."""
        return None

    # -- Exit logic -----------------------------------------------------------

    def check_exit(self, df, position, context) -> tuple[bool, str]:
        """No candle-based exit. Trailing stop + SL handle everything."""
        return False, ""

    # -- State for GUI --------------------------------------------------------

    def get_strategy_state(self, df: pd.DataFrame) -> dict:
        """Return breakout-specific state for GUI display."""
        n = self.config.breakout_bars
        if df is None or len(df) < n + 3:
            return {}

        current_close = float(df.iloc[-1]['close'])

        breakout_high = self._breakout_high or 0
        breakout_low = self._breakout_low or 0
        buy_stop = self._buy_stop_price or 0
        sell_stop = self._sell_stop_price or 0

        dist_to_high = breakout_high - current_close if breakout_high else 0
        dist_to_low = current_close - breakout_low if breakout_low else 0

        return {
            'breakout_high': breakout_high,
            'breakout_low': breakout_low,
            'buy_stop_price': buy_stop,
            'sell_stop_price': sell_stop,
            'close': current_close,
            'atr': self._current_atr,
            'uptrend': self._trend_up,
            'downtrend': self._trend_down,
            'dist_to_high': dist_to_high,
            'dist_to_low': dist_to_low,
            'atr_filter_ok': self._current_atr >= self.config.breakout_min_atr,
            'bars_since_signal': self._bars_processed - self._last_breakout_bar,
            'pending_buy': self._pending_buy_ticket is not None,
            'pending_sell': self._pending_sell_ticket is not None,
        }
