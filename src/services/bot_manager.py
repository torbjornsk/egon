"""
Bot manager  --  starts/stops bots in background threads.

The GUI creates a BotManager, starts bots, and reads their state via get_state().
Bots run in-process (not as subprocesses), so the GUI has direct access to
the bot's state dict  --  single source of truth, no log parsing needed.
"""

import logging
import threading
import io

from src.bot.base import BaseTradingBot
from src.bot.m1_bot import create_m1_bot
from src.bot.m5_bot import create_m5_bot

logger = logging.getLogger(__name__)


class BotRunner:
    """Wraps a BaseTradingBot with thread management and log capture."""

    def __init__(self, bot: BaseTradingBot):
        self.bot = bot
        self.thread: threading.Thread | None = None
        self.running = False
        self.log_buffer = io.StringIO()
        self._log_handler: logging.Handler | None = None

    def start(self, check_interval: int = 1):
        """Start the bot in a background thread."""
        if self.running:
            return

        self.running = True

        # Capture log output for THIS bot only (bot-specific logger)
        bot_logger = logging.getLogger(f"src.bot.{self.bot.strategy.bot_label}")
        self._log_handler = logging.StreamHandler(self.log_buffer)
        self._log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        bot_logger.addHandler(self._log_handler)

        self.thread = threading.Thread(
            target=self._run, args=(check_interval,),
            daemon=True,
            name=f"egon-{self.bot.strategy.bot_label}",
        )
        self.thread.start()

    def _run(self, check_interval: int):
        try:
            self.bot.run(check_interval=check_interval)
        except Exception as e:
            logger.error(f"Bot {self.bot.strategy.bot_label} crashed: {e}", exc_info=True)
        finally:
            self.running = False

    def stop(self):
        """Signal the bot to stop cleanly."""
        self.running = False
        self.bot._stop_requested = True
        if self._log_handler:
            bot_logger = logging.getLogger(f"src.bot.{self.bot.strategy.bot_label}")
            bot_logger.removeHandler(self._log_handler)

    def get_state(self) -> dict:
        """Get the bot's current state snapshot."""
        if not self.running:
            return {
                'bot_label': self.bot.strategy.bot_label,
                'status': 'Stopped',
                'positions': [],
                'indicators': {},
                'cooldown': {'active': False, 'reason': 'Bot stopped'},
                'max_positions': self.bot.config.max_positions,
                'consecutive_losses': 0,
                'trades_today': 0,
                'drawdown_pct': 0,
                'balance': 0,
                'equity': 0,
                'price': 0,
            }
        try:
            return self.bot.get_state()
        except Exception as e:
            logger.error(f"Error getting bot state: {e}")
            return {
                'bot_label': self.bot.strategy.bot_label,
                'status': 'Error',
                'positions': [],
                'indicators': {},
                'cooldown': {'active': False, 'reason': str(e)},
                'max_positions': self.bot.config.max_positions,
                'consecutive_losses': 0,
                'trades_today': 0,
                'drawdown_pct': 0,
                'balance': 0,
                'equity': 0,
                'price': 0,
            }

    def get_recent_logs(self, max_chars: int = 10000) -> str:
        """Get recent log output."""
        content = self.log_buffer.getvalue()
        if len(content) > max_chars:
            return content[-max_chars:]
        return content


class BotManager:
    """Manages M1 and M5 bot instances for the GUI."""

    def __init__(self):
        self.runners: dict[str, BotRunner] = {}

    def start_bot(
        self, label: str, config_path: str | None = None, check_interval: int = 1
    ):
        """Start a bot by label ('M1' or 'M5')."""
        if label in self.runners and self.runners[label].running:
            logger.warning(f"{label} bot is already running")
            return

        if label == 'M1':
            path = config_path or 'config/m1_params.json'
            bot = create_m1_bot(path)
            interval = check_interval or 1
        elif label == 'M5':
            path = config_path or 'config/m5_params.json'
            bot = create_m5_bot(path)
            interval = check_interval or 15
        else:
            raise ValueError(f"Unknown bot label: {label}")

        runner = BotRunner(bot)
        runner.start(interval)
        self.runners[label] = runner
        logger.info(f"Started {label} bot")

    def stop_bot(self, label: str):
        """Stop a bot by label."""
        if label in self.runners:
            self.runners[label].stop()
            logger.info(f"Stopped {label} bot")

    def get_state(self, label: str) -> dict:
        """Get state for a specific bot."""
        if label in self.runners:
            return self.runners[label].get_state()
        return {
            'bot_label': label,
            'status': 'Stopped',
            'positions': [],
            'indicators': {},
            'cooldown': {'active': False, 'reason': 'Not started'},
            'max_positions': 2,
            'consecutive_losses': 0,
            'trades_today': 0,
            'drawdown_pct': 0,
            'balance': 0,
            'equity': 0,
            'price': 0,
        }

    def get_logs(self, label: str) -> str:
        """Get recent logs for a bot."""
        if label in self.runners:
            return self.runners[label].get_recent_logs()
        return ""

    def is_running(self, label: str) -> bool:
        return label in self.runners and self.runners[label].running

    def stop_all(self):
        for label in list(self.runners.keys()):
            self.stop_bot(label)
