"""
M5 Bot  --  thin wiring of BaseTradingBot + M5ScalpingStrategy.
"""

from src.bot.base import BaseTradingBot
from src.core.config import TradingConfig, load_config
from src.strategy.m5_scalping import M5ScalpingStrategy


def create_m5_bot(config_path: str = 'config/m5_params.json') -> BaseTradingBot:
    """Create an M5 scalping bot with the given config."""
    config = load_config(config_path)
    strategy = M5ScalpingStrategy(config)
    return BaseTradingBot(strategy, config)
