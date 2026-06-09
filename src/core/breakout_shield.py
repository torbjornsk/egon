"""
Breakout Shield -- escalating re-entry protection after stop-loss exits.

After a losing stop-loss, blocks re-entry with escalating requirements:

1st SL:  Need 2 green candles (long) or 2 red candles (short) before re-entry
2nd SL:  Need RSI to reach 40+ (stopped long) or 60- (stopped short)
3rd+ SL: Need RSI to fully revert past 50 (55+ for stopped long, 45- for stopped short)

Simple, conservative, and predictable.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)


class ShieldSeverity:
    """Escalation level based on consecutive SLs."""
    FIRST = "first"       # 1st SL: need 2 recovery candles
    SECOND = "second"     # 2nd SL: need RSI 40/60
    THIRD = "third"       # 3rd+ SL: need RSI 55/45 (full revert past 50)


@dataclass
class ShieldState:
    """Current state of the breakout shield for one direction."""
    active: bool = False
    severity: str = ""
    direction_blocked: str = ""     # "LONG" or "SHORT"
    # For 1st SL: count recovery candles
    recovery_candles_seen: int = 0
    recovery_candles_needed: int = 2
    # For 2nd/3rd SL: RSI threshold that must be reached
    rsi_threshold: float = 0.0
    # Tracking
    entry_price: float = 0.0
    reason: str = ""


class BreakoutShield:
    """
    Escalating re-entry protection after stop-loss exits.

    Behavior:
    - 1st SL in a direction: block until 2 green candles (long) / red candles (short)
    - 2nd consecutive SL: block until RSI reaches 40 (long) / 60 (short)
    - 3rd+ consecutive SL: block until RSI reaches 55 (long) / 45 (short)
    - A profitable trade resets the consecutive counter

    All thresholds configurable.
    """

    def __init__(self, config: TradingConfig, bot_label: str = ""):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger

        self._enabled = config.shield_enabled

        # Configurable thresholds
        # 2nd SL: RSI must reach this level (stopped long needs RSI >= this)
        self._second_sl_rsi = getattr(config, 'shield_second_sl_rsi', 40.0)
        # 3rd+ SL: RSI must reach this level (past midline)
        self._third_sl_rsi = getattr(config, 'shield_third_sl_rsi', 55.0)
        # 1st SL: recovery candles needed
        self._recovery_candles = getattr(config, 'shield_recovery_candles', 2)

        # Shield states (one per direction)
        self._long_shield = ShieldState()
        self._short_shield = ShieldState()

        # Consecutive SL tracking per direction
        self._consecutive_sl_long: int = 0
        self._consecutive_sl_short: int = 0

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def allow_entry(self, direction: str) -> tuple[bool, str]:
        """
        Check if entry is allowed for the given direction.

        Returns (allowed: bool, reason: str).
        """
        if not self._enabled:
            return True, ""

        shield = self._long_shield if direction == "LONG" else self._short_shield

        if shield.active:
            return False, (
                f"Shield ({shield.severity}): {shield.reason}"
            )

        return True, ""

    def get_sizing_adjustment(self) -> float:
        """Always 1.0 (no reduced sizing)."""
        return 1.0

    def get_sl_adjustment(self) -> float:
        """Always 1.0 (no SL adjustment)."""
        return 1.0

    def record_entry(self, direction: str):
        """No-op, kept for interface compat."""
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
        Record a losing stop-loss exit and activate the shield.

        Escalation based on consecutive SLs in the same direction.
        """
        if not self._enabled:
            return

        # Track consecutive SLs
        if direction == "LONG":
            self._consecutive_sl_long += 1
            consecutive = self._consecutive_sl_long
        else:
            self._consecutive_sl_short += 1
            consecutive = self._consecutive_sl_short

        # Determine severity and requirements
        shield = self._long_shield if direction == "LONG" else self._short_shield

        if consecutive == 1:
            # 1st SL: need N recovery candles (green for long, red for short)
            shield.active = True
            shield.severity = ShieldSeverity.FIRST
            shield.direction_blocked = direction
            shield.recovery_candles_seen = 0
            shield.recovery_candles_needed = self._recovery_candles
            shield.rsi_threshold = 0
            shield.entry_price = entry_price
            candle_type = "green" if direction == "LONG" else "red"
            shield.reason = (
                f"1st SL: need {self._recovery_candles} {candle_type} candles "
                f"(seen 0/{self._recovery_candles})"
            )

        elif consecutive == 2:
            # 2nd SL: need RSI to reach 40 (long) or 60 (short)
            shield.active = True
            shield.severity = ShieldSeverity.SECOND
            shield.direction_blocked = direction
            shield.recovery_candles_seen = 0
            shield.entry_price = entry_price
            if direction == "LONG":
                shield.rsi_threshold = self._second_sl_rsi
                shield.reason = f"2nd SL: need RSI >= {self._second_sl_rsi:.0f}"
            else:
                # For stopped short, RSI must go LOW (opposite direction recovery)
                shield.rsi_threshold = 100 - self._second_sl_rsi  # 60
                shield.reason = f"2nd SL: need RSI <= {100 - self._second_sl_rsi:.0f}"

        else:
            # 3rd+ SL: need RSI to fully revert past midline
            shield.active = True
            shield.severity = ShieldSeverity.THIRD
            shield.direction_blocked = direction
            shield.recovery_candles_seen = 0
            shield.entry_price = entry_price
            if direction == "LONG":
                shield.rsi_threshold = self._third_sl_rsi
                shield.reason = f"3rd+ SL: need RSI >= {self._third_sl_rsi:.0f}"
            else:
                shield.rsi_threshold = 100 - self._third_sl_rsi  # 45
                shield.reason = f"3rd+ SL: need RSI <= {100 - self._third_sl_rsi:.0f}"

        self.logger.warning(
            f"[SHIELD] ACTIVATED for {direction}: {shield.severity}, "
            f"consecutive={consecutive}, {shield.reason}"
        )

    def update(
        self,
        current_price: float,
        rsi: float,
        df: pd.DataFrame,
        htf_df: pd.DataFrame | None = None,
    ):
        """
        Update shield state. Check if recovery conditions are met.

        Call this each candle.
        """
        if not self._enabled:
            return

        for shield in [self._long_shield, self._short_shield]:
            if not shield.active:
                continue

            if shield.severity == ShieldSeverity.FIRST:
                self._check_recovery_candles(shield, df)
            elif shield.severity in (ShieldSeverity.SECOND, ShieldSeverity.THIRD):
                self._check_rsi_recovery(shield, rsi)

    def _check_recovery_candles(self, shield: ShieldState, df: pd.DataFrame):
        """
        For 1st SL: count candles that closed in the recovery direction.

        Stopped long: count green candles (close > open)
        Stopped short: count red candles (close < open)
        Not consecutive required -- just total count.
        """
        if df is None or len(df) < 2:
            return

        # Check the latest closed candle
        latest = df.iloc[-1]
        candle_close = float(latest['close'])
        candle_open = float(latest['open'])

        is_green = candle_close > candle_open
        is_red = candle_close < candle_open

        # We track using the latest candle each update.
        # To avoid counting the same candle twice, we use df length as a proxy.
        # Actually simpler: just count from recent candles in the df since shield activated.
        # Reset and recount from recent data each update.
        recent_n = shield.recovery_candles_needed + 5  # Look at last few candles
        if len(df) < recent_n:
            recent_n = len(df)

        recent = df.iloc[-recent_n:]
        closes = recent['close'].values
        opens = recent['open'].values

        if shield.direction_blocked == "LONG":
            # Count green candles (recovery for stopped long = price going up)
            count = int(np.sum(closes > opens))
        else:
            # Count red candles (recovery for stopped short = price going down)
            count = int(np.sum(closes < opens))

        shield.recovery_candles_seen = min(count, shield.recovery_candles_needed)
        candle_type = "green" if shield.direction_blocked == "LONG" else "red"
        shield.reason = (
            f"1st SL: need {shield.recovery_candles_needed} {candle_type} candles "
            f"(seen {shield.recovery_candles_seen}/{shield.recovery_candles_needed})"
        )

        if shield.recovery_candles_seen >= shield.recovery_candles_needed:
            self._lift_shield(shield)

    def _check_rsi_recovery(self, shield: ShieldState, rsi: float):
        """
        For 2nd/3rd+ SL: check if RSI has reached the required threshold.
        """
        if np.isnan(rsi):
            return

        threshold = shield.rsi_threshold

        if shield.direction_blocked == "LONG":
            # Stopped long: RSI must go UP to threshold (40 or 55)
            if rsi >= threshold:
                self.logger.info(
                    f"[SHIELD] RSI {rsi:.1f} >= {threshold:.0f}: lifting for LONG"
                )
                self._lift_shield(shield)
            else:
                shield.reason = (
                    f"{shield.severity} SL: need RSI >= {threshold:.0f} "
                    f"(current {rsi:.1f})"
                )
        else:
            # Stopped short: RSI must go DOWN to threshold (60 or 45)
            if rsi <= threshold:
                self.logger.info(
                    f"[SHIELD] RSI {rsi:.1f} <= {threshold:.0f}: lifting for SHORT"
                )
                self._lift_shield(shield)
            else:
                shield.reason = (
                    f"{shield.severity} SL: need RSI <= {threshold:.0f} "
                    f"(current {rsi:.1f})"
                )

    def _lift_shield(self, shield: ShieldState):
        """Lift the shield -- re-entry allowed."""
        direction = shield.direction_blocked
        self.logger.info(f"[SHIELD] LIFTED for {direction}: {shield.reason}")

        shield.active = False
        shield.severity = ""
        shield.direction_blocked = ""
        shield.recovery_candles_seen = 0
        shield.rsi_threshold = 0
        shield.entry_price = 0
        shield.reason = ""

    def record_profitable_exit(self, direction: str):
        """A profitable exit resets the consecutive SL counter."""
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
                'severity': self._long_shield.severity,
                'reason': self._long_shield.reason,
                'recovery_candles': f"{self._long_shield.recovery_candles_seen}/{self._long_shield.recovery_candles_needed}",
            },
            'short_shield': {
                'active': self._short_shield.active,
                'severity': self._short_shield.severity,
                'reason': self._short_shield.reason,
                'recovery_candles': f"{self._short_shield.recovery_candles_seen}/{self._short_shield.recovery_candles_needed}",
            },
            'consecutive_sl_long': self._consecutive_sl_long,
            'consecutive_sl_short': self._consecutive_sl_short,
        }
