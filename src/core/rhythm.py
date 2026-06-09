"""
Market Rhythm Analyzer -- determines if current market conditions
are suitable for RSI-based swing trading.

Analyzes RSI cycles, swing amplitude, and regime to answer:
1. Is the market swinging (tradeable with RSI)?
2. How deep/fast are the swings (parameter adaptation)?
3. Where should sniper levels be placed (support-aware)?

Three modes:
- manual: computed for logging/GUI but never overrides params
- gated: blocks entries when market doesn't fit, keeps manual params
- dynamic: actively adjusts sniper offset, sizing, SL/trail based on rhythm

Works across timeframes (M1/M5/M15) with per-TF sensible defaults.
"""

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import TIMEFRAME_MAP, TIMEFRAME_MINUTES
from src.core.liquidity import find_liquidity_zones

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Current market regime classification."""
    SWINGING = "swinging"       # Regular RSI oscillations, tradeable
    TRENDING = "trending"       # RSI stuck on one side, mean-revert risky
    DEAD = "dead"               # ATR too low, swings don't cover costs
    CHAOTIC = "chaotic"         # No stable cycle, noise dominates


@dataclass
class RhythmState:
    """Current rhythm analysis results."""
    regime: MarketRegime = MarketRegime.SWINGING
    # Observed cycle metrics
    half_cycle_bars: float = 10.0       # Median bars per half-cycle
    full_cycle_bars: float = 20.0       # = half_cycle * 2
    amplitude_rsi: float = 20.0         # Median RSI distance from 50 at extremes
    amplitude_dollars: float = 3.0      # Median price move per half-cycle
    cycle_stability: float = 0.7        # 0-1: how consistent the cycles are
    # Confidence in the analysis (based on number of observed cycles)
    confidence: float = 0.5             # 0-1: more cycles observed = higher
    # Dynamic parameter adjustments (only applied in dynamic mode)
    sizing_scale: float = 1.0           # Multiply risk_per_trade_pct by this
    sl_scale: float = 1.0              # Multiply SL/trail distances by this
    sniper_offset_dynamic: float = 10.0 # Suggested sniper RSI offset
    breakeven_trigger_scale: float = 1.0  # Multiply breakeven_atr_trigger by this
    # Reason for current state (for logging/GUI)
    reason: str = ""


class MarketRhythm:
    """
    Analyzes market rhythm to determine RSI tradeability.

    On each candle update:
    1. Detects RSI half-cycles (crossings of the midline)
    2. Measures swing amplitude (RSI depth and price distance)
    3. Classifies regime (swinging/trending/dead/chaotic)
    4. Computes parameter adjustments for dynamic mode

    Multi-timeframe: analyzes primary TF and one higher TF for confirmation.
    """

    def __init__(self, config: TradingConfig, bot_label: str = ""):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger

        self._enabled = config.rhythm_enabled
        self._mode = config.rhythm_mode  # "manual", "gated", "dynamic"

        # Thresholds from config
        self._min_amplitude_atr = config.rhythm_min_amplitude_atr
        self._max_cycle_bars = config.rhythm_max_cycle_bars
        self._min_cycle_bars = config.rhythm_min_cycle_bars
        self._dead_atr_factor = config.rhythm_dead_atr_factor
        self._support_aware = config.rhythm_support_aware_sniper

        # State
        self._state = RhythmState()
        self._last_regime = MarketRegime.SWINGING
        self._regime_bars = 0  # How long we've been in current regime

        # RSI midline (50) crossing history
        self._crossings: list[dict] = []  # [{bar_idx, rsi, price, direction}]
        self._extremes: list[dict] = []   # [{bar_idx, rsi, price, direction}]

        # HTF state
        self._htf_trending: bool = False
        self._htf_trend_direction: str = ""  # "up" or "down" or ""

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def state(self) -> RhythmState:
        return self._state

    @property
    def regime(self) -> MarketRegime:
        return self._state.regime

    def is_tradeable(self) -> bool:
        """
        Check if current market is suitable for RSI trading.

        In manual mode: always returns True (logging only).
        In gated/dynamic mode: returns False for dead/trending/chaotic regimes.
        """
        if not self._enabled:
            return True
        if self._mode == "manual":
            return True

        return self._state.regime == MarketRegime.SWINGING

    def get_dynamic_params(self) -> dict:
        """
        Get dynamic parameter adjustments.

        Only meaningful in dynamic mode. In other modes, returns neutral values.
        """
        if not self._enabled or self._mode != "dynamic":
            return {
                'sizing_scale': 1.0,
                'sl_scale': 1.0,
                'sniper_offset': self.config.sniper_rsi_offset,
                'breakeven_trigger_scale': 1.0,
            }

        return {
            'sizing_scale': self._state.sizing_scale,
            'sl_scale': self._state.sl_scale,
            'sniper_offset': self._state.sniper_offset_dynamic,
            'breakeven_trigger_scale': self._state.breakeven_trigger_scale,
        }

    def get_sniper_level_cap(self, direction: str, df: pd.DataFrame) -> float | None:
        """
        Get support/resistance-aware cap for sniper level placement.

        For LONG: returns the minimum price the sniper buy level should be at
                  (don't place below nearest demand zone — that's breakout territory).
        For SHORT: returns the maximum price the sniper sell level should be at
                   (don't place above nearest supply zone).

        Returns None if no cap applies (support-aware disabled or no zones found).
        """
        if not self._enabled or not self._support_aware:
            return None

        if df is None or len(df) < 50 or 'ATR' not in df.columns:
            return None

        zones = find_liquidity_zones(
            df, lookback=100, max_zones=5,
            swing_left=5, swing_right=2,
        )

        if not zones:
            return None

        current_price = float(df.iloc[-1]['close'])
        current_atr = float(df.iloc[-1]['ATR'])

        if direction == "LONG":
            # Find nearest demand zone below current price
            demand_zones = [z for z in zones
                           if z.zone_type == "demand" and z.mid_price < current_price]
            if demand_zones:
                nearest = demand_zones[0]  # Already sorted by distance
                # Cap: don't place buy limit below the top of nearest demand zone
                # (below it = you're catching a break of support)
                cap = nearest.price_high
                self.logger.info(
                    f"[RHYTHM] Sniper buy cap: ${cap:.2f} "
                    f"(demand zone ${nearest.price_low:.2f}-${nearest.price_high:.2f})"
                )
                return cap
        else:
            # Find nearest supply zone above current price
            supply_zones = [z for z in zones
                           if z.zone_type == "supply" and z.mid_price > current_price]
            if supply_zones:
                nearest = supply_zones[0]
                # Cap: don't place sell limit above the bottom of nearest supply zone
                cap = nearest.price_low
                self.logger.info(
                    f"[RHYTHM] Sniper sell cap: ${cap:.2f} "
                    f"(supply zone ${nearest.price_low:.2f}-${nearest.price_high:.2f})"
                )
                return cap

        return None

    def update(self, df: pd.DataFrame, htf_df: pd.DataFrame | None = None):
        """
        Update rhythm analysis with new candle data.

        Args:
            df: Primary timeframe DataFrame with RSI and ATR columns
            htf_df: Higher timeframe DataFrame (M15 for M5 bot, M5 for M1 bot)
        """
        if not self._enabled:
            return

        if df is None or len(df) < 50 or 'RSI' not in df.columns:
            return

        # Step 1: Detect RSI midline crossings
        self._detect_crossings(df)

        # Step 2: Measure swing extremes
        self._detect_extremes(df)

        # Step 3: Compute cycle metrics
        self._compute_cycle_metrics(df)

        # Step 4: Classify regime
        self._classify_regime(df, htf_df)

        # Step 5: Compute dynamic parameters (if dynamic mode)
        if self._mode == "dynamic":
            self._compute_dynamic_params(df)
            s = self._state
            self.logger.info(
                f"[RHYTHM] Dynamic params: regime={s.regime.value}, "
                f"cycle={s.full_cycle_bars:.0f}bars, amp=${s.amplitude_dollars:.2f}, "
                f"sizing={s.sizing_scale:.0%}, SL={s.sl_scale:.2f}x, "
                f"offset={s.sniper_offset_dynamic:.1f}, BE={s.breakeven_trigger_scale:.2f}x, "
                f"confidence={s.confidence:.2f}"
            )

    def _detect_crossings(self, df: pd.DataFrame):
        """Detect RSI crossings of the 50 midline."""
        rsi = df['RSI'].values
        closes = df['close'].values
        n = len(df)

        # Only look at last 100 bars for crossings
        start = max(0, n - 100)
        self._crossings = []

        for i in range(start + 1, n):
            if np.isnan(rsi[i]) or np.isnan(rsi[i - 1]):
                continue

            # Crossed from below to above
            if rsi[i - 1] < 50 and rsi[i] >= 50:
                self._crossings.append({
                    'bar_idx': i,
                    'rsi': float(rsi[i]),
                    'price': float(closes[i]),
                    'direction': 'up',
                })
            # Crossed from above to below
            elif rsi[i - 1] > 50 and rsi[i] <= 50:
                self._crossings.append({
                    'bar_idx': i,
                    'rsi': float(rsi[i]),
                    'price': float(closes[i]),
                    'direction': 'down',
                })

    def _detect_extremes(self, df: pd.DataFrame):
        """Detect RSI extremes between crossings (swing peaks/troughs)."""
        rsi = df['RSI'].values
        closes = df['close'].values
        self._extremes = []

        if len(self._crossings) < 2:
            return

        # Between each pair of crossings, find the RSI extreme
        for i in range(len(self._crossings) - 1):
            start_idx = self._crossings[i]['bar_idx']
            end_idx = self._crossings[i + 1]['bar_idx']
            direction = self._crossings[i]['direction']

            if end_idx <= start_idx:
                continue

            segment_rsi = rsi[start_idx:end_idx]
            segment_prices = closes[start_idx:end_idx]

            if len(segment_rsi) == 0:
                continue

            # Filter out NaN values
            valid_mask = ~np.isnan(segment_rsi)
            if not valid_mask.any():
                continue

            if direction == 'up':
                # RSI went above 50, find the peak
                extreme_local_idx = np.nanargmax(segment_rsi)
                extreme_rsi = float(segment_rsi[extreme_local_idx])
                extreme_price = float(segment_prices[extreme_local_idx])
                extreme_type = 'high'
            else:
                # RSI went below 50, find the trough
                extreme_local_idx = np.nanargmin(segment_rsi)
                extreme_rsi = float(segment_rsi[extreme_local_idx])
                extreme_price = float(segment_prices[extreme_local_idx])
                extreme_type = 'low'

            self._extremes.append({
                'bar_idx': start_idx + extreme_local_idx,
                'rsi': extreme_rsi,
                'price': extreme_price,
                'type': extreme_type,
                'crossing_price': self._crossings[i]['price'],
            })

    def _compute_cycle_metrics(self, df: pd.DataFrame):
        """Compute cycle length, amplitude, and stability from detected patterns."""
        if len(self._crossings) < 3:
            self._state.confidence = 0.1
            return

        # Half-cycle lengths (bars between consecutive crossings)
        half_cycles = []
        for i in range(1, len(self._crossings)):
            bars = self._crossings[i]['bar_idx'] - self._crossings[i - 1]['bar_idx']
            if bars > 0:
                half_cycles.append(bars)

        if not half_cycles:
            self._state.confidence = 0.1
            return

        self._state.half_cycle_bars = float(np.median(half_cycles))
        self._state.full_cycle_bars = self._state.half_cycle_bars * 2

        # Cycle stability: low std/mean ratio = stable
        if len(half_cycles) >= 3:
            cv = float(np.std(half_cycles) / np.mean(half_cycles))
            self._state.cycle_stability = max(0.0, min(1.0, 1.0 - cv))
        else:
            self._state.cycle_stability = 0.4

        # Amplitude from extremes
        if self._extremes:
            rsi_distances = [abs(e['rsi'] - 50) for e in self._extremes]
            self._state.amplitude_rsi = float(np.median(rsi_distances))

            # Price amplitude: distance from crossing to extreme
            price_moves = []
            for e in self._extremes:
                move = abs(e['price'] - e['crossing_price'])
                if move > 0:
                    price_moves.append(move)
            if price_moves:
                self._state.amplitude_dollars = float(np.median(price_moves))

        # Confidence based on number of observed cycles
        num_full_cycles = len(self._crossings) // 2
        self._state.confidence = min(1.0, num_full_cycles / 5.0)

    def _classify_regime(self, df: pd.DataFrame, htf_df: pd.DataFrame | None):
        """Classify current market regime based on computed metrics."""
        rsi = df['RSI'].values
        n = len(df)
        current_atr = float(df.iloc[-1]['ATR'])

        # Check for trending: RSI stuck on one side
        # Look at last 40 bars - if RSI never crosses 50, it's trending
        lookback = min(40, n - 1)
        recent_rsi = rsi[-lookback:]
        valid_rsi = recent_rsi[~np.isnan(recent_rsi)]

        if len(valid_rsi) < 10:
            self._state.regime = MarketRegime.CHAOTIC
            self._state.reason = "Insufficient RSI data"
            return

        all_above_50 = np.all(valid_rsi > 45)  # Slight tolerance
        all_below_50 = np.all(valid_rsi < 55)

        # Also check bars since last crossing
        bars_since_crossing = n - self._crossings[-1]['bar_idx'] if self._crossings else lookback
        trending_threshold = self._max_cycle_bars  # If no crossing for > max_cycle, it's trending

        # HTF confirmation of trend
        htf_trend_confirmed = False
        if htf_df is not None and len(htf_df) > 20 and 'RSI' in htf_df.columns:
            htf_rsi = float(htf_df.iloc[-1]['RSI'])
            htf_ema_fast = htf_df.iloc[-1].get('ema_fast', 0)
            htf_ema_slow = htf_df.iloc[-1].get('ema_slow', 0)
            htf_atr = float(htf_df.iloc[-1].get('ATR', 1))

            if htf_atr > 0:
                htf_divergence = abs(htf_ema_fast - htf_ema_slow) / htf_atr
                if htf_divergence > 1.5:
                    htf_trend_confirmed = True
                    self._htf_trending = True
                    self._htf_trend_direction = "up" if htf_ema_fast > htf_ema_slow else "down"
                else:
                    self._htf_trending = False
                    self._htf_trend_direction = ""

        # Dead market: ATR too low relative to historical or amplitude too small
        atr_values = df['ATR'].values[-100:]
        valid_atr = atr_values[~np.isnan(atr_values)]
        if len(valid_atr) >= 20:
            median_atr = float(np.median(valid_atr))
            if median_atr > 0 and current_atr < median_atr * self._dead_atr_factor:
                self._state.regime = MarketRegime.DEAD
                self._state.reason = (
                    f"ATR ${current_atr:.2f} < {self._dead_atr_factor:.0%} of "
                    f"median ${median_atr:.2f}"
                )
                return

            # Also dead if median ATR itself is tiny (consistently flat market)
            # Use absolute threshold: if ATR < 0.5 (for gold, $0.50 range per candle)
            if median_atr < 0.5:
                self._state.regime = MarketRegime.DEAD
                self._state.reason = (
                    f"Market dead: median ATR ${median_atr:.2f} (too low for trading)"
                )
                return

        # Trending: RSI hasn't crossed 50 for a long time, or stuck on one side
        if bars_since_crossing > trending_threshold or (all_above_50 or all_below_50):
            if bars_since_crossing > trending_threshold:
                # Clear case: no RSI crossing for longer than max cycle
                self._state.regime = MarketRegime.TRENDING
                self._state.reason = (
                    f"RSI hasn't crossed 50 for {bars_since_crossing} bars "
                    f"(max cycle {trending_threshold})"
                )
                return
            elif htf_trend_confirmed:
                self._state.regime = MarketRegime.TRENDING
                self._state.reason = (
                    f"RSI one-sided for {lookback} bars, "
                    f"HTF confirms {self._htf_trend_direction} trend"
                )
                return
            else:
                # RSI one-sided but no HTF confirmation and recent crossings exist
                # Could be just a strong half-cycle
                self._state.regime = MarketRegime.SWINGING
                self._state.reason = "Extended half-cycle (borderline)"
                return

        # Chaotic: REMOVED — fast oscillations are actually good for RSI trading.
        # Only trending (RSI one-sided) and dead (ATR too low) should block.
        # The min_cycle_bars check was causing false blocks on M1 where RSI(14)
        # naturally crosses 50 every 2-3 candles in normal swinging conditions.

        # Cycle too long for this timeframe
        if self._state.half_cycle_bars > self._max_cycle_bars:
            self._state.regime = MarketRegime.TRENDING
            self._state.reason = (
                f"Cycle too slow: {self._state.half_cycle_bars:.0f} bars "
                f"(max {self._max_cycle_bars})"
            )
            return

        # Check amplitude (is it worth trading?)
        if self._state.amplitude_dollars < current_atr * self._min_amplitude_atr:
            self._state.regime = MarketRegime.DEAD
            self._state.reason = (
                f"Swing amplitude ${self._state.amplitude_dollars:.2f} too small "
                f"(need ${current_atr * self._min_amplitude_atr:.2f})"
            )
            return

        # All checks passed: market is swinging
        self._state.regime = MarketRegime.SWINGING
        self._state.reason = (
            f"Cycle={self._state.full_cycle_bars:.0f} bars, "
            f"amplitude=${self._state.amplitude_dollars:.2f}, "
            f"stability={self._state.cycle_stability:.2f}"
        )

    def _compute_dynamic_params(self, df: pd.DataFrame):
        """Compute dynamic parameter adjustments based on rhythm analysis."""
        current_atr = float(df.iloc[-1]['ATR'])

        # -- Sizing scale --
        # Inverse relationship: smaller swings need larger positions to overcome costs.
        # Target: maintain consistent dollar profit per trade regardless of amplitude.
        # If amplitude is high (> 2 ATR), use normal size (1.0).
        # If amplitude is low but tradeable, scale UP so profit covers commission.
        # Capped at 1.5x to avoid excessive risk.
        # Below minimum amplitude, the regime check blocks entry entirely (DEAD).
        target_amplitude = current_atr * 1.5  # "Normal" amplitude benchmark
        if target_amplitude > 0 and self._state.amplitude_dollars > 0:
            # Inverse: smaller amplitude → larger scale
            raw_scale = target_amplitude / self._state.amplitude_dollars
            # Clamp: never below 0.7 (would mean huge swings, just use normal)
            # Never above 1.5 (risk cap)
            self._state.sizing_scale = max(0.7, min(1.5, raw_scale))
        else:
            self._state.sizing_scale = 1.0

        # -- SL/Trail scale --
        # High confidence + stable cycles = can tighten slightly
        # Low confidence + irregular = widen to survive noise
        if self._state.confidence > 0.7 and self._state.cycle_stability > 0.6:
            # Clean swings: slight tightening OK
            self._state.sl_scale = max(0.85, 1.0 - (self._state.cycle_stability - 0.6) * 0.3)
        elif self._state.confidence < 0.4 or self._state.cycle_stability < 0.3:
            # Irregular: widen SL
            self._state.sl_scale = min(1.4, 1.0 + (0.5 - self._state.cycle_stability) * 0.8)
        else:
            self._state.sl_scale = 1.0

        # -- Sniper offset --
        # Based on observed RSI extremes: place limit at typical extreme depth
        if self._extremes:
            # Look at recent low extremes (for buy side)
            low_extremes = [e for e in self._extremes[-6:] if e['type'] == 'low']
            high_extremes = [e for e in self._extremes[-6:] if e['type'] == 'high']

            if low_extremes:
                typical_low_rsi = float(np.median([e['rsi'] for e in low_extremes]))
                # Offset = how far below rsi_buy the typical extreme goes
                # But we want to be slightly inside the typical extreme (catch the swing)
                depth_below_buy = self.config.rsi_buy - typical_low_rsi
                # Place at 70% of typical depth (slightly conservative)
                suggested_offset = max(3.0, min(20.0, depth_below_buy * 0.7))
            else:
                suggested_offset = self.config.sniper_rsi_offset

            self._state.sniper_offset_dynamic = suggested_offset
        else:
            self._state.sniper_offset_dynamic = self.config.sniper_rsi_offset

        # -- Breakeven trigger scale --
        # High amplitude = fast moves = trigger BE faster
        # Low amplitude = slow moves = give more room
        if self._state.amplitude_dollars > current_atr * 2.0:
            self._state.breakeven_trigger_scale = 0.8  # Faster BE
        elif self._state.amplitude_dollars < current_atr * 0.8:
            self._state.breakeven_trigger_scale = 1.4  # Slower BE, more room
        else:
            self._state.breakeven_trigger_scale = 1.0

    def get_status(self) -> dict:
        """Current rhythm state for GUI display."""
        return {
            'enabled': self._enabled,
            'mode': self._mode,
            'regime': self._state.regime.value,
            'reason': self._state.reason,
            'half_cycle_bars': self._state.half_cycle_bars,
            'full_cycle_bars': self._state.full_cycle_bars,
            'amplitude_rsi': self._state.amplitude_rsi,
            'amplitude_dollars': self._state.amplitude_dollars,
            'cycle_stability': self._state.cycle_stability,
            'confidence': self._state.confidence,
            'sizing_scale': self._state.sizing_scale,
            'sl_scale': self._state.sl_scale,
            'sniper_offset': self._state.sniper_offset_dynamic,
            'tradeable': self.is_tradeable(),
            'htf_trending': self._htf_trending,
            'htf_direction': self._htf_trend_direction,
        }
