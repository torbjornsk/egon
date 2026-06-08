"""
MT5Broker -- live trading backend using MetaTrader5.

Wraps MT5Client to implement the Broker protocol.
"""

from datetime import datetime

import pandas as pd

from src.core.broker import Broker, Tick, OrderResult
from src.core.mt5_client import MT5Client


class MT5Broker:
    """Live broker backed by MetaTrader5."""

    def __init__(self, symbol: str = 'XAUUSD.p'):
        self._client = MT5Client(symbol)

    def connect(self) -> bool:
        return self._client.connect()

    def disconnect(self) -> None:
        self._client.disconnect()

    def get_account_info(self) -> dict | None:
        return self._client.get_account_info()

    def get_historical_data(self, timeframe: int, bars: int) -> pd.DataFrame | None:
        return self._client.get_historical_data(timeframe=timeframe, bars=bars)

    def get_tick(self) -> Tick | None:
        tick = self._client.get_tick()
        if tick is None or tick.ask <= 0 or tick.bid <= 0:
            return None
        return Tick(bid=tick.bid, ask=tick.ask)

    def get_open_positions(self, magic_number: int) -> list:
        return self._client.get_open_positions(magic_number)

    def place_order(self, order_type: int, volume: float, sl: float, tp: float,
                    magic_number: int, comment: str) -> OrderResult | None:
        result = self._client.place_order(order_type, volume, sl, tp, magic_number, comment)
        if result is None:
            return None
        return OrderResult(order=result.order)

    def close_position(self, position, magic_number: int, comment: str) -> OrderResult | None:
        result = self._client.close_position(position, magic_number, comment)
        if result is None:
            return None
        return OrderResult(order=0)

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify stop loss of an open position via MT5."""
        return self._client.modify_sl(ticket, new_sl)

    def place_stop_order(self, order_type: int, price: float, volume: float,
                         sl: float, tp: float, magic_number: int,
                         comment: str = "egon_stop"):
        """Place a pending BUY STOP or SELL STOP order."""
        return self._client.place_stop_order(order_type, price, volume, sl, tp, magic_number, comment)

    def cancel_order(self, order_ticket: int) -> bool:
        """Cancel a pending order by ticket."""
        return self._client.cancel_order(order_ticket)

    def get_pending_orders(self, magic_number: int) -> list:
        """Get all pending orders for a given magic number."""
        return self._client.get_pending_orders(magic_number)

    def partial_close(self, position, close_volume: float, magic_number: int, comment: str) -> OrderResult | None:
        """Partially close a position by closing a portion of the volume."""
        result = self._client.partial_close(position, close_volume, magic_number, comment)
        if result is None:
            return None
        return OrderResult(order=0)

    def calculate_lot_size(self, balance: float, position_size_pct: float,
                           leverage: int, current_price: float) -> float | None:
        return self._client.calculate_lot_size(balance, position_size_pct, leverage, current_price)

    def calculate_lot_size_from_risk(self, risk_amount: float, stop_distance: float) -> float | None:
        """Calculate lot size from dollar risk and stop distance in price units."""
        return self._client.calculate_lot_size_from_risk(risk_amount, stop_distance)

    def get_deal_history(self, ticket: int) -> list | None:
        return self._client.get_deal_history(ticket)

    def mt5_timestamp_to_local(self, mt5_timestamp: int) -> datetime:
        return self._client.mt5_timestamp_to_local(mt5_timestamp)
