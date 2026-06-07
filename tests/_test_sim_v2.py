"""Quick smoke test for SimulatorV2."""
import logging
from datetime import timedelta

from src.core.config import load_config
from src.strategy.m1_scalping import M1ScalpingStrategy
from tests.data_cache import fetch_and_cache, slice_window
from tests.simulator_v2 import SimulatorV2

logging.basicConfig(level=logging.WARNING)

config = load_config("config/m1_params.json")
data = fetch_and_cache(days=365)
candle_df = data["m1"]

# Last 48 hours
end = candle_df["time"].max()
start = end - timedelta(hours=48)
window = slice_window(candle_df, start.to_pydatetime(), end.to_pydatetime())

print(f"Window: {len(window)} bars")

strategy = M1ScalpingStrategy(config)
sim = SimulatorV2(strategy, config, window, None, 10000.0)
result = sim.run()

print(f"Trades: {len(result.trades)}")
print(f"Return: {result.total_return_pct:+.2f}%")
print(f"Win rate: {result.win_rate:.1f}%")
print(f"Max DD: {result.max_drawdown_pct:.2f}%")
print(f"Paused: {result.paused}")

# Exit breakdown
from collections import Counter
reasons = Counter()
for t in result.trades:
    if "profit protection" in t.exit_reason.lower():
        reasons["Profit protection"] += 1
    elif "rsi" in t.exit_reason.lower():
        reasons["RSI exit"] += 1
    elif "stop loss" in t.exit_reason.lower():
        reasons["Stop loss"] += 1
    elif "take profit" in t.exit_reason.lower():
        reasons["Take profit"] += 1
    else:
        reasons[t.exit_reason[:25]] += 1

print("\nExit breakdown:")
for reason, count in reasons.most_common():
    print(f"  {reason}: {count}")
