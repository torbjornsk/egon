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
from src.bot.zone_bot import ZoneBot
from src.bot.sniper_bot import SniperBot
from src.bot.tick_scalper import TickScalper
from src.bot.momentum_scalper import MomentumScalper

logger = logging.getLogger(__name__)


class BotRunner:
    """Wraps a trading bot (BaseTradingBot or ZoneBot) with thread management and log capture."""

    def __init__(self, bot):
        self.bot = bot
        self.thread: threading.Thread | None = None
        self.running = False
        self.log_buffer = io.StringIO()
        self._log_handler: logging.Handler | None = None
        self._last_read_pos: int = 0

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
        # Keep file logging via root, but stop console spam when GUI is running
        bot_logger.propagate = True

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
                'pp_active': False,
                'pp_override': self.bot.pp_override,
                'high_volatility': False,
                'trading_mode': self.bot.effective_trading_mode,
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
                'pp_active': False,
                'pp_override': None,
                'high_volatility': False,
                'trading_mode': 'both',
            }

    def get_recent_logs(self, max_chars: int = 10000) -> str:
        """Get new log output since last call."""
        content = self.log_buffer.getvalue()
        new_content = content[self._last_read_pos:]
        self._last_read_pos = len(content)

        # Trim buffer if it gets too large (prevent unbounded memory growth)
        if len(content) > 500_000:
            trimmed = content[-100_000:]
            self.log_buffer = io.StringIO()
            self.log_buffer.write(trimmed)
            self._last_read_pos = len(trimmed)
            if self._log_handler:
                self._log_handler.stream = self.log_buffer

        if len(new_content) > max_chars:
            return new_content[-max_chars:]
        return new_content


