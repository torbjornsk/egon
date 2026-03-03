"""
TEMPLATE: Analysis Script with Proper Timezone Handling

This template shows the correct way to handle MT5 timestamps in analysis scripts.
Copy this template when creating new analysis scripts.

Key Points:
1. Always import timezone utilities
2. Use mt5_to_local() for MT5 timestamps
3. Use get_local_now() for current time
4. Never use hardcoded time offsets
"""

import sys
sys.path.append('.')

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# REQUIRED: Import timezone utilities
from src.timezone_utils import (
    MT5_TZ, LOCAL_TZ,           # Timezone objects
    mt5_to_local,                # Convert MT5 timestamp to local time
    get_local_now,               # Get current time in local timezone
    calculate_hold_time,         # Calculate position hold time
    format_time_local            # Format datetime for display
)

def analyze_positions():
    """Example: Analyze open positions with proper timezone handling"""
    
    # Get positions from MT5
    positions = mt5.positions_get(symbol='XAUUSD')
    
    if not positions:
        print("No open positions")
        return
    
    print("="*80)
    print("OPEN POSITIONS ANALYSIS")
    print("="*80)
    print()
    
    for pos in positions:
        # CORRECT: Convert MT5 timestamp to local timezone
        open_time = mt5_to_local(pos.time)
        
        # CORRECT: Calculate hold time using timezone-aware datetimes
        time_held, minutes_held = calculate_hold_time(open_time)
        
        # Display information
        pos_type = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
        print(f"Position {pos.ticket} [{pos_type}]:")
        print(f"  Opened: {format_time_local(open_time)}")
        print(f"  Held: {minutes_held:.1f} minutes ({minutes_held/60:.2f} hours)")
        print(f"  Entry: ${pos.price_open:.2f}")
        print(f"  Current: ${pos.price_current:.2f}")
        print(f"  P/L: ${pos.profit:.2f}")
        print()

def analyze_historical_deals():
    """Example: Analyze historical deals with proper timezone handling"""
    
    # Get deals from last 24 hours
    from_date = datetime.now() - timedelta(hours=24)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if not deals:
        print("No deals found")
        return
    
    print("="*80)
    print("HISTORICAL DEALS ANALYSIS")
    print("="*80)
    print()
    
    for deal in deals:
        # CORRECT: Convert MT5 timestamp to local timezone
        deal_time = mt5_to_local(deal.time)
        
        print(f"Deal {deal.ticket}:")
        print(f"  Time: {format_time_local(deal_time)}")
        print(f"  Type: {deal.type}")
        print(f"  Price: ${deal.price:.2f}")
        print(f"  Profit: ${deal.profit:.2f}")
        print()

def analyze_trade_duration():
    """Example: Calculate trade durations with proper timezone handling"""
    
    # Get deals from last 24 hours
    from_date = datetime.now() - timedelta(hours=24)
    deals = mt5.history_deals_get(from_date, datetime.now())
    
    if not deals:
        print("No deals found")
        return
    
    # Group deals by position
    positions = {}
    for deal in deals:
        pos_id = deal.position_id
        if pos_id not in positions:
            positions[pos_id] = []
        positions[pos_id].append(deal)
    
    print("="*80)
    print("TRADE DURATION ANALYSIS")
    print("="*80)
    print()
    
    for pos_id, deals_list in positions.items():
        if len(deals_list) < 2:
            continue
        
        # Sort by time
        deals_list.sort(key=lambda x: x.time)
        
        entry_deal = deals_list[0]
        exit_deal = deals_list[-1]
        
        # CORRECT: Convert both timestamps to local timezone
        entry_time = mt5_to_local(entry_deal.time)
        exit_time = mt5_to_local(exit_deal.time)
        
        # CORRECT: Calculate duration using timezone-aware datetimes
        duration = exit_time - entry_time
        duration_minutes = duration.total_seconds() / 60
        
        print(f"Position {pos_id}:")
        print(f"  Entry: {format_time_local(entry_time)}")
        print(f"  Exit: {format_time_local(exit_time)}")
        print(f"  Duration: {duration_minutes:.1f} minutes ({duration_minutes/60:.2f} hours)")
        print(f"  Profit: ${exit_deal.profit:.2f}")
        print()

def main():
    """Main analysis function"""
    
    # Connect to MT5
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
    
    try:
        # Run your analysis functions
        analyze_positions()
        analyze_historical_deals()
        analyze_trade_duration()
        
    finally:
        # Always disconnect
        mt5.shutdown()

if __name__ == "__main__":
    main()


# ============================================================================
# COMMON MISTAKES TO AVOID
# ============================================================================

# ❌ WRONG: Hardcoded offset (breaks during DST)
# time_open = datetime.fromtimestamp(pos.time - 7200)
# time_held = datetime.now() - time_open

# ✅ CORRECT: Use timezone utilities
# time_open = mt5_to_local(pos.time)
# time_held, minutes = calculate_hold_time(time_open)

# ❌ WRONG: Naive datetime comparison
# now = datetime.now()
# time_held = now - position_open_time  # May give wrong result if timezones differ

# ✅ CORRECT: Timezone-aware datetime comparison
# now = get_local_now()
# time_held = now - position_open_time  # Always correct

# ❌ WRONG: Mixing naive and aware datetimes
# mt5_time = datetime.fromtimestamp(pos.time)  # Naive
# local_time = datetime.now()  # Naive
# # This works but is fragile and breaks if system timezone changes

# ✅ CORRECT: Always use timezone-aware datetimes
# mt5_time = mt5_to_local(pos.time)  # Aware
# local_time = get_local_now()  # Aware
# # This always works correctly regardless of system settings
