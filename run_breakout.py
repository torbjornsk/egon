"""
Entry point for Breakout Scalper bot (standalone, outside GUI).

Usage:
    .venv/Scripts/python.exe run_breakout.py
    .venv/Scripts/python.exe run_breakout.py --config config/breakout_params.json
"""

import argparse
import logging
import sys

from src.core.config import load_config
from src.strategy.breakout import BreakoutStrategy
from src.bot.base import BaseTradingBot


def main():
    parser = argparse.ArgumentParser(description="Egon Breakout Scalper")
    parser.add_argument(
        '--config', default='config/breakout_params.json',
        help='Path to config JSON file'
    )
    parser.add_argument(
        '--interval', type=int, default=1,
        help='Check interval in seconds (default: 1)'
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    config = load_config(args.config)
    strategy = BreakoutStrategy(config)
    bot = BaseTradingBot(strategy, config)
    bot.run(check_interval=args.interval)


if __name__ == '__main__':
    main()
