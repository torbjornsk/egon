"""Quick check: current lot size and SL dollar risk."""
import sys
sys.path.append('.')

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

mt5.initialize()
info = mt5.account_info()
balance = info.balance
tick = mt5.symbol_info_tick('XAUUSD.p')
price = tick.bid

# Replicate calculate_lot_size
pct = 0.10
leverage = 30
volume = balance * pct * leverage / (price * 100)
volume = round(volume / 0.01) * 0.01

print(f"Balance: ${balance:.2f}")
print(f"Price: ${price:.2f}")
print(f"Volume: {volume} lots")
print(f"$1 move = ${volume * 100:.2f}")
print()

# M5 ATR
rates = mt5.copy_rates_from_pos('XAUUSD.p', mt5.TIMEFRAME_M5, 0, 20)
df = pd.DataFrame(rates)
tr = []
for i in range(1, len(df)):
    tr.append(max(
        df['high'].iloc[i] - df['low'].iloc[i],
        abs(df['high'].iloc[i] - df['close'].iloc[i-1]),
        abs(df['low'].iloc[i] - df['close'].iloc[i-1]),
    ))
m5_atr = np.mean(tr[-14:])

print(f"M5 ATR: ${m5_atr:.2f}")
print()
print("SL SCENARIOS:")
for mult in [2, 3, 4, 6]:
    dist = m5_atr * mult
    loss = dist * volume * 100
    print(f"  {mult}x ATR = ${dist:.2f} distance = ${loss:.2f} loss")

print()
print("TICK ATR trail scenarios:")
# Simulate tick ATR (~$0.20-0.40 typically)
for tick_atr in [0.15, 0.25, 0.40]:
    trail = tick_atr * 2.5
    loss = trail * volume * 100
    print(f"  tick_atr=${tick_atr:.2f}, trail={trail:.2f} = ${loss:.2f} loss if hit at entry")

mt5.shutdown()
