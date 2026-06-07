"""
Broker abstraction -- interface between trading logic and execution backend.

Live trading uses MT5Broker (wraps MT5Client).
Backtesting uses SimBroker (replays historical data).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol, runtime_checkable, Any

import pandas as pd

logger = logging.getLogger(__name__)

# MT5 order type constants (shared across both backends)
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1

# Deal constants
DEAL_ENTRY_OUT = 1
DEAL_REASON_SL = 4
DEAL_REASON_TP = 5

# Timeframe constants (match MT5 values)
TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_M15 = 15
TIMEFRAME_H1 = 60
TIMEFRAME_H4 = 240

# Mapping from config string to MT5 constant
TIMEFRAME_MAP: dict[str, int] = {
    'M1': TIMEFRAME_M1,
    'M5': TIMEFRAME_M5,
    'M15': TIMEFRAME_M15,
    'H1': TIMEFRAME_H1,
    'H4': TIMEFRAME_H4,
}

TIMEFRAME_MINUTES: dict[str, int] = {
    'M1': 1,
    'M5': 5,
    'M15': 15,
    'H1': 60,
    'H4': 240,
}


class Tick:
    """Minimal tick data."""
    __slots__ = ('bid', 'ask')

    def __init__(self, bid: float, ask: float):
        self.bid = bid
        self.ask = ask


class OrderResult:
    """Minimal order result."""
    __slots__ = ('order',)

    def __init__(self, order: int):
        self.order = order


@runtime_checkable
class Broker(Protocol):
    """Interface for trade execution backends."""

    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def get_account_info(self) -> dict | None: ...
    def get_historical_data(self, timeframe: int, bars: int) -> pd.DataFrame | None: ...
    def get_tick(self) -> Tick | None: ...
    def get_open_positions(self, magic_number: int) -> list: ...
    def place_order(self, order_type: int, volume: float, sl: float, tp: float,
                    magic_number: int, comment: str) -> OrderResult | None: ...
    def close_position(self, position: Any, magic_number: int, comment: str) -> OrderResult | None: ...
    def calculate_lot_size(self, balance: float, position_size_pct: float,
                           leverage: int, current_price: float) -> float | None: ...
    def calculate_lot_size_from_risk(self, risk_amount: float,
                                     stop_distance: float) -> float | None: ...
    def get_deal_history(self, ticket: int) -> list | None: ...
    def mt5_timestamp_to_local(self, mt5_timestamp: int) -> datetime: ...
