"""
Risk management  --  Dead Man's Switch.

Safety checks: max drawdown, emergency equity threshold, weekend close,
market gap detection.

Legacy checks (daily loss, rapid loss, consecutive losses) have been removed.
Those concerns are now handled by per-bot mechanisms: breakout shield,
loss backoff cooldown, and rhythm gating.
"""

import logging
from datetime import datetime

import numpy as np
import pytz

from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)


class RiskManager:
    """Centralized safety checks for trading bots."""

    def __init__(
        self,
        max_drawdown_limit: float = 0.35,
        emergency_equity_threshold_pct: float = 0.50,
        bot_label: str = "",
    ):
        self.max_drawdown_limit = max_drawdown_limit
        self.emergency_equity_threshold_pct = emergency_equity_threshold_pct
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger

        # State
        self.starting_balance: float | None = None
        self.peak_balance: float | None = None
        self.consecutive_losses: int = 0

        self.trading_paused: bool = False
        self.pause_reason: str | None = None

    def initialize(self, balance: float):
        """Set starting/peak balance on connect."""
        self.starting_balance = balance
        self.peak_balance = balance

    def record_trade_result(self, profit: float):
        """Update consecutive loss counter after a trade closes."""
        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def _pause(self, reason: str):
        if not self.trading_paused:
            self.logger.warning(f"TRADING PAUSED: {reason}")
            self.trading_paused = True
            self.pause_reason = reason

    # ── Individual checks ───────────────────────────────────────────────

    def check_drawdown(self, current_balance: float) -> bool:
        if self.peak_balance is None:
            self.peak_balance = current_balance
        self.peak_balance = max(self.peak_balance, current_balance)

        drawdown = (self.peak_balance - current_balance) / self.peak_balance
        if drawdown >= self.max_drawdown_limit:
            self._pause(f"Drawdown limit ({drawdown*100:.1f}%)")
            return True
        return False

    def check_emergency_equity(self, equity: float) -> bool:
        if self.starting_balance is None:
            return False
        loss = (self.starting_balance - equity) / self.starting_balance
        if loss >= self.emergency_equity_threshold_pct:
            self.logger.critical(f"EMERGENCY THRESHOLD: Equity down {loss*100:.1f}%!")
            self._pause("Emergency equity threshold")
            return True
        return False

    # ── Aggregate check ─────────────────────────────────────────────────

    def run_all_checks(self, balance: float, equity: float) -> bool:
        """Run all safety checks. Returns True if trading should be paused."""
        self.check_emergency_equity(equity)
        self.check_drawdown(balance)

        if self.trading_paused and self.pause_reason:
            self.logger.info(f"Trading paused: {self.pause_reason}")

        return self.trading_paused

    # ── Weekend / Market gap ────────────────────────────────────────────

    @staticmethod
    def is_near_weekend_close(minutes_before: int = 30) -> tuple[bool, str | None]:
        """Check if approaching Friday 5pm EST market close."""
        try:
            est = pytz.timezone('US/Eastern')
            now_est = datetime.now(est)

            if now_est.weekday() == 4:  # Friday
                close_time = now_est.replace(hour=17, minute=0, second=0, microsecond=0)
                minutes_until = (close_time - now_est).total_seconds() / 60

                if 0 < minutes_until <= minutes_before:
                    return True, f"Weekend close in {minutes_until:.0f} minutes"
                if -60 < minutes_until <= 0:
                    return True, "Market closed for weekend"

            return False, None
        except Exception as e:
            logger.error(f"Error checking weekend close: {e}")
            return False, None

    @staticmethod
    def detect_market_gap(df, max_normal_gap_minutes: int = 15) -> tuple[bool, float, float]:
        """
        Detect market gaps from OHLCV data.

        Returns: (has_gap, gap_pct, time_gap_minutes)
        """
        if len(df) < 2:
            return False, 0.0, 0.0

        times = df['time'].values
        time_gap = (times[-1] - times[-2]) / np.timedelta64(1, 'm')

        if time_gap > max_normal_gap_minutes:
            closes = df['close'].values
            opens = df['open'].values
            gap_pct = abs(float(opens[-1]) - float(closes[-2])) / float(closes[-2]) * 100
            logger.warning(f"Market gap: {time_gap:.0f}min, {gap_pct:.2f}% price change")
            return True, gap_pct, time_gap

        return False, 0.0, time_gap
