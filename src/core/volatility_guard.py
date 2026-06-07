"""
Volatility Guard -- halts entries during ATR spikes (breakouts).

When ATR exceeds a configurable multiple of its recent median, new entries
are paused. Existing positions are still managed (exits, trailing).
Resumes automatically once ATR drops back below the resume threshold.

Configuration via TradingConfig fields (from JSON):
  "volatility_guard": {
    "enabled": true,
    "atr_spike_multiplier": 2.5,
    "cooldown_minutes": 15,
    "resume_below_multiplier": 1.5,
    "lookback_bars": 100
  }
"""

import logging
from datetime import datetime, timedelta

from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)


class VolatilityGuard:
    """
    Monitors ATR and pauses entries when volatility spikes.

    Behavior:
    - Pauses when current ATR > median_atr * atr_spike_multiplier
    - Stays paused for at least cooldown_minutes
    - Resumes when ATR drops below median_atr * resume_below_multiplier
    """

    def __init__(self, guard_config: dict | None = None, bot_label: str = ""):
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger
        self._config = guard_config or {}

        self._enabled = self._config.get('enabled', False)
        self._spike_mult = self._config.get('atr_spike_multiplier', 2.5)
        self._cooldown_minutes = self._config.get('cooldown_minutes', 15)
        self._resume_mult = self._config.get('resume_below_multiplier', 1.5)
        self._lookback = self._config.get('lookback_bars', 100)

        self._paused = False
        self._pause_reason = ""
        self._pause_start: datetime | None = None
        self._last_atr: float = 0
        self._last_median: float = 0

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def pause_reason(self) -> str:
        return self._pause_reason

    def check(self, atr_values) -> bool:
        """
        Check ATR values and decide whether to pause.

        Args:
            atr_values: numpy array or list of recent ATR values (at least lookback_bars)

        Returns:
            True if entries are allowed, False if paused by volatility guard.
        """
        if not self._enabled:
            return True

        if atr_values is None or len(atr_values) < 20:
            return True

        import numpy as np

        lookback = min(self._lookback, len(atr_values))
        recent_atr = atr_values[-lookback:]
        current_atr = float(atr_values[-1])
        median_atr = float(np.median(recent_atr))

        self._last_atr = current_atr
        self._last_median = median_atr

        if median_atr <= 0:
            return True

        ratio = current_atr / median_atr

        # Already paused: check if we can resume
        if self._paused:
            # Must wait for cooldown
            if self._pause_start:
                elapsed = (get_local_now() - self._pause_start).total_seconds() / 60
                if elapsed < self._cooldown_minutes:
                    remaining = self._cooldown_minutes - elapsed
                    self._pause_reason = (
                        f"ATR spike cooldown ({remaining:.0f}min remaining, "
                        f"ATR ${current_atr:.2f} = {ratio:.1f}x median)"
                    )
                    return False

            # Cooldown elapsed: check if ATR has calmed down
            if ratio <= self._resume_mult:
                self._set_resumed(current_atr, median_atr, ratio)
                return True
            else:
                self._pause_reason = (
                    f"ATR still elevated: ${current_atr:.2f} = {ratio:.1f}x median "
                    f"(need < {self._resume_mult:.1f}x to resume)"
                )
                return False

        # Not paused: check if we should pause
        if ratio >= self._spike_mult:
            self._set_paused(current_atr, median_atr, ratio)
            return False

        return True

    def _set_paused(self, current_atr: float, median_atr: float, ratio: float):
        """Transition to paused state."""
        self._paused = True
        self._pause_start = get_local_now()
        self._pause_reason = (
            f"ATR spike detected: ${current_atr:.2f} = {ratio:.1f}x median "
            f"(threshold: {self._spike_mult:.1f}x)"
        )
        self.logger.warning(
            f"[VOLATILITY GUARD] PAUSED: ATR ${current_atr:.2f} = {ratio:.1f}x "
            f"median ${median_atr:.2f} (>{self._spike_mult:.1f}x threshold)"
        )

    def _set_resumed(self, current_atr: float, median_atr: float, ratio: float):
        """Transition back to active state."""
        self._paused = False
        self._pause_start = None
        self._pause_reason = ""
        self.logger.info(
            f"[VOLATILITY GUARD] RESUMED: ATR ${current_atr:.2f} = {ratio:.1f}x "
            f"median ${median_atr:.2f} (<={self._resume_mult:.1f}x threshold)"
        )

    def get_status(self) -> dict:
        """Return current guard state for GUI display."""
        return {
            'enabled': self._enabled,
            'paused': self._paused,
            'reason': self._pause_reason,
            'current_atr': self._last_atr,
            'median_atr': self._last_median,
            'ratio': self._last_atr / self._last_median if self._last_median > 0 else 0,
            'spike_threshold': self._spike_mult,
            'resume_threshold': self._resume_mult,
        }
