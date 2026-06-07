"""
Scheduler -- time-based trading schedule for bots.

Uses flat config fields:
  schedule_enabled: bool
  schedule_mon..schedule_sun: "HH:MM-HH:MM" or "" (closed)
  schedule_closed: list of "YYYY-MM-DD HH:MM-HH:MM" (news event windows)

When outside schedule or during a closed window: bot stays connected,
existing positions are still managed, but no new entries are placed.
"""

import logging
from datetime import datetime, date, time, timedelta

from src.core.timezone import get_local_now

logger = logging.getLogger(__name__)

DAY_FIELDS = ['schedule_mon', 'schedule_tue', 'schedule_wed', 'schedule_thu',
              'schedule_fri', 'schedule_sat', 'schedule_sun']
DAY_NAMES = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


def _parse_time_range(s: str) -> tuple[time, time] | None:
    """Parse 'HH:MM-HH:MM' into (start_time, end_time). Returns None if empty/invalid."""
    s = s.strip()
    if not s:
        return None
    try:
        parts = s.split('-')
        if len(parts) != 2:
            return None
        start = parts[0].strip().split(':')
        end = parts[1].strip().split(':')
        return (time(int(start[0]), int(start[1])),
                time(int(end[0]), int(end[1])))
    except (ValueError, IndexError):
        return None


def _parse_closed_window(s: str) -> tuple[datetime, datetime] | None:
    """Parse 'YYYY-MM-DD HH:MM-HH:MM' into (start_dt, end_dt). Returns None if invalid."""
    s = s.strip()
    if not s:
        return None
    try:
        # Split on space: "2026-06-10 14:30-15:00"
        date_part, time_part = s.rsplit(' ', 1)
        d = date.fromisoformat(date_part)
        times = time_part.split('-')
        if len(times) != 2:
            return None
        start_parts = times[0].strip().split(':')
        end_parts = times[1].strip().split(':')
        start_dt = datetime(d.year, d.month, d.day,
                            int(start_parts[0]), int(start_parts[1]))
        end_dt = datetime(d.year, d.month, d.day,
                          int(end_parts[0]), int(end_parts[1]))
        return (start_dt, end_dt)
    except (ValueError, IndexError):
        return None


class Scheduler:
    """
    Evaluates whether trading is allowed based on per-day hours
    and closed windows (news events).
    """

    def __init__(self, config, bot_label: str = ""):
        self.logger = logging.getLogger(f"src.bot.{bot_label}") if bot_label else logger
        self._enabled = getattr(config, 'schedule_enabled', False)
        self._paused = False
        self._pause_reason = ""

        # Parse per-day schedules
        self._day_hours: dict[int, tuple[time, time] | None] = {}
        for i, field_name in enumerate(DAY_FIELDS):
            raw = getattr(config, field_name, "")
            self._day_hours[i] = _parse_time_range(raw)

        # Parse closed windows
        self._closed_windows: list[tuple[datetime, datetime]] = []
        closed_list = getattr(config, 'schedule_closed', [])
        if isinstance(closed_list, list):
            for entry in closed_list:
                parsed = _parse_closed_window(str(entry))
                if parsed:
                    self._closed_windows.append(parsed)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def pause_reason(self) -> str:
        return self._pause_reason

    def check(self) -> bool:
        """
        Check if trading is currently allowed.
        Returns True if entries are allowed, False if paused.
        """
        if not self._enabled:
            return True

        now = get_local_now()
        current_time = now.time()
        current_weekday = now.weekday()  # 0=Monday
        now_naive = now.replace(tzinfo=None)

        # Check closed windows first (news events override everything)
        for start_dt, end_dt in self._closed_windows:
            if start_dt <= now_naive <= end_dt:
                self._set_paused(True,
                    f"Closed window: {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}")
                return False

        # Check per-day schedule
        day_range = self._day_hours.get(current_weekday)
        if day_range is None:
            # No schedule for this day = closed
            self._set_paused(True, f"Closed: {DAY_NAMES[current_weekday]}")
            return False

        start_time, end_time = day_range
        if start_time <= end_time:
            in_window = start_time <= current_time <= end_time
        else:
            # Overnight range
            in_window = current_time >= start_time or current_time <= end_time

        if not in_window:
            self._set_paused(True,
                f"Outside hours ({start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')})")
            return False

        self._set_paused(False, "")
        return True

    def get_next_resume(self) -> str:
        """Human-readable string of when trading will resume."""
        if not self._paused:
            return "Active now"

        now = get_local_now()
        now_naive = now.replace(tzinfo=None)

        # If in a closed window, show when it ends
        for start_dt, end_dt in self._closed_windows:
            if start_dt <= now_naive <= end_dt:
                return f"After {end_dt.strftime('%H:%M')}"

        # Find next open day/time
        for offset in range(0, 8):
            check_day = (now.weekday() + offset) % 7
            day_range = self._day_hours.get(check_day)
            if day_range is None:
                continue
            start_time, _ = day_range
            if offset == 0 and now.time() < start_time:
                return f"Today at {start_time.strftime('%H:%M')}"
            elif offset > 0:
                return f"{DAY_NAMES[check_day].capitalize()} {start_time.strftime('%H:%M')}"

        return "No active schedule"

    def _set_paused(self, paused: bool, reason: str):
        if paused != self._paused:
            if paused:
                self.logger.info(f"[SCHEDULE] Paused: {reason}")
            else:
                self.logger.info("[SCHEDULE] Resumed")
        self._paused = paused
        self._pause_reason = reason
