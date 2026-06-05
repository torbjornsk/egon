"""Quick test to see what MT5 data is available."""
import MetaTrader5 as mt5

mt5.initialize()

# Binary search for max bars
for tf_name, tf_const in [("M5", mt5.TIMEFRAME_M5), ("M1", mt5.TIMEFRAME_M1)]:
    lo, hi = 100, 100000
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        r = mt5.copy_rates_from_pos("XAUUSD.p", tf_const, 0, mid)
        if r is not None and len(r) > 0:
            best = len(r)
            lo = mid + 1
        else:
            hi = mid - 1
    print(f"{tf_name}: max fetchable = {best} bars")

    if best > 0:
        import pandas as pd
        r = mt5.copy_rates_from_pos("XAUUSD.p", tf_const, 0, best)
        df = pd.DataFrame(r)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        days = (df["time"].max() - df["time"].min()).days
        print(f"  Range: {df['time'].min()} to {df['time'].max()} ({days} days)")

mt5.shutdown()
