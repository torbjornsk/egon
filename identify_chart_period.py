"""
Identify the exact period from the user's chart
MT5 times are GMT+2, need to map user's local time to MT5 time
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def identify_period():
    """Help identify what period the user is looking at"""
    
    print("="*70)
    print("CHART PERIOD IDENTIFICATION")
    print("="*70)
    
    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed")
        return
    
    symbol = 'XAUUSD.p'
    
    # Get recent M1 data
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 500)
    
    if rates is None:
        print("Failed to get data")
        mt5.shutdown()
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Find gaps (weekend closures)
    print("\nRecent gaps found (likely weekend closures):")
    print("-" * 70)
    
    gaps = []
    for i in range(1, len(df)):
        time_diff = (df.iloc[i]['time'] - df.iloc[i-1]['time']).total_seconds() / 60
        if time_diff > 30:  # Gap > 30 minutes
            gap_info = {
                'index': i,
                'close_time': df.iloc[i-1]['time'],
                'close_price': df.iloc[i-1]['close'],
                'open_time': df.iloc[i]['time'],
                'open_price': df.iloc[i]['open'],
                'gap_minutes': time_diff,
                'price_gap': df.iloc[i]['open'] - df.iloc[i-1]['close']
            }
            gaps.append(gap_info)
    
    # Show last 3 gaps
    for idx, gap in enumerate(gaps[-3:], 1):
        print(f"\nGap {idx}:")
        print(f"  Closed: {gap['close_time'].strftime('%Y-%m-%d %H:%M')} MT5 (GMT+2) @ ${gap['close_price']:.2f}")
        print(f"  Opened: {gap['open_time'].strftime('%Y-%m-%d %H:%M')} MT5 (GMT+2) @ ${gap['open_price']:.2f}")
        print(f"  Gap duration: {gap['gap_minutes']:.0f} minutes ({gap['gap_minutes']/60:.1f} hours)")
        print(f"  Price gap: ${gap['price_gap']:+.2f} ({gap['price_gap']/gap['close_price']*100:+.2f}%)")
    
    if not gaps:
        print("No gaps found in recent data")
        mt5.shutdown()
        return
    
    # Focus on most recent gap
    latest_gap = gaps[-1]
    gap_index = latest_gap['index']
    
    print("\n" + "="*70)
    print("MOST RECENT GAP ANALYSIS")
    print("="*70)
    print(f"\nGap opened at: {latest_gap['open_time'].strftime('%Y-%m-%d %H:%M')} MT5 (GMT+2)")
    print(f"Opening price: ${latest_gap['open_price']:.2f}")
    print(f"Previous close: ${latest_gap['close_price']:.2f}")
    print(f"Gap size: ${latest_gap['price_gap']:+.2f} ({latest_gap['price_gap']/latest_gap['close_price']*100:+.2f}%)")
    
    # Show price action after gap
    print(f"\nPrice action after gap opening:")
    print("-" * 70)
    
    post_gap = df.iloc[gap_index:gap_index+100]
    
    print(f"\nFirst 30 minutes (30 candles) after gap:")
    for i, (idx, row) in enumerate(post_gap.head(30).iterrows()):
        mt5_time = row['time'].strftime('%H:%M')
        
        # Show what this would be in different timezones
        # GMT+2 (MT5) → subtract 2 hours for GMT
        # Common timezones: EST (GMT-5), PST (GMT-8), etc.
        
        print(f"  {i:2d}. MT5 {mt5_time} | ${row['close']:7.2f} | "
              f"H: ${row['high']:7.2f} | L: ${row['low']:7.2f}")
    
    # Price statistics
    high_30min = post_gap.head(30)['high'].max()
    low_30min = post_gap.head(30)['low'].min()
    close_30min = post_gap.iloc[29]['close']
    
    print(f"\n30-minute summary:")
    print(f"  Highest: ${high_30min:.2f} (+${high_30min - latest_gap['open_price']:.2f})")
    print(f"  Lowest:  ${low_30min:.2f} (${low_30min - latest_gap['open_price']:+.2f})")
    print(f"  Close:   ${close_30min:.2f} (${close_30min - latest_gap['open_price']:+.2f})")
    
    # Extended period
    high_100min = post_gap['high'].max()
    low_100min = post_gap['low'].min()
    close_100min = post_gap.iloc[-1]['close']
    
    print(f"\n100-minute summary:")
    print(f"  Highest: ${high_100min:.2f} (+${high_100min - latest_gap['open_price']:.2f})")
    print(f"  Lowest:  ${low_100min:.2f} (${low_100min - latest_gap['open_price']:+.2f})")
    print(f"  Close:   ${close_100min:.2f} (${close_100min - latest_gap['open_price']:+.2f})")
    
    print("\n" + "="*70)
    print("TIMEZONE REFERENCE")
    print("="*70)
    print(f"\nMT5 times shown above are in GMT+2")
    print(f"\nTo convert to your local time:")
    print(f"  - If you're in EST (GMT-5): MT5 time - 7 hours")
    print(f"  - If you're in PST (GMT-8): MT5 time - 10 hours")
    print(f"  - If you're in CET (GMT+1): MT5 time - 1 hour")
    print(f"  - If you're in GMT:         MT5 time - 2 hours")
    
    print(f"\nExample: Gap opened at {latest_gap['open_time'].strftime('%H:%M')} MT5")
    print(f"  → EST: {(latest_gap['open_time'] - timedelta(hours=7)).strftime('%H:%M')}")
    print(f"  → PST: {(latest_gap['open_time'] - timedelta(hours=10)).strftime('%H:%M')}")
    print(f"  → GMT: {(latest_gap['open_time'] - timedelta(hours=2)).strftime('%H:%M')}")
    
    print("\n" + "="*70)
    print("\nPlease tell me:")
    print("  1. What timezone is your chart in?")
    print("  2. What time range does your chart show? (e.g., '20:45 to 01:30')")
    print("\nThis will help me analyze the exact period you're interested in.")
    print("="*70)
    
    mt5.shutdown()

if __name__ == "__main__":
    identify_period()
