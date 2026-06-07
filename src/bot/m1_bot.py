"""
M1 Bot  --  thin wiring of BaseTradingBot + M1ScalpingStrategy.
"""

from src.bot.base import BaseTradingBot
from src.core.config import TradingConfig, load_config
from src.strategy.m1_scalping import M1ScalpingStrategy


def create_m1_bot(config_path: str = 'config/m1_params.json') -> BaseTradingBot:
    """Create an M1 scalping bot with the given config."""
    config = load_config(config_path)
    strategy = M1ScalpingStrategy(config)
    return BaseTradingBot(strategy, config)
