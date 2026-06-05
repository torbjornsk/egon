"""
M15 Bot -- thin wiring of BaseTradingBot + M15ScalpingStrategy.
"""

from src.bot.base import BaseTradingBot
from src.core.config import load_config
from src.strategy.m15_scalping import M15ScalpingStrategy


def create_m15_bot(config_path: str = 'config/m15_params.json') -> BaseTradingBot:
    """Create an M15 scalping bot with the given config."""
    config = load_config(config_path)
    strategy = M15ScalpingStrategy(config)
    return BaseTradingBot(strategy, config)
