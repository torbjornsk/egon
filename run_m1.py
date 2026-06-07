"""
Egon M1 Scalping Bot
Entry point for the M1 (1-minute) trading strategy.
"""

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler(),
    ],
)

from src.bot.m1_bot import create_m1_bot


def main():
    parser = argparse.ArgumentParser(description='Egon M1 Scalping Bot')
    parser.add_argument('--config', default='config/m1_params.json',
                        help='Path to configuration file')
    parser.add_argument('--interval', type=int, default=1,
                        help='Check interval in seconds (default: 1)')
    args = parser.parse_args()

    bot = create_m1_bot(args.config)
    bot.run(check_interval=args.interval)


if __name__ == "__main__":
    main()
