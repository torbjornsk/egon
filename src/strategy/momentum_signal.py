"""
Momentum Signal Engine -- weighted rolling directional pressure.

Computes a single directional score every second from -1.0 (strong short)
to +1.0 (strong long). Maintains a rolling window of recent scores and
applies exponential decay weighting so the last few seconds dominate.

The signal IS the strategy: enter when it's strong, hold while it stays,
exit when it fades or flips.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SignalReading:
    """Single signal sample."""
    score: float        # -1.0 to +1.0 (negative = short, positive = long)
    long_raw: float     # Raw long factor score (0-1)
    short_raw: float    # Raw short factor score (0-1)


class SignalStream:
    """
    Rolling weighted signal stream.

    Stores the last N directional readings and computes a weighted
    signal where recent samples dominate. The weighted score drives
    all trading decisions.
    """

    def __init__(self, window: int = 15, heavy_count: int = 5):
        """
        Args:
            window: total number of samples to keep
            heavy_count: how many recent samples get dominant weight
        """
        self.window = window
        self.heavy_count = heavy_count
        self.readings: deque[SignalReading] = deque(maxlen=window)

        # Precompute weights: exponential decay
        # Last heavy_count samples share ~65% of total weight
        # Remaining (window - heavy_count) share ~35%
        self._weights = self._compute_weights()

    def _compute_weights(self) -> list[float]:
        """Compute exponential decay weights, newest first."""
        # Decay factor: each older sample is 0.7x the previous
        decay = 0.70
        raw = [decay ** i for i in range(self.window)]
        total = sum(raw)
        return [w / total for w in raw]

    def push(self, reading: SignalReading):
        """Add a new signal reading."""
        self.readings.append(reading)

    @property
    def weighted_score(self) -> float:
        """
        Weighted directional score from -1.0 to +1.0.

        Positive = long pressure, negative = short pressure.
        Magnitude indicates strength.
        """
        n = len(self.readings)
        if n == 0:
            return 0.0

        # readings are oldest-first, we want newest-first for weighting
        scores = [self.readings[-(i + 1)].score for i in range(n)]
        weights = self._weights[:n]

        # Re-normalize weights for actual sample count
        total_w = sum(weights)
        if total_w <= 0:
            return 0.0

        return sum(s * w for s, w in zip(scores, weights)) / total_w

    @property
    def consistency(self) -> float:
        """
        How consistent the last heavy_count readings are (0-1).

        1.0 = all readings on same side with similar magnitude.
        0.0 = mixed signals or empty.
        """
        n = min(self.heavy_count, len(self.readings))
        if n < 3:
            return 0.0

        recent = [self.readings[-(i + 1)].score for i in range(n)]

        # All same sign?
        signs = [1 if s > 0 else (-1 if s < 0 else 0) for s in recent]
        dominant_sign = 1 if sum(signs) > 0 else -1
        same_side = sum(1 for s in signs if s == dominant_sign) / n

        # Low variance in magnitude?
        magnitudes = [abs(s) for s in recent]
        if max(magnitudes) > 0:
            cv = np.std(magnitudes) / (np.mean(magnitudes) + 1e-9)
            stability = max(0, 1.0 - cv)
        else:
            stability = 0.0

        return same_side * 0.7 + stability * 0.3

    @property
    def is_ready(self) -> bool:
        """True if we have enough samples to make decisions."""
        return len(self.readings) >= self.heavy_count

    @property
    def direction(self) -> str:
        """Current direction: LONG, SHORT, or NEUTRAL."""
        score = self.weighted_score
        if score > 0.05:
            return "LONG"
        elif score < -0.05:
            return "SHORT"
        return "NEUTRAL"


class MomentumEngine:
    """
    Computes raw directional pressure from tick data every second.

    Uses short-window (5-15 tick) factors similar to tick bot V4:
    - Micro-trend: price direction over last N ticks
    - Tick momentum: acceleration (recent vs older movement)
    - RSI pressure: oversold/overbought from M1 candles
    - Rejection: price recovering from dips/spikes

    Outputs a single -1 to +1 score each tick.
    """

    def __init__(self, config: dict):
        self.factor_window = config.get('factor_window_ticks', 15)
        self.rsi_period = config.get('rsi_period', 14)

        # Rolling tick buffer (10 minutes)
        self.ticks: deque[float] = deque(maxlen=600)
        self.spreads: deque[float] = deque(maxlen=600)

        # M1 candle closes for RSI
        self.m1_closes: deque[float] = deque(maxlen=100)

        # Spread tracking
        self._normal_spread: float = 0.0
        self._current_spread: float = 0.0

    def update_tick(self, bid: float, ask: float):
        """Feed a new tick."""
        mid = (bid + ask) / 2
        spread = ask - bid
        self.ticks.append(mid)
        self.spreads.append(spread)
        self._current_spread = spread

        # Update normal spread (EMA)
        if self._normal_spread <= 0:
            self._normal_spread = spread
        else:
            self._normal_spread = self._normal_spread * 0.99 + spread * 0.01

    def update_m1_candle(self, close: float):
        """Feed a completed M1 candle close."""
        self.m1_closes.append(close)

    def compute_signal(self) -> SignalReading | None:
        """
        Compute directional pressure from current tick state.

        Returns None if not enough data.
        """
        n = len(self.ticks)
        if n < self.factor_window:
            return None

        # Factor 1: Micro-trend (direction over last factor_window ticks)
        long_trend, short_trend = self._micro_trend()

        # Factor 2: Tick momentum (acceleration)
        long_momentum, short_momentum = self._tick_momentum()

        # Factor 3: RSI pressure
        long_rsi, short_rsi = self._rsi_pressure()

        # Factor 4: Rejection (recovery from dips/spikes)
        long_rej, short_rej = self._rejection()

        # Composite long/short scores (0-1 each)
        long_score = (
            long_trend * 0.35 +
            long_momentum * 0.30 +
            long_rsi * 0.20 +
            long_rej * 0.15
        )

        short_score = (
            short_trend * 0.35 +
            short_momentum * 0.30 +
            short_rsi * 0.20 +
            short_rej * 0.15
        )

        # Map to -1 to +1: positive = long dominant, negative = short dominant
        directional = long_score - short_score

        return SignalReading(
            score=max(-1.0, min(1.0, directional)),
            long_raw=long_score,
            short_raw=short_score,
        )

    def is_spread_ok(self) -> bool:
        """Check if spread is acceptable for trading."""
        if self._current_spread <= 0:
            return True
        if self._normal_spread <= 0:
            return True
        # Block if spread > 3x normal or > $1.00 absolute
        if self._current_spread > self._normal_spread * 3:
            return False
        if self._current_spread > 1.0:
            return False
        return True

    @property
    def current_spread(self) -> float:
        return self._current_spread

    @property
    def spread_ratio(self) -> float:
        if self._normal_spread <= 0:
            return 1.0
        return self._current_spread / self._normal_spread

    # ── Internal factor calculations (short-window, V4-style) ───────

    def _micro_trend(self) -> tuple[float, float]:
        """Price direction over last factor_window ticks."""
        n = min(self.factor_window, len(self.ticks))
        if n < 5:
            return 0.0, 0.0

        prices = list(self.ticks)[-n:]
        x = np.arange(n)
        slope = np.polyfit(x, prices, 1)[0]

        std = np.std(prices)
        if std <= 0:
            return 0.0, 0.0

        normalized = slope / std * 10

        if normalized > 0:
            return min(1.0, normalized), 0.0
        else:
            return 0.0, min(1.0, -normalized)

    def _tick_momentum(self) -> tuple[float, float]:
        """Acceleration: recent 5 ticks vs previous 5-10 ticks."""
        n = len(self.ticks)
        if n < 10:
            return 0.0, 0.0

        recent = list(self.ticks)[-5:]
        older = list(self.ticks)[-10:-5]

        recent_move = recent[-1] - recent[0]
        older_move = older[-1] - older[0]

        # Acceleration: recent move stronger in same direction
        if recent_move > 0 and recent_move > older_move:
            diff = recent_move - max(0, older_move)
            accel = min(1.0, diff / (abs(older_move) + 0.01))
            return accel, 0.0
        elif recent_move < 0 and recent_move < older_move:
            diff = abs(recent_move) - max(0, abs(older_move))
            accel = min(1.0, diff / (abs(older_move) + 0.01))
            return 0.0, accel

        return 0.0, 0.0

    def _rsi_pressure(self) -> tuple[float, float]:
        """RSI from M1 candles. Oversold = long pressure, overbought = short."""
        if len(self.m1_closes) < self.rsi_period + 1:
            return 0.0, 0.0

        closes = list(self.m1_closes)[-(self.rsi_period + 1):]
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        # Map: RSI < 40 = long pressure, RSI > 60 = short pressure
        long_rsi = max(0, (40 - rsi) / 40)
        short_rsi = max(0, (rsi - 60) / 40)
        return long_rsi, short_rsi

    def _rejection(self) -> tuple[float, float]:
        """Price recovery from recent dips/spikes (last 15 ticks)."""
        n = min(15, len(self.ticks))
        if n < 10:
            return 0.0, 0.0

        prices = list(self.ticks)[-n:]
        low = min(prices)
        high = max(prices)
        current = prices[-1]
        price_range = high - low

        if price_range <= 0:
            return 0.0, 0.0

        # Need meaningful range (at least some movement)
        std = np.std(list(self.ticks)[-60:]) if len(self.ticks) >= 60 else 1.0
        if price_range < std * 0.3:
            return 0.0, 0.0

        # Long rejection: recovered from low
        long_rej = (current - low) / price_range
        # Short rejection: dropped from high
        short_rej = (high - current) / price_range

        # Only count strong rejections (> 50% recovery)
        return max(0, long_rej - 0.5) * 2, max(0, short_rej - 0.5) * 2
