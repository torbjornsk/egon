import sys
sys.path.append('src')

from mt5_connector import MT5Connector
from datetime import datetime, timedelta

mt5 = MT5Connector()
print("Connecting...")
if not mt5.connect():
    print("Failed to connect")
    quit()

print("Connected!")

end_date = datetime.now()
start_date = end_date - timedelta(days=7)

print(f"Fetching data from {start_date} to {end_date}")
data = mt5.get_historical_data('XAUUSD', 'M5', start_date, end_date)

if data is not None:
    print(f"Success! Got {len(data)} bars")
    print(data.head())
else:
    print("Failed to get data")

mt5.disconnect()
