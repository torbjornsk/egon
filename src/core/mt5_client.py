"""
MT5 connection, data fetching, and order execution.

Thin wrapper around the MetaTrader5 library. All MT5 calls go through here
so the rest of the codebase never imports MetaTrader5 directly.
"""

import logging
import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from src.core.timezone import MT5_TZ, LOCAL_TZ, mt5_to_local

logger = logging.getLogger(__name__)

# Re-export constants so callers don't need to import mt5 directly
ORDER_TYPE_BUY = mt5.ORDER_TYPE_BUY
ORDER_TYPE_SELL = mt5.ORDER_TYPE_SELL
TIMEFRAME_M1 = mt5.TIMEFRAME_M1
TIMEFRAME_M5 = mt5.TIMEFRAME_M5
DEAL_ENTRY_OUT = mt5.DEAL_ENTRY_OUT
DEAL_REASON_SL = mt5.DEAL_REASON_SL
DEAL_REASON_TP = mt5.DEAL_REASON_TP


class MT5Client:
    """Manages MT5 connection, market data, and order execution."""

    def __init__(self, symbol: str = 'XAUUSD.p'):
        self.symbol = symbol
        self.mt5_timezone = MT5_TZ
        self.local_timezone = LOCAL_TZ

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not mt5.initialize():
            logger.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False

        info = mt5.account_info()
        if not info:
            logger.error("Not logged in to MT5")
            return False

        logger.info(f"Connected to MT5 -- Account: {info.login}, "
                     f"Server: {info.server}, Balance: ${info.balance:.2f}, "
                     f"Leverage: 1:{info.leverage}")
        return True

    def disconnect(self):
        mt5.shutdown()
        logger.info("Disconnected from MT5")

    # ── Account ─────────────────────────────────────────────────────────

    def get_account_info(self) -> dict | None:
        info = mt5.account_info()
        if not info:
            return None
        return {
            'balance': info.balance,
            'equity': info.equity,
            'margin': info.margin,
            'free_margin': info.margin_free,
            'profit': info.profit,
        }

    # ── Market Data ─────────────────────────────────────────────────────

    def get_historical_data(
        self, timeframe: int = mt5.TIMEFRAME_M5, bars: int = 500
    ) -> pd.DataFrame | None:
        """Fetch OHLCV bars. Returns DataFrame with 'time' as datetime."""
        sym_info = mt5.symbol_info(self.symbol)
        if sym_info is None:
            logger.error(f"Symbol {self.symbol} not found")
            return None
        if not sym_info.visible:
            if not mt5.symbol_select(self.symbol, True):
                logger.error(f"Failed to select {self.symbol}")
                return None

        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, bars)
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to get data: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def get_tick(self):
        """Get current bid/ask tick."""
        return mt5.symbol_info_tick(self.symbol)

    def get_symbol_info(self):
        return mt5.symbol_info(self.symbol)

    # ── Positions ───────────────────────────────────────────────────────

    def get_open_positions(self, magic_number: int) -> list:
        """Get open positions filtered by magic number."""
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return []
        return [p for p in positions if p.magic == magic_number]

    def get_deal_history(self, ticket: int):
        """Get deal history for a position ticket."""
        return mt5.history_deals_get(position=ticket)

    # ── Orders ──────────────────────────────────────────────────────────

    def place_order(
        self,
        order_type: int,
        volume: float,
        sl: float,
        tp: float,
        magic_number: int,
        comment: str = "egon",
    ) -> mt5.OrderSendResult | None:
        """Place a market order with retry logic for tick data."""
        sym_info = mt5.symbol_info(self.symbol)
        if sym_info is None:
            logger.error(f"Symbol {self.symbol} not found")
            return None

        # Get price with retries
        tick = None
        for attempt in range(3):
            tick = mt5.symbol_info_tick(self.symbol)
            if tick and tick.ask > 0 and tick.bid > 0:
                break
            if attempt < 2:
                logger.warning(f"No prices (attempt {attempt+1}/3), retrying...")
                time.sleep(2)

        if not tick or tick.ask <= 0 or tick.bid <= 0:
            logger.error("Failed to get valid tick data after retries")
            return None

        price = tick.ask if order_type == ORDER_TYPE_BUY else tick.bid
        if price <= 0:
            logger.error(f"Invalid price: {price}")
            return None

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "deviation": 20,
            "magic": magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Only include TP if it's a valid price (0 means no TP)
        if tp and tp > 0:
            request["tp"] = tp

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"order_send returned None: {mt5.last_error()}")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.retcode} - {result.comment}")
            return None

        return result

    def close_position(
        self,
        position,
        magic_number: int,
        comment: str = "egon_close",
    ) -> mt5.OrderSendResult | None:
        """Close an open position by sending an opposite market order."""
        close_type = ORDER_TYPE_SELL if position.type == ORDER_TYPE_BUY else ORDER_TYPE_BUY

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logger.error("Failed to get tick data for close")
            return None

        price = tick.bid if position.type == ORDER_TYPE_BUY else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": position.volume,
            "type": close_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"close_position order_send returned None: {mt5.last_error()}")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Failed to close position: {result.retcode} - {result.comment}")
            return None

        return result

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify the stop loss of an open position."""
        # Get the position to find its current TP
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logger.error(f"Position {ticket} not found for SL modification")
            return False

        pos = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": pos.tp,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"modify_sl order_send returned None: {mt5.last_error()}")
            return False
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            # 10025 = "No changes" — not a real error, just SL already at that level
            if result.retcode != 10025:
                logger.error(f"Failed to modify SL: {result.retcode} - {result.comment}")
            return False

        return True

    def partial_close(self, position, close_volume: float, magic_number: int,
                      comment: str = "partial_close") -> mt5.OrderSendResult | None:
        """Partially close a position by closing a portion of the volume."""
        close_type = ORDER_TYPE_SELL if position.type == ORDER_TYPE_BUY else ORDER_TYPE_BUY

        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logger.error("Failed to get tick data for partial close")
            return None

        price = tick.bid if position.type == ORDER_TYPE_BUY else tick.ask

        # Round volume to step
        sym_info = self.get_symbol_info()
        if sym_info:
            close_volume = round(close_volume / sym_info.volume_step) * sym_info.volume_step
            close_volume = max(sym_info.volume_min, close_volume)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": close_volume,
            "type": close_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error(f"partial_close order_send returned None: {mt5.last_error()}")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Failed to partial close: {result.retcode} - {result.comment}")
            return None

        logger.info(f"Partial close: {close_volume} lots of ticket {position.ticket}")
        return result

    def calculate_lot_size(
        self, balance: float, position_size_pct: float, leverage: int, current_price: float
    ) -> float | None:
        """Calculate lot size from balance, position %, leverage, and price (legacy mode)."""
        sym_info = self.get_symbol_info()
        if sym_info is None:
            return None

        base_value = balance * position_size_pct
        leveraged_value = base_value * leverage
        units = leveraged_value / current_price
        lots = units / sym_info.trade_contract_size

        # Round to volume step
        lots = round(lots / sym_info.volume_step) * sym_info.volume_step
        lots = max(sym_info.volume_min, min(lots, sym_info.volume_max))
        return lots

    def calculate_lot_size_from_risk(
        self, risk_amount: float, stop_distance: float
    ) -> float | None:
        """
        Calculate lot size from dollar risk and stop distance.

        Formula: lots = risk_amount / (stop_distance * contract_size)
        This gives the lot size where hitting the stop loss costs exactly risk_amount.
        """
        sym_info = self.get_symbol_info()
        if sym_info is None:
            return None

        if stop_distance <= 0:
            return None

        # $1 price move per lot = contract_size dollars P/L
        lots = risk_amount / (stop_distance * sym_info.trade_contract_size)

        # Round to volume step
        lots = round(lots / sym_info.volume_step) * sym_info.volume_step
        lots = max(sym_info.volume_min, min(lots, sym_info.volume_max))
        return lots

    def mt5_timestamp_to_local(self, mt5_timestamp) -> datetime:
        """Convert MT5 timestamp to local timezone-aware datetime."""
        return mt5_to_local(mt5_timestamp)
