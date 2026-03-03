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

    # Loss backoff
    use_loss_backoff: bool = True
    loss_backoff_multipliers: list[int] = field(default_factory=lambda: [1, 3, 7, 15])

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
