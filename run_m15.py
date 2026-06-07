"""Egon M15 bot entry point."""

import argparse
import logging
import sys

from src.bot.m15_bot import create_m15_bot


def main():
    parser = argparse.ArgumentParser(description="Egon M15 Trading Bot")
    parser.add_argument("--config", default="config/m15_params.json", help="Config file path")
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

    bot = create_m15_bot(args.config)
    bot.run(check_interval=args.interval)


if __name__ == "__main__":
    main()
