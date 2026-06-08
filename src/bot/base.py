"""
BaseTradingBot -- main loop, safety, lifecycle.

Contains all shared logic: connection, candle detection, cooldown,
loss backoff, position opening/closing, profit protection, MT5 close detection.
Strategies plug in via the TradingStrategy protocol.
"""

import logging
import time
from datetime import datetime

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.indicators import compute_indicators, get_adaptive_atr_multiplier
from src.core.broker import (
    ORDER_TYPE_BUY, ORDER_TYPE_SELL,
    DEAL_ENTRY_OUT, DEAL_REASON_SL, DEAL_REASON_TP,
)
from src.core.position import PositionManager
from src.core.risk import RiskManager
from src.core.timezone import get_local_now, LOCAL_TZ, MT5_TZ
from src.strategy.base import TradingStrategy

logger = logging.getLogger(__name__)


class BaseTradingBot:
    """
    Orchestrates the trading loop using a pluggable TradingStrategy.

    Handles: MT5 connection, candle detection, safety checks, cooldown/backoff,
    position opening/closing, profit protection, MT5 close detection, reporting.
    """

    def __init__(self, strategy: TradingStrategy, config: TradingConfig, broker=None):
        self.strategy = strategy
        self.config = config

        # Broker backend: injected for testing, defaults to MT5 for live
        if broker is not None:
            self.mt5 = broker
        else:
            from src.core.mt5_broker import MT5Broker
            self.mt5 = MT5Broker()

        # When True, skip disconnect() on shutdown (GUI owns the MT5 connection)
        self._shared_connection = False

        # Bot-specific logger so GUI can capture logs per-bot
        self.logger = logging.getLogger(f"src.bot.{strategy.bot_label}")

        self.risk = RiskManager(
            max_drawdown_limit=config.max_drawdown_limit,
            max_consecutive_losses=12,
            bot_label=strategy.bot_label,
        )

        self.positions = PositionManager(
            config=config,
            bot_label=strategy.bot_label,
            exit_reasons_file=f'data/exit_reasons_{strategy.bot_label.lower()}.json',
            drawdown_limit_fn=self._make_drawdown_limit_fn(strategy, config),
        )

        # Cooldown / entry state
        self.last_close_time: datetime | None = None
        self.last_close_position_type: str | None = None
        self.last_trade_profitable: bool = False
        self.cooldown_candles: int = 2
        self.warmup_candles: int = 2

        # Candle tracking
        self.last_processed_candle = None

        # Trade log
        self.trade_log: list[dict] = []
        self.trades_today: int = 0
        self.session_start: datetime = get_local_now()

        # Stop flag for clean shutdown from BotManager
        self._stop_requested: bool = False

        # Profit protection runtime override (None=config/auto, True=force on, False=force off)
        self.pp_override: bool | None = None

        # Trading mode runtime override (None=use config, else "both"/"long_only"/"short_only")
        self.trading_mode_override: str | None = None

        # Volatility state for auto-PP
        self._high_volatility: bool = False

        # Consecutive stop-loss exits (for SL tightening)
        self.consecutive_sl_exits: int = 0

        # Trailing stop state
        self._breakeven_applied: set[int] = set()
        self._last_df: pd.DataFrame | None = None

    # ── Connection ──────────────────────────────────────────────────────

    def is_profit_protection_active(self) -> bool:
        """Check if profit protection is currently active.

        Priority: GUI override > auto-volatility > config.
        """
        if self.pp_override is not None:
            return self.pp_override
        if self.config.profit_protection_auto_volatility:
            return self._high_volatility
        return self.config.use_profit_protection

    @property
    def effective_trading_mode(self) -> str:
        """Get the active trading mode. GUI override > config."""
        if self.trading_mode_override is not None:
            return self.trading_mode_override
        return self.config.trading_mode

    def _update_volatility_state(self, df):
        """Update high-volatility flag from recent ATR data."""
        if df is None or 'ATR' not in df.columns or len(df) < 100:
            return
        atr_vals = df['ATR'].values
        current_atr = atr_vals[-1]
        atr_80th = float(np.percentile(atr_vals[-100:], 80))
        was_high = self._high_volatility
        self._high_volatility = current_atr > atr_80th
        if self._high_volatility != was_high:
            state = "HIGH" if self._high_volatility else "NORMAL"
            self.logger.info(
                f"[VOLATILITY] {state} -- ATR ${current_atr:.2f} "
                f"(80th pctl: ${atr_80th:.2f}) -- "
                f"PP {'ACTIVE' if self.is_profit_protection_active() else 'INACTIVE'}"
            )

    @staticmethod
    def _make_drawdown_limit_fn(strategy: TradingStrategy, config: TradingConfig):
        """Create the appropriate drawdown limit function for the strategy."""
        from src.core.position import get_m5_drawdown_limit, get_m1_drawdown_limit

        if strategy.bot_label == "M5":
            base = config.profit_protection_drawdown_limit_pct
            return lambda minutes: get_m5_drawdown_limit(minutes, base)
        else:
            return None

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

    # ── Candle detection ────────────────────────────────────────────────

    def has_new_candle(self) -> tuple[bool, object]:
        rates = self.mt5.get_historical_data(
            timeframe=self.strategy.mt5_timeframe, bars=1
        )
        if rates is None or len(rates) == 0:
            return False, None

        candle_time = rates.iloc[0]['time']

        if self.last_processed_candle is None:
            self.last_processed_candle = candle_time
            return True, candle_time

        if candle_time > self.last_processed_candle:
            self.last_processed_candle = candle_time
            return True, candle_time

        return False, candle_time

    # ── Position opening ────────────────────────────────────────────────

    def open_position(self, direction: str, df: pd.DataFrame):
        """Open a position in the given direction using adaptive ATR stops."""
        tick = self.mt5.get_tick()
        if tick is None:
            return

        current_price = tick.bid if direction == 'LONG' else tick.ask

        # Use breakout-specific SL multiplier if configured, else adaptive ATR
        if self.config.breakout_sl_atr_mult > 0 and self.config.bot_type == "breakout":
            stop_distance = df.iloc[-1]['ATR'] * self.config.breakout_sl_atr_mult
        else:
            adaptive_mult = get_adaptive_atr_multiplier(
                df, self.config.atr_multiplier, self.config.atr_high_volatility_multiplier
            )
            stop_distance = df.iloc[-1]['ATR'] * adaptive_mult

        # Tighten stop loss after consecutive SL exits
        if self.consecutive_sl_exits > 0 and self.config.sl_tightening_factor < 1.0:
            factor = self.config.sl_tightening_factor ** self.consecutive_sl_exits
            stop_distance *= factor
            self.logger.info(
                f"[SL TIGHTENING] {self.consecutive_sl_exits} consecutive SL exits, "
                f"stop distance x{factor:.2f}"
            )

        if direction == 'LONG':
            sl = current_price - stop_distance
            tp = current_price + (current_price * self.config.profit_target_pct)
            order_type = ORDER_TYPE_BUY
        else:
            sl = current_price + stop_distance
            tp = current_price - (current_price * self.config.profit_target_pct)
            order_type = ORDER_TYPE_SELL

        info = self.mt5.get_account_info()
        if not info:
            return

        # Use risk-based sizing when configured
        if self.config.sizing_mode == "risk_pct":
            risk_amount = info['balance'] * self.config.risk_per_trade_pct
            volume = self.mt5.calculate_lot_size_from_risk(risk_amount, stop_distance)
        elif self.config.sizing_mode == "fixed":
            volume = self.config.fixed_lots
        else:
            volume = self.mt5.calculate_lot_size(
                info['balance'], self.config.per_position_size_pct,
                self.config.leverage, current_price,
            )
        if not volume:
            return

        self.logger.info(f"Placing {direction} order: Volume={volume}, SL={sl:.2f}, TP={tp:.2f}")

        result = self.mt5.place_order(
            order_type, volume, sl, tp,
            self.strategy.magic_number,
            self.strategy.order_comment,
        )

        if result:
            ticket = result.order
            price = tick.ask if direction == 'LONG' else tick.bid
            sl_dist = abs(price - sl)
            tp_dist = abs(tp - price)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0

            self.positions.register_open(ticket)
            self.trade_log.append({
                'action': 'OPEN', 'time': get_local_now(),
                'type': direction, 'entry_price': price,
                'sl': sl, 'tp': tp, 'volume': volume, 'order_id': ticket,
            })
            self.trades_today += 1

            self.logger.info(f">>> TRADE OPENED [{direction}]")
            self.logger.info(f"  Entry: ${price:.2f}, SL: ${sl:.2f} (${sl_dist:.2f}), "
                        f"TP: ${tp:.2f} (${tp_dist:.2f}), R:R 1:{rr:.2f}, "
                        f"Volume: {volume}, Ticket: {ticket}")

    # ── Position closing ────────────────────────────────────────────────

    def close_position(self, position, reason: str, emergency: bool = False):
        """Close a position and record the result."""
        ticket = position.ticket
        comment = f"{self.strategy.bot_label.lower()}_{'emergency' if emergency else 'close'}"

        result = self.mt5.close_position(position, self.strategy.magic_number, comment)
        if not result:
            return

        profit = position.profit
        entry = position.price_open
        tick = self.mt5.get_tick()
        exit_price = tick.bid if position.type == ORDER_TYPE_BUY else tick.ask
        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"
        price_change = (exit_price - entry) if position.type == ORDER_TYPE_BUY else (entry - exit_price)
        pct = (price_change / entry) * 100

        # Update risk tracking
        self.risk.record_trade_result(profit)
        if profit < 0:
            self.last_trade_profitable = False
        else:
            self.last_trade_profitable = True

        # Bot-initiated close resets consecutive SL counter
        self.consecutive_sl_exits = 0

        # Log
        self.trade_log.append({
            'action': 'CLOSE', 'time': get_local_now(), 'exit_time': get_local_now(),
            'type': direction, 'entry_price': entry, 'exit_price': exit_price,
            'profit': profit, 'price_change_pct': pct, 'ticket': ticket,
            'emergency': emergency, 'exit_reason': reason,
        })

        self.positions.save_exit(ticket, reason)
        self.positions.register_close(ticket)

        label = "EMERGENCY CLOSE" if emergency else "TRADE CLOSED"
        self.logger.info(f"<<< {label} [{direction}] -- {reason}")
        self.logger.info(f"  Entry: ${entry:.2f} -> Exit: ${exit_price:.2f}, "
                     f"Change: ${price_change:.2f} ({pct:+.3f}%), P/L: ${profit:.2f}")
        if self.risk.consecutive_losses > 0:
            self.logger.info(f"  Consecutive losses: {self.risk.consecutive_losses}")

        self.last_close_time = get_local_now()
        self.last_close_position_type = direction

    # ── Cooldown / backoff ──────────────────────────────────────────────

    def can_enter_new_position(self, df: pd.DataFrame | None = None) -> bool:
        """Check if cooldown/backoff allows a new entry."""
        if self.last_close_time is None:
            return True

        time_since_close = (get_local_now() - self.last_close_time).total_seconds()
        tf_seconds = self.strategy.timeframe_minutes * 60

        # Simple reentry cooldown (independent of loss backoff, applies to all closes)
        if self.config.reentry_cooldown_bars > 0:
            cooldown = self.config.reentry_cooldown_bars * tf_seconds
            if time_since_close < cooldown:
                remaining = (cooldown - time_since_close) / 60
                self.logger.info(
                    f"Reentry cooldown: {remaining:.1f}min remaining "
                    f"({self.config.reentry_cooldown_bars} bars)"
                )
                return False

        # Log backoff state for live debugging
        if self.config.use_loss_backoff:
            sl_mode = self.config.loss_backoff_sl_only
            loss_count = self.consecutive_sl_exits if sl_mode else self.risk.consecutive_losses
            self.logger.info(
                f"[BACKOFF STATE] {'sl_exits' if sl_mode else 'consecutive_losses'}={loss_count}, "
                f"time_since_close={time_since_close:.0f}s, "
                f"last_close={self.last_close_time.strftime('%H:%M:%S')}"
            )

        # Loss backoff
        if self.config.use_loss_backoff:
            if self.config.loss_backoff_sl_only:
                # SL-only flat backoff
                if self.consecutive_sl_exits >= self.config.loss_backoff_sl_threshold:
                    cooldown = self.config.loss_backoff_sl_candles * tf_seconds
                    if time_since_close < cooldown:
                        remaining = (cooldown - time_since_close) / 60
                        self.logger.info(
                            f"SL backoff: {remaining:.1f}min remaining "
                            f"(after {self.consecutive_sl_exits} SL exits, "
                            f"{self.config.loss_backoff_sl_candles} candle cooldown)"
                        )
                        return False
            elif self.risk.consecutive_losses > 0:
                # Original exponential backoff on any loss
                multipliers = self.config.loss_backoff_multipliers
                idx = min(self.risk.consecutive_losses - 1, len(multipliers) - 1)
                backoff = multipliers[idx]
                cooldown = self.warmup_candles * tf_seconds * backoff

                if time_since_close < cooldown:
                    remaining = (cooldown - time_since_close) / 60
                    self.logger.info(
                        f"Loss backoff: {remaining:.1f}min remaining "
                        f"(after {self.risk.consecutive_losses} losses, {backoff}x multiplier)"
                    )
                    return False
                return True

        # Standard cooldown
        cooldown = self.warmup_candles * tf_seconds

        if time_since_close < cooldown:
            # M1 smart cooldown check
            if hasattr(self.strategy, 'should_skip_cooldown') and df is not None:
                should_skip, skip_reason = self.strategy.should_skip_cooldown(
                    df, self.last_close_position_type
                )
                if should_skip:
                    self.logger.info(f"[SMART COOLDOWN SKIP] {skip_reason}")
                    return True

            # Skip cooldown after profitable trade (M1 only -- M5 always waits)
            if self.last_trade_profitable and hasattr(self.strategy, 'should_skip_cooldown'):
                self.logger.info("Skipping cooldown after profitable trade")
                return True

            remaining = (cooldown - time_since_close) / 60
            self.logger.info(f"Cooldown active: {remaining:.1f}min remaining")
            return False

        return True

    # ── Main trading logic (per candle) ─────────────────────────────────

    def trading_logic(self):
        """Run once per new candle."""
        info = self.mt5.get_account_info()
        if not info:
            self.logger.error("Failed to get account info")
            return

        # Safety checks
        if self.risk.run_all_checks(info['balance'], info['equity']):
            return

        # Weekend protection
        is_closing, close_reason = RiskManager.is_near_weekend_close(minutes_before=30)
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)

        if is_closing:
            if open_positions:
                self.logger.warning(f"WEEKEND CLOSE: {close_reason}")
                for pos in open_positions:
                    self.close_position(pos, f"Weekend protection -- {close_reason}")
            else:
                self.logger.info("Weekend close approaching -- no new positions")
            return

        # Get data + indicators
        df = self.mt5.get_historical_data(
            timeframe=self.strategy.mt5_timeframe, bars=500
        )
        if df is None or len(df) < 200:
            self.logger.error("Insufficient data")
            return

        # Market gap detection
        has_gap, gap_pct, time_gap = RiskManager.detect_market_gap(df)
        gap_warmup = False
        if has_gap:
            self.last_close_time = get_local_now()
            gap_warmup = True
            self.logger.warning(f"Market gap -- {self.warmup_candles} candle warmup")

        # Skip indicator computation if already present (pre-computed in backtest)
        if 'RSI' not in df.columns:
            df = compute_indicators(df, self.config)
        latest = df.iloc[-1]

        # Store for trailing stop ATR lookups
        self._last_df = df

        # Update breakout levels if strategy supports tick-based entry
        if hasattr(self.strategy, 'update_levels'):
            self.strategy.update_levels(df)

        # Update volatility state for auto-PP
        self._update_volatility_state(df)

        tick = self.mt5.get_tick()
        if tick is None:
            return
        current_price = tick.bid

        # Register existing positions
        for pos in open_positions:
            self.positions.register_existing(
                pos.ticket,
                self.mt5.mt5_timestamp_to_local(pos.time),
                pos.profit,
            )

        # ── Exit logic (run FIRST so a candle can exit + re-enter) ────
        for pos in open_positions:
            ticket = pos.ticket

            # Profit protection (candle-based, in addition to continuous)
            if self.is_profit_protection_active():
                should_exit, reason = self.positions.check_profit_protection(
                    ticket, pos.profit, info['balance']
                )
                if should_exit:
                    self.logger.info(f"EXIT SIGNAL (ticket {ticket}): {reason}")
                    self.close_position(pos, reason)
                    continue

            # Strategy-specific exit
            should_exit, reason = self.strategy.check_exit(df, pos, {
                'current_profit': pos.profit,
                'minutes_held': self.positions.get_minutes_held(ticket),
                'rsi_tracker': self.positions.rsi_confirmation_tracker,
            })
            if should_exit:
                self.logger.info(f"EXIT SIGNAL (ticket {ticket}): {reason}, P/L: ${pos.profit:.2f}")
                self.close_position(pos, reason)

        # ── Entry logic (after exits, so freed slots can be used) ───
        # Re-fetch positions after exits
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        if len(open_positions) < self.config.max_positions:
            if gap_warmup:
                self.logger.info("Gap warmup -- skipping new entries")
            elif self.can_enter_new_position(df):
                has_long = any(p.type == ORDER_TYPE_BUY for p in open_positions)
                has_short = any(p.type == ORDER_TYPE_SELL for p in open_positions)

                # Don't add a 2nd position if existing one(s) are underwater
                if open_positions and self.config.block_second_when_underwater:
                    any_underwater = any(p.profit < 0 for p in open_positions)
                    if any_underwater:
                        self.logger.info("Skipping 2nd entry -- existing position underwater")
                    else:
                        signal = self.strategy.check_entry(df, open_positions, {
                            'has_long': has_long,
                            'has_short': has_short,
                        })
                        if signal:
                            mode = self.effective_trading_mode
                            if mode == "long_only" and signal['direction'] == "SHORT":
                                self.logger.info("SHORT signal blocked -- trading mode: long_only")
                            elif mode == "short_only" and signal['direction'] == "LONG":
                                self.logger.info("LONG signal blocked -- trading mode: short_only")
                            else:
                                self.open_position(signal['direction'], df)
                else:
                    signal = self.strategy.check_entry(df, open_positions, {
                        'has_long': has_long,
                        'has_short': has_short,
                    })
                    if signal:
                        mode = self.effective_trading_mode
                        if mode == "long_only" and signal['direction'] == "SHORT":
                            self.logger.info("SHORT signal blocked -- trading mode: long_only")
                        elif mode == "short_only" and signal['direction'] == "LONG":
                            self.logger.info("LONG signal blocked -- trading mode: short_only")
                        else:
                            self.open_position(signal['direction'], df)

    # ── Trailing stop management (every second) ───────────────────────

    def check_breakout_fills(self):
        """Check if live price has crossed a breakout level (runs every second)."""
        if not hasattr(self.strategy, 'check_tick_entry'):
            return

        tick = self.mt5.get_tick()
        if tick is None:
            return

        positions = self.mt5.get_open_positions(self.strategy.magic_number)
        if len(positions) >= self.config.max_positions:
            return

        # Check cooldown
        if not self.can_enter_new_position():
            return

        has_long = any(p.type == ORDER_TYPE_BUY for p in positions)
        has_short = any(p.type == ORDER_TYPE_SELL for p in positions)

        # Check trading mode
        mode = self.effective_trading_mode

        signal = self.strategy.check_tick_entry(tick.bid, tick.ask, has_long, has_short)
        if signal and self._last_df is not None:
            direction = signal['direction']
            if mode == "long_only" and direction == "SHORT":
                return
            if mode == "short_only" and direction == "LONG":
                return
            self.open_position(direction, self._last_df)

    def _manage_trailing(self, positions, current_atr: float, tick):
        """
        Update trailing stop using live tick data.

        Supports two breakeven modes:
        - "first_pip": move SL to BE as soon as price moves in your direction
        - "atr_threshold": move SL to BE after profit > breakeven_atr_trigger * ATR

        After breakeven, trail at trail_atr_after_breakeven * ATR.
        Before breakeven, trail at trail_atr_before_breakeven * ATR (wider).
        """
        if current_atr < 0.5:
            return

        be_trigger = self.config.breakeven_atr_trigger
        be_mode = self.config.breakeven_mode

        for pos in positions:
            ticket = pos.ticket
            entry = pos.price_open
            current = tick.bid if pos.type == ORDER_TYPE_BUY else tick.ask

            if pos.type == ORDER_TYPE_BUY:
                move_atr = (current - entry) / current_atr
            else:
                move_atr = (entry - current) / current_atr

            # Stage 1: Move to breakeven
            if ticket not in self._breakeven_applied:
                should_apply_be = False

                if be_mode == "first_pip":
                    # Move to BE as soon as price is on the right side of entry
                    should_apply_be = move_atr > 0
                else:
                    # Standard: wait for profit to exceed threshold
                    should_apply_be = be_trigger > 0 and move_atr >= be_trigger

                if should_apply_be:
                    offset = current_atr * self.config.breakeven_offset
                    new_sl = entry + offset if pos.type == ORDER_TYPE_BUY else entry - offset
                    if hasattr(self.mt5, 'modify_sl'):
                        if self.mt5.modify_sl(ticket, new_sl):
                            self._breakeven_applied.add(ticket)
                            self.logger.info(
                                f"[BREAKEVEN] Ticket {ticket}: SL -> ${new_sl:.2f} "
                                f"(mode={be_mode})"
                            )

            # Stage 2: Trail
            if ticket in self._breakeven_applied:
                trail_distance = current_atr * self.config.trail_atr_after_breakeven
            else:
                trail_distance = current_atr * self.config.trail_atr_before_breakeven

            if pos.type == ORDER_TYPE_BUY:
                new_sl = current - trail_distance
                if new_sl > pos.sl:
                    if hasattr(self.mt5, 'modify_sl'):
                        self.mt5.modify_sl(ticket, new_sl)
            else:
                new_sl = current + trail_distance
                if new_sl < pos.sl:
                    if hasattr(self.mt5, 'modify_sl'):
                        self.mt5.modify_sl(ticket, new_sl)

    def manage_trailing_continuous(self):
        """Update trailing stop every second using live tick data."""
        # Only run if trailing is configured (breakeven_atr_trigger > 0 or first_pip mode)
        if self.config.breakeven_mode != "first_pip" and self.config.breakeven_atr_trigger <= 0:
            return

        tick = self.mt5.get_tick()
        if tick is None:
            return

        positions = self.mt5.get_open_positions(self.strategy.magic_number)
        if not positions:
            return

        # Use last known ATR from candle data
        current_atr = 0.0
        if self._last_df is not None and 'ATR' in self._last_df.columns:
            current_atr = float(self._last_df.iloc[-1]['ATR'])

        if current_atr < 0.5:
            return

        self._manage_trailing(positions, current_atr, tick)

    # ── Continuous checks (every second) ────────────────────────────────

    def check_profit_protection_continuous(self):
        """Check profit protection on all positions (runs every second)."""
        if not self.is_profit_protection_active():
            return

        info = self.mt5.get_account_info()
        if not info:
            return

        positions = self.mt5.get_open_positions(self.strategy.magic_number)
        for pos in positions:
            should_exit, reason = self.positions.check_profit_protection(
                pos.ticket, pos.profit, info['balance']
            )
            if should_exit:
                self.logger.info(f"EXIT SIGNAL (ticket {pos.ticket}): {reason}")
                self.close_position(pos, reason)

    def check_mt5_closed_positions(self):
        """Detect positions closed by MT5 (stop loss / take profit)."""
        current = self.mt5.get_open_positions(self.strategy.magic_number)
        current_tickets = {p.ticket for p in current}

        self.positions.tracked_positions.update(current_tickets)
        closed = self.positions.tracked_positions - current_tickets

        for ticket in closed:
            if ticket in self.positions.bot_closed_positions:
                self.positions.bot_closed_positions.discard(ticket)
                self.positions.tracked_positions.discard(ticket)
                continue

            deals = self.mt5.get_deal_history(ticket)
            if not deals:
                # MT5 deal history not available yet -- assume loss to be safe.
                # This prevents the bot from ignoring SL exits when MT5 is slow
                # to flush deal history.
                self.logger.warning(
                    f"[MT5 EXIT] Ticket {ticket}: No deal history found -- "
                    f"recording as unknown loss for backoff safety"
                )
                self.risk.record_trade_result(-1)  # Assume loss
                self.last_trade_profitable = False
                self.last_close_time = get_local_now()
                self.last_close_position_type = None
                self.positions.tracked_positions.discard(ticket)
                continue

            exit_deal = next(
                (d for d in deals if d.entry == DEAL_ENTRY_OUT), None
            )
            if not exit_deal:
                # Deals found but no exit deal -- same safety treatment
                self.logger.warning(
                    f"[MT5 EXIT] Ticket {ticket}: No exit deal in history -- "
                    f"recording as unknown loss for backoff safety"
                )
                self.risk.record_trade_result(-1)
                self.last_trade_profitable = False
                self.last_close_time = get_local_now()
                self.last_close_position_type = None
                self.positions.tracked_positions.discard(ticket)
                continue

            if exit_deal.reason == DEAL_REASON_SL:
                exit_reason = "Stop loss"
            elif exit_deal.reason == DEAL_REASON_TP:
                exit_reason = "Take profit"
            else:
                exit_reason = "MT5 close"

            profit = exit_deal.profit
            self.risk.record_trade_result(profit)
            self.last_trade_profitable = profit >= 0
            self.last_close_time = get_local_now()
            self.last_close_position_type = None

            # Track consecutive SL exits for stop tightening
            if exit_deal.reason == DEAL_REASON_SL:
                self.consecutive_sl_exits += 1
            else:
                self.consecutive_sl_exits = 0

            if profit < 0:
                self.logger.info(
                    f"[MT5 EXIT] Ticket {ticket}: {exit_reason} "
                    f"(${profit:.2f}) -- Consecutive losses: {self.risk.consecutive_losses}"
                )
            else:
                self.logger.info(f"[MT5 EXIT] Ticket {ticket}: {exit_reason} (${profit:.2f})")

            self.positions.save_exit(ticket, exit_reason)
            self.positions.tracked_positions.discard(ticket)

    # ── State snapshot for GUI ──────────────────────────────────────────

    def get_state(self) -> dict:
        """
        Return a complete state snapshot for the GUI.

        This is THE single source of truth. The GUI reads this dict and
        renders it -- no independent MT5 calls, no indicator computation,
        no log parsing. What the bot knows is what the GUI shows.
        """
        info = self.mt5.get_account_info()
        balance = info['balance'] if info else 0
        equity = info['equity'] if info else 0

        # Positions with full profit protection details
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        position_states = []
        for pos in open_positions:
            ticket = pos.ticket
            direction = "LONG" if pos.type == ORDER_TYPE_BUY else "SHORT"

            pos_state = self.positions.get_position_state(ticket, pos.profit, balance)
            pos_state.update({
                'direction': direction,
                'entry_price': pos.price_open,
                'current_price': pos.price_current,
                'sl': pos.sl,
                'tp': pos.tp,
                'volume': pos.volume,
                'profit': pos.profit,
            })
            position_states.append(pos_state)

        # Latest indicators
        indicators = {}
        try:
            df = self.mt5.get_historical_data(
                timeframe=self.strategy.mt5_timeframe, bars=100
            )
            if df is not None and len(df) > 50:
                from src.core.indicators import compute_indicators
                if 'RSI' not in df.columns:
                    df = compute_indicators(df, self.config)
                latest = df.iloc[-1]
                indicators = {
                    'rsi': float(latest['RSI']),
                    'atr': float(latest['ATR']),
                    'ema_fast': float(latest['ema_fast']),
                    'ema_slow': float(latest['ema_slow']),
                    'uptrend': bool(latest['uptrend']),
                    'downtrend': bool(latest['downtrend']),
                }
                # Strategy-specific state (e.g. breakout levels)
                if hasattr(self.strategy, 'get_strategy_state'):
                    indicators['strategy_state'] = self.strategy.get_strategy_state(df)
        except Exception:
            pass

        cooldown_info = self._get_cooldown_state()

        tick = self.mt5.get_tick()
        price = tick.bid if tick else 0

        return {
            'bot_label': self.strategy.bot_label,
            'status': 'Paused' if self.risk.trading_paused else 'Running',
            'pause_reason': self.risk.pause_reason,
            'balance': balance,
            'equity': equity,
            'price': price,
            'positions': position_states,
            'max_positions': self.config.max_positions,
            'indicators': indicators,
            'cooldown': cooldown_info,
            'consecutive_losses': self.risk.consecutive_losses,
            'trades_today': self.trades_today,
            'drawdown_pct': (
                (self.risk.peak_balance - balance) / self.risk.peak_balance * 100
                if self.risk.peak_balance and self.risk.peak_balance > 0 else 0
            ),
            'pp_active': self.is_profit_protection_active(),
            'pp_override': self.pp_override,
            'high_volatility': self._high_volatility,
            'trading_mode': self.effective_trading_mode,
            'rsi_buy': self.config.rsi_buy,
            'rsi_sell': self.config.rsi_sell,
            'rsi_exit_long': self.config.rsi_exit_long,
            'rsi_exit_short': self.config.rsi_exit_short,
        }

    def _get_cooldown_state(self) -> dict:
        """Get current cooldown/backoff state for GUI."""
        if self.last_close_time is None:
            return {'active': False, 'reason': 'Ready'}

        time_since = (get_local_now() - self.last_close_time).total_seconds()
        tf_seconds = self.strategy.timeframe_minutes * 60

        if self.config.use_loss_backoff and self.risk.consecutive_losses > 0:
            multipliers = self.config.loss_backoff_multipliers
            idx = min(self.risk.consecutive_losses - 1, len(multipliers) - 1)
            backoff = multipliers[idx]
            cooldown = self.warmup_candles * tf_seconds * backoff
            if time_since < cooldown:
                remaining = (cooldown - time_since) / 60
                return {
                    'active': True,
                    'reason': f'Loss backoff ({self.risk.consecutive_losses} losses, {backoff}x)',
                    'remaining_minutes': remaining,
                }

        cooldown = self.warmup_candles * tf_seconds
        if time_since < cooldown:
            # M1 skips cooldown after profitable trade; M5 does not
            if self.last_trade_profitable and hasattr(self.strategy, 'should_skip_cooldown'):
                return {'active': False, 'reason': 'Skipped (after win)'}
            remaining = (cooldown - time_since) / 60
            return {
                'active': True,
                'reason': 'Standard cooldown',
                'remaining_minutes': remaining,
            }

        return {'active': False, 'reason': 'Ready'}

    # ── Report ──────────────────────────────────────────────────────────

    def generate_report(self) -> str:
        closes = [t for t in self.trade_log if t['action'] == 'CLOSE']
        if not closes:
            return "No trades this session"

        total_profit = sum(t['profit'] for t in closes)
        wins = [t for t in closes if t['profit'] > 0]
        losses = [t for t in closes if t['profit'] < 0]
        hours = (get_local_now() - self.session_start).total_seconds() / 3600

        lines = [
            "=" * 80,
            f"{self.strategy.bot_label} BOT SESSION REPORT",
            "=" * 80,
            f"Duration: {hours:.1f}h | Trades: {len(closes)} | "
            f"Wins: {len(wins)} ({len(wins)/len(closes)*100:.0f}%) | "
            f"P/L: ${total_profit:.2f}",
        ]
        if wins:
            lines.append(f"Avg Win: ${sum(t['profit'] for t in wins)/len(wins):.2f}")
        if losses:
            lines.append(f"Avg Loss: ${sum(t['profit'] for t in losses)/len(losses):.2f}")
        lines.append("=" * 80)
        return "\n".join(lines)

    # ── Main loop ───────────────────────────────────────────────────────

    def run(self, check_interval: int = 1):
        """Main bot loop.

        The loop always ticks every 1 second so that profit protection and
        MT5-closed-position detection stay responsive.  Candle checks and
        the heavier trading_logic only run every *check_interval* seconds.
        """
        self.logger.info("=" * 80)
        self.logger.info(f"EGON {self.strategy.bot_label} BOT STARTED")
        self.logger.info("=" * 80)
        self.logger.info(f"Strategy: {self.config.strategy}")
        self.logger.info(f"Timeframe: M{self.strategy.timeframe_minutes}")
        self.logger.info(f"Check interval: {check_interval}s")
        self.logger.info(f"Active parameters:")
        self.logger.info(f"  position_size_pct={self.config.position_size_pct}, "
                         f"leverage={self.config.leverage}, "
                         f"max_positions={self.config.max_positions}")
        self.logger.info(f"  rsi_buy={self.config.rsi_buy}, "
                         f"rsi_sell={self.config.rsi_sell}, "
                         f"rsi_exit_long={self.config.rsi_exit_long}, "
                         f"rsi_exit_short={self.config.rsi_exit_short}")
        self.logger.info(f"  atr_multiplier={self.config.atr_multiplier}, "
                         f"profit_target_pct={self.config.profit_target_pct}")
        self.logger.info(f"  breakeven_atr_trigger={self.config.breakeven_atr_trigger}, "
                         f"trading_mode={self.config.trading_mode}")
        self.logger.info("=" * 80)

        if not self.connect():
            self.logger.error("Failed to connect to MT5")
            return

        last_status_time = time.time()
        last_candle_check = 0.0
        last_data_refresh = 0.0
        data_refresh_interval = self.config.data_refresh_interval_seconds

        try:
            while not self._stop_requested:
                try:
                    # Always run every second regardless of check_interval
                    self.check_breakout_fills()
                    self.manage_trailing_continuous()
                    self.check_profit_protection_continuous()
                    self.check_mt5_closed_positions()

                    now = time.time()
                    if now - last_candle_check >= check_interval:
                        last_candle_check = now

                        has_new, candle_time = self.has_new_candle()
                        if has_new:
                            self.logger.info(f"\n{'='*60}")
                            self.logger.info(f"NEW M{self.strategy.timeframe_minutes} CANDLE: {candle_time}")
                            self.logger.info(f"{'='*60}")

                            self.trading_logic()

                            info = self.mt5.get_account_info()
                            if info and self.risk.peak_balance:
                                dd = (self.risk.peak_balance - info['balance']) / self.risk.peak_balance * 100
                                self.logger.info(
                                    f"Status: Balance=${info['balance']:.2f}, "
                                    f"Equity=${info['equity']:.2f}, "
                                    f"DD={dd:.2f}%, Trades={self.trades_today}"
                                )
                            last_status_time = now
                        else:
                            if now - last_status_time >= 60:
                                df = self.mt5.get_historical_data(
                                    timeframe=self.strategy.mt5_timeframe, bars=10
                                )
                                if df is not None and len(df) > 0:
                                    latest = df.iloc[-1]
                                    age = (pd.Timestamp.now(tz=str(MT5_TZ)) - latest['time'].tz_localize(str(MT5_TZ))).total_seconds() / 60
                                    if age > 10:
                                        self.logger.info(f"[WAITING] Market closed -- last data {age:.0f}min ago")
                                    else:
                                        self.logger.info(f"[MONITORING] Price: {latest['close']:.2f}")
                                last_status_time = now

                    # Refresh indicator data periodically (for trailing ATR)
                    if now - last_data_refresh >= data_refresh_interval:
                        last_data_refresh = now
                        df = self.mt5.get_historical_data(
                            timeframe=self.strategy.mt5_timeframe, bars=500
                        )
                        if df is not None and len(df) >= 200:
                            if 'RSI' not in df.columns:
                                from src.core.indicators import compute_indicators
                                df = compute_indicators(df, self.config)
                            self._last_df = df

                    time.sleep(1)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"Error in trading loop: {e}", exc_info=True)
                    time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            self.logger.info("\n" + self.generate_report())
        finally:
            self.disconnect()
            self.logger.info("Bot shutdown complete")

