"""
SniperBot -- configurable RSI scalping with limit order pre-placement.

Each candle cycle:
1. Cancel previous sniper orders
2. Calculate RSI trigger prices
3. Place limit orders at those levels
4. Monitor for fills between candles
5. On candle close: if no fill, check RSI normally (market order fallback)

Fully configurable via TradingConfig: timeframe, RSI levels, sniper offsets,
trailing distances, TP calculation, position sizing -- all from JSON config.
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
from src.core.scheduler import Scheduler
from src.core.volatility_guard import VolatilityGuard
from src.strategy.sniper import SniperStrategy, SniperOrder

logger = logging.getLogger(__name__)


class SniperBot:
    """
    RSI bot with limit order pre-placement for better entries.

    All constants are configurable via TradingConfig. Create different
    JSON configs to run M1, M5, M15 or any other timeframe variant.
    """

    def __init__(self, strategy: SniperStrategy, config: TradingConfig, broker=None):
        self.strategy = strategy
        self.config = config

        if broker is not None:
            self.mt5 = broker
        else:
            from src.core.mt5_broker import MT5Broker
            self.mt5 = MT5Broker(symbol=config.symbol)

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

        # State
        self.last_processed_candle = None
        self.last_close_time: datetime | None = None
        self.last_trade_profitable: bool = False
        self.warmup_candles: int = 2
        self.consecutive_sl_exits: int = 0

        # Trade tracking
        self.trade_log: list[dict] = []
        self.trades_today: int = 0
        self.session_start: datetime = get_local_now()

        # Control
        self._stop_requested: bool = False
        self.pp_override: bool | None = None
        self.trading_mode_override: str | None = None
        self._high_volatility: bool = False

        # Breakeven tracking
        self._breakeven_applied: set[int] = set()
        self._partial_closed: set[int] = set()

        # Sniper state
        self._sniper_active: bool = False
        self._last_df: pd.DataFrame | None = None

        # Scheduler (time-based pause)
        self.scheduler = Scheduler(
            config=config,
            bot_label=strategy.bot_label,
        )

        # Volatility guard (ATR spike pause)
        self.volatility_guard = VolatilityGuard(
            config=config,
            bot_label=strategy.bot_label,
        )

    # ── Properties ──────────────────────────────────────────────────

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

    # ── Connection ──────────────────────────────────────────────────

    def connect(self) -> bool:
        if not self.mt5.connect():
            return False
        info = self.mt5.get_account_info()
        if info:
            self.risk.initialize(info['balance'])
        # Pre-load candle data so trailing stop works immediately
        df = self.mt5.get_historical_data(timeframe=self.strategy.mt5_timeframe, bars=500)
        if df is not None and len(df) >= 200:
            self._last_df = compute_indicators(df, self.config)
        return True

    def disconnect(self):
        if self._shared_connection:
            self.logger.info("Skipping disconnect (shared MT5 connection)")
            return
        self.mt5.disconnect()

    # ── Position sizing ─────────────────────────────────────────────

    def calculate_volume(self, balance: float, current_price: float,
                         stop_distance: float, df: pd.DataFrame | None = None) -> float | None:
        """
        Calculate lot size based on the configured sizing mode.

        Modes:
        - legacy: position_size_pct * leverage / price (old behavior)
        - fixed: use fixed_lots directly
        - risk_pct: risk X% of account, SL distance determines size
        - atr_adaptive: risk_pct scaled down when ATR is elevated
        """
        mode = self.config.sizing_mode

        if mode == "fixed":
            return self.config.fixed_lots

        if mode == "risk_pct" or mode == "atr_adaptive":
            risk_pct = self.config.risk_per_trade_pct

            # ATR-adaptive: reduce risk when volatility is above median
            if mode == "atr_adaptive" and df is not None and 'ATR' in df.columns:
                atr_vals = df['ATR'].values
                if len(atr_vals) >= 50:
                    current_atr = float(atr_vals[-1])
                    median_atr = float(np.median(atr_vals[-100:]))
                    if current_atr > median_atr and median_atr > 0:
                        damping = self.config.atr_damping
                        scale = (median_atr / current_atr) ** damping
                        risk_pct = risk_pct * scale
                        self.logger.info(
                            f"[SIZING] ATR adaptive: {current_atr:.2f} > median {median_atr:.2f}, "
                            f"risk scaled to {risk_pct*100:.3f}%"
                        )

            # risk_amount / (stop_distance_per_unit * contract_size) = lots
            risk_amount = balance * risk_pct
            if stop_distance <= 0:
                self.logger.warning("[SIZING] Stop distance <= 0, cannot calculate lot size")
                return None

            # For XAUUSD: 1 lot = 100 oz, price move of $1 = $100 per lot
            # Generic: use broker's contract size info
            # Delegate to broker for contract size awareness
            return self.mt5.calculate_lot_size_from_risk(
                risk_amount, stop_distance
            ) if hasattr(self.mt5, 'calculate_lot_size_from_risk') else (
                # Fallback: assume 100 oz contract size for gold
                self._calculate_lots_fallback(risk_amount, stop_distance)
            )

        # Legacy mode (default)
        return self.mt5.calculate_lot_size(
            balance, self.config.per_position_size_pct,
            self.config.leverage, current_price,
        )

    def _calculate_lots_fallback(self, risk_amount: float, stop_distance: float) -> float:
        """Fallback lot calculation when broker doesn't support risk-based sizing."""
        # XAUUSD: 1 lot = 100 oz, so $1 move = $100/lot
        contract_size = 100.0
        lots = risk_amount / (stop_distance * contract_size)
        # Round to 0.01 step
        lots = round(lots / 0.01) * 0.01
        return max(0.01, lots)

    # ── Position management ─────────────────────────────────────────

    def open_position(self, direction: str, df: pd.DataFrame, entry_price: float | None = None):
        """Open a position. If entry_price is given, use limit fill (no spread)."""
        tick = self.mt5.get_tick()
        if tick is None:
            return

        current_price = tick.bid if direction == 'LONG' else tick.ask
        adaptive_mult = get_adaptive_atr_multiplier(
            df, self.config.atr_multiplier, self.config.atr_high_volatility_multiplier
        )
        stop_distance = df.iloc[-1]['ATR'] * adaptive_mult

        # Calculate TP using RSI level prediction (spike catcher)
        from src.core.rsi_levels import calculate_rsi_sell_price, calculate_rsi_buy_price
        tp_rsi = self.strategy.get_tp_rsi(df, direction)

        if direction == 'LONG':
            fill_price = entry_price or current_price
            sl = fill_price - stop_distance
            tp = calculate_rsi_sell_price(df, tp_rsi, self.config.rsi_period)
            if tp is None or tp <= fill_price:
                tp = fill_price + df.iloc[-1]['ATR'] * self.config.tp_fallback_atr_mult
            order_type = ORDER_TYPE_BUY
        else:
            fill_price = entry_price or current_price
            sl = fill_price + stop_distance
            tp = calculate_rsi_buy_price(df, tp_rsi, self.config.rsi_period)
            if tp is None or tp >= fill_price:
                tp = fill_price - df.iloc[-1]['ATR'] * self.config.tp_fallback_atr_mult
            order_type = ORDER_TYPE_SELL

        self.logger.info(
            f"[TP CALC] {direction}: TP RSI target={tp_rsi:.1f}, TP=${tp:.2f}"
        )

        info = self.mt5.get_account_info()
        if not info:
            return

        volume = self.calculate_volume(info['balance'], current_price, stop_distance, df)
        if not volume:
            return

        # Use limit fill if we have a specific entry price and broker supports it
        if entry_price and hasattr(self.mt5, 'place_limit_order'):
            result = self.mt5.place_limit_order(
                order_type, volume, entry_price, sl, tp,
                self.strategy.magic_number, self.strategy.order_comment,
            )
        else:
            result = self.mt5.place_order(
                order_type, volume, sl, tp,
                self.strategy.magic_number, self.strategy.order_comment,
            )

        if result:
            ticket = result.order
            self.positions.register_open(ticket)
            self.trades_today += 1
            entry_type = "SNIPER" if entry_price else "MARKET"
            self.logger.info(
                f">>> [{entry_type}] {direction} @ ${fill_price:.2f} "
                f"(SL ${sl:.2f}, TP ${tp:.2f}, Vol {volume})"
            )

    def close_position(self, position, reason: str, emergency: bool = False):
        """Close a position."""
        ticket = position.ticket
        result = self.mt5.close_position(
            position, self.strategy.magic_number, self.strategy.order_comment
        )
        if not result:
            return

        profit = position.profit
        self.risk.record_trade_result(profit)
        self.last_trade_profitable = profit >= 0
        self.consecutive_sl_exits = 0

        self.positions.save_exit(ticket, reason)
        self.positions.register_close(ticket)
        self._breakeven_applied.discard(ticket)
        self._partial_closed.discard(ticket)

        direction = "LONG" if position.type == ORDER_TYPE_BUY else "SHORT"
        self.logger.info(f"<<< CLOSED [{direction}] -- {reason}, P/L: ${profit:.2f}")
        self.last_close_time = get_local_now()

    # ── MT5 close detection ─────────────────────────────────────────

    def check_mt5_closed_positions(self):
        """Detect SL/TP closes."""
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
            self.last_trade_profitable = profit >= 0

            if exit_deal.reason == DEAL_REASON_SL:
                self.consecutive_sl_exits += 1
            else:
                self.consecutive_sl_exits = 0

            reason = "Stop loss" if exit_deal.reason == DEAL_REASON_SL else "Take profit"
            self.logger.info(f"[MT5 EXIT] Ticket {ticket}: {reason} (${profit:.2f})")
            self.positions.save_exit(ticket, reason)
            self.positions.tracked_positions.discard(ticket)
            self._breakeven_applied.discard(ticket)
            self._partial_closed.discard(ticket)

    # ── Breakeven & trailing management ─────────────────────────────

    def _manage_trailing(self, positions, current_atr: float, tick):
        """
        Update trailing stop using live tick data.

        Uses config values for trail distances:
        - trail_atr_after_breakeven: tighter trail once breakeven is applied
        - trail_atr_before_breakeven: wider trail before breakeven
        """
        be_trigger = self.config.breakeven_atr_trigger
        if current_atr < 0.5:
            return

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
                if be_trigger > 0 and move_atr >= be_trigger:
                    offset = current_atr * self.config.breakeven_offset
                    new_sl = entry + offset if pos.type == ORDER_TYPE_BUY else entry - offset
                    if hasattr(self.mt5, 'modify_sl'):
                        if self.mt5.modify_sl(ticket, new_sl):
                            self._breakeven_applied.add(ticket)
                            self.logger.info(f"[BREAKEVEN] Ticket {ticket}: SL -> ${new_sl:.2f}")

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

    # ── Main trading logic ──────────────────────────────────────────

    def trading_logic(self):
        """Run on each new candle."""
        info = self.mt5.get_account_info()
        if not info:
            return

        if self.risk.run_all_checks(info['balance'], info['equity']):
            return

        # Weekend protection
        is_closing, _ = RiskManager.is_near_weekend_close(minutes_before=30)
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        if is_closing:
            for pos in open_positions:
                self.close_position(pos, "Weekend protection")
            self.strategy.cancel_pending()
            return

        # Get data
        df = self.mt5.get_historical_data(timeframe=self.strategy.mt5_timeframe, bars=500)
        if df is None or len(df) < 200:
            return
        if 'RSI' not in df.columns:
            df = compute_indicators(df, self.config)

        self._last_df = df
        latest = df.iloc[-1]

        # Update volatility
        if 'ATR' in df.columns and len(df) >= 100:
            atr_vals = df['ATR'].values
            current_atr = float(atr_vals[-1])
            atr_80th = float(np.percentile(atr_vals[-100:], 80))
            self._high_volatility = current_atr > atr_80th

        # Register positions
        for pos in open_positions:
            self.positions.register_existing(
                pos.ticket, self.mt5.mt5_timestamp_to_local(pos.time), pos.profit
            )

        # ── Exit logic (always runs, regardless of schedule/guard) ──
        for pos in open_positions:
            if self.is_profit_protection_active():
                should_exit, reason = self.positions.check_profit_protection(
                    pos.ticket, pos.profit, info['balance']
                )
                if should_exit:
                    self.close_position(pos, reason)
                    continue

            should_exit, reason = self.strategy.check_exit(df, pos, {
                'current_profit': pos.profit,
                'minutes_held': self.positions.get_minutes_held(pos.ticket),
            })
            if should_exit:
                self.close_position(pos, reason)

        # ── Schedule check (blocks new entries only) ────────────────
        if not self.scheduler.check():
            self.strategy.cancel_pending()
            return

        # ── Volatility guard (blocks new entries only) ──────────────
        if 'ATR' in df.columns:
            if not self.volatility_guard.check(df['ATR'].values):
                self.strategy.cancel_pending()
                return

        # ── Entry logic ─────────────────────────────────────────────
        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        if len(open_positions) >= self.config.max_positions:
            self.strategy.cancel_pending()
            return

        # Cancel previous sniper orders
        self.strategy.cancel_pending()

        has_long = any(p.type == ORDER_TYPE_BUY for p in open_positions)
        has_short = any(p.type == ORDER_TYPE_SELL for p in open_positions)

        signal = self.strategy.check_entry(df, open_positions, {
            'has_long': has_long, 'has_short': has_short,
        })

        if signal:
            mode = self.effective_trading_mode
            if mode == "long_only" and signal['direction'] == "SHORT":
                pass
            elif mode == "short_only" and signal['direction'] == "LONG":
                pass
            else:
                self.open_position(signal['direction'], df)
                return  # Don't place sniper if we just entered

        # ── Place sniper orders for next candle ─────────────────────
        current_atr = float(latest['ATR']) if 'ATR' in df.columns else 0
        levels = self.strategy.calculate_sniper_levels(df)
        current_price = latest['close']

        if levels['buy_price'] and not has_long:
            mode = self.effective_trading_mode
            if mode != "short_only":
                adaptive_mult = get_adaptive_atr_multiplier(
                    df, self.config.atr_multiplier, self.config.atr_high_volatility_multiplier
                )
                stop_distance = current_atr * adaptive_mult
                entry = levels['buy_price']
                sl = entry - stop_distance

                from src.core.rsi_levels import calculate_rsi_sell_price
                exit_rsi = self.strategy.get_tp_rsi(df, 'LONG')
                tp = calculate_rsi_sell_price(df, exit_rsi, self.config.rsi_period)
                if tp is None or tp <= entry:
                    tp = entry + current_atr * self.config.tp_fallback_atr_mult

                self.strategy.pending_buy = SniperOrder(
                    direction="LONG", entry_price=entry, sl=sl, tp=tp,
                    placed_at=get_local_now(),
                )
                self.logger.info(
                    f"[SNIPER] Buy limit @ ${entry:.2f} "
                    f"(RSI target {self.config.rsi_buy - self.config.sniper_rsi_offset:.0f}, "
                    f"TP ${tp:.2f} at RSI {exit_rsi:.0f})"
                )

        if levels['sell_price'] and not has_short and self.config.enable_shorts:
            mode = self.effective_trading_mode
            if mode != "long_only":
                adaptive_mult = get_adaptive_atr_multiplier(
                    df, self.config.atr_multiplier, self.config.atr_high_volatility_multiplier
                )
                stop_distance = current_atr * adaptive_mult
                entry = levels['sell_price']
                sl = entry + stop_distance

                from src.core.rsi_levels import calculate_rsi_buy_price
                exit_rsi = self.strategy.get_tp_rsi(df, 'SHORT')
                tp = calculate_rsi_buy_price(df, exit_rsi, self.config.rsi_period)
                if tp is None or tp >= entry:
                    tp = entry - current_atr * self.config.tp_fallback_atr_mult

                self.strategy.pending_sell = SniperOrder(
                    direction="SHORT", entry_price=entry, sl=sl, tp=tp,
                    placed_at=get_local_now(),
                )
                self.logger.info(
                    f"[SNIPER] Sell limit @ ${entry:.2f} "
                    f"(RSI target {self.config.rsi_sell + self.config.sniper_rsi_offset:.0f}, "
                    f"TP ${tp:.2f} at RSI {exit_rsi:.0f})"
                )

    # ── Continuous checks (every second) ────────────────────────────

    def check_profit_protection_continuous(self):
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

    def manage_trailing_continuous(self):
        """Update trailing stop every second using live tick data."""
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

        self._manage_trailing(positions, current_atr, tick)

    def check_sniper_fills(self):
        """Check if current price has hit a sniper level (runs every second)."""
        tick = self.mt5.get_tick()
        if tick is None:
            return

        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        if len(open_positions) >= self.config.max_positions:
            return

        filled = self.strategy.check_sniper_fills(tick.bid, tick.ask)

        if filled and self._last_df is not None:
            self.open_position(filled.direction, self._last_df, entry_price=filled.entry_price)

    # ── State for GUI ───────────────────────────────────────────────

    def get_state(self) -> dict:
        info = self.mt5.get_account_info()
        balance = info['balance'] if info else 0
        equity = info['equity'] if info else 0

        open_positions = self.mt5.get_open_positions(self.strategy.magic_number)
        position_states = []
        for pos in open_positions:
            pos_state = self.positions.get_position_state(pos.ticket, pos.profit, balance)
            direction = "LONG" if pos.type == ORDER_TYPE_BUY else "SHORT"
            pos_state.update({
                'direction': direction, 'entry_price': pos.price_open,
                'current_price': pos.price_current, 'sl': pos.sl, 'tp': pos.tp,
                'volume': pos.volume, 'profit': pos.profit,
            })
            position_states.append(pos_state)

        indicators = {}
        try:
            df = self._last_df
            if df is not None and len(df) > 50:
                latest = df.iloc[-1]
                indicators = {
                    'rsi': float(latest['RSI']),
                    'atr': float(latest['ATR']),
                    'ema_fast': float(latest['ema_fast']),
                    'ema_slow': float(latest['ema_slow']),
                    'uptrend': bool(latest['uptrend']),
                    'downtrend': bool(latest['downtrend']),
                }
        except Exception:
            pass

        tick = self.mt5.get_tick()
        price = tick.bid if tick else 0

        # Sniper info
        sniper_info = {}
        if self.strategy.pending_buy:
            sniper_info['buy_level'] = self.strategy.pending_buy.entry_price
        if self.strategy.pending_sell:
            sniper_info['sell_level'] = self.strategy.pending_sell.entry_price

        return {
            'bot_label': self.strategy.bot_label,
            'config_name': self.config.config_name,
            'status': 'Paused' if self.risk.trading_paused else 'Running',
            'pause_reason': self.risk.pause_reason,
            'balance': balance, 'equity': equity, 'price': price,
            'positions': position_states,
            'max_positions': self.config.max_positions,
            'indicators': indicators,
            'cooldown': {'active': False, 'reason': 'Ready'},
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
            'sniper': sniper_info,
            'rsi_buy': self.config.rsi_buy,
            'rsi_sell': self.config.rsi_sell,
            'rsi_exit_long': self.config.rsi_exit_long,
            'rsi_exit_short': self.config.rsi_exit_short,
            'sizing_mode': self.config.sizing_mode,
            'timeframe': self.config.timeframe,
            'schedule': {
                'enabled': self.scheduler.is_enabled,
                'paused': self.scheduler.is_paused,
                'reason': self.scheduler.pause_reason,
                'next_resume': self.scheduler.get_next_resume(),
            },
            'volatility_guard': self.volatility_guard.get_status(),
        }

    # ── Main loop ───────────────────────────────────────────────────

    def run(self, check_interval: int = 1):
        self.logger.info("=" * 80)
        self.logger.info(f"EGON SNIPER BOT STARTED [{self.config.bot_label}]")
        self.logger.info(f"  Config: {self.config.config_name or self.config.strategy}")
        self.logger.info(f"  Timeframe: {self.config.timeframe}, Symbol: {self.config.symbol}")
        self.logger.info(f"  RSI: buy={self.config.rsi_buy}, sell={self.config.rsi_sell}, "
                         f"exit_long={self.config.rsi_exit_long}, exit_short={self.config.rsi_exit_short}")
        self.logger.info(f"  Sniper offset: {self.config.sniper_rsi_offset}, "
                         f"ATR mult: {self.config.atr_multiplier}")
        self.logger.info(f"  Sizing: {self.config.sizing_mode}, "
                         f"Breakeven: {self.config.breakeven_atr_trigger} ATR")
        self.logger.info(f"  Trail: {self.config.trail_atr_after_breakeven} ATR (after BE), "
                         f"{self.config.trail_atr_before_breakeven} ATR (before BE)")
        if self.scheduler.is_enabled:
            self.logger.info(
                f"  Schedule: Mon={self.config.schedule_mon}, Tue={self.config.schedule_tue}, "
                f"Fri={self.config.schedule_fri}"
            )
        if self.volatility_guard.is_enabled:
            self.logger.info(
                f"  Volatility Guard: spike={self.config.vg_atr_spike_multiplier}x, "
                f"resume={self.config.vg_resume_below_multiplier}x, "
                f"cooldown={self.config.vg_cooldown_minutes}min"
            )
        self.logger.info("=" * 80)

        if not self.connect():
            self.logger.error("Failed to connect to MT5")
            return

        last_candle_check = 0.0
        last_data_refresh = 0.0
        data_refresh_interval = self.config.data_refresh_interval_seconds

        try:
            while not self._stop_requested:
                try:
                    # Every second: check sniper fills, trailing stop, PP, SL/TP
                    self.check_sniper_fills()
                    self.manage_trailing_continuous()
                    self.check_profit_protection_continuous()
                    self.check_mt5_closed_positions()

                    now = time.time()

                    # Refresh indicator data periodically (for GUI display between candles)
                    if now - last_data_refresh >= data_refresh_interval:
                        last_data_refresh = now
                        df = self.mt5.get_historical_data(
                            timeframe=self.strategy.mt5_timeframe, bars=500
                        )
                        if df is not None and len(df) >= 200:
                            if 'RSI' not in df.columns:
                                df = compute_indicators(df, self.config)
                            self._last_df = df

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
                    self.logger.error(f"Error: {e}", exc_info=True)
                    time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        finally:
            self.disconnect()
