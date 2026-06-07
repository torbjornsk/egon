"""
Multi-timeframe trend analysis.

Computes a continuous trend score from -1.0 (strong downtrend) to +1.0
(strong uptrend) using multiple timeframes and factors.

Used by bots to:
- Filter entries (only trade with the trend, or require stronger signals counter-trend)
- Adjust trailing stop width (wider with-trend, tighter counter-trend)
- Weight entry scores (boost with-trend signals)
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """
    Multi-timeframe trend scoring.

    Fetches M5, M15, and H1 data periodically and computes a composite
    trend score. Call update() every few minutes, read score anytime.
    """

    def __init__(self, broker, symbol_timeframes: dict | None = None):
        """
        Args:
            broker: MT5Broker instance for fetching data
            symbol_timeframes: dict of {label: mt5_timeframe_const}
        """
        self.broker = broker
        self._score: float = 0.0
        self._factors: dict = {}
        self._last_update: datetime | None = None
        self._update_interval_seconds: int = 120  # Update every 2 minutes

    @property
    def score(self) -> float:
        """Trend score: -1.0 (strong down) to +1.0 (strong up). 0 = no trend."""
        return self._score

    @property
    def direction(self) -> str:
        """Simple direction string based on score."""
        if self._score > 0.3:
            return "UP"
        elif self._score < -0.3:
            return "DOWN"
        return "NEUTRAL"

    @property
    def strength(self) -> float:
        """Absolute trend strength 0-1."""
        return abs(self._score)

    @property
    def factors(self) -> dict:
        """Individual factor scores for debugging."""
        return self._factors

    def should_update(self) -> bool:
        """Check if enough time has passed for a refresh."""
        if self._last_update is None:
            return True
        from src.core.timezone import get_local_now
        elapsed = (get_local_now() - self._last_update).total_seconds()
        return elapsed >= self._update_interval_seconds

    def update(self):
        """Recalculate trend score from multiple timeframes."""
        factors = {}

        # Fetch M5 data (short-term trend)
        m5_df = self.broker.get_historical_data(timeframe=5, bars=100)
        if m5_df is not None and len(m5_df) >= 50:
            factors['m5_ema'] = self._ema_score(m5_df, fast=9, slow=21)
            factors['m5_position'] = self._price_position_score(m5_df, period=21)
            factors['m5_momentum'] = self._momentum_score(m5_df, period=14)

        # Fetch M15 data (medium-term trend)
        m15_df = self.broker.get_historical_data(timeframe=15, bars=100)
        if m15_df is not None and len(m15_df) >= 50:
            factors['m15_ema'] = self._ema_score(m15_df, fast=9, slow=21)
            factors['m15_position'] = self._price_position_score(m15_df, period=21)

        # Fetch H1 data (long-term trend)
        h1_df = self.broker.get_historical_data(timeframe=60, bars=50)
        if h1_df is not None and len(h1_df) >= 20:
            factors['h1_ema'] = self._ema_score(h1_df, fast=9, slow=21)
            factors['h1_position'] = self._price_position_score(h1_df, period=21)

        # Structure score (higher highs / lower lows on M15)
        if m15_df is not None and len(m15_df) >= 30:
            factors['structure'] = self._structure_score(m15_df)

        self._factors = factors

        # Composite score (weighted by timeframe importance)
        if not factors:
            self._score = 0.0
            return

        # Higher timeframes get more weight
        weights = {
            'm5_ema': 0.10, 'm5_position': 0.10, 'm5_momentum': 0.10,
            'm15_ema': 0.15, 'm15_position': 0.15,
            'h1_ema': 0.20, 'h1_position': 0.10,
            'structure': 0.10,
        }

        total_weight = 0.0
        weighted_sum = 0.0
        for key, weight in weights.items():
            if key in factors:
                weighted_sum += factors[key] * weight
                total_weight += weight

        self._score = weighted_sum / total_weight if total_weight > 0 else 0.0
        self._score = max(-1.0, min(1.0, self._score))

        from src.core.timezone import get_local_now
        self._last_update = get_local_now()

    def _ema_score(self, df: pd.DataFrame, fast: int, slow: int) -> float:
        """EMA cross score: +1 if fast > slow and diverging, -1 if fast < slow."""
        closes = df['close'].values
        ema_fast = pd.Series(closes).ewm(span=fast).mean().values
        ema_slow = pd.Series(closes).ewm(span=slow).mean().values

        # Current relationship
        diff = ema_fast[-1] - ema_slow[-1]
        # Normalize by recent price range
        price_range = np.std(closes[-20:])
        if price_range <= 0:
            return 0.0

        normalized = diff / price_range
        return max(-1.0, min(1.0, normalized * 2))

    def _price_position_score(self, df: pd.DataFrame, period: int) -> float:
        """Where is price relative to its EMA? Above = bullish, below = bearish."""
        closes = df['close'].values
        ema = pd.Series(closes).ewm(span=period).mean().values

        price = closes[-1]
        ema_val = ema[-1]
        distance = price - ema_val

        # Normalize by ATR-like measure
        atr_proxy = np.std(closes[-20:])
        if atr_proxy <= 0:
            return 0.0

        normalized = distance / atr_proxy
        return max(-1.0, min(1.0, normalized))

    def _momentum_score(self, df: pd.DataFrame, period: int) -> float:
        """RSI-based momentum: >60 = bullish momentum, <40 = bearish."""
        closes = df['close'].values
        if len(closes) < period + 1:
            return 0.0

        deltas = np.diff(closes[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = gains.mean()
        avg_loss = losses.mean()

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        # Convert RSI to -1..+1 score (50 = neutral)
        return (rsi - 50) / 50

    def _structure_score(self, df: pd.DataFrame) -> float:
        """Higher highs/lows = uptrend, lower highs/lows = downtrend."""
        highs = df['high'].values
        lows = df['low'].values

        # Compare recent swing points
        # Simple: compare last 10 bars' high/low vs previous 10
        if len(df) < 20:
            return 0.0

        recent_high = highs[-10:].max()
        older_high = highs[-20:-10].max()
        recent_low = lows[-10:].min()
        older_low = lows[-20:-10].min()

        score = 0.0
        # Higher high
        if recent_high > older_high:
            score += 0.5
        elif recent_high < older_high:
            score -= 0.5

        # Higher low
        if recent_low > older_low:
            score += 0.5
        elif recent_low < older_low:
            score -= 0.5

        return max(-1.0, min(1.0, score))
