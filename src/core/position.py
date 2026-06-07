"""
Position tracking, profit protection, MT5 close detection, exit reason management.

Extracts all position lifecycle logic from the monolithic bot classes.
"""

import json
import logging
import os
from datetime import datetime
from typing import Protocol, runtime_checkable

from src.core.config import TradingConfig
from src.core.timezone import get_local_now, LOCAL_TZ

logger = logging.getLogger(__name__)


# -- Exit reason helpers --

def simplify_exit_reason(reason: str) -> str:
    """Shorten exit reason for GUI display."""
    r = reason.lower()
    if 'profit protection' in r:
        return 'Profit protection'
    if 'rsi exit' in r:
        return 'RSI exit'
    if 'weekend' in r:
        return 'Weekend close'
    if 'emergency' in r:
        if 'consecutive loss' in r:
            return 'Emergency (losses)'
        if 'daily loss' in r:
            return 'Emergency (daily loss)'
        if 'rapid loss' in r:
            return 'Emergency (rapid loss)'
        if 'equity' in r:
            return 'Emergency (equity)'
        return 'Emergency stop'
    if 'stop loss' in r:
        return 'Stop loss'
    if 'take profit' in r:
        return 'Take profit'
    if 'mt5 close' in r:
        return 'MT5 close'
    return reason[:30] + '...' if len(reason) > 30 else reason