class BotManager:
    """Manages M1 and M5 bot instances for the GUI."""

    def __init__(self):
        self.runners: dict[str, BotRunner] = {}

    # Default config paths per bot label
    CONFIG_PATHS: dict[str, str] = {
        'M1': 'config/m1_params.json',
        'M5': 'config/m5_params.json',
        'M15': 'config/m15_params.json',
        'LZ': 'config/lz_params.json',
        'M5S': 'config/m5s_params.json',
        'M1S': 'config/m1s_params.json',
        'M15S': 'config/m15s_params.json',
        'TICK': 'config/tick_params.json',
        'MOM': 'config/momentum_params.json',
    }

    def get_config_path(self, label: str) -> str:
        """Get the default config file path for a bot label."""
        return self.CONFIG_PATHS.get(label, '')

    def start_bot(
        self, label: str, config_path: str | None = None, check_interval: int = 1,
        instance_id: str | None = None, config_overrides: dict | None = None,
    ):
        """Start a bot by label ('M1', 'M5', 'M15', 'LZ', 'M5S', 'TICK').

        If instance_id is provided, uses it as the key (allows multiple instances).
        Otherwise uses the label as key (single instance per type).

        config_overrides: dict of field_name -> value to override after loading
        the JSON config file. These are NOT persisted to disk.
        """
        key = instance_id or label
        if key in self.runners and self.runners[key].running:
            logger.warning(f"{key} bot is already running")
            return

        from src.core.config import load_config, TradingConfig

        if label == 'M1':
            path = config_path or 'config/m1_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.m1_scalping import M1ScalpingStrategy
            strategy = M1ScalpingStrategy(config)
            bot = BaseTradingBot(strategy, config)
            interval = check_interval or 1
        elif label == 'M5':
            path = config_path or 'config/m5_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.m5_scalping import M5ScalpingStrategy
            strategy = M5ScalpingStrategy(config)
            bot = BaseTradingBot(strategy, config)
            interval = check_interval or 15
        elif label == 'M15':
            path = config_path or 'config/m15_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.m15_scalping import M15ScalpingStrategy
            strategy = M15ScalpingStrategy(config)
            bot = BaseTradingBot(strategy, config)
            interval = check_interval or 1
        elif label == 'LZ':
            path = config_path or 'config/lz_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.liquidity_zones import LiquidityZoneStrategy
            strategy = LiquidityZoneStrategy(config)
            bot = ZoneBot(strategy, config)
            interval = check_interval or 1
        elif label == 'M5S':
            path = config_path or 'config/m5s_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.m5_sniper import M5SniperStrategy
            strategy = M5SniperStrategy(config)
            bot = SniperBot(strategy, config)
            interval = check_interval or 1
        elif label == 'M1S':
            path = config_path or 'config/m1s_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.m1_sniper import M1SniperStrategy
            strategy = M1SniperStrategy(config)
            bot = SniperBot(strategy, config)
            interval = check_interval or 1
        elif label == 'M15S':
            path = config_path or 'config/m15s_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            from src.strategy.m15_sniper import M15SniperStrategy
            strategy = M15SniperStrategy(config)
            bot = SniperBot(strategy, config)
            interval = check_interval or 1
        elif label == 'TICK':
            path = config_path or 'config/tick_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            bot = TickScalper(config)
            interval = check_interval or 1
        elif label == 'MOM':
            path = config_path or 'config/momentum_params.json'
            config = load_config(path)
            self._apply_overrides(config, config_overrides)
            bot = MomentumScalper(config)
            interval = check_interval or 1
        else:
            raise ValueError(f"Unknown bot label: {label}")

        # Log all overridden values for verification
        if config_overrides:
            logger.info(f"[{key}] Config overrides from GUI:")
            for field, value in config_overrides.items():
                logger.info(f"  {field} = {value}")

        runner = BotRunner(bot)
        runner.start(interval)
        self.runners[key] = runner
        logger.info(f"Started {key} bot")

    @staticmethod
    def _apply_overrides(config: 'TradingConfig', overrides: dict | None):
        """Apply GUI overrides to a loaded TradingConfig (mutates in place)."""
        if not overrides:
            return
        from src.core.config import TradingConfig
        for field_name, value in overrides.items():
            if field_name not in TradingConfig.__dataclass_fields__:
                logger.warning(f"Unknown config field: {field_name}")
                continue
            # Cast to the correct type based on the dataclass field
            field_type = TradingConfig.__dataclass_fields__[field_name].type
            try:
                if field_type == 'float' or field_type is float:
                    value = float(value)
                elif field_type == 'int' or field_type is int:
                    value = int(value)
                elif field_type == 'bool' or field_type is bool:
                    if isinstance(value, str):
                        value = value.lower() in ('true', '1', 'yes')
                setattr(config, field_name, value)
            except (ValueError, TypeError) as e:
                logger.warning(f"Cannot cast {field_name}={value}: {e}")

    def stop_bot(self, label: str):
        """Stop a bot by label or instance_id."""
        if label in self.runners:
            self.runners[label].stop()
            logger.info(f"Stopped {label} bot")

    def get_state(self, label: str) -> dict:
        """Get state for a specific bot (by label or instance_id)."""
        if label in self.runners:
            return self.runners[label].get_state()
        return {
            'bot_label': label,
            'status': 'Stopped',
            'positions': [],
            'indicators': {},
            'cooldown': {'active': False, 'reason': 'Not started'},
            'max_positions': 1,
            'consecutive_losses': 0,
            'trades_today': 0,
            'drawdown_pct': 0,
            'balance': 0,
            'equity': 0,
            'price': 0,
            'pp_active': False,
            'pp_override': None,
            'high_volatility': False,
            'trading_mode': 'both',
        }

    def get_logs(self, label: str) -> str:
        """Get recent logs for a bot (by label or instance_id)."""
        if label in self.runners:
            return self.runners[label].get_recent_logs()
        return ""

    def is_running(self, label: str) -> bool:
        return label in self.runners and self.runners[label].running

    def toggle_profit_protection(self, label: str) -> bool | None:
        """Cycle PP override."""
        if label not in self.runners:
            return None
        bot = self.runners[label].bot
        if bot.pp_override is None:
            bot.pp_override = True
        elif bot.pp_override is True:
            bot.pp_override = False
        else:
            bot.pp_override = None
        return bot.pp_override

    def toggle_trading_mode(self, label: str) -> str:
        """Cycle trading mode."""
        if label not in self.runners:
            return "both"
        bot = self.runners[label].bot
        current = bot.effective_trading_mode
        if current == "both":
            bot.trading_mode_override = "long_only"
        elif current == "long_only":
            bot.trading_mode_override = "short_only"
        else:
            bot.trading_mode_override = "both"
        return bot.effective_trading_mode

    def stop_all(self):
        for key in list(self.runners.keys()):
            self.stop_bot(key)
