"""
Breakout Shield -- market-aware re-entry protection for the sniper bot.

After any stop-loss exit, analyzes whether the market is in a structural
breakout and blocks re-entry until evidence shows the breakout has failed
or been absorbed.

NOT timer-based. The shield lifts based on market analysis:
- Price returns past entry level (breakout failed)
- RSI normalizes (crosses back through 50)
- Momentum stalls (small-body candles in breakout direction)
- HTF reversal (higher timeframe unwinding)

Simple logic:
- SL hit → block that direction
- Price goes back to swinging → unblock, trade normally
- Price keeps breaking out → stay blocked
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.broker import TIMEFRAME_MAP, TIMEFRAME_MINUTES
from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)


class ShieldSeverity(Enum):
    """How serious the SL event was -- determines how many signals needed to lift."""
    NONE = "none"           # No shield active
    LIGHT = "light"         # Normal SL, need 1 normalization signal
    MEDIUM = "medium"       # Rapid SL or breakout detected, need 1 signal
    HEAVY = "heavy"         # Rapid SL + breakout + HTF aligned, need 2 signals


@dataclass
class SLEvent:
    """Record of a stop-loss exit for analysis."""
    direction: str              # "LONG" or "SHORT" -- the direction that was stopped
    entry_price: float
    sl_price: float
    exit_time: datetime
    duration_bars: int          # How many candles the position lasted
    was_rapid: bool = False     # Position lasted < rapid_sl_candles
    breakout_detected: bool = False
    htf_aligned: bool = False
    severity: ShieldSeverity = ShieldSeverity.LIGHT


@dataclass
class ShieldState:
    """Current state of the breakout shield for one direction."""
    active: bool = False
    severity: ShieldSeverity = ShieldSeverity.NONE
    direction_blocked: str = ""     # "LONG" or "SHORT"
    signals_needed: int = 0         # How many normalization signals still needed
    signals_collected: list[str] = field(default_factory=list)
    event: SLEvent | None = None    # The SL event that triggered the shield
    reason: str = ""


class BreakoutShield:
    """
    Market-aware re-entry protection after stop-loss exits.

    After any SL exit:
    1. Classifies severity (was it a normal swing miss or a breakout?)
    2. Blocks re-entry for the affected direction
    3. Monitors market for normalization signals
    4. Lifts the shield when sufficient evidence shows the breakout is over

    Simple behavior: block until the market proves it's swinging again.
    No reduced sizing, no timers. Just block/unblock.
    """

    def __init__(self, config: TradingConfig, bot_label: str = ""):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger

        self._enabled = config.shield_enabled
        self._rapid_sl_candles = config.shield_rapid_sl_candles

        # Shield states (one per direction)
        self._long_shield = ShieldState()
        self._short_shield = ShieldState()

        # History of SL events (for pattern detection)
        self._sl_history: list[SLEvent] = []

        # Consecutive SL tracking
        self._consecutive_sl_long: int = 0
        self._consecutive_sl_short: int = 0

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def allow_entry(self, direction: str) -> tuple[bool, str]:
        """
        Check if entry is allowed for the given direction.

        Returns (allowed: bool, reason: str).
        If not allowed, reason explains why.
        """
        if not self._enabled:
            return True, ""

        shield = self._long_shield if direction == "LONG" else self._short_shield

        if shield.active:
            signals_text = ", ".join(shield.signals_collected) if shield.signals_collected else "none yet"
            return False, (
                f"Shield active ({shield.severity.value}): "
                f"need {shield.signals_needed} more signal(s). "
                f"Got: [{signals_text}]. {shield.reason}"
            )

        return True, ""

    def get_sizing_adjustment(self) -> float:
        """Get position sizing multiplier. Always 1.0 (no reduced sizing)."""
        return 1.0

    def get_sl_adjustment(self) -> float:
        """Get SL/trail distance multiplier. Always 1.0 (no SL adjustment)."""
        return 1.0

    def record_entry(self, direction: str):
        """Record that an entry was made (no-op, kept for interface compat)."""
        pass

    def record_sl_exit(
        self,
        direction: str,
        duration_bars: int,
        entry_price: float,
        sl_price: float,
        df: pd.DataFrame,
        htf_df: pd.DataFrame | None = None,
        h1_df: pd.DataFrame | None = None,
    ):
        """
        Record a stop-loss exit and activate the shield.

        Immediately analyzes the SL event, classifies severity,
        and blocks re-entry for the affected direction.

        Args:
            direction: "LONG" or "SHORT" -- which direction was stopped out
            duration_bars: How many candles the position was open
            entry_price: Position entry price
            sl_price: Where the SL was hit
            df: Primary timeframe data (for breakout level detection)
            htf_df: Higher timeframe data (M15 for M5 bot)
            h1_df: H1 data for macro trend confirmation
        """
        if not self._enabled:
            return

        now = get_local_now()

        # Step 1: Was it a rapid SL?
        was_rapid = duration_bars <= self._rapid_sl_candles

        # Step 2: Breakout level detection
        breakout_detected = self._check_breakout_level(direction, sl_price, df)

        # Step 3: HTF alignment check
        htf_aligned = self._check_htf_alignment(direction, htf_df, h1_df)

        # Step 4: Track consecutive SLs
        if direction == "LONG":
            self._consecutive_sl_long += 1
            self._consecutive_sl_short = 0
        else:
            self._consecutive_sl_short += 1
            self._consecutive_sl_long = 0

        consecutive = (self._consecutive_sl_long if direction == "LONG"
                       else self._consecutive_sl_short)

        # Step 5: Classify severity
        severity = self._classify_severity(
            was_rapid, breakout_detected, htf_aligned, consecutive
        )

        # Create event record
        event = SLEvent(
            direction=direction,
            entry_price=entry_price,
            sl_price=sl_price,
            exit_time=now,
            duration_bars=duration_bars,
            was_rapid=was_rapid,
            breakout_detected=breakout_detected,
            htf_aligned=htf_aligned,
            severity=severity,
        )
        self._sl_history.append(event)
        # Keep history bounded
        if len(self._sl_history) > 20:
            self._sl_history = self._sl_history[-20:]

        # Step 6: Activate the shield
        self._activate_shield(direction, event)

        self.logger.warning(
            f"[SHIELD] ACTIVATED for {direction}: severity={severity.value}, "
            f"rapid={was_rapid}, breakout={breakout_detected}, htf_aligned={htf_aligned}, "
            f"duration={duration_bars} bars, consecutive={consecutive}"
        )

    def update(
        self,
        current_price: float,
        rsi: float,
        df: pd.DataFrame,
        htf_df: pd.DataFrame | None = None,
    ):
        """
        Update shield state -- check if normalization conditions are met.

        Call this each candle (or more frequently). Checks if the market
        has stabilized enough to lift the shield.

        Args:
            current_price: Current bid price
            rsi: Current RSI value on primary timeframe
            df: Primary timeframe DataFrame (for momentum stall detection)
            htf_df: Higher timeframe DataFrame (for HTF reversal detection)
        """
        if not self._enabled:
            return

        for shield in [self._long_shield, self._short_shield]:
            if not shield.active:
                continue

            event = shield.event
            if event is None:
                continue

            signals_before = len(shield.signals_collected)

            # Check each normalization condition
            self._check_price_return(shield, event, current_price)
            self._check_rsi_normalize(shield, event, rsi)
            self._check_momentum_stall(shield, event, df)
            self._check_htf_reversal(shield, event, htf_df)

            # Log new signals
            if len(shield.signals_collected) > signals_before:
                new_signals = shield.signals_collected[signals_before:]
                self.logger.info(
                    f"[SHIELD] New signals for {shield.direction_blocked}: "
                    f"{new_signals}. Need {shield.signals_needed} more."
                )

            # Check if enough signals collected to lift
            if shield.signals_needed <= 0:
                self._lift_shield(shield)

    def _check_breakout_level(self, direction: str, sl_price: float, df: pd.DataFrame) -> bool:
        """Check if the SL price was near a structural breakout level."""
        if df is None or len(df) < 20 or 'ATR' not in df.columns:
            return False

        current_atr = float(df.iloc[-1]['ATR'])
        if current_atr <= 0:
            return False

        # Compute N-bar high/low (same logic as breakout strategy)
        n = min(20, len(df) - 2)  # Look at last 20 bars
        lookback = df.iloc[-(n + 1):-1]
        breakout_high = float(lookback['high'].max())
        breakout_low = float(lookback['low'].min())

        current_price = float(df.iloc[-1]['close'])

        if direction == "LONG":
            # Long got stopped: check if price broke below support
            distance_to_low = abs(sl_price - breakout_low)
            # If SL was within 1 ATR of the breakout low AND price went through
            if distance_to_low < current_atr and current_price < breakout_low:
                return True
        else:
            # Short got stopped: check if price broke above resistance
            distance_to_high = abs(sl_price - breakout_high)
            if distance_to_high < current_atr and current_price > breakout_high:
                return True

        return False

    def _check_htf_alignment(
        self,
        direction: str,
        htf_df: pd.DataFrame | None,
        h1_df: pd.DataFrame | None,
    ) -> bool:
        """Check if higher timeframes align with the direction that stopped us."""
        aligned_count = 0

        # Check M15/M5 (first HTF)
        if htf_df is not None and len(htf_df) > 20:
            if 'RSI' in htf_df.columns:
                htf_rsi = float(htf_df.iloc[-1]['RSI'])
                if direction == "LONG" and htf_rsi < 40:
                    # HTF bearish momentum confirms the long was fighting the trend
                    aligned_count += 1
                elif direction == "SHORT" and htf_rsi > 60:
                    aligned_count += 1

            if 'ema_fast' in htf_df.columns and 'ema_slow' in htf_df.columns:
                htf_fast = float(htf_df.iloc[-1]['ema_fast'])
                htf_slow = float(htf_df.iloc[-1]['ema_slow'])
                if direction == "LONG" and htf_fast < htf_slow:
                    aligned_count += 1
                elif direction == "SHORT" and htf_fast > htf_slow:
                    aligned_count += 1

        # Check H1 (macro)
        if h1_df is not None and len(h1_df) > 10:
            if 'ema_fast' in h1_df.columns and 'ema_slow' in h1_df.columns:
                h1_fast = float(h1_df.iloc[-1]['ema_fast'])
                h1_slow = float(h1_df.iloc[-1]['ema_slow'])
                if direction == "LONG" and h1_fast < h1_slow:
                    aligned_count += 1
                elif direction == "SHORT" and h1_fast > h1_slow:
                    aligned_count += 1

        # Need at least 2 HTF signals agreeing
        return aligned_count >= 2

    def _classify_severity(
        self,
        was_rapid: bool,
        breakout_detected: bool,
        htf_aligned: bool,
        consecutive: int,
    ) -> ShieldSeverity:
        """Classify the severity of the SL event."""
        # Worst case: rapid + breakout + HTF aligned
        if was_rapid and breakout_detected and htf_aligned:
            return ShieldSeverity.HEAVY

        # Rapid + breakout OR consecutive > 2
        if (was_rapid and breakout_detected) or consecutive >= 3:
            return ShieldSeverity.HEAVY

        # Rapid SL alone OR breakout alone
        if was_rapid or breakout_detected:
            return ShieldSeverity.MEDIUM

        # Normal duration SL + HTF aligned (might still be dangerous)
        if htf_aligned and consecutive >= 2:
            return ShieldSeverity.MEDIUM

        # Default: any SL triggers at least light shield
        return ShieldSeverity.LIGHT

    def _activate_shield(self, direction: str, event: SLEvent):
        """Activate the shield for the given direction."""
        shield = self._long_shield if direction == "LONG" else self._short_shield

        # Determine signals needed based on severity
        # HEAVY = need 2 signals (strong evidence needed that breakout is over)
        # MEDIUM/LIGHT = need 1 signal (any sign of normalization is enough)
        if event.severity == ShieldSeverity.HEAVY:
            signals_needed = 2
        else:
            signals_needed = 1

        shield.active = True
        shield.severity = event.severity
        shield.direction_blocked = direction
        shield.signals_needed = signals_needed
        shield.signals_collected = []
        shield.event = event
        shield.reason = (
            f"SL at ${event.sl_price:.2f} after {event.duration_bars} bars"
        )

    def _check_price_return(self, shield: ShieldState, event: SLEvent, current_price: float):
        """Check if price has returned past the entry level (breakout failed)."""
        signal_name = "price_return"
        if signal_name in shield.signals_collected:
            return

        if event.direction == "LONG":
            # For a stopped long: price returning ABOVE entry = breakout failed
            if current_price >= event.entry_price:
                shield.signals_collected.append(signal_name)
                shield.signals_needed -= 1
        else:
            # For a stopped short: price returning BELOW entry = breakout failed
            if current_price <= event.entry_price:
                shield.signals_collected.append(signal_name)
                shield.signals_needed -= 1

    def _check_rsi_normalize(self, shield: ShieldState, event: SLEvent, rsi: float):
        """Check if RSI has crossed back through 50 (momentum exhausted)."""
        signal_name = "rsi_normalize"
        if signal_name in shield.signals_collected:
            return

        if np.isnan(rsi):
            return

        if event.direction == "LONG":
            # Long was stopped (price went down). RSI going back above 50 = selling exhausted.
            if rsi >= 50:
                shield.signals_collected.append(signal_name)
                shield.signals_needed -= 1
        else:
            # Short was stopped (price went up). RSI going back below 50 = buying exhausted.
            if rsi <= 50:
                shield.signals_collected.append(signal_name)
                shield.signals_needed -= 1

    def _check_momentum_stall(self, shield: ShieldState, event: SLEvent, df: pd.DataFrame):
        """Check if momentum has stalled (3 small-body candles)."""
        signal_name = "momentum_stall"
        if signal_name in shield.signals_collected:
            return

        if df is None or len(df) < 5 or 'ATR' not in df.columns:
            return

        current_atr = float(df.iloc[-1]['ATR'])
        if current_atr <= 0:
            return

        # Check last 3 candles: all have small bodies relative to ATR
        last_3 = df.iloc[-3:]
        bodies = (last_3['close'] - last_3['open']).abs().values

        # All bodies < 0.5 ATR = momentum stalled
        if np.all(bodies < current_atr * 0.5):
            shield.signals_collected.append(signal_name)
            shield.signals_needed -= 1

    def _check_htf_reversal(self, shield: ShieldState, event: SLEvent, htf_df: pd.DataFrame | None):
        """Check if HTF has started reversing (momentum unwinding on higher TF)."""
        signal_name = "htf_reversal"
        if signal_name in shield.signals_collected:
            return

        if htf_df is None or len(htf_df) < 5 or 'RSI' not in htf_df.columns:
            return

        htf_rsi = float(htf_df.iloc[-1]['RSI'])
        htf_rsi_prev = float(htf_df.iloc[-2]['RSI'])

        if np.isnan(htf_rsi) or np.isnan(htf_rsi_prev):
            return

        if event.direction == "LONG":
            # Long was stopped (bearish move). HTF RSI turning up from extreme = reversal
            if htf_rsi > htf_rsi_prev and htf_rsi_prev < 40:
                shield.signals_collected.append(signal_name)
                shield.signals_needed -= 1
        else:
            # Short was stopped (bullish move). HTF RSI turning down from extreme = reversal
            if htf_rsi < htf_rsi_prev and htf_rsi_prev > 60:
                shield.signals_collected.append(signal_name)
                shield.signals_needed -= 1

    def _lift_shield(self, shield: ShieldState):
        """Lift the shield -- re-entry is now allowed."""
        direction = shield.direction_blocked

        self.logger.info(
            f"[SHIELD] LIFTED for {direction}. "
            f"Signals: {shield.signals_collected}."
        )

        # Reset the shield
        shield.active = False
        shield.severity = ShieldSeverity.NONE
        shield.direction_blocked = ""
        shield.signals_needed = 0
        shield.signals_collected = []
        shield.event = None
        shield.reason = ""

    def record_profitable_exit(self, direction: str):
        """
        Record a profitable exit -- resets consecutive SL counter for that direction.
        """
        if direction == "LONG":
            self._consecutive_sl_long = 0
        else:
            self._consecutive_sl_short = 0

    def get_status(self) -> dict:
        """Current shield state for GUI display."""
        return {
            'enabled': self._enabled,
            'long_shield': {
                'active': self._long_shield.active,
                'severity': self._long_shield.severity.value,
                'signals_needed': self._long_shield.signals_needed,
                'signals_collected': self._long_shield.signals_collected,
                'reason': self._long_shield.reason,
            },
            'short_shield': {
                'active': self._short_shield.active,
                'severity': self._short_shield.severity.value,
                'signals_needed': self._short_shield.signals_needed,
                'signals_collected': self._short_shield.signals_collected,
                'reason': self._short_shield.reason,
            },
            'consecutive_sl_long': self._consecutive_sl_long,
            'consecutive_sl_short': self._consecutive_sl_short,
        }
