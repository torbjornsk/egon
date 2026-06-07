"""Egon Tick Scalper entry point."""

import argparse
import logging
import sys

from src.core.config import load_config
from src.bot.tick_scalper import TickScalper


def main():
    parser = argparse.ArgumentParser(description="Egon Tick Scalper")
    parser.add_argument("--config", default="config/tick_params.json")
    parser.add_argument("--debug", action="store_true")
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
    bot = TickScalper(config)
    bot.run()


if __name__ == "__main__":
    main()
