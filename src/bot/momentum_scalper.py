"""
MomentumScalper -- signal-stream momentum trader.

Computes directional pressure every second, maintains a weighted rolling
signal, and uses that signal for BOTH entry and exit decisions.

Philosophy: enter when directional signal is strong and consistent,
hold while it stays, exit immediately when it fades or flips.
No separate exit scoring logic -- the signal IS the exit logic.

Target: catch 5-15 second moves, dump on signal fade.
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
from src.strategy.momentum_signal import MomentumEngine, SignalStream

logger = logging.getLogger(__name__)


class MomentumScalper:
    """
    Signal-stream momentum scalper.

    Main loop (every second):
    1. Feed tick into engine, compute raw signal
    2. Push signal into weighted stream
    3. If no position: check if stream is strong enough to enter
    4. If in position: check if stream has faded below hold threshold
    """

    MAGIC_NUMBER = 234300
    BOT_LABEL = "MOM"

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
            bot_label=self.BOT_LABEL,
        )

        self.positions = PositionManager(
            config=config,
            bot_label=self.BOT_LABEL,
            exit_reasons_file='data/exit_reasons_momentum.json',
            drawdown_limit_fn=None,
        )

        # Signal engine and stream
        signal_window = getattr(config, 'signal_window', 15)
        heavy_count = getattr(config, 'heavy_weight_count', 5)
        factor_window = getattr(config, 'factor_window_ticks', 15)

        self.engine = MomentumEngine({
            'factor_window_ticks': factor_window,
            'rsi_period': config.rsi_period,
        })

        self.stream = SignalStream(window=signal_window, heavy_count=heavy_count)

        # Thresholds
        self.entry_threshold = getattr(config, 'entry_threshold', 0.45)
        self.hold_threshold = getattr(config, 'hold_threshold', 0.15)
        self.min_profit_for_signal_exit = getattr(config, 'min_profit_for_signal_exit', 0.50)
        self.sl_atr_mult = getattr(config, 'sl_atr_mult', 1.5)
        self.cooldown_seconds = getattr(config, 'cooldown_seconds', 15)
        self.max_trades_per_day = getattr(config, 'max_trades_per_day', 300)

        # Position state
        self._position_direction: str = ""
        self._entry_price: float = 0
        self._entry_signal_score: float = 0
        self._neutral_ticks: int = 0  # Patience counter for neutral zone

        # Tracking
        self._stop_requested = False
        self.pp_override: bool | None = None
        self.trading_mode_override: str | None = None
        self.trades_today = 0
        self.trade_log: list[dict] = []
        self.last_close_time: datetime | None = None
        self.session_start = get_local_now()

        # M1 candle tracking for RSI
        self._last_m1_candle = None

    # ── Properties ──────────────────────────────────────────────────

    @property
    def strategy(self):
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
        return False

    # ── Connection ──────────────────────────────────────────────────

    def connect(self) -> bool:
        if not self.mt5.connect():
            return False
        info = self.mt5.get_account_info()
        if info:
            self.risk.initialize(info['balance'])
        return True

    def disconnect(self):
        if self._shared_connection:
            self.logger.info("Skipping disconnect (shared MT5 connection)")
            return
        self.mt5.disconnect()

    # ── Core loop ───────────────────────────────────────────────────

    def tick(self):
        """Single iteration. Called every second."""
        tick_data = self.mt5.get_tick()
        if tick_data is None:
            return

        now = get_local_now()

        # Reset daily counter
        if now.date() > self.session_start.date():
            self.trades_today = 0
            self.session_start = now

        # Feed tick to engine
        self.engine.update_tick(tick_data.bid, tick_data.ask)

        # Feed M1 candles for RSI
        self._feed_m1_data()

        # Compute signal and push to stream
        reading = self.engine.compute_signal()
        if reading is not None:
            self.stream.push(reading)

        # Safety checks
        info = self.mt5.get_account_info()
        if not info:
            return
        if self.risk.run_all_checks(info['balance'], info['equity']):
            return

        # Check for MT5-closed positions (SL hit)
        self._check_mt5_closes()

        # Get current positions
        positions = self.mt5.get_open_positions(self.MAGIC_NUMBER)

        if positions:
            self._manage_exit(positions[0], info)
        else:
            self._manage_entry(tick_data, info, now)

    def _feed_m1_data(self):
        """Feed M1 candle data for RSI calculation."""
        rates = self.mt5.get_historical_data(timeframe=1, bars=20)
        if rates is None or len(rates) < 2:
            return

        latest_time = rates.iloc[-1]['time']

        if self._last_m1_candle is None:
            for i in range(len(rates) - 1):
                close = float(rates.iloc[i]['close'])
                self.engine.update_m1_candle(close)
            self._last_m1_candle = latest_time
            self.logger.info(f"[RSI] Bootstrapped with {len(rates) - 1} M1 candles")
        elif latest_time > self._last_m1_candle:
            close = float(rates.iloc[-2]['close'])
            self.engine.update_m1_candle(close)
            self._last_m1_candle = latest_time

    # ── Entry ───────────────────────────────────────────────────────

    def _manage_entry(self, tick_data, info: dict, now: datetime):
        """Enter when weighted signal is strong and consistent."""
        # Cooldown
        if self.last_close_time:
            elapsed = (now - self.last_close_time).total_seconds()
            if elapsed < self.cooldown_seconds:
                return

        # Max trades
        if self.trades_today >= self.max_trades_per_day:
            return

        # Need enough signal data
        if not self.stream.is_ready:
            return

        # Check spread
        if not self.engine.is_spread_ok():
            return

        score = self.stream.weighted_score
        consistency = self.stream.consistency

        # Need both strong score and good consistency
        if abs(score) < self.entry_threshold:
            return
        if consistency < 0.6:
            return

        # Determine direction
        if score > 0:
            direction = "LONG"
        else:
            direction = "SHORT"

        # Check trading mode
        mode = self.effective_trading_mode
        if mode == "long_only" and direction == "SHORT":
            return
        if mode == "short_only" and direction == "LONG":
            return

        # Calculate lot size
        volume = self.mt5.calculate_lot_size(
            info['balance'], self.config.per_position_size_pct,
            self.config.leverage, tick_data.bid,
        )
        if not volume:
            return

        # SL from M5 ATR
        m5_atr = self._get_m5_atr()
        sl_distance = m5_atr * self.sl_atr_mult

        if direction == "LONG":
            entry_price = tick_data.ask
            sl = entry_price - sl_distance
            tp = 0  # No TP -- signal exit handles it
        else:
            entry_price = tick_data.bid
            sl = entry_price + sl_distance
            tp = 0

        # Place market order
        order_type = ORDER_TYPE_BUY if direction == "LONG" else ORDER_TYPE_SELL
        result = self.mt5.place_order(
            order_type, volume, sl, tp,
            self.MAGIC_NUMBER, "momentum_scalper",
        )

        if result:
            ticket = result.order
            self.positions.register_open(ticket)
            self.trades_today += 1
            self._position_direction = direction
            self._entry_price = entry_price
            self._entry_signal_score = score

            self.logger.info(
                f">>> ENTER [{direction}] @ ${entry_price:.2f} "
                f"(signal={score:.3f}, consistency={consistency:.2f}, "
                f"SL=${sl:.2f})"
            )

            self.trade_log.append({
                'action': 'OPEN', 'time': now,
                'type': direction, 'entry_price': entry_price,
                'signal_score': score, 'consistency': consistency,
            })

    # ── Exit ────────────────────────────────────────────────────────

    def _manage_exit(self, position, info: dict):
        """Exit when signal fades below hold threshold or flips."""
        ticket = position.ticket
        profit = position.profit
        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"

        # Sync internal state if needed (restart recovery)
        if not self._position_direction:
            self._position_direction = direction
            self._entry_price = position.price_open

        # Register for tracking
        self.positions.register_existing(
            ticket, self.mt5.mt5_timestamp_to_local(position.time), profit
        )

        # Need signal data to decide
        if not self.stream.is_ready:
            return

        score = self.stream.weighted_score

        # ── Signal zone classification (relative to our position direction) ──
        # For a LONG: positive score = favorable, negative = unfavorable
        # For a SHORT: negative score = favorable, positive = unfavorable
        if direction == "LONG":
            directional_score = score   # Positive = good for us
        else:
            directional_score = -score  # Flip: negative score = good for short

        # Zones:
        #   Strong favorable:  directional_score >= entry_threshold (move is strong)
        #   Weak favorable:    hold_threshold <= directional_score < entry_threshold
        #   Neutral:           -hold_threshold < directional_score < hold_threshold
        #   Strong unfavorable: directional_score <= -hold_threshold (flipped against us)

        strong_favorable = directional_score >= self.entry_threshold
        weak_favorable = self.hold_threshold <= directional_score < self.entry_threshold
        neutral = -self.hold_threshold < directional_score < self.hold_threshold
        strong_unfavorable = directional_score <= -self.hold_threshold

        # ── Exit decision with patience ──────────────────────────────
        should_exit = False
        reason = ""

        if strong_unfavorable:
            # Signal flipped hard against us — close immediately
            should_exit = True
            reason = f"Signal flipped ({score:.3f}, dir_score={directional_score:.3f})"
            self._neutral_ticks = 0

        elif strong_favorable:
            # Move is strong in our favor — reset patience, hold
            self._neutral_ticks = 0

        elif weak_favorable:
            # Still on our side but weakening — partial patience reset
            # Reduce neutral tick count but don't fully reset
            self._neutral_ticks = max(0, self._neutral_ticks - 2)

        elif neutral:
            # Signal in no-man's land — tick the patience counter
            self._neutral_ticks += 1
            # Grace period: allow up to 15 seconds in neutral before exiting
            max_neutral_patience = 15
            if self._neutral_ticks >= max_neutral_patience:
                should_exit = True
                reason = f"Neutral timeout ({self._neutral_ticks}s, score={score:.3f})"
                self._neutral_ticks = 0

        if not should_exit:
            return

        # Commission protection: don't exit for tiny loss if signal is just in neutral
        if profit < -self.min_profit_for_signal_exit and not strong_unfavorable:
            return

        # Close position
        result = self.mt5.close_position(position, self.MAGIC_NUMBER, "momentum_close")
        if not result:
            return

        self.risk.record_trade_result(profit)
        self.positions.save_exit(ticket, reason)
        self.positions.register_close(ticket)

        self.logger.info(
            f"<<< EXIT [{direction}] -- {reason}, P/L: ${profit:.2f}"
        )

        self.last_close_time = get_local_now()
        self._position_direction = ""
        self._entry_price = 0
        self._entry_signal_score = 0
        self._neutral_ticks = 0

        self.trade_log.append({
            'action': 'CLOSE', 'time': get_local_now(),
            'type': direction, 'profit': profit, 'reason': reason,
        })

    # ── MT5 close detection ─────────────────────────────────────────

    def _check_mt5_closes(self):
        """Detect SL closes by MT5."""
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
                    elif exit_deal.reason == DEAL_REASON_TP:
                        reason = "Take profit"

            self.risk.record_trade_result(profit)
            self.last_close_time = get_local_now()
            self._position_direction = ""
            self._entry_price = 0
            self.positions.save_exit(ticket, reason)
            self.positions.tracked_positions.discard(ticket)
            self.logger.info(f"[MT5 EXIT] Ticket {ticket}: {reason} (${profit:.2f})")

    # ── Helpers ─────────────────────────────────────────────────────

    def _get_m5_atr(self) -> float:
        """Get M5 ATR for stop loss calculation."""
        df = self.mt5.get_historical_data(timeframe=5, bars=20)
        if df is None or len(df) < 15:
            return 5.0
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        tr = []
        for i in range(1, len(df)):
            tr.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return float(np.mean(tr[-14:])) if tr else 5.0

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

        tick_data = self.mt5.get_tick()
        price = tick_data.bid if tick_data else 0

        # Signal info
        weighted = self.stream.weighted_score
        consistency = self.stream.consistency

        # Latest raw reading
        latest = self.stream.readings[-1] if self.stream.readings else None
        long_raw = latest.long_raw if latest else 0
        short_raw = latest.short_raw if latest else 0

        return {
            'bot_label': self.BOT_LABEL,
            'status': 'Paused' if self.risk.trading_paused else 'Running',
            'pause_reason': self.risk.pause_reason,
            'balance': balance, 'equity': equity, 'price': price,
            'positions': position_states,
            'max_positions': self.config.max_positions,
            'indicators': {
                'signal_score': weighted,
                'consistency': consistency,
                'long_raw': long_raw,
                'short_raw': short_raw,
                'spread': self.engine.current_spread,
                'spread_ratio': self.engine.spread_ratio,
                'direction': self.stream.direction,
                'samples': len(self.stream.readings),
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
            'high_volatility': False,
            'trading_mode': self.effective_trading_mode,
        }

    # ── Main loop ───────────────────────────────────────────────────

    def run(self, check_interval: int = 1):
        self.logger.info("=" * 80)
        self.logger.info("MOMENTUM SCALPER STARTED")
        self.logger.info(f"Active parameters:")
        self.logger.info(f"  entry_threshold={self.entry_threshold}, "
                         f"hold_threshold={self.hold_threshold}")
        self.logger.info(f"  signal_window={self.stream.window}s, "
                         f"heavy_weight_count={self.stream.heavy_count}")
        self.logger.info(f"  sl_atr_mult={self.sl_atr_mult}, "
                         f"cooldown_seconds={self.cooldown_seconds}")
        self.logger.info(f"  max_trades_per_day={self.max_trades_per_day}, "
                         f"leverage={self.config.leverage}, "
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
