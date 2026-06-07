"""
Scheduler -- time-based trading schedule for bots.

Controls when a bot is allowed to enter new positions.
When outside schedule: bot stays connected, existing positions still managed
(exits fire, trailing works), but no new entries are placed.

Configuration via TradingConfig fields (from JSON):
  "schedule": {
    "active_hours": {"start": "08:00", "end": "22:00"},
    "active_days": ["mon", "tue", "wed", "thu", "fri"],
    "blackout_dates": ["2026-07-04", "2026-12-25"],
    "timezone": "Europe/Berlin"
  }
"""

import logging
from datetime import datetime, date, time

from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)

DAY_NAMES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


class Scheduler:
    """
    Evaluates whether trading is allowed based on time-of-day,
    day-of-week, and blackout dates.
    """

    def __init__(self, schedule_config: dict | None = None, bot_label: str = ""):
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger
        self._config = schedule_config or {}
        self._paused_by_schedule = False
        self._pause_reason = ""

        # Parse config
        hours = self._config.get('active_hours', {})
        self._start_time = self._parse_time(hours.get('start', '00:00'))
        self._end_time = self._parse_time(hours.get('end', '23:59'))

        days = self._config.get('active_days', DAY_NAMES[:5])  # Default: Mon-Fri
        self._active_days = set(d.lower()[:3] for d in days)

        blackouts = self._config.get('blackout_dates', [])
        self._blackout_dates = set()
        for d in blackouts:
            try:
                self._blackout_dates.add(date.fromisoformat(d))
            except (ValueError, TypeError):
                pass

    @staticmethod
    def _parse_time(t: str) -> time:
        """Parse HH:MM string to time object."""
        try:
            parts = t.split(':')
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return time(0, 0)

    @property
    def is_enabled(self) -> bool:
        """True if schedule config was provided (non-empty)."""
        return bool(self._config)

    @property
    def is_paused(self) -> bool:
        return self._paused_by_schedule

    @property
    def pause_reason(self) -> str:
        return self._pause_reason

    def check(self) -> bool:
        """
        Check if trading is currently allowed.

        Returns True if entries are allowed, False if paused by schedule.
        """
        if not self.is_enabled:
            return True

        now = get_local_now()
        current_time = now.time()
        current_day = DAY_NAMES[now.weekday()]
        current_date = now.date()

        # Blackout date check
        if current_date in self._blackout_dates:
            self._set_paused(True, f"Blackout date: {current_date.isoformat()}")
            return False

        # Day-of-week check
        if current_day not in self._active_days:
            self._set_paused(True, f"Inactive day: {current_day}")
            return False

        # Time-of-day check
        if self._start_time <= self._end_time:
            # Normal range (e.g., 08:00 - 22:00)
            in_window = self._start_time <= current_time <= self._end_time
        else:
            # Overnight range (e.g., 22:00 - 06:00)
            in_window = current_time >= self._start_time or current_time <= self._end_time

        if not in_window:
            start_str = self._start_time.strftime('%H:%M')
            end_str = self._end_time.strftime('%H:%M')
            self._set_paused(True, f"Outside hours ({start_str}-{end_str})")
            return False

        self._set_paused(False, "")
        return True

    def get_next_resume(self) -> str:
        """Get a human-readable string of when trading will resume."""
        if not self._paused_by_schedule:
            return "Active now"

        now = get_local_now()
        current_day = DAY_NAMES[now.weekday()]

        # If paused by blackout, next day
        if now.date() in self._blackout_dates:
            return f"After blackout ({now.date().isoformat()})"

        # If paused by day, find next active day
        if current_day not in self._active_days:
            for offset in range(1, 8):
                next_day_idx = (now.weekday() + offset) % 7
                if DAY_NAMES[next_day_idx] in self._active_days:
                    return f"Resumes {DAY_NAMES[next_day_idx].capitalize()} {self._start_time.strftime('%H:%M')}"
            return "No active days configured"

        # If paused by time, resume at start_time today or tomorrow
        if now.time() > self._end_time:
            # Past end time, resume next active day
            for offset in range(1, 8):
                next_day_idx = (now.weekday() + offset) % 7
                if DAY_NAMES[next_day_idx] in self._active_days:
                    return f"Resumes {DAY_NAMES[next_day_idx].capitalize()} {self._start_time.strftime('%H:%M')}"

        return f"Resumes at {self._start_time.strftime('%H:%M')}"

    def _set_paused(self, paused: bool, reason: str):
        """Set pause state, logging on transitions."""
        if paused != self._paused_by_schedule:
            if paused:
                self.logger.info(f"[SCHEDULE] Paused: {reason}")
            else:
                self.logger.info("[SCHEDULE] Resumed: trading window active")
        self._paused_by_schedule = paused
        self._pause_reason = reason