def save_exit_reason(ticket: int, reason: str, exit_time: datetime, bot_label: str, filepath: str):
    """Save exit reason to JSON file for GUI display."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    short_reason = simplify_exit_reason(reason)

    exit_reasons = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                exit_reasons = json.load(f)
        except Exception:
            pass

    exit_reasons[str(ticket)] = {
        'reason': short_reason,
        'full_reason': reason,
        'exit_time': exit_time.isoformat(),
        'bot': bot_label,
    }

    # Keep only last 200 entries
    if len(exit_reasons) > 200:
        sorted_items = sorted(
            exit_reasons.items(),
            key=lambda x: x[1].get('exit_time', ''),
            reverse=True,
        )
        exit_reasons = dict(sorted_items[:200])

    try:
        with open(filepath, 'w') as f:
            json.dump(exit_reasons, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save exit reason: {e}")


# -- Drawdown limit calculators --

def get_m5_drawdown_limit(
    minutes_held: float,
    base_limit: float = 0.40,
) -> float:
    """
    M5 time-based drawdown limit (hardcoded schedule).

    0-30min: base_limit (40%)
    30+min: drops by 10% at 30min, then 5% every 10min, min 15%
    """
    if minutes_held <= 30:
        return base_limit
    minutes_over_30 = minutes_held - 30
    reduction = min(0.15, 0.10 + (int(minutes_over_30 / 10) * 0.05))
    return max(0.15, base_limit - reduction)


def get_m1_drawdown_limit(
    minutes_held: float,
    config: TradingConfig,
) -> float:
    """
    M1 configurable time-based drawdown limit.

    Uses config values for start time, interval, step, and minimum.
    """
    if not config.profit_protection_time_based_tightening:
        return config.profit_protection_drawdown_limit_pct

    base = config.profit_protection_drawdown_limit_pct
    start = config.profit_protection_tightening_start_minutes
    interval = config.profit_protection_tightening_interval_minutes
    step = config.profit_protection_tightening_step_pct
    minimum = config.profit_protection_minimum_drawdown_pct

    if minutes_held < start:
        return base

    intervals_passed = int((minutes_held - start) / interval)
    adjusted = base - (intervals_passed * step)
    return max(adjusted, minimum)


# -- Position Manager --

class PositionManager:
    """
    Tracks open positions, peak profits, profit protection state,
    and detects MT5-triggered closes (stop loss / take profit).
    """

    def __init__(
        self,
        config: TradingConfig,
        bot_label: str,
        exit_reasons_file: str,
        drawdown_limit_fn=None,
    ):
        from src.core.paths import resolve_path

        self.config = config
        self.bot_label = bot_label
        self.exit_reasons_file = str(resolve_path(exit_reasons_file)) if exit_reasons_file else ''
        self._drawdown_limit_fn = drawdown_limit_fn
        self.logger = logging.getLogger(f"src.bot.{bot_label}")

        # Position tracking
        self.position_open_times: dict[int, datetime] = {}
        self.peak_position_profits: dict[int, float] = {}
        self.protection_activated: dict[int, bool] = {}

        # RSI confirmation tracker (M1)
        self.rsi_confirmation_tracker: dict[int, int] = {}

        # MT5 close detection
        self.tracked_positions: set[int] = set()
        self.bot_closed_positions: set[int] = set()

    def register_open(self, ticket: int, open_time: datetime | None = None):
        """Register a newly opened position."""
        self.position_open_times[ticket] = open_time or get_local_now()
        self.peak_position_profits[ticket] = 0
        self.tracked_positions.add(ticket)

    def register_existing(self, ticket: int, open_time: datetime, current_profit: float):
        """Register an existing position found on startup."""
        if ticket not in self.position_open_times:
            self.position_open_times[ticket] = open_time
            self.peak_position_profits[ticket] = max(0, current_profit)
            self.tracked_positions.add(ticket)
            minutes = (get_local_now() - open_time).total_seconds() / 60
            self.logger.info(
                f"Detected existing position {ticket}: "
                f"peak ${self.peak_position_profits[ticket]:.2f}, held {minutes:.1f}min"
            )

    def register_close(self, ticket: int):
        """Clean up tracking after a position is closed by the bot."""
        self.position_open_times.pop(ticket, None)
        self.peak_position_profits.pop(ticket, None)
        self.protection_activated.pop(ticket, None)
        self.rsi_confirmation_tracker.pop(ticket, None)
        self.bot_closed_positions.add(ticket)

    def save_exit(self, ticket: int, reason: str):
        """Save exit reason to file (skipped if exit_reasons_file is empty)."""
        if not self.exit_reasons_file:
            return
        save_exit_reason(ticket, reason, get_local_now(), self.bot_label, self.exit_reasons_file)

    def get_minutes_held(self, ticket: int) -> float:
        """Get how many minutes a position has been held."""
        if ticket not in self.position_open_times:
            return 0
        delta = get_local_now() - self.position_open_times[ticket]
        return delta.total_seconds() / 60

    # -- Profit protection --

    def update_peak_profit(
        self, ticket: int, current_profit: float, balance: float
    ) -> None:
        """Update peak profit tracking and log state changes."""
        if ticket not in self.peak_position_profits:
            self.peak_position_profits[ticket] = max(0, current_profit)
            invested = balance * self.config.per_position_size_pct
            threshold_dollars = invested * self.config.profit_protection_threshold_pct
            self.logger.info(
                f"[PROFIT PROTECTION] Ticket {ticket}: "
                f"Initialized peak at ${current_profit:.2f} "
                f"(will activate at ${threshold_dollars:.2f})"
            )
            return

        old_peak = self.peak_position_profits[ticket]
        self.peak_position_profits[ticket] = max(old_peak, current_profit)

        if self.peak_position_profits[ticket] > old_peak:
            new_peak = self.peak_position_profits[ticket]
            if ticket in self.protection_activated:
                # Show exit trigger level
                minutes = self.get_minutes_held(ticket)
                invested = balance * self.config.per_position_size_pct
                new_peak_pct = new_peak / invested if invested > 0 else 0
                drawdown_limit = self._get_profit_scaled_drawdown_limit(ticket, minutes, new_peak_pct)
                trigger_at = new_peak * (1 - drawdown_limit)
                self.logger.info(
                    f"[PROFIT PROTECTION] Ticket {ticket}: "
                    f"New peak ${new_peak:.2f} (was ${old_peak:.2f}, "
                    f"will exit at ${trigger_at:.2f})"
                )
            else:
                self.logger.info(
                    f"[PROFIT PROTECTION] Ticket {ticket}: "
                    f"New peak ${new_peak:.2f} (was ${old_peak:.2f})"
                )

    def check_profit_protection(
        self, ticket: int, current_profit: float, balance: float
    ) -> tuple[bool, str]:
        """
        Check if profit protection should trigger an exit.

        Returns: (should_exit, reason)
        """
        if not self.config.use_profit_protection:
            return False, ""

        self.update_peak_profit(ticket, current_profit, balance)

        peak = self.peak_position_profits.get(ticket, 0)
        invested = balance * self.config.per_position_size_pct
        peak_pct = peak / invested if invested > 0 else 0
        threshold = self.config.profit_protection_threshold_pct

        # Check activation
        if ticket not in self.protection_activated:
            if peak_pct > threshold and peak > 0:
                threshold_dollars = invested * threshold
                self.logger.info(
                    f"[PROFIT PROTECTION ACTIVATED] Ticket {ticket}: "
                    f"Profit ${peak:.2f} exceeded threshold ${threshold_dollars:.2f} "
                    f"({threshold*100:.2f}% of invested ${invested:.2f})"
                )
                self.protection_activated[ticket] = True

        if peak_pct <= threshold or peak <= 0:
            return False, ""

        # Calculate drawdown
        minutes = self.get_minutes_held(ticket)
        drawdown_limit = self._get_profit_scaled_drawdown_limit(ticket, minutes, peak_pct)
        profit_drawdown = (peak - current_profit) / peak

        if profit_drawdown > drawdown_limit:
            reason = (
                f"Profit protection (continuous): profit dropped {profit_drawdown*100:.1f}% "
                f"from peak ${peak:.2f} to ${current_profit:.2f} "
                f"(limit {drawdown_limit*100:.0f}% after {minutes:.0f}min)"
            )
            self.logger.info(
                f"[PROFIT PROTECTION - CONTINUOUS] Ticket {ticket}: "
                f"Peak ${peak:.2f} -> Current ${current_profit:.2f} "
                f"({profit_drawdown*100:.1f}% drop, limit {drawdown_limit*100:.0f}% "
                f"after {minutes:.0f}min)"
            )
            return True, reason

        return False, ""

    def _get_drawdown_limit(self, ticket: int, minutes_held: float) -> float:
        """Get the appropriate drawdown limit."""
        if self._drawdown_limit_fn is not None:
            return self._drawdown_limit_fn(minutes_held)
        # Default: config-driven tightening
        return get_m1_drawdown_limit(minutes_held, self.config)

    def _get_profit_scaled_drawdown_limit(
        self, ticket: int, minutes_held: float, peak_pct: float
    ) -> float:
        """
        Get drawdown limit factoring in profit-based scaling.

        When scaling is enabled, the drawdown limit is determined by how far
        above the threshold the peak profit is. Time-based tightening still
        applies as a further reduction.
        """
        scaling = self.config.profit_protection_scaling
        threshold = self.config.profit_protection_threshold_pct

        if scaling == "none" or threshold <= 0:
            return self._get_drawdown_limit(ticket, minutes_held)

        ratio = peak_pct / threshold  # How many multiples of threshold

        if scaling == "tiered":
            tiers = self.config.profit_protection_tiers
            # Tiers are sorted by multiplier ascending: [[1.0, 0.25], [1.5, 0.50], ...]
            # Find the highest tier we've reached
            base_limit = tiers[0][1] if tiers else self.config.profit_protection_drawdown_limit_pct
            for mult, limit in tiers:
                if ratio >= mult:
                    base_limit = limit
                else:
                    break

        elif scaling == "continuous":
            base_limit = min(
                self.config.profit_protection_continuous_max,
                self.config.profit_protection_continuous_base
                + self.config.profit_protection_continuous_rate * (ratio - 1),
            )
            base_limit = max(base_limit, self.config.profit_protection_continuous_base)

        else:
            return self._get_drawdown_limit(ticket, minutes_held)

        # Apply time-based tightening on top (reduces the limit over time)
        if self.config.profit_protection_time_based_tightening:
            time_limit = self._get_drawdown_limit(ticket, minutes_held)
            # Use the more restrictive of profit-scaled and time-based
            return min(base_limit, time_limit)

        return base_limit

    def get_position_state(self, ticket: int, current_profit: float, balance: float) -> dict:
        """
        Get a complete state snapshot for a position, including profit protection details.

        This is the single source of truth for the GUI  --  no independent computation needed.
        """
        minutes_held = self.get_minutes_held(ticket)
        peak = self.peak_position_profits.get(ticket, 0)
        invested = balance * self.config.per_position_size_pct
        threshold = self.config.profit_protection_threshold_pct
        threshold_dollars = invested * threshold
        peak_pct = peak / invested if invested > 0 else 0
        is_activated = ticket in self.protection_activated

        state = {
            'ticket': ticket,
            'minutes_held': minutes_held,
            'current_profit': current_profit,
            'peak_profit': peak,
            'invested_amount': invested,
        }

        # Profit protection state
        if self.config.use_profit_protection:
            peak_pct = peak / invested if invested > 0 else 0
            drawdown_limit = self._get_profit_scaled_drawdown_limit(ticket, minutes_held, peak_pct)
            profit_drawdown = (peak - current_profit) / peak if peak > 0 else 0
            trigger_at = peak * (1 - drawdown_limit) if peak > 0 else 0

            state['protection'] = {
                'enabled': True,
                'activated': is_activated,
                'threshold_pct': threshold,
                'threshold_dollars': threshold_dollars,
                'peak_profit': peak,
                'drawdown_limit_pct': drawdown_limit,
                'current_drawdown_pct': profit_drawdown,
                'exit_trigger_at': trigger_at,
                'minutes_held': minutes_held,
            }
        else:
            state['protection'] = {'enabled': False}

        return state

