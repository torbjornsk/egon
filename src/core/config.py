"""
Configuration loading and validation for Egon trading bots.

Supports "approved" configs in config/ and "experimental" configs in config/experimental/.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TradingConfig:
    """Validated trading configuration."""

    # Strategy identity
    strategy: str = "m5_scalping"

    # Position sizing
    position_size_pct: float = 0.18
    leverage: int = 27
    max_positions: int = 2

    # Drawdown / safety
    max_drawdown_limit: float = 0.35

    # Indicators
    fast_ema: int = 9
    slow_ema: int = 21
    rsi_period: int = 14
    rsi_buy: float = 38
    rsi_sell: float = 62
    rsi_exit_long: float = 60
    rsi_exit_short: float = 40

    # ATR / stop loss
    atr_multiplier: float = 2.0
    atr_high_volatility_multiplier: float = 1.5

    # Profit target
    profit_target_pct: float = 0.028

    # Shorts
    enable_shorts: bool = True
    # Require downtrend (fast EMA < slow EMA) for short entries
    # True = original behavior (M5 style), False = symmetric RSI-only shorts
    short_requires_downtrend: bool = True
    # Require uptrend (fast EMA > slow EMA) for long entries
    # True = only buy in uptrends, False = buy on RSI alone (current behavior)
    long_requires_uptrend: bool = False

    # RSI reversal entry: instead of entering immediately when RSI crosses threshold,
    # wait for RSI to start reversing (current RSI > previous RSI for longs,
    # current RSI < previous RSI for shorts). Catches the swing point.
    entry_on_rsi_reversal: bool = False

    # RSI exit confirmation (M1 feature)
    rsi_exit_confirmation: bool = False

    # Smart cooldown (M1 feature)
    use_smart_cooldown: bool = False
    smart_cooldown_threshold: int = 3

    # Entry signal confirmation
    entry_signal_confirmations: int = 0

    # Profit protection
    use_profit_protection: bool = True
    profit_protection_threshold_pct: float = 0.04
    profit_protection_drawdown_limit_pct: float = 0.40
    profit_protection_time_based_tightening: bool = True
    profit_protection_tightening_start_minutes: float = 30
    profit_protection_tightening_interval_minutes: float = 10
    profit_protection_tightening_step_pct: float = 0.05
    profit_protection_minimum_drawdown_pct: float = 0.15

    # Profit-based drawdown scaling (overrides base drawdown_limit when active)
    # "none" = flat drawdown limit (current behavior)
    # "tiered" = step-wise tiers based on profit multiples of threshold
    # "continuous" = smooth curve scaling drawdown with profit size
    profit_protection_scaling: str = "none"

    # Tiered scaling: list of [threshold_multiplier, drawdown_limit] pairs
    profit_protection_tiers: list = field(default_factory=lambda: [
        [1.0, 0.25], [1.5, 0.50], [2.0, 0.75]
    ])

    # Continuous scaling: drawdown = min(max, base + rate * (peak_pct/threshold - 1))
    profit_protection_continuous_base: float = 0.20
    profit_protection_continuous_rate: float = 0.15
    profit_protection_continuous_max: float = 0.75

    # Auto-volatility: only enable PP when ATR > 80th percentile of recent history
    profit_protection_auto_volatility: bool = False

    # Loss backoff
    use_loss_backoff: bool = True
    loss_backoff_multipliers: list[int] = field(default_factory=lambda: [1, 3, 7, 15])

    # SL-only backoff: only trigger backoff on consecutive stop-loss exits (not RSI losses)
    # When True, uses consecutive_sl_exits instead of consecutive_losses
    # loss_backoff_sl_only_candles: flat number of candles to sit out (0 = use multiplier system)
    loss_backoff_sl_only: bool = False
    loss_backoff_sl_threshold: int = 2       # consecutive SL exits before backoff kicks in
    loss_backoff_sl_candles: int = 2         # flat candles to sit out

    # Tighten stop loss after consecutive SL exits
    # Each consecutive SL multiplies stop distance by this factor (0.5 = halve each time)
    # 1.0 = disabled (no tightening)
    sl_tightening_factor: float = 1.0

    # Block 2nd position when existing position is underwater
    block_second_when_underwater: bool = True

    # Trading mode: controls which directions the bot will trade
    # "both" = longs and shorts (default)
    # "long_only" = only take long positions
    # "short_only" = only take short positions
    trading_mode: str = "both"

    # Trend filter for entries
    # "none" = no filter (current behavior)
    # "ema_cross" = LONG requires uptrend (fast EMA > slow EMA), SHORT requires downtrend
    # "ema_200" = LONG requires close > EMA200, SHORT requires close < EMA200
    trend_filter: str = "none"

    # Liquidity zone strategy settings
    zone_lookback: int = 100              # Bars to look back for zone detection
    max_active_zones: int = 6             # Max zones to track simultaneously
    zone_update_interval: int = 15        # Minutes between zone recalculations
    zone_rr_ratio: float = 2.0            # Risk:reward ratio for TP placement
    zone_min_strength: float = 0.4        # Minimum zone strength to place an order
    zone_max_distance_atr: float = 3.0    # Max distance from price (in ATR) to place orders
    zone_order_max_age_minutes: int = 120  # Cancel unfilled orders after this
    zone_max_hold_minutes: int = 240      # Close positions held longer than this with no profit

    # Breakeven stop: move SL to entry once profit exceeds this multiple of ATR
    breakeven_atr_trigger: float = 1.0    # 0 = disabled, 1.0 = move to BE after 1 ATR profit
    breakeven_offset: float = 0.1         # Small offset above entry (in ATR) to cover spread

    # Partial close: close a portion of the position at first target
    partial_close_enabled: bool = False
    partial_close_fraction: float = 0.5   # Close this fraction at first target (0.5 = half)
    partial_close_atr_target: float = 1.5 # Close partial at this ATR multiple of profit

    # Tick scalper settings
    tick_entry_threshold: float = 0.40    # Minimum composite score to enter
    tick_exit_threshold: float = 0.50     # Minimum exit score to close
    tick_micro_trend_window: int = 30     # Seconds of tick data for micro-trend
    tick_support_lookback: int = 300      # Seconds of history for support/resistance
    tick_cooldown_seconds: int = 30       # Seconds to wait between trades
    tick_max_trades_per_day: int = 30     # Maximum trades per day

    # Momentum scalper settings
    signal_window: int = 15               # Seconds of signal history to weight
    heavy_weight_count: int = 5           # How many recent samples get dominant weight
    entry_threshold: float = 0.45         # Weighted signal must exceed this to enter
    hold_threshold: float = 0.15          # Signal below this = exit (conviction gone)
    min_profit_for_signal_exit: float = 0.50  # Don't signal-exit if losing more than this
    sl_atr_mult: float = 1.5             # SL distance in M5 ATR multiples
    cooldown_seconds: int = 15            # Seconds between trades
    max_trades_per_day: int = 300         # Daily trade cap
    factor_window_ticks: int = 15         # Ticks used for factor calculations

    @property
    def per_position_size_pct(self) -> float:
        """Position size per individual position (split across max_positions)."""
        return self.position_size_pct / self.max_positions

    @property
    def effective_leverage_per_position(self) -> float:
        return self.per_position_size_pct * self.leverage

    @property
    def effective_leverage_total(self) -> float:
        return self.position_size_pct * self.leverage


def load_config(config_path: str | Path) -> TradingConfig:
    """
    Load a trading config from JSON file and return a validated TradingConfig.

    Keys starting with '_' are treated as comments and ignored.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, 'r') as f:
        raw = json.load(f)

    # Filter out comment keys
    data = {k: v for k, v in raw.items() if not k.startswith('_')}

    config = TradingConfig(**{
        k: v for k, v in data.items()
        if k in TradingConfig.__dataclass_fields__
    })

    logger.info(f"Config loaded: {config.strategy} from {path.name}")
    logger.info(
        f"Position: {config.position_size_pct*100:.0f}% total "
        f"({config.per_position_size_pct*100:.1f}% x {config.max_positions}), "
        f"Leverage: {config.leverage}x, "
        f"Effective: {config.effective_leverage_total*100:.0f}%"
    )

    return config
