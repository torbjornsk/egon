"""
Timezone Utilities for MT5 Trading Bots

Provides consistent timezone handling across all bots and analysis scripts.
Automatically handles daylight savings transitions.

Usage:
    from src.timezone_utils import MT5_TZ, LOCAL_TZ, mt5_to_local, get_local_now
    
    # Convert MT5 timestamp to local time
    local_time = mt5_to_local(position.time)
    
    # Get current time in local timezone
    now = get_local_now()
    
    # Calculate hold time
    time_held = now - local_time
"""

import pytz
from datetime import datetime

# Timezone Configuration
# MT5 uses Eastern European Time (aligns with NY market open)
MT5_TZ = pytz.timezone('Europe/Athens')  # EET/EEST (GMT+2 winter, GMT+3 summer)

# Local timezone (adjust if needed for your location)
LOCAL_TZ = pytz.timezone('Europe/Berlin')  # CET/CEST (GMT+1 winter, GMT+2 summer)

def mt5_to_local(mt5_timestamp):
    """
    Convert MT5 Unix timestamp to local timezone-aware datetime
    
    Args:
        mt5_timestamp (float): Unix timestamp from MT5 (in EET/EEST)
        
    Returns:
        datetime: Timezone-aware datetime in local timezone
        
    Example:
        >>> position_time = mt5_to_local(position.time)
        >>> print(position_time)
        2026-03-02 13:42:35.140447+01:00
    """
    mt5_time = datetime.fromtimestamp(mt5_timestamp, tz=MT5_TZ)
    return mt5_time.astimezone(LOCAL_TZ)

def get_local_now():
    """
    Get current time as timezone-aware datetime in local timezone
    
    Returns:
        datetime: Current time in local timezone
        
    Example:
        >>> now = get_local_now()
        >>> print(now)
        2026-03-02 13:42:35.140447+01:00
    """
    return datetime.now(LOCAL_TZ)

def get_mt5_now():
    """
    Get current time as timezone-aware datetime in MT5 timezone
    
    Returns:
        datetime: Current time in MT5 timezone
        
    Example:
        >>> mt5_now = get_mt5_now()
        >>> print(mt5_now)
        2026-03-02 14:42:35.140447+02:00
    """
    return datetime.now(MT5_TZ)

def calculate_hold_time(position_open_time):
    """
    Calculate how long a position has been held
    
    Args:
        position_open_time (datetime): Timezone-aware datetime when position opened
        
    Returns:
        tuple: (timedelta, float) - time held as timedelta and minutes as float
        
    Example:
        >>> open_time = mt5_to_local(position.time)
        >>> time_held, minutes = calculate_hold_time(open_time)
        >>> print(f"Held for {minutes:.1f} minutes")
        Held for 120.5 minutes
    """
    now = get_local_now()
    time_held = now - position_open_time
    minutes = time_held.total_seconds() / 60
    return time_held, minutes

def format_time_local(dt):
    """
    Format datetime for display in local timezone
    
    Args:
        dt (datetime): Timezone-aware datetime
        
    Returns:
        str: Formatted time string
        
    Example:
        >>> time_str = format_time_local(position_time)
        >>> print(time_str)
        2026-03-02 13:42:35 CET
    """
    if dt.tzinfo is None:
        # Naive datetime - assume local timezone
        dt = LOCAL_TZ.localize(dt)
    else:
        # Convert to local timezone
        dt = dt.astimezone(LOCAL_TZ)
    
    return dt.strftime('%Y-%m-%d %H:%M:%S %Z')

def is_timezone_aware(dt):
    """
    Check if datetime is timezone-aware
    
    Args:
        dt (datetime): Datetime to check
        
    Returns:
        bool: True if timezone-aware, False if naive
    """
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None

# Backward compatibility helper
def ensure_timezone_aware(dt, assume_local=True):
    """
    Ensure datetime is timezone-aware, converting if necessary
    
    Args:
        dt (datetime): Datetime to check/convert
        assume_local (bool): If naive, assume local timezone (default: True)
        
    Returns:
        datetime: Timezone-aware datetime
        
    Example:
        >>> naive_dt = datetime.now()
        >>> aware_dt = ensure_timezone_aware(naive_dt)
        >>> print(aware_dt.tzinfo)
        Europe/Berlin
    """
    if is_timezone_aware(dt):
        return dt
    
    # Naive datetime - localize it
    tz = LOCAL_TZ if assume_local else MT5_TZ
    return tz.localize(dt)

# DST transition information
def get_dst_info(year=None):
    """
    Get DST transition dates for a given year
    
    Args:
        year (int, optional): Year to check. Defaults to current year.
        
    Returns:
        dict: DST transition information
        
    Example:
        >>> info = get_dst_info(2026)
        >>> print(info['spring_forward'])
        2026-03-29
    """
    if year is None:
        year = datetime.now().year
    
    # Find DST transitions by checking each day
    spring_forward = None
    fall_back = None
    
    for month in [3, 10]:  # March and October
        for day in range(1, 32):
            try:
                dt = datetime(year, month, day, 12, 0, 0)
                dt_local = LOCAL_TZ.localize(dt)
                dt_prev = LOCAL_TZ.localize(datetime(year, month, day-1, 12, 0, 0)) if day > 1 else None
                
                if dt_prev and dt_local.dst() != dt_prev.dst():
                    if month == 3:
                        spring_forward = dt.date()
                    else:
                        fall_back = dt.date()
            except ValueError:
                continue
    
    return {
        'year': year,
        'spring_forward': spring_forward,
        'fall_back': fall_back,
        'local_tz': str(LOCAL_TZ),
        'mt5_tz': str(MT5_TZ)
    }

if __name__ == "__main__":
    # Self-test
    print("="*80)
    print("TIMEZONE UTILITIES - SELF TEST")
    print("="*80)
    print()
    
    print(f"MT5 Timezone: {MT5_TZ}")
    print(f"Local Timezone: {LOCAL_TZ}")
    print()
    
    # Test current time
    local_now = get_local_now()
    mt5_now = get_mt5_now()
    print(f"Current time (Local): {format_time_local(local_now)}")
    print(f"Current time (MT5): {mt5_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()
    
    # Test timestamp conversion
    import time
    ts = time.time() - 7200  # 2 hours ago
    converted = mt5_to_local(ts)
    time_held, minutes = calculate_hold_time(converted)
    print(f"Test position opened 2 hours ago:")
    print(f"  Open time: {format_time_local(converted)}")
    print(f"  Hold time: {minutes:.1f} minutes")
    print()
    
    # Test DST info
    dst_info = get_dst_info()
    print(f"DST Transitions for {dst_info['year']}:")
    print(f"  Spring forward: {dst_info['spring_forward']}")
    print(f"  Fall back: {dst_info['fall_back']}")
    print()
    
    print("✅ All tests passed")
