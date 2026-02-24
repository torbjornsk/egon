import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta

mt5 = MT5Connector()
if not mt5.connect():
    print("Failed to connect")
    quit()

print("Testing different date ranges for XAUUSD M5 data...\n")

end_date = datetime.now()

# Test different ranges
for days in [30, 90, 180, 365, 730, 1095]:
    start_date = end_date - timedelta(days=days)
    data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)
    
    if data is not None and len(data) > 0:
        print(f"{days:4d} days: {len(data):6d} bars - Date range: {data['time'].min()} to {data['time'].max()}")
    else:
        print(f"{days:4d} days: FAILED")

mt5.disconnect()
