"""
Tick-level analysis engine for the precision scalper.

Maintains rolling windows of tick data and computes multi-factor
scores for entry and exit decisions. Updated every second.

Entry factors (each 0-1, weighted):
  - Micro-trend: price direction over recent ticks
  - RSI pressure: how oversold/overbought on M1 timeframe
  - Support proximity: distance to weighted recent floors
  - VWAP deviation: mean reversion pressure
  - Volatility squeeze: low vol periods precede moves
  - Tick momentum: acceleration/deceleration of price movement
  - Candle rejection: wicks showing buying/selling pressure

Exit factors (each 0-1, weighted):
  - Momentum exhaustion: tick velocity slowing
  - Resistance proximity: approaching weighted ceilings
  - Profit velocity: rate of profit change (slowing = exit)
  - Time decay: longer hold = more eager to exit
  - Reversal signal: opposite entry score getting strong
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TickData:
    """Single tick record."""
    time: datetime
    bid: float
    ask: float
    mid: float


@dataclass
class EntrySignal:
    """Entry signal with score and metadata."""
    direction: str          # "LONG" or "SHORT"
    score: float            # 0-1 composite score
    entry_price: float      # Suggested limit order price
    sl: float
    tp: float
    factors: dict           # Individual factor scores for debugging


@dataclass
class ExitSignal:
    """Exit signal with score."""
    score: float            # 0-1 (higher = more urgent to exit)
    reason: str
    factors: dict
    partial_close: bool = False  # True = close 50%, False = close all


class VelocityTracker:
    """
    Tracks price velocity and acceleration for a single position.

    Velocity = rate of price change per second in our favor.
    Acceleration = rate of velocity change (speeding up or slowing down).

    Used to detect when a move is "exhausting" — velocity peaked and is declining.
    """

    def __init__(self, direction: str, entry_price: float):
        self.direction = direction
        self.entry_price = entry_price

        # Rolling velocity measurements (price change per second, last 30 readings)
        self.velocities: deque[float] = deque(maxlen=30)
        self.peak_velocity: float = 0
        self.peak_price: float = entry_price
        self._last_price: float = entry_price
        self._last_time: datetime | None = None
        self._partial_triggered: bool = False

    def update(self, price: float, time: datetime):
        """Feed a new price tick. Call every second."""
        if self._last_time is not None:
            dt = (time - self._last_time).total_seconds()
            if dt > 0:
                # Velocity in our favor (positive = good)
                if self.direction == "LONG":
                    velocity = (price - self._last_price) / dt
                else:
                    velocity = (self._last_price - price) / dt

                self.velocities.append(velocity)

                # Track peak velocity (smoothed over 3 readings)
                if len(self.velocities) >= 3:
                    smooth_vel = sum(list(self.velocities)[-3:]) / 3
                    if smooth_vel > self.peak_velocity:
                        self.peak_velocity = smooth_vel

        # Track peak price
        if self.direction == "LONG" and price > self.peak_price:
            self.peak_price = price
        elif self.direction == "SHORT" and price < self.peak_price:
            self.peak_price = price

        self._last_price = price
        self._last_time = time

    @property
    def current_velocity(self) -> float:
        """Smoothed current velocity (average of last 3 readings)."""
        if len(self.velocities) < 3:
            return 0.0
        return sum(list(self.velocities)[-3:]) / 3

    @property
    def velocity_ratio(self) -> float:
        """Current velocity as fraction of peak (0-1). Below 0.3 = exhausting."""
        if self.peak_velocity <= 0:
            return 0.0
        return max(0, self.current_velocity / self.peak_velocity)

    @property
    def is_decelerating(self) -> bool:
        """True if velocity has been declining for 5+ seconds."""
        if len(self.velocities) < 8:
            return False
        recent = list(self.velocities)[-5:]
        older = list(self.velocities)[-8:-5]
        return np.mean(recent) < np.mean(older) * 0.7

    @property
    def profit_from_entry(self) -> float:
        """Current profit in price points."""
        if self.direction == "LONG":
            return self._last_price - self.entry_price
        return self.entry_price - self._last_price

    @property
    def drawdown_from_peak(self) -> float:
        """How much we've given back from peak (in price points)."""
        if self.direction == "LONG":
            return self.peak_price - self._last_price
        return self._last_price - self.peak_price

    def should_partial_close(self) -> bool:
        """
        Should we close 50%?

        Triggers when:
        - We're in profit
        - Velocity peaked and dropped to 30% of peak
        - Haven't already triggered partial
        """
        if self._partial_triggered:
            return False
        if self.profit_from_entry <= 0:
            return False
        if self.peak_velocity <= 0:
            return False
        if len(self.velocities) < 10:
            return False

        # Velocity has dropped to 30% of peak = move is exhausting
        if self.velocity_ratio < 0.30 and self.is_decelerating:
            self._partial_triggered = True
            return True

        return False

    def mark_partial_done(self):
        """Mark that partial close has been executed."""
        self._partial_triggered = True


