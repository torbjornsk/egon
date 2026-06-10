"""
Breakout Shield -- candle-based re-entry protection after stop-loss exits.

After a losing stop-loss, blocks re-entry in that direction until N candles
close in the recovery direction (confirming the move against us is pausing).

Escalation:
  1st SL:  Need 1 candle in recovery direction
  2nd SL:  Need 2 candles in recovery direction
  3rd+ SL: Need 3 candles in recovery direction

Rules:
- Buy and sell counters are independent
- Counter resets on: successful trade (breakeven or better) in same direction,
  OR any entry in the opposite direction
- No position size reduction
- Recovery candles do NOT need to be consecutive
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)


@dataclass
class ShieldState:
    """Current state of the breakout shield for one direction."""
    active: bool = False
    direction_blocked: str = ""
    recovery_candles_seen: int = 0
    recovery_candles_needed: int = 1
    candles_since_activation: int = 0
    reason: str = ""


class BreakoutShield:
    """
    Candle-based re-entry protection after stop-loss exits.

    Simple escalating protection: more consecutive SLs = more recovery
    candles needed before re-entry is allowed.
    """

    def __init__(self, config: TradingConfig, bot_label: str = ""):
        self.config = config
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger

        self._enabled = config.shield_enabled

        # Shield states (one per direction, fully independent)
        self._long_shield = ShieldState()
        self._short_shield = ShieldState()

        # Consecutive SL tracking per direction (independent counters)
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
            return False, f"Shield: {shield.reason}"

        return True, ""

    def get_sizing_adjustment(self) -> float:
        """No reduced sizing."""
        return 1.0

    def get_sl_adjustment(self) -> float:
        """No SL adjustment."""
        return 1.0

    def record_entry(self, direction: str):
        """
        Record that a position was opened.

        Opening in the OPPOSITE direction resets the other side's counter.
        """
        if not self._enabled:
            return

        # Entry in opposite direction resets the other side's consecutive counter
        if direction == "LONG":
            if self._consecutive_sl_short > 0:
                self.logger.info(
                    f"[SHIELD] LONG entry resets SHORT consecutive SL counter "
                    f"({self._consecutive_sl_short} -> 0)"
                )
                self._consecutive_sl_short = 0
                # Also lift short shield if active
                if self._short_shield.active:
                    self._lift_shield(self._short_shield)
        else:
            if self._consecutive_sl_long > 0:
                self.logger.info(
                    f"[SHIELD] SHORT entry resets LONG consecutive SL counter "
                    f"({self._consecutive_sl_long} -> 0)"
                )
                self._consecutive_sl_long = 0
                if self._long_shield.active:
                    self._lift_shield(self._long_shield)

    def record_sl_exit(
        self,
        direction: str,
        duration_bars: int = 0,
        entry_price: float = 0.0,
        sl_price: float = 0.0,
        df: pd.DataFrame | None = None,
        htf_df: pd.DataFrame | None = None,
        h1_df: pd.DataFrame | None = None,
    ):
        """
        Record a losing stop-loss exit and activate the shield.

        Escalation: 1st SL = 1 candle, 2nd SL = 2 candles, 3rd+ = 3 candles.
        """
        if not self._enabled:
            return

        # Track consecutive SLs per direction
        if direction == "LONG":
            self._consecutive_sl_long += 1
            consecutive = self._consecutive_sl_long
        else:
            self._consecutive_sl_short += 1
            consecutive = self._consecutive_sl_short

        # Determine candles needed (1, 2, or 3 based on consecutive count)
        candles_needed = min(consecutive, 3)

        # Activate shield
        shield = self._long_shield if direction == "LONG" else self._short_shield
        shield.active = True
        shield.direction_blocked = direction
        shield.recovery_candles_seen = 0
        shield.recovery_candles_needed = candles_needed
        shield.candles_since_activation = 0

        candle_type = "green" if direction == "LONG" else "red"
        shield.reason = (
            f"SL #{consecutive}: need {candles_needed} {candle_type} "
            f"candles (seen 0/{candles_needed})"
        )

        self.logger.warning(
            f"[SHIELD] ACTIVATED for {direction}: consecutive={consecutive}, "
            f"{shield.reason}"
        )

    def update(
        self,
        current_price: float,
        rsi: float,
        df: pd.DataFrame,
        htf_df: pd.DataFrame | None = None,
    ):
        """
        Update shield state. Check if recovery candles condition is met.

        Call this each candle.
        """
        if not self._enabled:
            return

        for shield in [self._long_shield, self._short_shield]:
            if not shield.active:
                continue
            self._check_recovery_candles(shield, df)

    def _check_recovery_candles(self, shield: ShieldState, df: pd.DataFrame):
        """
        Count candles that closed in the recovery direction AFTER activation.

        Stopped long: count green candles (close > open)
        Stopped short: count red candles (close < open)
        Not required to be consecutive -- just total count since activation.
        """
        if df is None or len(df) < 2:
            return

        # Increment candle counter (only look at candles since shield was activated)
        shield.candles_since_activation += 1

        n = min(shield.candles_since_activation, len(df))
        recent = df.iloc[-n:]
        closes = recent['close'].values
        opens = recent['open'].values

        if shield.direction_blocked == "LONG":
            # Recovery for stopped long = green candles (price going up)
            count = int(np.sum(closes > opens))
        else:
            # Recovery for stopped short = red candles (price going down)
            count = int(np.sum(closes < opens))

        shield.recovery_candles_seen = count
        candle_type = "green" if shield.direction_blocked == "LONG" else "red"
        shield.reason = (
            f"SL: need {shield.recovery_candles_needed} {candle_type} "
            f"candles (seen {count}/{shield.recovery_candles_needed})"
        )

        if count >= shield.recovery_candles_needed:
            self._lift_shield(shield)

    def _lift_shield(self, shield: ShieldState):
        """Lift the shield -- re-entry allowed."""
        direction = shield.direction_blocked
        if direction:
            self.logger.info(f"[SHIELD] LIFTED for {direction}: {shield.reason}")

        shield.active = False
        shield.direction_blocked = ""
        shield.recovery_candles_seen = 0
        shield.recovery_candles_needed = 1
        shield.candles_since_activation = 0
        shield.reason = ""

    def record_profitable_exit(self, direction: str):
        """
        A successful trade (breakeven or better) resets the consecutive
        SL counter for that direction.
        """
        if direction == "LONG":
            if self._consecutive_sl_long > 0:
                self.logger.info(
                    f"[SHIELD] Profitable LONG exit resets consecutive counter "
                    f"({self._consecutive_sl_long} -> 0)"
                )
                self._consecutive_sl_long = 0
        else:
            if self._consecutive_sl_short > 0:
                self.logger.info(
                    f"[SHIELD] Profitable SHORT exit resets consecutive counter "
                    f"({self._consecutive_sl_short} -> 0)"
                )
                self._consecutive_sl_short = 0

    def get_status(self) -> dict:
        """Current shield state for GUI display."""
        return {
            'enabled': self._enabled,
            'long_shield': {
                'active': self._long_shield.active,
                'reason': self._long_shield.reason,
                'recovery_candles': (
                    f"{self._long_shield.recovery_candles_seen}/"
                    f"{self._long_shield.recovery_candles_needed}"
                ),
            },
            'short_shield': {
                'active': self._short_shield.active,
                'reason': self._short_shield.reason,
                'recovery_candles': (
                    f"{self._short_shield.recovery_candles_seen}/"
                    f"{self._short_shield.recovery_candles_needed}"
                ),
            },
            'consecutive_sl_long': self._consecutive_sl_long,
            'consecutive_sl_short': self._consecutive_sl_short,
        }
