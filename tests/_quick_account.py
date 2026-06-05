"""Quick account + 14-day P/L summary."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta

mt5.initialize()

from_date = datetime.now() - timedelta(hours=336)
deals = mt5.history_deals_get(from_date, datetime.now() + timedelta(hours=3))

m5_profit = sum(d.profit for d in deals if d.magic == 234000 and d.profit != 0)
m1_profit = sum(d.profit for d in deals if d.magic == 234001 and d.profit != 0)
m5_count = len([d for d in deals if d.magic == 234000 and d.entry == 1])
m1_count = len([d for d in deals if d.magic == 234001 and d.entry == 1])

info = mt5.account_info()
print(f"Current balance: ${info.balance:.2f}")
print(f"Current equity:  ${info.equity:.2f}")
print(f"M5 (14d): {m5_count} trades, P/L: ${m5_profit:.2f}")
print(f"M1 (14d): {m1_count} trades, P/L: ${m1_profit:.2f}")
print(f"Combined 14d P/L: ${m5_profit + m1_profit:.2f}")
print(f"Implied balance 14d ago: ${info.balance - m5_profit - m1_profit:.2f}")

mt5.shutdown()
