"""Egon Liquidity Zone bot entry point."""

import argparse
import logging
import sys

from src.core.config import load_config
from src.strategy.liquidity_zones import LiquidityZoneStrategy
from src.bot.zone_bot import ZoneBot


def main():
    parser = argparse.ArgumentParser(description="Egon Liquidity Zone Bot")
    parser.add_argument("--config", default="config/lz_params.json", help="Config file path")
    parser.add_argument("--interval", type=int, default=1, help="Check interval in seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("trading_bot.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    config = load_config(args.config)
    strategy = LiquidityZoneStrategy(config)
    bot = ZoneBot(strategy, config)
    bot.run(check_interval=args.interval)


if __name__ == "__main__":
    main()