class TickAnalyzer:
    """
    Real-time tick analysis engine.

    Maintains rolling buffers of price data and computes entry/exit
    scores every second. Designed to be called from the bot's main loop.
    """

    def __init__(self, config: dict):
        # Config
        self.entry_threshold = config.get('entry_threshold', 0.65)
        self.exit_threshold = config.get('exit_threshold', 0.55)
        self.rsi_period = config.get('rsi_period', 14)
        self.micro_trend_window = config.get('micro_trend_window', 30)  # seconds
        self.support_lookback = config.get('support_lookback', 300)  # seconds
        self.vwap_period = config.get('vwap_period', 60)  # seconds
        self.atr_period = config.get('atr_period', 60)  # seconds for tick ATR

        # Rolling tick buffer (last 10 minutes of ticks)
        self.ticks: deque[TickData] = deque(maxlen=600)

        # M1 candle buffer (for RSI calculation)
        self.m1_closes: deque[float] = deque(maxlen=100)
        self.last_m1_time: datetime | None = None

        # Support/resistance levels (price, age_seconds, strength)
        self.support_levels: list[tuple[float, float]] = []  # (price, timestamp)
        self.resistance_levels: list[tuple[float, float]] = []

        # State
        self._last_update: datetime | None = None
        self._peak_price: float = 0
        self._trough_price: float = float('inf')
        self._current_spread: float = 0
        self._normal_spread: float = 0  # Running average of spread

    def update_tick(self, bid: float, ask: float, time: datetime):
        """Feed a new tick into the analyzer."""
        mid = (bid + ask) / 2
        self.ticks.append(TickData(time=time, bid=bid, ask=ask, mid=mid))
        self._last_update = time
        self._current_spread = ask - bid

        # Track peaks/troughs for support/resistance
        if mid > self._peak_price:
            self._peak_price = mid
        if mid < self._trough_price:
            self._trough_price = mid

    def update_m1_candle(self, close: float, time: datetime):
        """Feed a new M1 candle close for RSI calculation."""
        self.m1_closes.append(close)
        self.last_m1_time = time

        # Update support/resistance from M1 swing points
        if len(self.m1_closes) >= 5:
            closes = list(self.m1_closes)
            # Simple swing detection: if middle of last 5 is lowest, it's support
            if closes[-3] < closes[-4] and closes[-3] < closes[-2]:
                self.support_levels.append((closes[-3], time.timestamp()))
                # Keep only last 20 levels
                self.support_levels = self.support_levels[-20:]
            if closes[-3] > closes[-4] and closes[-3] > closes[-2]:
                self.resistance_levels.append((closes[-3], time.timestamp()))
                self.resistance_levels = self.resistance_levels[-20:]

    # ── Entry scoring ───────────────────────────────────────────────

    def get_entry_score(self) -> EntrySignal | None:
        """
        Calculate composite entry score.

        Returns an EntrySignal if score exceeds threshold, else None.
        """
        if len(self.ticks) < 30:
            return None

        factors = {}
        current = self.ticks[-1]
        price = current.mid

        # 1. Micro-trend (0-1): direction of recent price movement
        long_trend, short_trend = self._calc_micro_trend()
        factors['micro_trend_long'] = long_trend
        factors['micro_trend_short'] = short_trend

        # 2. RSI pressure (0-1): how oversold/overbought
        rsi = self._calc_tick_rsi()
        long_rsi = max(0, (40 - rsi) / 40) if rsi is not None else 0  # Oversold = high score
        short_rsi = max(0, (rsi - 60) / 40) if rsi is not None else 0  # Overbought = high score
        factors['rsi_long'] = long_rsi
        factors['rsi_short'] = short_rsi

        # 3. Support/resistance proximity (0-1)
        long_support, short_resistance = self._calc_structure_proximity(price)
        factors['support_proximity'] = long_support
        factors['resistance_proximity'] = short_resistance

        # 4. VWAP deviation (0-1): mean reversion pressure
        vwap_long, vwap_short = self._calc_vwap_deviation(price)
        factors['vwap_long'] = vwap_long
        factors['vwap_short'] = vwap_short

        # 5. Volatility squeeze (0-1): low vol = pending breakout
        squeeze = self._calc_volatility_squeeze()
        factors['vol_squeeze'] = squeeze

        # 6. Tick momentum (0-1): acceleration of movement
        long_momentum, short_momentum = self._calc_tick_momentum()
        factors['momentum_long'] = long_momentum
        factors['momentum_short'] = short_momentum

        # 7. Rejection wicks (0-1): candle structure showing buying/selling
        long_rejection, short_rejection = self._calc_rejection()
        factors['rejection_long'] = long_rejection
        factors['rejection_short'] = short_rejection

        # Composite scores (weighted)
        long_score = (
            long_trend * 0.15 +
            long_rsi * 0.25 +
            long_support * 0.20 +
            vwap_long * 0.15 +
            squeeze * 0.05 +
            long_momentum * 0.10 +
            long_rejection * 0.10
        )

        short_score = (
            short_trend * 0.15 +
            short_rsi * 0.25 +
            short_resistance * 0.20 +
            vwap_short * 0.15 +
            squeeze * 0.05 +
            short_momentum * 0.10 +
            short_rejection * 0.10
        )

        # Return the stronger signal if above threshold
        # First: check spread. If spread is abnormally wide, don't enter.
        spread_ok = self._check_spread()
        if not spread_ok:
            return None

        if long_score >= self.entry_threshold and long_score > short_score:
            atr = self._calc_tick_atr()
            entry_price = price - atr * 0.3  # Limit order slightly below current
            sl = entry_price - atr * 2.5
            tp = entry_price + atr * 4.0  # Initial TP (will be trailed)
            return EntrySignal(
                direction="LONG", score=long_score, entry_price=entry_price,
                sl=sl, tp=tp, factors=factors,
            )

        if short_score >= self.entry_threshold and short_score > long_score:
            atr = self._calc_tick_atr()
            entry_price = price + atr * 0.3
            sl = entry_price + atr * 2.5
            tp = entry_price - atr * 4.0
            return EntrySignal(
                direction="SHORT", score=short_score, entry_price=entry_price,
                sl=sl, tp=tp, factors=factors,
            )

        return None

    # ── Exit scoring ────────────────────────────────────────────────

    def get_exit_score(self, direction: str, entry_price: float,
                       current_profit: float, minutes_held: float,
                       velocity_tracker: VelocityTracker | None = None,
                       m5_atr: float = 5.0) -> ExitSignal:
        """
        Calculate exit urgency score.

        Higher score = more urgent to exit.
        If velocity_tracker is provided, uses velocity-based exit logic.
        """
        if len(self.ticks) < 10:
            return ExitSignal(score=0, reason="", factors={})

        factors = {}
        price = self.ticks[-1].mid

        # 1. Momentum exhaustion (0-1): is the move slowing down?
        exhaustion = self._calc_momentum_exhaustion(direction)
        factors['exhaustion'] = exhaustion

        # 2. Opposite pressure (0-1): is the other side getting strong?
        if direction == "LONG":
            _, opposite = self._calc_micro_trend()
        else:
            opposite, _ = self._calc_micro_trend()
        factors['opposite_pressure'] = opposite

        # 3. Resistance/support approach (0-1)
        if direction == "LONG":
            _, resistance = self._calc_structure_proximity(price)
            factors['structure_pressure'] = resistance
        else:
            support, _ = self._calc_structure_proximity(price)
            factors['structure_pressure'] = support

        # 4. Time decay (0-1): longer hold = more eager to exit
        time_decay = min(1.0, minutes_held / 60)  # Full decay at 60 min
        factors['time_decay'] = time_decay

        # 5. Profit velocity (0-1): if profit is stalling
        profit_stall = self._calc_profit_stall(direction, entry_price)
        factors['profit_stall'] = profit_stall

        # 6. Velocity-based factors (if tracker available)
        velocity_exhaustion = 0.0
        partial_close = False
        if velocity_tracker and len(velocity_tracker.velocities) >= 15:
            vel_ratio = velocity_tracker.velocity_ratio
            # Only consider exhaustion if we had a meaningful peak velocity
            # (peak must be at least 0.01 price units/sec to count)
            if velocity_tracker.peak_velocity > 0.01:
                velocity_exhaustion = max(0, 1.0 - vel_ratio)
            factors['velocity_exhaustion'] = velocity_exhaustion

            # Check for partial close trigger
            if velocity_tracker.should_partial_close():
                partial_close = True
                factors['partial_trigger'] = 1.0

            # Drawdown from peak (giving back profit)
            if m5_atr > 0:
                drawdown_ratio = velocity_tracker.drawdown_from_peak / m5_atr
                factors['peak_drawdown'] = min(1.0, drawdown_ratio / 1.5)  # 1.5 ATR giveback = score 1.0

        # Composite exit score (velocity-aware)
        if velocity_tracker and len(velocity_tracker.velocities) >= 15:
            score = (
                velocity_exhaustion * 0.30 +
                exhaustion * 0.15 +
                opposite * 0.20 +
                factors.get('structure_pressure', 0) * 0.10 +
                factors.get('peak_drawdown', 0) * 0.15 +
                time_decay * 0.05 +
                profit_stall * 0.05
            )
        else:
            # Fallback without velocity data (first 15 seconds)
            score = (
                exhaustion * 0.30 +
                opposite * 0.25 +
                factors.get('structure_pressure', 0) * 0.20 +
                time_decay * 0.10 +
                profit_stall * 0.15
            )

        reason = ""
        if partial_close:
            vr = velocity_tracker.velocity_ratio if velocity_tracker else 0
            pv = velocity_tracker.peak_velocity if velocity_tracker else 0
            reason = f"Velocity partial (vel ratio {vr:.2f}, peak vel {pv:.4f})"
        elif score >= self.exit_threshold:
            top_factor = max(factors, key=factors.get)
            reason = f"Exit score {score:.2f} ({top_factor}: {factors[top_factor]:.2f})"

        return ExitSignal(score=score, reason=reason, factors=factors, partial_close=partial_close)

    # ── Trailing stop calculation ───────────────────────────────────

    def get_trailing_stop(self, direction: str, entry_price: float,
                          current_sl: float, peak_profit_price: float) -> float:
        """
        Calculate dynamic trailing stop level.

        Tightens as profit grows. Uses tick ATR for distance.
        """
        atr = self._calc_tick_atr()
        if atr <= 0:
            return current_sl

        price = self.ticks[-1].mid

        if direction == "LONG":
            profit_distance = price - entry_price
            # Trail distance: starts at 2.5 ATR, tightens to 1.0 ATR as profit grows
            trail_factor = max(1.0, 2.5 - (profit_distance / atr) * 0.3)
            trail_distance = atr * trail_factor
            new_sl = peak_profit_price - trail_distance
            return max(current_sl, new_sl)  # Only move up
        else:
            profit_distance = entry_price - price
            trail_factor = max(1.0, 2.5 - (profit_distance / atr) * 0.3)
            trail_distance = atr * trail_factor
            new_sl = peak_profit_price + trail_distance
            return min(current_sl, new_sl)  # Only move down

    # ── Internal calculations ───────────────────────────────────────

    def _check_spread(self) -> bool:
        """
        Check if spread is acceptable for trading.

        Returns False if spread is abnormally wide (news, low liquidity).
        Also updates the running average of normal spread.
        """
        if self._current_spread <= 0:
            return True

        # Update running average (exponential moving average of spread)
        if self._normal_spread <= 0:
            self._normal_spread = self._current_spread
        else:
            self._normal_spread = self._normal_spread * 0.99 + self._current_spread * 0.01

        # Block if spread is more than 3x normal
        if self._current_spread > self._normal_spread * 3:
            return False

        # Block if spread exceeds absolute maximum ($1.00)
        if self._current_spread > 1.0:
            return False

        return True

    def get_current_spread(self) -> float:
        """Get current spread (for display/logging)."""
        return self._current_spread

    def get_spread_ratio(self) -> float:
        """Get current spread as ratio of normal (1.0 = normal, 3.0 = 3x wide)."""
        if self._normal_spread <= 0:
            return 1.0
        return self._current_spread / self._normal_spread

    def _calc_micro_trend(self) -> tuple[float, float]:
        """Calculate micro-trend direction over recent ticks. Returns (long_score, short_score)."""
        n = min(self.micro_trend_window, len(self.ticks))
        if n < 5:
            return 0.0, 0.0

        prices = [self.ticks[-i].mid for i in range(1, n + 1)]
        prices.reverse()

        # Linear regression slope
        x = np.arange(n)
        slope = np.polyfit(x, prices, 1)[0]

        # Normalize by recent volatility
        std = np.std(prices) if np.std(prices) > 0 else 1
        normalized = slope / std * 10

        if normalized > 0:
            return min(1.0, normalized), 0.0
        else:
            return 0.0, min(1.0, -normalized)

    def _calc_tick_rsi(self) -> float | None:
        """Calculate RSI from M1 closes."""
        if len(self.m1_closes) < self.rsi_period + 1:
            return None

        closes = list(self.m1_closes)[-(self.rsi_period + 1):]
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]

        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calc_structure_proximity(self, price: float) -> tuple[float, float]:
        """How close to support (long score) and resistance (short score)."""
        now = self._last_update.timestamp() if self._last_update else 0
        atr = self._calc_tick_atr()
        if atr <= 0:
            return 0.0, 0.0

        # Weighted support proximity (newer levels count more)
        long_score = 0.0
        for level_price, level_time in self.support_levels:
            age_minutes = (now - level_time) / 60
            weight = max(0.1, 1.0 - age_minutes / 120)  # Decay over 2 hours
            distance = (price - level_price) / atr
            if 0 < distance < 2.0:  # Within 2 ATR above support
                proximity = max(0, 1.0 - distance / 2.0)
                long_score = max(long_score, proximity * weight)

        # Weighted resistance proximity
        short_score = 0.0
        for level_price, level_time in self.resistance_levels:
            age_minutes = (now - level_time) / 60
            weight = max(0.1, 1.0 - age_minutes / 120)
            distance = (level_price - price) / atr
            if 0 < distance < 2.0:
                proximity = max(0, 1.0 - distance / 2.0)
                short_score = max(short_score, proximity * weight)

        return long_score, short_score

    def _calc_vwap_deviation(self, price: float) -> tuple[float, float]:
        """VWAP deviation score. Below VWAP = long opportunity, above = short."""
        n = min(self.vwap_period, len(self.ticks))
        if n < 10:
            return 0.0, 0.0

        prices = [self.ticks[-i].mid for i in range(1, n + 1)]
        vwap = np.mean(prices)  # Simplified VWAP (no volume data from ticks)
        atr = self._calc_tick_atr()
        if atr <= 0:
            return 0.0, 0.0

        deviation = (price - vwap) / atr

        if deviation < 0:  # Below VWAP = long opportunity
            return min(1.0, -deviation / 2.0), 0.0
        else:  # Above VWAP = short opportunity
            return 0.0, min(1.0, deviation / 2.0)

    def _calc_volatility_squeeze(self) -> float:
        """Detect low volatility (squeeze). Returns 0-1 (1 = tight squeeze)."""
        n = min(60, len(self.ticks))
        if n < 20:
            return 0.0

        recent = [self.ticks[-i].mid for i in range(1, n + 1)]
        current_range = max(recent[:10]) - min(recent[:10])  # Last 10 ticks range
        historical_range = max(recent) - min(recent)  # Full window range

        if historical_range <= 0:
            return 0.0

        ratio = current_range / historical_range
        # Low ratio = squeeze (current range is small vs historical)
        return max(0, 1.0 - ratio * 2)

    def _calc_tick_momentum(self) -> tuple[float, float]:
        """Tick-level momentum (acceleration). Returns (long, short)."""
        if len(self.ticks) < 10:
            return 0.0, 0.0

        # Compare velocity of last 5 ticks vs previous 5
        recent = [self.ticks[-i].mid for i in range(1, 6)]
        older = [self.ticks[-i].mid for i in range(6, 11)]

        recent_move = recent[0] - recent[-1]  # Last 5 ticks movement
        older_move = older[0] - older[-1]  # Previous 5 ticks movement

        # Acceleration: recent move stronger than older move in same direction
        if recent_move > 0 and recent_move > older_move:
            accel = min(1.0, (recent_move - max(0, older_move)) / max(0.01, abs(older_move) + 0.01))
            return accel, 0.0
        elif recent_move < 0 and recent_move < older_move:
            accel = min(1.0, (abs(recent_move) - max(0, abs(older_move))) / max(0.01, abs(older_move) + 0.01))
            return 0.0, accel

        return 0.0, 0.0

    def _calc_rejection(self) -> tuple[float, float]:
        """Detect rejection wicks from recent tick data. Returns (long, short)."""
        if len(self.ticks) < 20:
            return 0.0, 0.0

        # Look at last 20 ticks: if price dipped then recovered = buying rejection
        prices = [self.ticks[-i].mid for i in range(1, 21)]
        prices.reverse()

        low = min(prices)
        high = max(prices)
        current = prices[-1]
        price_range = high - low

        if price_range <= 0:
            return 0.0, 0.0

        # Long rejection: price near the high after touching the low
        long_rej = (current - low) / price_range  # 1.0 = full recovery from low
        # Short rejection: price near the low after touching the high
        short_rej = (high - current) / price_range

        # Only count as rejection if there was a meaningful dip/spike
        atr = self._calc_tick_atr()
        if price_range < atr * 0.3:
            return 0.0, 0.0

        return max(0, long_rej - 0.5) * 2, max(0, short_rej - 0.5) * 2

    def _calc_tick_atr(self) -> float:
        """Calculate ATR-equivalent from tick data (average range per minute)."""
        if len(self.ticks) < 20:
            return 1.0  # Default

        # Use standard deviation of recent prices as volatility proxy
        prices = [self.ticks[-i].mid for i in range(1, min(61, len(self.ticks)))]
        return float(np.std(prices)) * 2  # ~2 std devs ≈ typical range

    def _calc_momentum_exhaustion(self, direction: str) -> float:
        """
        Short-window exhaustion detection (V4-style).

        Compares velocity of last 5 ticks vs previous 10 ticks.
        Fires quickly on momentum shifts — reactive, not smooth.
        """
        if len(self.ticks) < 15:
            return 0.0

        recent = [self.ticks[-i].mid for i in range(1, 6)]
        older = [self.ticks[-i].mid for i in range(6, 16)]

        recent_velocity = abs(recent[0] - recent[-1]) / 5
        older_velocity = abs(older[0] - older[-1]) / 10

        if older_velocity <= 0:
            return 0.0

        ratio = recent_velocity / older_velocity
        if ratio < 1.0:
            return min(1.0, (1.0 - ratio) * 2)
        return 0.0

    def _calc_profit_stall(self, direction: str, entry_price: float) -> float:
        """
        Short-window profit stall detection (V4-style).

        Checks price movement over last 30 ticks only.
        Fires quickly when price stops progressing in our favor.
        """
        if len(self.ticks) < 30:
            return 0.0

        prices = [self.ticks[-i].mid for i in range(1, 31)]
        current = prices[0]
        thirty_ago = prices[-1]

        if direction == "LONG":
            progress = current - thirty_ago
        else:
            progress = thirty_ago - current

        atr = self._calc_tick_atr()
        if atr <= 0:
            return 0.0

        if progress < 0:
            return min(1.0, -progress / atr)
        if progress < atr * 0.1:
            return 0.3
        return 0.0
