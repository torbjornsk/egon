"""
Timezone utilities for Egon trading bots.

Provides consistent timezone handling across all components.
Automatically handles daylight savings transitions (EET/EEST ↔ CET/CEST).

KEY FACTS ABOUT MT5 TIMESTAMPS:
- Despite the docs saying "UTC", MT5 timestamps are actually in BROKER SERVER
  TIME (EET/EEST for most forex brokers). This is a well-known MT5 quirk.
  See: https://www.mql5.com/en/forum/369602
- position.time, deal.time, bar timestamps  --  all broker server time, NOT UTC.
- When calling MT5 API functions that take datetime params (history_deals_get,
  copy_rates_range, etc.), pass NAIVE datetimes in BROKER SERVER TIME.
  The API compares them directly against broker-time epochs without converting.
  Use get_mt5_now().replace(tzinfo=None) for "up to now" queries.
- Use mt5_to_local() to convert any MT5 timestamp to local display time.
- Use get_mt5_now() when building date ranges for MT5 API queries.

Usage:
    from src.core.timezone import mt5_to_local, get_local_now, get_mt5_now
"""

import pytz
from datetime import datetime, timezone

# MT5 broker server timezone  --  timestamps from MT5 are in this timezone
MT5_TZ = pytz.timezone('Europe/Athens')    # EET/EEST (GMT+2 winter, GMT+3 summer)
LOCAL_TZ = pytz.timezone('Europe/Berlin')  # CET/CEST (GMT+1 winter, GMT+2 summer)
UTC = pytz.UTC


def mt5_to_local(mt5_timestamp: float) -> datetime:
    """
    Convert MT5 timestamp to local timezone-aware datetime.

    MT5 timestamps look like Unix epochs but are actually in broker server
    time (EET/EEST), not UTC. We must NOT use fromtimestamp(ts, tz=...)
    because that interprets ts as a real UTC epoch and converts — which
    double-shifts the time. Instead we create a naive datetime from the
    raw seconds and localize it as broker server time.
    """
    # utcfromtimestamp gives us the raw numbers without any UTC->local shift
    naive = datetime.utcfromtimestamp(mt5_timestamp)
    mt5_time = MT5_TZ.localize(naive)
    return mt5_time.astimezone(LOCAL_TZ)


def get_local_now() -> datetime:
    """Get current time as timezone-aware datetime in local timezone."""
    return datetime.now(LOCAL_TZ)


def get_mt5_now() -> datetime:
    """
    Get current time in MT5 broker server timezone.

    Use this for MT5 API date range queries (history_deals_get, etc.)
    since MT5 expects broker server time, not UTC.
    """
    return datetime.now(MT5_TZ)


def calculate_hold_time(position_open_time: datetime) -> tuple[float, float]:
    """
    Calculate how long a position has been held.

    Returns:
        (total_seconds, minutes) as floats
    """
    delta = get_local_now() - position_open_time
    seconds = delta.total_seconds()
    return seconds, seconds / 60


def ensure_timezone_aware(dt: datetime, assume_local: bool = True) -> datetime:
    """Ensure datetime is timezone-aware, localizing naive datetimes."""
    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
        return dt
    tz = LOCAL_TZ if assume_local else MT5_TZ
    return tz.localize(dt)


def mt5_series_to_local(s):
    """
    Convert a pandas Series of MT5 Unix timestamps (broker server time)
    to timezone-aware local datetimes.

    Usage: df['time'] = mt5_series_to_local(df['time'])
    """
    import pandas as pd
    # Interpret as broker server time, then convert to local
    return (
        pd.to_datetime(s, unit='s')
        .dt.tz_localize(str(MT5_TZ))
        .dt.tz_convert(str(LOCAL_TZ))
    )
