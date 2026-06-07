"""
SimBroker -- backtesting backend that replays historical data.

Implements the Broker protocol so BaseTradingBot can run unmodified
against cached candle data instead of live MT5.

Features:
- Spread modeling (configurable, default $0.40 for XAUUSD)
- Slippage modeling (random adverse fill, configurable)
- SL/TP execution against candle high/low
- Pre-computed indicators passed through without recomputation
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.core.broker import (
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    DEAL_ENTRY_OUT, DEAL_REASON_SL, DEAL_REASON_TP,
    Tick, OrderResult,
)

logger = logging.getLogger(__name__)


@dataclass
class SimPosition:
    """Mock MT5 position object with the same attributes the bot reads."""
    ticket: int
    type: int  # 0=BUY, 1=SELL
    price_open: float
    price_current: float
    sl: float
    tp: float
    volume: float
    profit: float
    time: int  # unix timestamp
    magic: int

    CONTRACT_SIZE: float = 100.0

    def update_price(self, bid: float, ask: float):
        """Recalculate profit from current prices."""
        if self.type == ORDER_TYPE_BUY:
            self.price_current = bid
            self.profit = (bid - self.price_open) * self.volume * self.CONTRACT_SIZE
        else:
            self.price_current = ask
            self.profit = (self.price_open - ask) * self.volume * self.CONTRACT_SIZE


@dataclass
class SimDeal:
    """Mock MT5 deal for SL/TP detection."""
    entry: int
    reason: int
    profit: float


class SimBroker:
    """
    Backtesting broker that replays candle data.

    The bot calls the same methods as live trading. SimBroker feeds
    candle data one bar at a time via advance(), and the bot's trading
    loop processes each bar identically to live.

    Spread/slippage modeling:
    - spread_points: half-spread applied to bid/ask (total spread = 2x this)
    - slippage_points: max random adverse slippage on entry/exit
    """

    CONTRACT_SIZE = 100.0

    def __init__(
        self,
        candle_df: pd.DataFrame,
        starting_balance: float = 10000.0,
        tick_df: pd.DataFrame | None = None,
        spread_points: float = 0.15,    # half-spread ($0.15 each side = $0.30 total)
        slippage_points: float = 0.05,  # max random slippage per fill
    ):
        self.candle_df = candle_df
        self.tick_df = tick_df
        self.balance = starting_balance
        self.equity = starting_balance
        self.spread = spread_points
        self.slippage = slippage_points

        # Pre-extract numpy arrays for fast candle access
        self._times = candle_df['time'].values
        self._opens = candle_df['open'].values.astype(np.float64)
        self._highs = candle_df['high'].values.astype(np.float64)
        self._lows = candle_df['low'].values.astype(np.float64)
        self._closes = candle_df['close'].values.astype(np.float64)

        # Current state
        self._current_bar_idx: int = -1
        self._sim_time: datetime = datetime.now()
        self._bid: float = 0.0
        self._ask: float = 0.0

        # Positions
        self._positions: list[SimPosition] = []
        self._next_ticket: int = 1000
        self._deal_history: dict[int, list[SimDeal]] = {}

        # Store position info for SL/TP closes (before removal)
        self._sl_tp_info: dict[int, dict] = {}

    def _get_slippage(self) -> float:
        """Random slippage between 0 and max."""
        if self.slippage <= 0:
            return 0.0
        return random.uniform(0, self.slippage)

    # ── Candle advancement ──────────────────────────────────────────

    def advance(self, bar_idx: int):
        """Advance to the next candle. Updates prices, checks SL/TP."""
        self._current_bar_idx = bar_idx
        mid = self._closes[bar_idx]
        self._bid = mid - self.spread
        self._ask = mid + self.spread

        candle_time = self._times[bar_idx]
        if isinstance(candle_time, np.datetime64):
            # Convert numpy datetime64 to Python datetime
            self._sim_time = pd.Timestamp(candle_time).to_pydatetime()
        elif isinstance(candle_time, pd.Timestamp):
            self._sim_time = candle_time.to_pydatetime()
        else:
            self._sim_time = candle_time

        # Check SL/TP against candle high/low (with spread)
        high = self._highs[bar_idx]
        low = self._lows[bar_idx]

        for pos in list(self._positions):
            hit, exit_price, reason_code = self._check_sl_tp(pos, high, low)
            if hit:
                self._execute_sl_tp(pos, exit_price, reason_code)
            else:
                pos.update_price(self._bid, self._ask)

        # Update equity
        unrealized = sum(p.profit for p in self._positions)
        self.equity = self.balance + unrealized

    def _check_sl_tp(self, pos: SimPosition, high: float, low: float) -> tuple[bool, float, int]:
        """Check if candle high/low hit SL or TP (accounting for spread)."""
        if pos.type == ORDER_TYPE_BUY:
            # Long exits at bid (mid - spread)
            effective_low = low - self.spread
            effective_high = high - self.spread
            if effective_low <= pos.sl:
                return True, pos.sl, DEAL_REASON_SL
            if effective_high >= pos.tp:
                return True, pos.tp, DEAL_REASON_TP
        else:
            # Short exits at ask (mid + spread)
            effective_low = low + self.spread
            effective_high = high + self.spread
            if effective_high >= pos.sl:
                return True, pos.sl, DEAL_REASON_SL
            if effective_low <= pos.tp:
                return True, pos.tp, DEAL_REASON_TP
        return False, 0.0, -1

    def _execute_sl_tp(self, pos: SimPosition, exit_price: float, reason_code: int):
        """Close a position via SL/TP."""
        if pos.type == ORDER_TYPE_BUY:
            profit = (exit_price - pos.price_open) * pos.volume * self.CONTRACT_SIZE
        else:
            profit = (pos.price_open - exit_price) * pos.volume * self.CONTRACT_SIZE

        self._sl_tp_info[pos.ticket] = {
            'type': pos.type,
            'price_open': pos.price_open,
            'exit_price': exit_price,
            'volume': pos.volume,
            'profit': profit,
        }

        self.balance += profit
        self._positions.remove(pos)
        self._deal_history[pos.ticket] = [
            SimDeal(entry=DEAL_ENTRY_OUT, reason=reason_code, profit=profit)
        ]

    @property
    def sim_time(self) -> datetime:
        return self._sim_time

    # ── Broker protocol implementation ──────────────────────────────

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def get_account_info(self) -> dict | None:
        return {
            'balance': self.balance,
            'equity': self.equity,
            'margin': 0,
            'free_margin': self.equity,
            'profit': self.equity - self.balance,
        }

    def get_historical_data(self, timeframe: int, bars: int) -> pd.DataFrame | None:
        """Return the last N bars up to current position (pre-computed indicators included)."""
        end = self._current_bar_idx + 1
        start = max(0, end - bars)
        if end <= 0:
            return None
        return self.candle_df.iloc[start:end]

    def get_tick(self) -> Tick | None:
        return Tick(bid=self._bid, ask=self._ask)

    def get_open_positions(self, magic_number: int) -> list:
        # In sim, all positions have the same magic number — skip filtering
        return self._positions

    def place_order(self, order_type: int, volume: float, sl: float, tp: float,
                    magic_number: int, comment: str) -> OrderResult | None:
        """Place order with spread and slippage applied."""
        slip = self._get_slippage()

        if order_type == ORDER_TYPE_BUY:
            # Buy at ask + slippage (adverse)
            price = self._ask + slip
        else:
            # Sell at bid - slippage (adverse)
            price = self._bid - slip

        if price <= 0:
            return None

        ticket = self._next_ticket
        self._next_ticket += 1

        pos = SimPosition(
            ticket=ticket,
            type=order_type,
            price_open=price,
            price_current=price,
            sl=sl,
            tp=tp,
            volume=volume,
            profit=0.0,
            time=int(self._sim_time.timestamp()),
            magic=magic_number,
        )
        self._positions.append(pos)
        return OrderResult(order=ticket)

    def place_limit_order(self, order_type: int, volume: float, entry_price: float,
                          sl: float, tp: float, magic_number: int, comment: str) -> OrderResult | None:
        """
        Place a limit order fill at a specific price (no spread/slippage on entry).

        Limit orders provide liquidity, so the fill happens at the limit price.
        This is the key advantage over market orders.
        """
        if entry_price <= 0:
            return None

        ticket = self._next_ticket
        self._next_ticket += 1

        pos = SimPosition(
            ticket=ticket,
            type=order_type,
            price_open=entry_price,
            price_current=entry_price,
            sl=sl,
            tp=tp,
            volume=volume,
            profit=0.0,
            time=int(self._sim_time.timestamp()),
            magic=magic_number,
        )
        self._positions.append(pos)
        return OrderResult(order=ticket)

    def close_position(self, position, magic_number: int, comment: str) -> OrderResult | None:
        """Close a position (bot-initiated) with spread and slippage."""
        pos = next((p for p in self._positions if p.ticket == position.ticket), None)
        if pos is None:
            return None

        slip = self._get_slippage()

        if pos.type == ORDER_TYPE_BUY:
            # Close long at bid - slippage (adverse)
            price = self._bid - slip
            profit = (price - pos.price_open) * pos.volume * self.CONTRACT_SIZE
        else:
            # Close short at ask + slippage (adverse)
            price = self._ask + slip
            profit = (pos.price_open - price) * pos.volume * self.CONTRACT_SIZE

        self.balance += profit
        self._positions.remove(pos)

        unrealized = sum(p.profit for p in self._positions)
        self.equity = self.balance + unrealized

        return OrderResult(order=pos.ticket)

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify the stop loss of an open position."""
        pos = next((p for p in self._positions if p.ticket == ticket), None)
        if pos is None:
            return False
        pos.sl = new_sl
        return True

    def partial_close(self, position, close_volume: float, magic_number: int, comment: str) -> OrderResult | None:
        """
        Partially close a position (reduce volume).

        Returns profit from the closed portion. The remaining position stays open
        with reduced volume.
        """
        pos = next((p for p in self._positions if p.ticket == position.ticket), None)
        if pos is None:
            return None

        # Can't close more than we have
        close_volume = min(close_volume, pos.volume)
        close_volume = round(close_volume / 0.01) * 0.01
        if close_volume < 0.01:
            return None

        slip = self._get_slippage()

        if pos.type == ORDER_TYPE_BUY:
            price = self._bid - slip
            profit = (price - pos.price_open) * close_volume * self.CONTRACT_SIZE
        else:
            price = self._ask + slip
            profit = (pos.price_open - price) * close_volume * self.CONTRACT_SIZE

        self.balance += profit

        # Reduce position volume
        remaining = round((pos.volume - close_volume) / 0.01) * 0.01
        if remaining < 0.01:
            # Fully closed
            self._positions.remove(pos)
        else:
            pos.volume = remaining
            # Recalculate profit for remaining volume
            pos.update_price(self._bid, self._ask)

        unrealized = sum(p.profit for p in self._positions)
        self.equity = self.balance + unrealized

        return OrderResult(order=pos.ticket)

    def calculate_lot_size(self, balance: float, position_size_pct: float,
                           leverage: int, current_price: float) -> float | None:
        base_value = balance * position_size_pct
        leveraged_value = base_value * leverage
        units = leveraged_value / current_price
        lots = units / self.CONTRACT_SIZE
        lots = round(lots / 0.01) * 0.01
        return max(0.01, lots)

    def calculate_lot_size_from_risk(self, risk_amount: float, stop_distance: float) -> float | None:
        """Calculate lot size from dollar risk and stop distance."""
        if stop_distance <= 0:
            return None
        lots = risk_amount / (stop_distance * self.CONTRACT_SIZE)
        lots = round(lots / 0.01) * 0.01
        return max(0.01, lots)

    def get_deal_history(self, ticket: int) -> list | None:
        return self._deal_history.get(ticket)

    def mt5_timestamp_to_local(self, mt5_timestamp: int) -> datetime:
        return self._sim_time

    # ── Legacy compatibility (used by old tick-based PP testing) ─────

    def update_position_prices(self, price: float):
        """Update all position prices."""
        bid = price - self.spread
        ask = price + self.spread
        for pos in self._positions:
            pos.update_price(bid, ask)
        unrealized = sum(p.profit for p in self._positions)
        self.equity = self.balance + unrealized
