"""
M1 Scalping Strategy -- entry and exit logic only.

M1-specific features:
- RSI exit confirmation (2 consecutive candles)
- Smart cooldown (skip cooldown on genuine reversals, 3/4 conditions)
- Entry signal confirmation counter (0->1 positions only)
- Configurable time-based drawdown tightening
"""

import logging

import pandas as pd

from src.core.config import TradingConfig
from src.core.mt5_client import ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M1

logger = logging.getLogger(__name__)


class M1ScalpingStrategy:
    """M1 scalping: tight RSI bands, fast entries, confirmed exits."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.entry_signal_count = {'LONG': 0, 'SHORT': 0}
        self.logger = logging.getLogger("src.bot.M1")

    @property
    def timeframe_minutes(self) -> int:
        return 1

    @property
    def mt5_timeframe(self) -> int:
        return TIMEFRAME_M1

    @property
    def magic_number(self) -> int:
        return 234001

    @property
    def bot_label(self) -> str:
        return "M1"

    @property
    def order_comment(self) -> str:
        return "m1_scalping"

    # -- Smart cooldown --

    def should_skip_cooldown(self, df: pd.DataFrame, last_position_type: str | None) -> tuple[bool, str | None]:
        """
        Skip cooldown when 3/4 conditions met:
        1. RSI extreme (< 43.4 LONG, > 56.6 SHORT)
        2. RSI momentum negative (declining into exit)
        3. High volatility (ATR > 0.15% of price)
        4. Strong price momentum (|move| > 7.65)
        """
        if not self.config.use_smart_cooldown or df is None or len(df) < 10:
            return False, None

        latest = df.iloc[-1]
        conditions = 0
        details = []
        threshold = self.config.smart_cooldown_threshold

        # 1. RSI extreme
        if last_position_type == 'LONG' and latest['RSI'] < 43.4:
            conditions += 1
            details.append(f"RSI extreme ({latest['RSI']:.1f} < 43.4)")
        elif last_position_type == 'SHORT' and latest['RSI'] > 56.6:
            conditions += 1
            details.append(f"RSI extreme ({latest['RSI']:.1f} > 56.6)")

        # 2. RSI momentum
        if len(df) >= 4:
            rsi_momentum = latest['RSI'] - df.iloc[-4]['RSI']
            if rsi_momentum < -4.7:
                conditions += 1
                details.append(f"RSI declining ({rsi_momentum:.1f})")

        # 3. High volatility
        atr_threshold = latest['close'] * 0.0015
        if latest['ATR'] > atr_threshold:
            conditions += 1
            details.append(f"High volatility (ATR {latest['ATR']:.2f})")

        # 4. Strong price momentum
        if len(df) >= 6:
            momentum = latest['close'] - df.iloc[-6]['close']
            if abs(momentum) > 7.65:
                conditions += 1
                details.append(f"Strong momentum ({momentum:+.2f})")

        if conditions >= threshold:
            reason = f"Smart cooldown: {conditions}/{threshold} conditions -- " + ", ".join(details)
            return True, reason

        return False, None

    # -- Entry --

    def check_entry(
        self,
        df: pd.DataFrame,
        open_positions: list,
        context: dict,
    ) -> dict | None:
        latest = df.iloc[-1]
        has_long = context.get('has_long', False)
        has_short = context.get('has_short', False)
        num_positions = len(open_positions)

        # Signal confirmation: only when going 0->1, not 1->2
        required = self.config.entry_signal_confirmations if num_positions == 0 else 0

        # LONG
        if latest['RSI'] < self.config.rsi_buy:
            self.entry_signal_count['LONG'] += 1
            self.entry_signal_count['SHORT'] = 0

            if has_short:
                self.logger.info("LONG signal detected but skipping -- already have SHORT position(s)")
                return None

            if self.entry_signal_count['LONG'] <= required:
                self.logger.info(
                    f"LONG signal -- waiting for confirmation "
                    f"({self.entry_signal_count['LONG']}/{required + 1} candles)"
                )
                return None

            if required > 0:
                self.logger.info(f"LONG SIGNAL CONFIRMED: RSI={latest['RSI']:.2f} ({self.entry_signal_count['LONG']} candles)")
            else:
                status = "skipped (adding to position)" if num_positions > 0 else f"required ({required + 1} candles)"
                self.logger.info(f"LONG SIGNAL: RSI={latest['RSI']:.2f} ({status})")

            self.entry_signal_count['LONG'] = 0
            return {'direction': 'LONG'}

        # SHORT
        if (self.config.enable_shorts
                and latest['RSI'] > self.config.rsi_sell
                and latest['downtrend']):
            self.entry_signal_count['SHORT'] += 1
            self.entry_signal_count['LONG'] = 0

            if has_long:
                self.logger.info("SHORT signal detected but skipping -- already have LONG position(s)")
                return None

            if self.entry_signal_count['SHORT'] <= required:
                self.logger.info(
                    f"SHORT signal -- waiting for confirmation "
                    f"({self.entry_signal_count['SHORT']}/{required + 1} candles)"
                )
                return None

            if required > 0:
                self.logger.info(f"SHORT SIGNAL CONFIRMED: RSI={latest['RSI']:.2f} ({self.entry_signal_count['SHORT']} candles)")
            else:
                status = "skipped (adding to position)" if num_positions > 0 else f"required ({required + 1} candles)"
                self.logger.info(f"SHORT SIGNAL: RSI={latest['RSI']:.2f} ({status})")

            self.entry_signal_count['SHORT'] = 0
            return {'direction': 'SHORT'}

        # No signal -- reset
        self.entry_signal_count['LONG'] = 0
        self.entry_signal_count['SHORT'] = 0
        return None

    # -- Exit --

    def check_exit(
        self,
        df: pd.DataFrame,
        position,
        context: dict,
    ) -> tuple[bool, str]:
        """
        RSI exit with optional 2-candle confirmation.

        M1 analysis showed 100% of RSI spikes are false signals that
        drop back within 3 minutes, so we require confirmation.
        """
        latest = df.iloc[-1]
        previous = df.iloc[-2] if len(df) >= 2 else latest
        use_confirmation = self.config.rsi_exit_confirmation
        rsi_tracker = context.get('rsi_tracker', {})
        ticket = position.ticket

        if position.type == ORDER_TYPE_BUY:
            threshold = self.config.rsi_exit_long

            if use_confirmation:
                if latest['RSI'] > threshold and previous['RSI'] > threshold:
                    return True, f"RSI exit confirmed ({latest['RSI']:.2f} > {threshold} for 2 candles)"
                if latest['RSI'] > threshold:
                    if ticket not in rsi_tracker:
                        rsi_tracker[ticket] = 1
                        self.logger.info(f"RSI {latest['RSI']:.2f} > {threshold} -- waiting for confirmation (ticket {ticket})")
                else:
                    rsi_tracker.pop(ticket, None)
            else:
                if latest['RSI'] > threshold:
                    return True, f"RSI exit threshold ({latest['RSI']:.2f} > {threshold})"
        else:
            threshold = self.config.rsi_exit_short

            if use_confirmation:
                if latest['RSI'] < threshold and previous['RSI'] < threshold:
                    return True, f"RSI exit confirmed ({latest['RSI']:.2f} < {threshold} for 2 candles)"
                if latest['RSI'] < threshold:
                    if ticket not in rsi_tracker:
                        rsi_tracker[ticket] = 1
                        self.logger.info(f"RSI {latest['RSI']:.2f} < {threshold} -- waiting for confirmation (ticket {ticket})")
                else:
                    rsi_tracker.pop(ticket, None)
            else:
                if latest['RSI'] < threshold:
                    return True, f"RSI exit threshold ({latest['RSI']:.2f} < {threshold})"

        return False, ""
