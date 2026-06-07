"""
TickScalper -- precision scalper using tick-level analysis.

Runs every second, maintains multi-factor scoring for entries and exits.
Uses limit orders for entries (no spread cost) and dynamic trailing stops.

Target: 20-30 trades per day with high win rate.
"""

import logging
import time
from datetime import datetime

import numpy as np

from src.core.config import TradingConfig
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL
from src.core.position import PositionManager
from src.core.risk import RiskManager
from src.core.timezone import get_local_now
from src.core.tick_analysis import TickAnalyzer, EntrySignal, VelocityTracker
from src.core.trend import TrendAnalyzer

logger = logging.getLogger(__name__)


class TickScalper:
    """
    Precision tick-level scalper.

    Main loop (every second):
    1. Feed tick into analyzer
    2. If no position: check entry score, manage limit order
    3. If in position: check exit score, manage trailing stop
    """

    MAGIC_NUMBER = 234200
    BOT_LABEL = "TICK"

    def __init__(self, config: TradingConfig, broker=None):
        self.config = config

        if broker is not None:
            self.mt5 = broker
        else:
            from src.core.mt5_broker import MT5Broker
            self.mt5 = MT5Broker()

        self._shared_connection = False
        self.logger = logging.getLogger(f"src.bot.{self.BOT_LABEL}")

        self.risk = RiskManager(
            max_drawdown_limit=config.max_drawdown_limit,
            max_consecutive_losses=50,
            bot_label=self.BOT_LABEL,
        )

        self.positions = PositionManager(
            config=config,
            bot_label=self.BOT_LABEL,
            exit_reasons_file='data/exit_reasons_tick.json',
            drawdown_limit_fn=None,
        )

        # Tick analyzer
        self.analyzer = TickAnalyzer({
            'entry_threshold': getattr(config, 'tick_entry_threshold', 0.65),
            'exit_threshold': getattr(config, 'tick_exit_threshold', 0.55),
            'rsi_period': config.rsi_period,
            'micro_trend_window': getattr(config, 'tick_micro_trend_window', 30),
            'support_lookback': getattr(config, 'tick_support_lookback', 300),
        })

        # Pending limit order state
        self._pending_order: dict | None = None  # {direction, price, sl, tp, score, placed_at}
        self._order_ticket: int | None = None  # MT5 pending order ticket

        # Position management
        self._peak_profit_price: float = 0
        self._entry_price: float = 0
        self._position_direction: str = ""
        self._velocity_tracker: VelocityTracker | None = None
        self._partial_closed: bool = False
        self._exit_confirm_history: list[bool] = []  # rolling exit score hits

        # Entry state machine: IDLE -> ARMED -> CONFIRMING -> FILL
        # IDLE: no signal, waiting
        # ARMED: score exceeded threshold, watching for turn
        # CONFIRMING: velocity flipping, waiting for confirmation
        self._entry_state: str = "IDLE"
        self._armed_signal: EntrySignal | None = None
        self._armed_at: datetime | None = None
        self._confirm_ticks: int = 0  # consecutive ticks of positive velocity
        self._confirm_history: list[bool] = []  # rolling entry confirmation window

        # State
        self._stop_requested = False
        self.pp_override: bool | None = None
        self.trading_mode_override: str | None = None
        self._high_volatility = False
        self.consecutive_sl_exits = 0
        self.trades_today = 0
        self.trade_log: list[dict] = []
        self.last_close_time: datetime | None = None
        self.session_start = get_local_now()

        # M1 candle tracking for RSI feed
        self._last_m1_candle = None

        # Trend analyzer (multi-timeframe)
        self._trend: TrendAnalyzer | None = None

        # Cooldown after trade (seconds)
        self._cooldown_seconds = getattr(config, 'tick_cooldown_seconds', 30)

    # ── Properties ──────────────────────────────────────────────────

    @property
    def strategy(self):
        """Compatibility shim for BotManager."""
        return self

    @property
    def bot_label(self) -> str:
        return self.BOT_LABEL

    @property
    def magic_number(self) -> int:
        return self.MAGIC_NUMBER

    @property
    def effective_trading_mode(self) -> str:
        if self.trading_mode_override is not None:
            return self.trading_mode_override
        return self.config.trading_mode

    def is_profit_protection_active(self) -> bool:
        if self.pp_override is not None:
            return self.pp_override
        return False  # Tick scalper uses trailing stop instead of PP

    # ── Connection ──────────────────────────────────────────────────

    def connect(self) -> bool:
        if not self.mt5.connect():
            return False
        info = self.mt5.get_account_info()
        if info:
            self.risk.initialize(info['balance'])
        # Initialize trend analyzer
        self._trend = TrendAnalyzer(self.mt5)
        self._trend.update()
        return True

    def disconnect(self):
        if self._shared_connection:
            self.logger.info("Skipping disconnect (shared MT5 connection)")
            return
        self.mt5.disconnect()

    # ── Core loop (runs every second) ───────────────────────────────

    def tick(self):
        """Single tick iteration. Called every second from main loop."""
        # Get current tick
        tick = self.mt5.get_tick()
        if tick is None:
            return

        now = get_local_now()

        # Reset daily counter at midnight
        if now.date() > self.session_start.date():
            self.trades_today = 0
            self.session_start = now

        self.analyzer.update_tick(tick.bid, tick.ask, now)

        # Feed M1 candles for RSI
        self._feed_m1_data()

        # Safety checks
        info = self.mt5.get_account_info()
        if not info:
            return
        if self.risk.run_all_checks(info['balance'], info['equity']):
            return

        # Check for MT5-closed positions (SL/TP)
        self._check_mt5_closes()

        # Get current positions
        positions = self.mt5.get_open_positions(self.MAGIC_NUMBER)

        if positions:
            # ── In position: manage exit ────────────────────────────
            self._manage_position(positions[0], info)
        else:
            # ── No position: manage entry ───────────────────────────
            self._manage_entry(tick, info, now)

    def _feed_m1_data(self):
        """Feed M1 candle data to analyzer for RSI calculation."""
        rates = self.mt5.get_historical_data(timeframe=1, bars=20)  # TIMEFRAME_M1
        if rates is None or len(rates) < 2:
            return

        latest_time = rates.iloc[-1]['time']

        if self._last_m1_candle is None:
            # First call: bootstrap with all available completed candles
            for i in range(len(rates) - 1):  # Exclude last (incomplete) candle
                close = float(rates.iloc[i]['close'])
                candle_time = rates.iloc[i]['time']
                if hasattr(candle_time, 'to_pydatetime'):
                    candle_time = candle_time.to_pydatetime()
                self.analyzer.update_m1_candle(close, candle_time)
            self._last_m1_candle = latest_time
            self.logger.info(f"[RSI] Bootstrapped with {len(rates) - 1} M1 candles")
        elif latest_time > self._last_m1_candle:
            # New M1 candle appeared — feed the previous (now completed) candle
            close = float(rates.iloc[-2]['close'])
            candle_time = rates.iloc[-2]['time']
            if hasattr(candle_time, 'to_pydatetime'):
                candle_time = candle_time.to_pydatetime()
            self.analyzer.update_m1_candle(close, candle_time)
            self._last_m1_candle = latest_time

    # ── Entry management ────────────────────────────────────────────

    def _manage_entry(self, tick, info: dict, now: datetime):
        """
        Entry state machine with bottom confirmation.

        States:
          IDLE: no signal, checking score each tick
          ARMED: score exceeded threshold, waiting for price to stop falling
          CONFIRMING: velocity flipped positive, counting confirmation ticks

        This prevents entering during a continued drop. We wait for the
        actual turn before placing the order.
        """
        # Cooldown after last trade
        if self.last_close_time:
            elapsed = (now - self.last_close_time).total_seconds()
            if elapsed < self._cooldown_seconds:
                return

        # Check max trades per day
        max_trades = getattr(self.config, 'tick_max_trades_per_day', 30)
        if self.trades_today >= max_trades:
            return

        if self._entry_state == "IDLE":
            self._entry_idle(tick, info, now)
        elif self._entry_state == "ARMED":
            self._entry_armed(tick, info, now)
        elif self._entry_state == "CONFIRMING":
            self._entry_confirming(tick, info, now)

    def _entry_idle(self, tick, info: dict, now: datetime):
        """IDLE: check if entry score exceeds threshold."""
        # Update trend periodically
        if self._trend and self._trend.should_update():
            self._trend.update()

        signal = self.analyzer.get_entry_score()
        if signal is None:
            return

        # Check trading mode
        mode = self.effective_trading_mode
        if mode == "long_only" and signal.direction == "SHORT":
            return
        if mode == "short_only" and signal.direction == "LONG":
            return

        # Apply trend bias: boost with-trend, penalize counter-trend
        adjusted_score = signal.score
        if self._trend:
            trend_score = self._trend.score
            if signal.direction == "LONG":
                # Positive trend helps longs, negative hurts
                adjusted_score += trend_score * 0.15
            else:
                # Negative trend helps shorts, positive hurts
                adjusted_score -= trend_score * 0.15

        # Check threshold with trend-adjusted score
        threshold = getattr(self.config, 'tick_entry_threshold', 0.40)
        if adjusted_score < threshold:
            return

        # Score is high enough — arm the entry
        self._entry_state = "ARMED"
        self._armed_signal = signal
        self._armed_at = now
        self._confirm_ticks = 0

        trend_dir = self._trend.direction if self._trend else "?"
        self.logger.info(
            f"[ENTRY ARMED] {signal.direction} score={adjusted_score:.2f} "
            f"(raw={signal.score:.2f}, trend={trend_dir}) -- waiting for turn"
        )

    def _entry_armed(self, tick, info: dict, now: datetime):
        """ARMED: waiting for price to stop moving against us (velocity flip)."""
        # Timeout: if armed for more than 60 seconds without confirmation, reset
        if self._armed_at and (now - self._armed_at).total_seconds() > 60:
            self.logger.info("[ENTRY TIMEOUT] Armed for 60s without confirmation, resetting")
            self._reset_entry_state()
            return

        # Check if signal is still valid (score still above threshold)
        signal = self.analyzer.get_entry_score()
        if signal is None or signal.direction != self._armed_signal.direction:
            # Signal disappeared or flipped — reset
            self._reset_entry_state()
            return

        # Update the signal (price levels may have shifted)
        self._armed_signal = signal

        # Check velocity: is price still moving against us?
        if len(self.analyzer.ticks) < 5:
            return

        recent_prices = [self.analyzer.ticks[-i].mid for i in range(1, 6)]

        if self._armed_signal.direction == "LONG":
            # For longs: we want price to STOP falling (velocity >= 0)
            velocity = recent_prices[0] - recent_prices[-1]  # positive = rising
            spread_narrowing = self._is_spread_narrowing()

            if velocity >= 0 or spread_narrowing:
                # Price stopped falling or spread narrowing — move to confirming
                self._entry_state = "CONFIRMING"
                self._confirm_ticks = 1
                self.logger.info(
                    f"[ENTRY CONFIRMING] Price turning up (vel={velocity:.3f}, "
                    f"spread_narrowing={spread_narrowing})"
                )
        else:
            # For shorts: we want price to STOP rising
            velocity = recent_prices[-1] - recent_prices[0]  # positive = falling
            spread_narrowing = self._is_spread_narrowing()

            if velocity >= 0 or spread_narrowing:
                self._entry_state = "CONFIRMING"
                self._confirm_ticks = 1
                self.logger.info(
                    f"[ENTRY CONFIRMING] Price turning down (vel={velocity:.3f}, "
                    f"spread_narrowing={spread_narrowing})"
                )

    def _entry_confirming(self, tick, info: dict, now: datetime):
        """CONFIRMING: velocity flipped, counting confirmation ticks before entry."""
        # Need 5 of last 6 ticks favorable (allows one dip without resetting)
        if len(self.analyzer.ticks) < 3:
            return

        recent_prices = [self.analyzer.ticks[-i].mid for i in range(1, 4)]

        if self._armed_signal.direction == "LONG":
            still_rising = recent_prices[0] >= recent_prices[1]
        else:
            still_rising = recent_prices[0] <= recent_prices[1]

        self._confirm_history.append(still_rising)

        # Check: 5 of last 6 must be favorable
        window = list(self._confirm_history)[-6:]
        favorable_count = sum(window)

        if favorable_count >= 5 and len(window) >= 5:
            self.logger.info(
                f"[ENTRY CONFIRMED] {self._armed_signal.direction} "
                f"after {favorable_count}/{ len(window)} favorable ticks"
            )
            self._execute_confirmed_entry(tick, info)
            self._reset_entry_state()
        elif len(window) >= 6 and favorable_count < 5:
            # Window full and not enough favorable ticks — reset
            self._entry_state = "ARMED"
            self._confirm_history.clear()
            self._execute_confirmed_entry(tick, info)
            self._reset_entry_state()

    def _execute_confirmed_entry(self, tick, info: dict):
        """Execute entry after bottom/top confirmation."""
        signal = self._armed_signal
        if signal is None:
            return

        volume = self.mt5.calculate_lot_size(
            info['balance'], self.config.per_position_size_pct,
            self.config.leverage, tick.bid,
        )
        if not volume:
            return

        # Enter at current price (we've confirmed the turn)
        if signal.direction == "LONG":
            entry_price = tick.bid
        else:
            entry_price = tick.ask

        # Use M5 ATR for SL/TP (V7: wide SL like V4)
        m5_atr = self._get_m5_atr()
        if signal.direction == "LONG":
            sl = entry_price - m5_atr * 6.0
            tp = entry_price + m5_atr * 20.0
        else:
            sl = entry_price + m5_atr * 6.0
            tp = entry_price - m5_atr * 20.0

        order = {
            'direction': signal.direction,
            'price': entry_price,
            'sl': sl,
            'tp': tp,
            'score': signal.score,
            'volume': volume,
            'placed_at': get_local_now(),
        }

        self._execute_fill(order, info)

    def _get_m5_atr(self) -> float:
        """Get M5 ATR for stop distance calculations."""
        df = self.mt5.get_historical_data(timeframe=5, bars=20)
        if df is None or len(df) < 15:
            return 5.0  # Default fallback for gold
        # Calculate ATR from M5 candles
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        tr = []
        for i in range(1, len(df)):
            tr.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1]),
            ))
        return float(np.mean(tr[-14:])) if tr else 5.0

    def _is_spread_narrowing(self) -> bool:
        """Check if spread is narrowing (selling/buying pressure easing)."""
        if len(self.analyzer.ticks) < 10:
            return False

        # Compare average spread of last 3 ticks vs previous 7
        recent_spreads = [
            self.analyzer.ticks[-i].ask - self.analyzer.ticks[-i].bid
            for i in range(1, 4)
        ]
        older_spreads = [
            self.analyzer.ticks[-i].ask - self.analyzer.ticks[-i].bid
            for i in range(4, 11)
        ]

        avg_recent = sum(recent_spreads) / len(recent_spreads)
        avg_older = sum(older_spreads) / len(older_spreads)

        # Spread narrowed by at least 20%
        return avg_recent < avg_older * 0.8

    def _reset_entry_state(self):
        """Reset entry state machine to IDLE."""
        self._entry_state = "IDLE"
        self._armed_signal = None
        self._armed_at = None
        self._confirm_ticks = 0
        self._confirm_history.clear()

    def _execute_fill(self, order: dict, info: dict):
        """Execute a filled limit order."""
        order_type = ORDER_TYPE_BUY if order['direction'] == "LONG" else ORDER_TYPE_SELL

        if hasattr(self.mt5, 'place_limit_order'):
            result = self.mt5.place_limit_order(
                order_type, order['volume'], order['price'],
                order['sl'], order['tp'],
                self.MAGIC_NUMBER, "tick_scalper",
            )
        else:
            result = self.mt5.place_order(
                order_type, order['volume'], order['sl'], order['tp'],
                self.MAGIC_NUMBER, "tick_scalper",
            )

        if result:
            ticket = result.order
            self.positions.register_open(ticket)
            self.trades_today += 1
            self._entry_price = order['price']
            self._position_direction = order['direction']
            self._peak_profit_price = order['price']
            self._velocity_tracker = VelocityTracker(order['direction'], order['price'])
            self._partial_closed = False

            self.logger.info(
                f">>> FILL [{order['direction']}] @ ${order['price']:.2f} "
                f"(score={order['score']:.2f}, SL=${order['sl']:.2f}, TP=${order['tp']:.2f})"
            )

            self.trade_log.append({
                'action': 'OPEN', 'time': get_local_now(),
                'type': order['direction'], 'entry_price': order['price'],
                'score': order['score'],
            })

        self._pending_order = None

    def _cancel_pending_order(self):
        """Cancel the current pending order (legacy, kept for compatibility)."""
        self._reset_entry_state()

    # ── Position management ─────────────────────────────────────────

    def _manage_position(self, position, info: dict):
        """Manage an open position: velocity tracking + trailing stop + exit scoring."""
        ticket = position.ticket
        current_price = position.price_current
        entry = position.price_open
        profit = position.profit

        # Determine direction from the position itself (not internal state)
        # This handles positions found after restart
        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"
        if not self._position_direction:
            self._position_direction = direction
            self._entry_price = entry
            self._peak_profit_price = current_price

        # Track peak price for trailing stop
        if direction == "LONG":
            if current_price > self._peak_profit_price:
                self._peak_profit_price = current_price
        else:
            if current_price < self._peak_profit_price:
                self._peak_profit_price = current_price

        # Update velocity tracker
        now = get_local_now()
        if self._velocity_tracker:
            self._velocity_tracker.update(current_price, now)

        # Register for tracking
        self.positions.register_existing(
            ticket, self.mt5.mt5_timestamp_to_local(position.time), profit
        )

        minutes_held = self.positions.get_minutes_held(ticket)

        # 1. Trailing stop using tick ATR (V4-style: very tight, rarely triggers
        #    because exit score closes first in most cases)
        tick_atr = self.analyzer._calc_tick_atr()
        trail_distance = tick_atr * 2.5  # ~$0.50-0.75, effectively a tight safety net

        # Safety: don't trail if peak price is not set properly
        if self._peak_profit_price < 100:
            return

        # Minimum SL distance from current price (broker requires SL outside spread)
        spread = self.analyzer.get_current_spread() if hasattr(self.analyzer, 'get_current_spread') else 0.30
        min_stop_distance = max(1.0, spread * 3)  # At least $1 or 3x spread

        if direction == "LONG":
            new_sl = self._peak_profit_price - trail_distance
            # SL must be below current price by at least min_stop_distance
            if new_sl >= current_price - min_stop_distance:
                pass  # Too close or above price, skip
            elif new_sl > position.sl + 0.10 and hasattr(self.mt5, 'modify_sl'):
                self.mt5.modify_sl(ticket, new_sl)
        else:
            new_sl = self._peak_profit_price + trail_distance
            # SL must be above current price by at least min_stop_distance
            if new_sl <= current_price + min_stop_distance:
                pass  # Too close or below price, skip
            elif new_sl < position.sl - 0.10 and hasattr(self.mt5, 'modify_sl'):
                self.mt5.modify_sl(ticket, new_sl)

        # 2. Exit score (velocity-aware)
        entry = position.price_open
        exit_signal = self.analyzer.get_exit_score(
            self._position_direction, entry, profit, minutes_held,
            velocity_tracker=self._velocity_tracker,
            m5_atr=self._get_m5_atr(),
        )

        # 3. V4-style exit: score > threshold, 4 of last 5 ticks above, only in profit
        # Allows one tick to dip below without resetting the whole confirmation.
        above_threshold = profit > 0 and exit_signal.score >= self.analyzer.exit_threshold
        self._exit_confirm_history.append(above_threshold)

        # Keep only last 5
        if len(self._exit_confirm_history) > 5:
            self._exit_confirm_history = self._exit_confirm_history[-5:]

        # Need 4 of last 5 ticks above threshold
        if sum(self._exit_confirm_history[-5:]) >= 4:
            self._close_position(position, exit_signal.reason)

    def _close_position(self, position, reason: str):
        """Close a position."""
        ticket = position.ticket
        result = self.mt5.close_position(position, self.MAGIC_NUMBER, "tick_close")
        if not result:
            return

        profit = position.profit
        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"

        self.risk.record_trade_result(profit)
        self.positions.save_exit(ticket, reason)
        self.positions.register_close(ticket)

        self.logger.info(f"<<< CLOSED [{direction}] -- {reason}, P/L: ${profit:.2f}")
        self.last_close_time = get_local_now()
        self._pending_order = None
        self._peak_profit_price = 0
        self._velocity_tracker = None
        self._partial_closed = False
        self._exit_confirm_history.clear()
        self._reset_entry_state()

        self.trade_log.append({
            'action': 'CLOSE', 'time': get_local_now(),
            'type': direction, 'profit': profit, 'reason': reason,
        })

    # ── MT5 close detection ─────────────────────────────────────────

    def _check_mt5_closes(self):
        """Detect SL/TP closes."""
        from src.core.broker import DEAL_ENTRY_OUT, DEAL_REASON_SL, DEAL_REASON_TP

        current = self.mt5.get_open_positions(self.MAGIC_NUMBER)
        current_tickets = {p.ticket for p in current}
        self.positions.tracked_positions.update(current_tickets)
        closed = self.positions.tracked_positions - current_tickets

        for ticket in closed:
            if ticket in self.positions.bot_closed_positions:
                self.positions.bot_closed_positions.discard(ticket)
                self.positions.tracked_positions.discard(ticket)
                continue

            deals = self.mt5.get_deal_history(ticket)
            profit = -1
            reason = "MT5 close"

            if deals:
                exit_deal = next((d for d in deals if d.entry == DEAL_ENTRY_OUT), None)
                if exit_deal:
                    profit = exit_deal.profit
                    if exit_deal.reason == DEAL_REASON_SL:
                        reason = "Stop loss"
                        self.consecutive_sl_exits += 1
                    elif exit_deal.reason == DEAL_REASON_TP:
                        reason = "Take profit"
                        self.consecutive_sl_exits = 0

            self.risk.record_trade_result(profit)
            self.last_close_time = get_local_now()
            self._peak_profit_price = 0
            self._velocity_tracker = None
            self._partial_closed = False
            self.positions.save_exit(ticket, reason)
            self.positions.tracked_positions.discard(ticket)
            self.logger.info(f"[MT5 EXIT] Ticket {ticket}: {reason} (${profit:.2f})")

    # ── State for GUI ───────────────────────────────────────────────

    def get_state(self) -> dict:
        info = self.mt5.get_account_info()
        balance = info['balance'] if info else 0
        equity = info['equity'] if info else 0

        positions = self.mt5.get_open_positions(self.MAGIC_NUMBER)
        position_states = []
        for pos in positions:
            direction = "LONG" if pos.type == ORDER_TYPE_BUY else "SHORT"
            pos_state = self.positions.get_position_state(pos.ticket, pos.profit, balance)
            pos_state.update({
                'direction': direction, 'entry_price': pos.price_open,
                'current_price': pos.price_current, 'sl': pos.sl, 'tp': pos.tp,
                'volume': pos.volume, 'profit': pos.profit,
            })
            position_states.append(pos_state)

        tick = self.mt5.get_tick()
        price = tick.bid if tick else 0

        # Analyzer state
        rsi = self.analyzer._calc_tick_rsi()
        atr = self.analyzer._calc_tick_atr()

        # Current scores
        entry_signal = self.analyzer.get_entry_score()
        long_score = 0.0
        short_score = 0.0
        if entry_signal:
            if entry_signal.direction == "LONG":
                long_score = entry_signal.score
            else:
                short_score = entry_signal.score
        else:
            # Even if no signal, compute raw scores for display
            if len(self.analyzer.ticks) >= 30:
                lt, st = self.analyzer._calc_micro_trend()
                rsi_val = self.analyzer._calc_tick_rsi()
                lr = max(0, (40 - rsi_val) / 40) if rsi_val is not None else 0
                sr = max(0, (rsi_val - 60) / 40) if rsi_val is not None else 0
                long_score = lt * 0.15 + lr * 0.25
                short_score = st * 0.15 + sr * 0.25

        exit_score = 0.0
        vel_ratio = 0.0
        if self._velocity_tracker and positions:
            exit_sig = self.analyzer.get_exit_score(
                self._position_direction, self._entry_price,
                positions[0].profit if positions else 0,
                self.positions.get_minutes_held(positions[0].ticket) if positions else 0,
                velocity_tracker=self._velocity_tracker,
                m5_atr=self._get_m5_atr(),
            )
            exit_score = exit_sig.score
            vel_ratio = self._velocity_tracker.velocity_ratio

        pending_info = {}
        if self._armed_signal:
            pending_info = {
                'direction': self._armed_signal.direction,
                'price': self._armed_signal.entry_price,
                'score': self._armed_signal.score,
                'state': self._entry_state,
            }

        # Trend info
        trend_score = self._trend.score if self._trend else 0
        trend_dir = self._trend.direction if self._trend else "?"

        return {
            'bot_label': self.BOT_LABEL,
            'status': 'Paused' if self.risk.trading_paused else 'Running',
            'pause_reason': self.risk.pause_reason,
            'balance': balance, 'equity': equity, 'price': price,
            'positions': position_states,
            'max_positions': self.config.max_positions,
            'indicators': {
                'rsi': rsi or 0,
                'atr': atr,
                'ticks_buffered': len(self.analyzer.ticks),
                'long_score': long_score,
                'short_score': short_score,
                'exit_score': exit_score,
                'velocity_ratio': vel_ratio,
                'spread': self.analyzer.get_current_spread(),
                'spread_ratio': self.analyzer.get_spread_ratio(),
                'entry_state': self._entry_state,
                'trend_score': trend_score,
                'trend_dir': trend_dir,
            },
            'cooldown': {'active': False, 'reason': 'Ready'},
            'consecutive_losses': self.risk.consecutive_losses,
            'trades_today': self.trades_today,
            'drawdown_pct': (
                (self.risk.peak_balance - balance) / self.risk.peak_balance * 100
                if self.risk.peak_balance and self.risk.peak_balance > 0 else 0
            ),
            'pp_active': False,
            'pp_override': self.pp_override,
            'high_volatility': self._high_volatility,
            'trading_mode': self.effective_trading_mode,
            'pending_order': pending_info,
            'rsi_buy': self.config.rsi_buy,
            'rsi_sell': self.config.rsi_sell,
            'rsi_exit_long': self.config.rsi_exit_long,
            'rsi_exit_short': self.config.rsi_exit_short,
        }

    # ── Main loop ───────────────────────────────────────────────────

    def run(self, check_interval: int = 1):
        self.logger.info("=" * 80)
        self.logger.info("EGON TICK SCALPER STARTED")
        self.logger.info(f"Active parameters:")
        self.logger.info(f"  tick_entry_threshold={self.analyzer.entry_threshold}, "
                         f"tick_exit_threshold={self.analyzer.exit_threshold}")
        self.logger.info(f"  tick_cooldown_seconds={getattr(self.config, 'tick_cooldown_seconds', 30)}, "
                         f"tick_max_trades_per_day={getattr(self.config, 'tick_max_trades_per_day', 30)}")
        self.logger.info(f"  leverage={self.config.leverage}, "
                         f"position_size_pct={self.config.position_size_pct}")
        self.logger.info("=" * 80)

        if not self.connect():
            self.logger.error("Failed to connect to MT5")
            return

        try:
            while not self._stop_requested:
                try:
                    self.tick()
                    time.sleep(1)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"Error: {e}", exc_info=True)
                    time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        finally:
            self.disconnect()
