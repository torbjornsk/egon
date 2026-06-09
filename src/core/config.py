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

    # ── Bot identity ────────────────────────────────────────────────
    # config_name: human-readable label for this config (shown in GUI)
    config_name: str = ""
    # bot_type: determines which strategy/bot class to instantiate
    # Valid: "sniper", "rsi_scalper", "liquidity_zones", "tick_scalper", "momentum", "breakout"
    bot_type: str = "sniper"
    strategy: str = "m5_scalping"

    # ── Symbol & timeframe ──────────────────────────────────────────
    symbol: str = "XAUUSD.p"
    # Timeframe string: "M1", "M5", "M15", "H1", "H4"
    timeframe: str = "M5"
    # Unique magic number for MT5 order identification
    magic_number: int = 234050
    # Short label for logging and GUI display
    bot_label: str = "M5S"
    # Comment attached to MT5 orders
    order_comment: str = "m5_sniper"

    # ── Position sizing ─────────────────────────────────────────────
    # Sizing mode: "fixed", "risk_pct", "atr_adaptive"
    # "fixed" = use fixed_lots directly
    # "risk_pct" = risk X% of account per trade, SL distance determines lot size
    # "atr_adaptive" = risk_pct but scales down when ATR is elevated
    sizing_mode: str = "risk_pct"

    # Legacy sizing (kept for backward compat with old configs)
    position_size_pct: float = 0.18
    leverage: int = 27

    # Fixed lot sizing
    fixed_lots: float = 0.05

    # Risk-based sizing
    risk_per_trade_pct: float = 0.02      # Risk 2% of account per trade

    # ATR-adaptive sizing: scale risk down when ATR > median
    # effective_risk = risk_per_trade_pct * (median_atr / current_atr) ^ atr_damping
    atr_damping: float = 0.7              # 0 = no damping, 1 = full inverse scaling

    max_positions: int = 1

    # ── Drawdown / safety ───────────────────────────────────────────
    max_drawdown_limit: float = 0.35

    # ── Indicators ──────────────────────────────────────────────────
    fast_ema: int = 9
    slow_ema: int = 21
    rsi_period: int = 14
    rsi_buy: float = 38
    rsi_sell: float = 62
    rsi_exit_long: float = 60
    rsi_exit_short: float = 40

    # ── ATR / stop loss ─────────────────────────────────────────────
    atr_multiplier: float = 2.0
    atr_high_volatility_multiplier: float = 1.5

    # ── Profit target ───────────────────────────────────────────────
    profit_target_pct: float = 0.028

    # ── Direction control ───────────────────────────────────────────
    enable_shorts: bool = True
    short_requires_downtrend: bool = True
    long_requires_uptrend: bool = False

    # RSI reversal entry: wait for RSI to start reversing before entering
    entry_on_rsi_reversal: bool = False

    # RSI exit confirmation (M1 feature)
    rsi_exit_confirmation: bool = False

    # Smart cooldown (M1 feature)
    use_smart_cooldown: bool = False
    smart_cooldown_threshold: int = 3

    # Entry signal confirmation
    entry_signal_confirmations: int = 0

    # ── Profit protection ───────────────────────────────────────────
    use_profit_protection: bool = True
    profit_protection_threshold_pct: float = 0.04
    profit_protection_drawdown_limit_pct: float = 0.40
    profit_protection_time_based_tightening: bool = True
    profit_protection_tightening_start_minutes: float = 30
    profit_protection_tightening_interval_minutes: float = 10
    profit_protection_tightening_step_pct: float = 0.05
    profit_protection_minimum_drawdown_pct: float = 0.15

    # Profit-based drawdown scaling
    profit_protection_scaling: str = "none"
    profit_protection_tiers: list = field(default_factory=lambda: [
        [1.0, 0.25], [1.5, 0.50], [2.0, 0.75]
    ])
    profit_protection_continuous_base: float = 0.20
    profit_protection_continuous_rate: float = 0.15
    profit_protection_continuous_max: float = 0.75
    profit_protection_auto_volatility: bool = False

    # ── Loss backoff ────────────────────────────────────────────────
    use_loss_backoff: bool = True
    loss_backoff_multipliers: list[int] = field(default_factory=lambda: [1, 3, 7, 15])
    loss_backoff_sl_only: bool = False
    loss_backoff_sl_threshold: int = 2
    loss_backoff_sl_candles: int = 2
    sl_tightening_factor: float = 1.0

    # Simple re-entry cooldown: wait N candles after ANY close before new entry.
    # 0 = disabled (use standard cooldown logic instead).
    # This is independent of loss_backoff and applies to wins too.
    reentry_cooldown_bars: int = 0

    # Block 2nd position when existing position is underwater
    block_second_when_underwater: bool = True

    # ── Trading mode ────────────────────────────────────────────────
    # "both" = longs and shorts, "long_only", "short_only"
    trading_mode: str = "both"

    # Trend filter: "none", "ema_cross", "ema_200"
    trend_filter: str = "none"

    # ── Sniper-specific settings ────────────────────────────────────
    # RSI offset for limit order placement (deeper than entry threshold)
    # e.g. rsi_buy=35, sniper_rsi_offset=10 -> limit order at RSI 25 level
    sniper_rsi_offset: float = 10.0

    # ── Exit RSI ────────────────────────────────────────────────────
    # Base exit RSI level (mean revert target). Kept for backward compat.
    # Prefer exit_rsi_long / exit_rsi_short for per-direction control.
    exit_rsi: float = 50.0
    # Per-direction exit RSI targets. Longs close when RSI >= exit_rsi_long,
    # shorts close when RSI <= exit_rsi_short. Set both to 50 for true mean reversion.
    exit_rsi_long: float = 50.0
    exit_rsi_short: float = 50.0
    # TP order RSI targets (placed as MT5 TP price -- catches intra-candle spikes).
    # Set higher than exit_rsi_long / lower than exit_rsi_short for a more ambitious
    # spike catcher. When 0, falls back to exit_rsi_long / exit_rsi_short.
    tp_rsi_long: float = 0.0
    tp_rsi_short: float = 0.0
    # Adaptive exit: shift exit_rsi based on trend strength
    adaptive_exit_enabled: bool = True
    # EMA divergence threshold (in ATR) to trigger the shift
    exit_rsi_trend_threshold: float = 0.5
    # How many RSI points to shift when trend is strong
    exit_rsi_trend_shift: float = 5.0

    # ── Breakeven & trailing ────────────────────────────────────────
    # Breakeven mode: "atr_threshold" (default, wait for profit > breakeven_atr_trigger * ATR)
    #                 "first_pip" (move SL to BE as soon as price moves in your direction)
    breakeven_mode: str = "atr_threshold"
    # Move SL to entry once profit exceeds this multiple of ATR (0 = disabled)
    # Only used when breakeven_mode = "atr_threshold"
    breakeven_atr_trigger: float = 1.0
    # Small offset above entry (in ATR) to cover spread
    breakeven_offset: float = 0.1
    # Trail distance after breakeven is applied (in ATR multiples)
    trail_atr_after_breakeven: float = 1.0
    # Trail distance before breakeven (wider, in ATR multiples)
    trail_atr_before_breakeven: float = 1.5

    # ── TP calculation ──────────────────────────────────────────────
    # Fallback TP when RSI-based TP calculation fails (in ATR multiples)
    tp_fallback_atr_mult: float = 3.0
    # EMA divergence threshold (in ATR) for adaptive exit RSI shift
    exit_rsi_trend_threshold: float = 0.5
    # How much to shift exit RSI when trend is strong
    exit_rsi_trend_shift: float = 5.0

    # ── Partial close ───────────────────────────────────────────────
    partial_close_enabled: bool = False
    partial_close_fraction: float = 0.5
    partial_close_atr_target: float = 1.5

    # ── Data refresh ────────────────────────────────────────────────
    # Seconds between indicator data refreshes (for GUI display between candles)
    data_refresh_interval_seconds: int = 5
    # Milliseconds between trailing stop updates (lower = faster trailing)
    trail_interval_ms: int = 100

    # ── Schedule ────────────────────────────────────────────────────
    # Per-day trading hours ("HH:MM-HH:MM" or "" for closed)
    schedule_enabled: bool = False
    schedule_mon: str = "08:00-22:00"
    schedule_tue: str = "08:00-22:00"
    schedule_wed: str = "08:00-22:00"
    schedule_thu: str = "08:00-22:00"
    schedule_fri: str = "08:00-20:00"
    schedule_sat: str = ""
    schedule_sun: str = ""
    # Closed windows for news events: list of "YYYY-MM-DD HH:MM-HH:MM" strings
    schedule_closed: list = field(default_factory=list)

    # ── Volatility Guard (DEPRECATED -- replaced by Market Rhythm) ──
    # Kept for backward compat: old configs with these fields still load.
    # No longer used by the sniper bot.
    vg_enabled: bool = False
    vg_atr_spike_multiplier: float = 2.5
    vg_cooldown_minutes: int = 15
    vg_resume_below_multiplier: float = 1.5
    vg_lookback_bars: int = 100

    # ── Market Rhythm Analyzer ──────────────────────────────────────
    # Determines if current market conditions suit RSI-based swing trading.
    # Modes: "manual" (logging only), "gated" (blocks bad regimes),
    #        "dynamic" (adjusts params: offset, sizing, SL/trail)
    rhythm_enabled: bool = True
    rhythm_mode: str = "gated"
    # Minimum swing amplitude (in ATR multiples) to consider tradeable
    rhythm_min_amplitude_atr: float = 0.8
    # Max half-cycle length in bars (beyond this = trending, not swinging)
    rhythm_max_cycle_bars: int = 35
    # Min half-cycle length in bars (below this = chaotic/noise)
    rhythm_min_cycle_bars: int = 6
    # ATR factor below which market is considered dead
    rhythm_dead_atr_factor: float = 0.5
    # Higher timeframe for regime confirmation ("M5", "M15", "H1")
    rhythm_htf_timeframe: str = "M15"
    # Cap sniper levels at support/resistance (don't place below demand zones)
    rhythm_support_aware_sniper: bool = True

    # ── Breakout Shield ─────────────────────────────────────────────
    # Market-aware re-entry protection after stop-loss exits.
    # Blocks re-entry until analysis confirms breakout is over.
    shield_enabled: bool = True
    # Position lasted fewer than this many candles = "rapid SL" (higher severity)
    shield_rapid_sl_candles: int = 3
    # Legacy fields (kept for backward compat, no longer used)
    shield_reduced_size_factor: float = 0.5
    shield_reduced_size_trades: int = 2

    # ── Liquidity zone strategy settings ────────────────────────────
    zone_lookback: int = 100
    max_active_zones: int = 6
    zone_update_interval: int = 15
    zone_rr_ratio: float = 2.0
    zone_min_strength: float = 0.4
    zone_max_distance_atr: float = 3.0
    zone_order_max_age_minutes: int = 120
    zone_max_hold_minutes: int = 240

    # ── Tick scalper settings ───────────────────────────────────────
    tick_entry_threshold: float = 0.40
    tick_exit_threshold: float = 0.50
    tick_micro_trend_window: int = 30
    tick_support_lookback: int = 300
    tick_cooldown_seconds: int = 30
    tick_max_trades_per_day: int = 30

    # ── Momentum scalper settings ───────────────────────────────────
    signal_window: int = 15
    heavy_weight_count: int = 5
    entry_threshold: float = 0.45
    hold_threshold: float = 0.15
    min_profit_for_signal_exit: float = 0.50
    sl_atr_mult: float = 1.5
    cooldown_seconds: int = 15
    max_trades_per_day: int = 300
    factor_window_ticks: int = 15

    # ── Breakout strategy settings ──────────────────────────────────
    # Number of candles to look back for high/low breakout level
    breakout_bars: int = 5
    # Buffer above/below breakout level for stop order placement (in ATR multiples)
    # E.g. 0.1 means order placed 0.1*ATR above the high (catches momentum, avoids noise)
    breakout_entry_buffer_atr: float = 0.1
    # Minimum ATR value to avoid trading in dead markets (in price units, e.g. $2.0 for gold)
    breakout_min_atr: float = 2.0
    # Bars to wait after a breakout signal before allowing re-entry
    breakout_re_entry_bars: int = 1
    # SL distance in ATR multiples (tighter than sniper -- breakout uses momentum)
    breakout_sl_atr_mult: float = 1.0
    # Trail distance in ATR multiples (tight trailing for momentum capture)
    breakout_trail_atr_mult: float = 0.6
    # Daily risk limits
    breakout_max_daily_loss_pct: float = 0.05
    breakout_max_daily_trades: int = 150
    breakout_max_drawdown_pct: float = 0.15

    # ── Computed properties ─────────────────────────────────────────

    @property
    def per_position_size_pct(self) -> float:
        """Position size per individual position (split across max_positions). Legacy mode only."""
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
    Supports both absolute paths and relative paths (resolved from app root).
    """
    from src.core.paths import resolve_path

    path = Path(config_path)
    if not path.is_absolute():
        path = resolve_path(str(config_path))

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

    # Backward compat: if config has exit_rsi but not exit_rsi_long/short,
    # populate per-direction fields from the single value
    if 'exit_rsi' in data and 'exit_rsi_long' not in data:
        config.exit_rsi_long = config.exit_rsi
    if 'exit_rsi' in data and 'exit_rsi_short' not in data:
        config.exit_rsi_short = config.exit_rsi

    name = config.config_name or config.strategy
    logger.info(f"Config loaded: {name} from {path.name}")

    if config.sizing_mode == "legacy":
        logger.info(
            f"  Sizing: legacy ({config.position_size_pct*100:.0f}% x {config.leverage}x "
            f"= {config.effective_leverage_total*100:.0f}% exposure, "
            f"{config.per_position_size_pct*100:.1f}% per pos x {config.max_positions})"
        )
    elif config.sizing_mode == "fixed":
        logger.info(f"  Sizing: fixed {config.fixed_lots} lots")
    elif config.sizing_mode in ("risk_pct", "atr_adaptive"):
        logger.info(
            f"  Sizing: {config.sizing_mode} ({config.risk_per_trade_pct*100:.1f}% risk/trade, "
            f"max {config.max_positions} positions)"
        )

    if config.bot_type:
        logger.info(f"  Type: {config.bot_type}, TF: {config.timeframe}, Symbol: {config.symbol}")

    return config
