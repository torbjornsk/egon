"""
Risk management  --  Dead Man's Switch.

All safety checks: drawdown, daily loss, rapid loss, consecutive losses,
emergency equity threshold, weekend close, market gap detection.
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pytz

from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)


class RiskManager:
    """Centralized safety checks for trading bots."""

    def __init__(
        self,
        max_drawdown_limit: float = 0.35,
        daily_loss_limit_pct: float = 0.15,
        rapid_loss_threshold_pct: float = 0.10,
        rapid_loss_window_minutes: int = 60,
        max_consecutive_losses: int = 12,
        emergency_equity_threshold_pct: float = 0.50,
        bot_label: str = "",
    ):
        self.max_drawdown_limit = max_drawdown_limit
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.rapid_loss_threshold_pct = rapid_loss_threshold_pct
        self.rapid_loss_window_minutes = rapid_loss_window_minutes
        self.max_consecutive_losses = max_consecutive_losses
        self.emergency_equity_threshold_pct = emergency_equity_threshold_pct
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger

        # State
        self.starting_balance: float | None = None
        self.peak_balance: float | None = None
        self.daily_start_balance: float | None = None
        self.session_start: datetime = get_local_now()
        self.balance_history: list[dict] = []
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

    def check_daily_loss(self, current_balance: float) -> bool:
        now = get_local_now()
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance
            return False

        # Reset at midnight
        if now.date() > self.session_start.date():
            self.daily_start_balance = current_balance
            self.session_start = now
            return False

        daily_loss = (self.daily_start_balance - current_balance) / self.daily_start_balance
        if daily_loss >= self.daily_loss_limit_pct:
            self._pause(f"Daily loss limit ({daily_loss*100:.1f}%)")
            return True
        return False

    def check_rapid_loss(self, current_balance: float) -> bool:
        now = get_local_now()
        self.balance_history.append({'time': now, 'balance': current_balance})

        cutoff = now - timedelta(minutes=self.rapid_loss_window_minutes)
        self.balance_history = [h for h in self.balance_history if h['time'] > cutoff]

        if len(self.balance_history) < 2:
            return False

        start_balance = self.balance_history[0]['balance']
        rapid_loss = (start_balance - current_balance) / start_balance
        if rapid_loss >= self.rapid_loss_threshold_pct:
            self._pause(f"Rapid loss ({rapid_loss*100:.1f}% in {self.rapid_loss_window_minutes}min)")
            return True
        return False

    def check_consecutive_losses(self) -> bool:
        if self.consecutive_losses >= self.max_consecutive_losses:
            self._pause(f"Consecutive losses ({self.consecutive_losses})")
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
        self.check_daily_loss(balance)
        self.check_rapid_loss(balance)
        self.check_consecutive_losses()

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
