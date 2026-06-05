"""
Simulator v2 -- runs the REAL BaseTradingBot against SimBroker.

No duplicated trading logic. The bot runs its actual trading_logic()
method, and SimBroker feeds it candle data instead of live MT5.

Performance optimizations:
- Pre-computed indicators (no recomputation per candle)
- Numpy arrays for candle data access in SimBroker
- Minimal equity tracking (every N candles, not every candle)
- Spread and slippage modeling for realistic results
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.bot.base import BaseTradingBot
from src.core.config import TradingConfig
from src.core.indicators import compute_indicators
from src.core.broker import (
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    DEAL_ENTRY_OUT, DEAL_REASON_SL, DEAL_REASON_TP,
)
from src.strategy.base import TradingStrategy

from tests.sim_broker import SimBroker

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Completed trade for analysis."""
    ticket: int
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    profit: float
    exit_reason: str
    duration_minutes: float
    peak_profit: float


@dataclass
class BacktestResult:
    """Full backtest output."""
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    starting_balance: float = 10000.0
    final_balance: float = 10000.0
    peak_balance: float = 10000.0
    max_drawdown_pct: float = 0.0
    paused: bool = False
    pause_reason: str = ""
    config: TradingConfig | None = None
    strategy_label: str = ""
    period_days: int = 0

    @property
    def total_return_pct(self) -> float:
        return (self.final_balance / self.starting_balance - 1) * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.profit > 0)
        return wins / len(self.trades) * 100

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.profit for t in self.trades if t.profit > 0)
        gross_loss = abs(sum(t.profit for t in self.trades if t.profit < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def sharpe_ratio(self) -> float:
        if len(self.trades) < 2:
            return 0.0
        returns = [t.profit for t in self.trades]
        mean_r = np.mean(returns)
        std_r = np.std(returns)
        return mean_r / std_r if std_r > 0 else 0.0

    @property
    def avg_trade_duration_min(self) -> float:
        if not self.trades:
            return 0.0
        return np.mean([t.duration_minutes for t in self.trades])

    def summary(self) -> dict:
        wins = [t for t in self.trades if t.profit > 0]
        losses = [t for t in self.trades if t.profit < 0]
        return {
            "strategy": self.strategy_label,
            "period_days": self.period_days,
            "starting_balance": self.starting_balance,
            "final_balance": round(self.final_balance, 2),
            "return_pct": round(self.total_return_pct, 2),
            "trades": len(self.trades),
            "win_rate": round(self.win_rate, 1),
            "avg_win": round(np.mean([t.profit for t in wins]), 2) if wins else 0,
            "avg_loss": round(np.mean([t.profit for t in losses]), 2) if losses else 0,
            "profit_factor": round(self.profit_factor, 2),
            "sharpe": round(self.sharpe_ratio, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "avg_duration_min": round(self.avg_trade_duration_min, 1),
            "paused": self.paused,
        }


class SimulatorV2:
    """
    Runs BaseTradingBot against SimBroker.

    Feeds candles one at a time. The bot's trading_logic() runs
    identically to live -- no duplicated logic.

    Args:
        strategy: Trading strategy instance
        config: Trading configuration
        candle_df: OHLCV DataFrame (indicators will be pre-computed)
        tick_df: Optional tick data for intra-candle PP testing
        starting_balance: Initial account balance
        spread: Half-spread in price points (total spread = 2x this)
        slippage: Max random adverse slippage per fill
    """

    def __init__(
        self,
        strategy: TradingStrategy,
        config: TradingConfig,
        candle_df: pd.DataFrame,
        tick_df: pd.DataFrame | None = None,
        starting_balance: float = 10000.0,
        spread: float = 0.15,
        slippage: float = 0.05,
    ):
        self.config = config
        self.starting_balance = starting_balance

        # Pre-compute indicators once
        candle_df = compute_indicators(candle_df, config)

        # Create broker with spread/slippage
        self.broker = SimBroker(
            candle_df, starting_balance, tick_df,
            spread_points=spread,
            slippage_points=slippage,
        )
        self.bot = BaseTradingBot(strategy, config, broker=self.broker)

        # Disable exit reason file I/O during backtest
        self.bot.positions.exit_reasons_file = ""

        # Suppress bot logging during backtest
        self.bot.logger.setLevel(logging.WARNING)

        # Override get_local_now to use sim time.
        # Must patch every module that imported the function (they hold local refs).
        import src.core.timezone as tz_mod
        import src.core.position as pos_mod
        import src.bot.base as bot_mod
        import src.core.risk as risk_mod

        self._original_get_local_now = tz_mod.get_local_now
        self._tz_mod = tz_mod
        self._pos_mod = pos_mod
        self._bot_mod = bot_mod
        self._risk_mod = risk_mod

        # Override position manager's get_minutes_held
        def _sim_get_minutes_held(ticket: int) -> float:
            if ticket not in self.bot.positions.position_open_times:
                return 0
            delta = self.broker.sim_time - self.bot.positions.position_open_times[ticket]
            return max(0, delta.total_seconds() / 60)
        self.bot.positions.get_minutes_held = _sim_get_minutes_held

        # Track trades by intercepting close_position and check_mt5_closed_positions
        self._trade_records: list[TradeRecord] = []
        self._original_close = self.bot.close_position
        self.bot.close_position = self._intercepted_close
        self._original_check_mt5 = self.bot.check_mt5_closed_positions
        self.bot.check_mt5_closed_positions = self._intercepted_check_mt5

        # Track equity (sampled, not every candle)
        self._equity_samples: list[float] = []
        self._peak_balance = starting_balance
        self._max_drawdown_pct = 0.0

    def _intercepted_close(self, position, reason: str, emergency: bool = False):
        """Intercept close_position to record trades."""
        entry_price = position.price_open
        entry_time = datetime.fromtimestamp(position.time)
        profit_before = position.profit

        # Call the real close
        self._original_close(position, reason, emergency)

        # Record the trade
        exit_time = self.broker.sim_time
        duration = (exit_time - entry_time).total_seconds() / 60
        peak = self.bot.positions.peak_position_profits.get(position.ticket, 0)

        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"

        self._trade_records.append(TradeRecord(
            ticket=position.ticket,
            direction=direction,
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=position.price_current,
            profit=profit_before,
            exit_reason=reason,
            duration_minutes=duration,
            peak_profit=peak,
        ))

    def _intercepted_check_mt5(self):
        """Intercept check_mt5_closed_positions to record SL/TP trades."""
        bot = self.bot
        current = self.broker.get_open_positions(bot.strategy.magic_number)
        current_tickets = {p.ticket for p in current}
        closed_tickets = bot.positions.tracked_positions - current_tickets

        # Filter out bot-closed (already recorded by _intercepted_close)
        sl_tp_tickets = closed_tickets - bot.positions.bot_closed_positions

        # Capture open times before they get cleaned up
        open_times = {}
        for ticket in sl_tp_tickets:
            if ticket in bot.positions.position_open_times:
                open_times[ticket] = bot.positions.position_open_times[ticket]

        # Run the real check (updates risk, backoff, etc.)
        self._original_check_mt5()

        # Record SL/TP trades
        for ticket in sl_tp_tickets:
            deals = self.broker.get_deal_history(ticket)
            if not deals:
                continue
            exit_deal = next((d for d in deals if d.entry == DEAL_ENTRY_OUT), None)
            if not exit_deal:
                continue

            if exit_deal.reason == DEAL_REASON_SL:
                exit_reason = "Stop loss"
            elif exit_deal.reason == DEAL_REASON_TP:
                exit_reason = "Take profit"
            else:
                exit_reason = "MT5 close"

            entry_time = open_times.get(ticket, self.broker.sim_time)
            exit_time = self.broker.sim_time
            duration = (exit_time - entry_time).total_seconds() / 60
            peak = bot.positions.peak_position_profits.get(ticket, 0)

            pos_info = self.broker._sl_tp_info.get(ticket, {})
            entry_price = pos_info.get('price_open', 0)
            exit_price = pos_info.get('exit_price', 0)
            pos_type = pos_info.get('type', ORDER_TYPE_BUY)
            direction = "LONG" if pos_type == ORDER_TYPE_BUY else "SHORT"

            self._trade_records.append(TradeRecord(
                ticket=ticket,
                direction=direction,
                entry_time=entry_time,
                exit_time=exit_time,
                entry_price=entry_price,
                exit_price=exit_price,
                profit=exit_deal.profit,
                exit_reason=exit_reason,
                duration_minutes=duration,
                peak_profit=peak,
            ))

    def run(self) -> BacktestResult:
        """Run the full backtest."""
        df = self.broker.candle_df
        warmup = 200

        if len(df) <= warmup:
            return BacktestResult(starting_balance=self.starting_balance)

        # Patch get_local_now to return sim time in ALL modules that imported it
        sim_time_fn = lambda: self.broker.sim_time
        self._tz_mod.get_local_now = sim_time_fn
        self._pos_mod.get_local_now = sim_time_fn
        self._bot_mod.get_local_now = sim_time_fn
        self._risk_mod.get_local_now = sim_time_fn

        # Initialize bot
        self.bot.connect()

        try:
            for i in range(warmup, len(df)):
                # Advance broker (updates prices, checks SL/TP)
                self.broker.advance(i)

                # Track drawdown (lightweight — just balance comparison)
                balance = self.broker.balance
                if balance > self._peak_balance:
                    self._peak_balance = balance
                if self._peak_balance > 0:
                    dd = (self._peak_balance - balance) / self._peak_balance * 100
                    if dd > self._max_drawdown_pct:
                        self._max_drawdown_pct = dd

                # Detect SL/TP closed positions
                self.bot.check_mt5_closed_positions()

                # Run trading logic (every bar = new candle in sim)
                self.bot.last_processed_candle = df.iloc[i]["time"]
                self.bot.trading_logic()

                # Profit protection continuous check
                if self.bot.is_profit_protection_active():
                    self.bot.check_profit_protection_continuous()

                # Sample equity periodically (every 60 candles ≈ 1 hour for M1)
                if i % 60 == 0:
                    self._equity_samples.append(balance)

                # Check if risk manager paused trading
                if self.bot.risk.trading_paused:
                    break

        finally:
            # Restore get_local_now in all patched modules
            self._tz_mod.get_local_now = self._original_get_local_now
            self._pos_mod.get_local_now = self._original_get_local_now
            self._bot_mod.get_local_now = self._original_get_local_now
            self._risk_mod.get_local_now = self._original_get_local_now

        # Close remaining positions
        positions = self.broker.get_open_positions(self.bot.strategy.magic_number)
        for pos in positions:
            self.bot.close_position(pos, "End of backtest")

        final_info = self.broker.get_account_info()

        result = BacktestResult(
            trades=self._trade_records,
            equity_curve=self._equity_samples,
            starting_balance=self.starting_balance,
            final_balance=final_info["balance"],
            peak_balance=self._peak_balance,
            max_drawdown_pct=self._max_drawdown_pct,
            paused=self.bot.risk.trading_paused,
            pause_reason=self.bot.risk.pause_reason or "",
            config=self.config,
            strategy_label=self.bot.strategy.bot_label,
        )

        if self.broker._current_bar_idx > warmup:
            start_time = self.broker.candle_df.iloc[warmup]["time"]
            end_time = self.broker.candle_df.iloc[self.broker._current_bar_idx]["time"]
            if isinstance(start_time, pd.Timestamp):
                start_time = start_time.to_pydatetime()
            if isinstance(end_time, pd.Timestamp):
                end_time = end_time.to_pydatetime()
            result.period_days = (end_time - start_time).days

        return result
