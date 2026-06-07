"""
ZoneBot -- limit order bot for liquidity zone strategy.

Different from BaseTradingBot in that it:
1. Maintains pending limit orders at detected zones
2. Checks for limit order fills each candle
3. Manages zone lifecycle (create, test, expire)
4. Uses the same risk management and profit protection infrastructure
"""

import logging
import time
from datetime import datetime

import numpy as np
import pandas as pd

from src.core.config import TradingConfig
from src.core.indicators import compute_indicators, get_adaptive_atr_multiplier
from src.core.broker import ORDER_TYPE_BUY, ORDER_TYPE_SELL
from src.core.position import PositionManager
from src.core.risk import RiskManager
from src.core.timezone import get_local_now, LOCAL_TZ, MT5_TZ
from src.strategy.liquidity_zones import LiquidityZoneStrategy, PendingOrder

logger = logging.getLogger(__name__)


class ZoneBot:
    """
    Trading bot that places limit orders at liquidity zones.

    Main loop:
    1. Every candle: update zones, manage pending orders
    2. Check if any pending orders would have filled (sim) or did fill (live)
    3. Manage open positions (profit protection, exits)
    4. Place new limit orders at fresh zones
    """

    def __init__(self, strategy: LiquidityZoneStrategy, config: TradingConfig, broker=None):
        self.strategy = strategy
        self.config = config

        if broker is not None:
            self.mt5 = broker
        else:
            from src.core.mt5_broker import MT5Broker
            self.mt5 = MT5Broker()

        self._shared_connection = False
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
            drawdown_limit_fn=None,
        )

        # Pending limit orders
        self.pending_orders: list[PendingOrder] = []
        self._next_order_id: int = 5000

        # Candle tracking
        self.last_processed_candle = None

        # Cooldown
        self.last_close_time: datetime | None = None
        self.warmup_candles: int = 1

        # Trade log
        self.trade_log: list[dict] = []
        self.trades_today: int = 0
        self.session_start: datetime = get_local_now()

        # Stop flag
        self._stop_requested: bool = False

        # PP override
        self.pp_override: bool | None = None
        self.trading_mode_override: str | None = None
        self._high_volatility: bool = False

        # Consecutive SL exits
        self.consecutive_sl_exits: int = 0

        # Breakeven and partial close tracking
        self._breakeven_applied: set[int] = set()
        self._partial_closed: set[int] = set()

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

    def is_profit_protection_active(self) -> bool:
        if self.pp_override is not None:
            return self.pp_override
        if self.config.profit_protection_auto_volatility:
            return self._high_volatility
        return self.config.use_profit_protection

    @property
    def effective_trading_mode(self) -> str:
        if self.trading_mode_override is not None:
            return self.trading_mode_override
        return self.config.trading_mode

    # ── Limit order management ──────────────────────────────────────

    def _place_pending_order(self, order_spec: dict, volume: float, current_time: datetime):
        """Create a pending limit order."""
        order_id = self._next_order_id
        self._next_order_id += 1

        order = PendingOrder(
            ticket=order_id,
            direction=order_spec['direction'],
            entry_price=order_spec['entry_price'],
            sl=order_spec['sl'],
            tp=order_spec['tp'],
            zone=order_spec['zone'],
            placed_at=current_time,
            volume=volume,
        )
        self.pending_orders.append(order)

        self.logger.info(
            f"[LIMIT ORDER] {order.direction} @ ${order.entry_price:.2f} "
            f"(SL ${order.sl:.2f}, TP ${order.tp:.2f}) -- "
            f"Zone: {order.zone.zone_type} [{order.zone.price_low:.2f}-{order.zone.price_high:.2f}] "
            f"strength={order.zone.strength:.2f}"
        )

    def _check_limit_fills(self, bar_high: float, bar_low: float):
        """Check if any pending orders would have filled on this candle."""
        for order in self.pending_orders:
            if order.filled or order.cancelled:
                continue

            # Don't fill if we're already at max positions
            current_positions = self.mt5.get_open_positions(self.strategy.magic_number)
            if len(current_positions) >= self.config.max_positions:
                break

            filled = False
            if order.direction == "LONG" and bar_low <= order.entry_price:
                filled = True
            elif order.direction == "SHORT" and bar_high >= order.entry_price:
                filled = True

            if filled:
                order.filled = True
                self._execute_limit_fill(order)

    def _execute_limit_fill(self, order: PendingOrder):
        """Execute a filled limit order -- open a position at the limit price."""
        order_type = ORDER_TYPE_BUY if order.direction == "LONG" else ORDER_TYPE_SELL

        # Use place_limit_order if available (SimBroker), otherwise fall back to place_order
        if hasattr(self.mt5, 'place_limit_order'):
            result = self.mt5.place_limit_order(
                order_type, order.volume, order.entry_price,
                order.sl, order.tp,
                self.strategy.magic_number, self.strategy.order_comment,
            )
        else:
            # Live MT5: place a market order (the limit was already managed by MT5)
            result = self.mt5.place_order(
                order_type, order.volume, order.sl, order.tp,
                self.strategy.magic_number, self.strategy.order_comment,
            )

        if result:
            ticket = result.order
            self.positions.register_open(ticket)
            self.trades_today += 1

            self.logger.info(
                f">>> LIMIT FILL [{order.direction}] @ ${order.entry_price:.2f} "
                f"(SL ${order.sl:.2f}, TP ${order.tp:.2f}, Vol {order.volume})"
            )
            self.trade_log.append({
                'action': 'OPEN', 'time': get_local_now(),
                'type': order.direction, 'entry_price': order.entry_price,
                'sl': order.sl, 'tp': order.tp, 'volume': order.volume,
                'order_id': ticket, 'zone_type': order.zone.zone_type,
            })

    def _cancel_stale_orders(self, current_time: datetime, current_price: float):
        """Cancel orders that are too old or too far from price."""
        max_age_minutes = getattr(self.config, 'zone_order_max_age_minutes', 120)
        current_atr = 1.0  # Will be updated from df

        for order in self.pending_orders:
            if order.filled or order.cancelled:
                continue

            # Cancel if too old
            age_minutes = (current_time - order.placed_at).total_seconds() / 60
            if age_minutes > max_age_minutes:
                order.cancelled = True
                self.logger.info(
                    f"[CANCEL] {order.direction} @ ${order.entry_price:.2f} "
                    f"-- expired ({age_minutes:.0f}min)"
                )
                continue

            # Cancel if price moved too far away (zone no longer relevant)
            distance = abs(current_price - order.entry_price)
            if distance > current_price * 0.02:  # > 2% away
                order.cancelled = True
                self.logger.info(
                    f"[CANCEL] {order.direction} @ ${order.entry_price:.2f} "
                    f"-- price moved away (${distance:.2f})"
                )

        # Clean up cancelled/filled orders
        self.pending_orders = [
            o for o in self.pending_orders
            if not o.cancelled and not o.filled
        ]

    # ── Breakeven + Partial close management ───────────────────────

    def _manage_open_positions(self, df, open_positions):
        """
        Manage breakeven stops and partial closes on open positions.

        Called every candle after fills are checked.
        """
        if not open_positions:
            return

        current_atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else 1.0

        for pos in open_positions:
            ticket = pos.ticket
            entry = pos.price_open
            current_price = pos.price_current

            # Calculate how far price has moved in our favor (in ATR units)
            if pos.type == ORDER_TYPE_BUY:
                move_atr = (current_price - entry) / current_atr if current_atr > 0 else 0
            else:
                move_atr = (entry - current_price) / current_atr if current_atr > 0 else 0

            # ── Breakeven stop ──────────────────────────────────────
            be_trigger = self.config.breakeven_atr_trigger
            if be_trigger > 0 and move_atr >= be_trigger:
                # Only move SL if it hasn't been moved to BE yet
                if ticket not in self._breakeven_applied:
                    offset = current_atr * self.config.breakeven_offset
                    if pos.type == ORDER_TYPE_BUY:
                        new_sl = entry + offset
                        # Only move if new SL is better (higher) than current
                        if new_sl > pos.sl:
                            success = self.mt5.modify_sl(ticket, new_sl)
                            if success:
                                self._breakeven_applied.add(ticket)
                                self.logger.info(
                                    f"[BREAKEVEN] Ticket {ticket}: SL moved to ${new_sl:.2f} "
                                    f"(entry ${entry:.2f} + ${offset:.2f} offset)"
                                )
                    else:
                        new_sl = entry - offset
                        if new_sl < pos.sl:
                            success = self.mt5.modify_sl(ticket, new_sl)
                            if success:
                                self._breakeven_applied.add(ticket)
                                self.logger.info(
                                    f"[BREAKEVEN] Ticket {ticket}: SL moved to ${new_sl:.2f} "
                                    f"(entry ${entry:.2f} - ${offset:.2f} offset)"
                                )

            # ── Partial close ───────────────────────────────────────
            if self.config.partial_close_enabled:
                pc_target = self.config.partial_close_atr_target
                if move_atr >= pc_target and ticket not in self._partial_closed:
                    close_vol = round(pos.volume * self.config.partial_close_fraction / 0.01) * 0.01
                    if close_vol >= 0.01:
                        result = self.mt5.partial_close(
                            pos, close_vol, self.strategy.magic_number, "lz_partial"
                        )
                        if result:
                            self._partial_closed.add(ticket)
                            self.logger.info(
                                f"[PARTIAL CLOSE] Ticket {ticket}: closed {close_vol} lots "
                                f"at {move_atr:.1f} ATR profit (keeping {pos.volume - close_vol:.2f})"
                            )

    # ── Position closing ────────────────────────────────────────────────

    def close_position(self, position, reason: str, emergency: bool = False):
        """Close a position and record the result."""
        ticket = position.ticket
        comment = f"lz_{'emergency' if emergency else 'close'}"

        result = self.mt5.close_position(position, self.strategy.magic_number, comment)
        if not result:
            return

        profit = position.profit
        entry = position.price_open
        tick = self.mt5.get_tick()
        exit_price = tick.bid if position.type == ORDER_TYPE_BUY else tick.ask
        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"

        self.risk.record_trade_result(profit)
        self.consecutive_sl_exits = 0

        self.trade_log.append({
            'action': 'CLOSE', 'time': get_local_now(),
            'type': direction, 'entry_price': entry, 'exit_price': exit_price,
            'profit': profit, 'ticket': ticket, 'exit_reason': reason,
        })

        self.positions.save_exit(ticket, reason)
        self.positions.register_close(ticket)

        # Clean up breakeven/partial close tracking
        self._breakeven_applied.discard(ticket)
        self._partial_closed.discard(ticket)

        self.logger.info(f"<<< CLOSED [{direction}] -- {reason}, P/L: ${profit:.2f}")
        self.last_close_time = get_local_now()

    # ── MT5 close detection ─────────────────────────────────────────

    def check_mt5_closed_positions(self):
        """Detect positions closed by MT5 (SL/TP)."""
        from src.core.broker import DEAL_ENTRY_OUT, DEAL_REASON_SL, DEAL_REASON_TP

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
                self.risk.record_trade_result(-1)
                self.last_close_time = get_local_now()
                self.positions.tracked_positions.discard(ticket)
                continue

            exit_deal = next((d for d in deals if d.entry == DEAL_ENTRY_OUT), None)
            if not exit_deal:
                self.risk.record_trade_result(-1)
                self.last_close_time = get_local_now()
                self.positions.tracked_positions.discard(ticket)
                continue

            profit = exit_deal.profit
            self.risk.record_trade_result(profit)
            self.last_close_time = get_local_now()

            if exit_deal.reason == DEAL_REASON_SL:
                self.consecutive_sl_exits += 1
                self.logger.info(f"[MT5 EXIT] Ticket {ticket}: Stop loss (${profit:.2f})")
            elif exit_deal.reason == DEAL_REASON_TP:
                self.consecutive_sl_exits = 0
                self.logger.info(f"[MT5 EXIT] Ticket {ticket}: Take profit (${profit:.2f})")
            else:
                self.consecutive_sl_exits = 0
                self.logger.info(f"[MT5 EXIT] Ticket {ticket}: MT5 close (${profit:.2f})")

            self.positions.save_exit(ticket, "Stop loss" if exit_deal.reason == DEAL_REASON_SL else "Take profit")
            self.positions.tracked_positions.discard(ticket)

    # ── Main trading logic ──────────────────────────────────────────

    def trading_logic(self):
        """Run once per new candle."""
        info = self.mt5.get_account_info()
        if not info:
            return

        if self.risk.run_all_checks(info['balance'], info['equity']):
            return

        # Weekend protection
        is_closing, close_reason = RiskManager.is_near_weekend_close(minutes_before=30)
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)

        if is_closing:
            for pos in open_positions:
                self.close_position(pos, f"Weekend protection -- {close_reason}")
            self.pending_orders.clear()
            return

        # Get data
        df = self.mt5.get_historical_data(timeframe=self.strategy.mt5_timeframe, bars=500)
        if df is None or len(df) < 200:
            return

        if 'RSI' not in df.columns:
            df = compute_indicators(df, self.config)

        latest = df.iloc[-1]
        current_time = get_local_now()
        current_price = latest['close']

        # Update volatility state
        if 'ATR' in df.columns and len(df) >= 100:
            atr_vals = df['ATR'].values
            current_atr = atr_vals[-1]
            atr_80th = float(np.percentile(atr_vals[-100:], 80))
            self._high_volatility = current_atr > atr_80th

        # Register existing positions
        for pos in open_positions:
            self.positions.register_existing(
                pos.ticket,
                self.mt5.mt5_timestamp_to_local(pos.time),
                pos.profit,
            )

        # ── Check limit order fills ─────────────────────────────────
        bar_high = latest['high']
        bar_low = latest['low']
        self._check_limit_fills(bar_high, bar_low)

        # ── Manage open positions (breakeven, partial close) ────────
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        self._manage_open_positions(df, open_positions)

        # ── Exit logic ──────────────────────────────────────────────
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        for pos in open_positions:
            ticket = pos.ticket

            # Profit protection
            if self.is_profit_protection_active():
                should_exit, reason = self.positions.check_profit_protection(
                    ticket, pos.profit, info['balance']
                )
                if should_exit:
                    self.close_position(pos, reason)
                    continue

            # Strategy exit
            should_exit, reason = self.strategy.check_exit(df, pos, {
                'current_profit': pos.profit,
                'minutes_held': self.positions.get_minutes_held(ticket),
            })
            if should_exit:
                self.close_position(pos, reason)

        # ── Zone update + order placement ───────────────────────────
        self.strategy.update_zones(df, current_time)
        self._cancel_stale_orders(current_time, current_price)

        # Place new limit orders
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        order_specs = self.strategy.get_pending_orders(
            df, open_positions, current_time, info['balance'], current_price
        )

        for spec in order_specs:
            volume = self.mt5.calculate_lot_size(
                info['balance'], self.config.per_position_size_pct,
                self.config.leverage, current_price,
            )
            if volume:
                self._place_pending_order(spec, volume, current_time)

    # ── Continuous checks ───────────────────────────────────────────

    def check_profit_protection_continuous(self):
        """Check profit protection on all positions."""
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
                self.close_position(pos, reason)

    # ── State for GUI ───────────────────────────────────────────────

    def get_state(self) -> dict:
        """State snapshot for GUI."""
        info = self.mt5.get_account_info()
        balance = info['balance'] if info else 0
        equity = info['equity'] if info else 0

        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        position_states = []
        for pos in open_positions:
            pos_state = self.positions.get_position_state(pos.ticket, pos.profit, balance)
            direction = "LONG" if pos.type == ORDER_TYPE_BUY else "SHORT"
            pos_state.update({
                'direction': direction,
                'entry_price': pos.price_open,
                'current_price': pos.price_current,
                'sl': pos.sl, 'tp': pos.tp,
                'volume': pos.volume, 'profit': pos.profit,
            })
            position_states.append(pos_state)

        pending = [
            {'direction': o.direction, 'price': o.entry_price,
             'zone_type': o.zone.zone_type, 'strength': o.zone.strength}
            for o in self.pending_orders if not o.filled and not o.cancelled
        ]

        tick = self.mt5.get_tick()
        price = tick.bid if tick else 0

        return {
            'bot_label': self.strategy.bot_label,
            'status': 'Paused' if self.risk.trading_paused else 'Running',
            'pause_reason': self.risk.pause_reason,
            'balance': balance, 'equity': equity, 'price': price,
            'positions': position_states,
            'pending_orders': pending,
            'active_zones': len(self.strategy.active_zones),
            'max_positions': self.config.max_positions,
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
        }

    # ── Main loop ───────────────────────────────────────────────────

    def run(self, check_interval: int = 1):
        """Main bot loop."""
        self.logger.info("=" * 80)
        self.logger.info("EGON LIQUIDITY ZONE BOT STARTED")
        self.logger.info(f"Active parameters:")
        self.logger.info(f"  zone_rr_ratio={self.config.zone_rr_ratio}, "
                         f"zone_min_strength={self.config.zone_min_strength}, "
                         f"zone_max_distance_atr={self.config.zone_max_distance_atr}")
        self.logger.info(f"  leverage={self.config.leverage}, "
                         f"position_size_pct={self.config.position_size_pct}, "
                         f"max_positions={self.config.max_positions}")
        self.logger.info(f"Timeframe: M{self.strategy.timeframe_minutes}")
        self.logger.info(f"Check interval: {check_interval}s")
        self.logger.info("=" * 80)

        if not self.connect():
            self.logger.error("Failed to connect to MT5")
            return

        last_candle_check = 0.0

        try:
            while not self._stop_requested:
                try:
                    self.check_profit_protection_continuous()
                    self.check_mt5_closed_positions()

                    now = time.time()
                    if now - last_candle_check >= check_interval:
                        last_candle_check = now

                        rates = self.mt5.get_historical_data(
                            timeframe=self.strategy.mt5_timeframe, bars=1
                        )
                        if rates is not None and len(rates) > 0:
                            candle_time = rates.iloc[0]['time']
                            if self.last_processed_candle is None or candle_time > self.last_processed_candle:
                                self.last_processed_candle = candle_time
                                self.trading_logic()

                    time.sleep(1)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"Error in trading loop: {e}", exc_info=True)
                    time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        finally:
            self.disconnect()
            self.logger.info("Bot shutdown complete")
