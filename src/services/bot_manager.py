"""
Bot manager  --  starts/stops bots in background threads.

The GUI creates a BotManager, starts bots, and reads their state via get_state().
Bots run in-process (not as subprocesses), so the GUI has direct access to
the bot's state dict  --  single source of truth, no log parsing needed.

Bot types are registered in BOT_REGISTRY. Adding a new type requires only:
1. A strategy class + bot class
2. One entry in BOT_REGISTRY
3. A config JSON file with bot_type set
"""

import logging
import threading
import io
from pathlib import Path

from src.bot.base import BaseTradingBot
from src.bot.zone_bot import ZoneBot
from src.bot.sniper_bot import SniperBot
from src.bot.tick_scalper import TickScalper
from src.bot.momentum_scalper import MomentumScalper

logger = logging.getLogger(__name__)


class BotRunner:
    """Wraps a trading bot with thread management and log capture."""

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

        # Mark bot as using a shared MT5 connection (GUI owns it)
        if hasattr(self.bot, '_shared_connection'):
            self.bot._shared_connection = True

        # Capture log output for THIS bot only (bot-specific logger)
        bot_label = self._get_bot_label()
        bot_logger = logging.getLogger(f"src.bot.{bot_label}")
        self._log_handler = logging.StreamHandler(self.log_buffer)
        self._log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        bot_logger.addHandler(self._log_handler)
        bot_logger.propagate = True

        self.thread = threading.Thread(
            target=self._run, args=(check_interval,),
            daemon=True,
            name=f"egon-{bot_label}",
        )
        self.thread.start()

    def _get_bot_label(self) -> str:
        if hasattr(self.bot, 'strategy'):
            return self.bot.strategy.bot_label
        if hasattr(self.bot, 'config'):
            return self.bot.config.bot_label
        return "unknown"

    def _run(self, check_interval: int):
        try:
            self.bot.run(check_interval=check_interval)
        except Exception as e:
            logger.error(f"Bot {self._get_bot_label()} crashed: {e}", exc_info=True)
        finally:
            self.running = False

    def stop(self):
        """Signal the bot to stop cleanly."""
        self.running = False
        self.bot._stop_requested = True
        if self._log_handler:
            bot_label = self._get_bot_label()
            bot_logger = logging.getLogger(f"src.bot.{bot_label}")
            bot_logger.removeHandler(self._log_handler)

    def get_state(self) -> dict:
        """Get the bot's current state snapshot."""
        if not self.running:
            return {
                'bot_label': self._get_bot_label(),
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
                'bot_label': self._get_bot_label(),
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


def _create_sniper_bot(config):
    """Factory: create a SniperBot from config."""
    from src.strategy.sniper import SniperStrategy
    strategy = SniperStrategy(config)
    return SniperBot(strategy, config)


def _create_rsi_scalper_bot(config):
    """Factory: create a BaseTradingBot with the appropriate RSI scalping strategy."""
    from src.core.broker import TIMEFRAME_MINUTES
    tf = config.timeframe
    if tf == 'M1':
        from src.strategy.m1_scalping import M1ScalpingStrategy
        strategy = M1ScalpingStrategy(config)
    elif tf == 'M15':
        from src.strategy.m15_scalping import M15ScalpingStrategy
        strategy = M15ScalpingStrategy(config)
    else:
        from src.strategy.m5_scalping import M5ScalpingStrategy
        strategy = M5ScalpingStrategy(config)
    return BaseTradingBot(strategy, config)


def _create_zone_bot(config):
    """Factory: create a ZoneBot."""
    from src.strategy.liquidity_zones import LiquidityZoneStrategy
    strategy = LiquidityZoneStrategy(config)
    return ZoneBot(strategy, config)


def _create_tick_bot(config):
    """Factory: create a TickScalper."""
    return TickScalper(config)


def _create_momentum_bot(config):
    """Factory: create a MomentumScalper."""
    return MomentumScalper(config)


def _create_breakout_bot(config):
    """Factory: create a BaseTradingBot with BreakoutStrategy."""
    from src.strategy.breakout import BreakoutStrategy
    strategy = BreakoutStrategy(config)
    return BaseTradingBot(strategy, config)


# Registry: bot_type -> factory function
BOT_REGISTRY: dict[str, callable] = {
    'sniper': _create_sniper_bot,
    'rsi_scalper': _create_rsi_scalper_bot,
    'liquidity_zones': _create_zone_bot,
    'tick_scalper': _create_tick_bot,
    'momentum': _create_momentum_bot,
    'breakout': _create_breakout_bot,
}

# Legacy label -> (bot_type, default config path) mapping for backward compat
LEGACY_LABEL_MAP: dict[str, tuple[str, str]] = {
    'M5S': ('sniper', 'config/m5s_params.json'),
    'M1S': ('sniper', 'config/m1s_params.json'),
    'M15S': ('sniper', 'config/m15s_params.json'),
    'M5': ('rsi_scalper', 'config/m5_params.json'),
    'M1': ('rsi_scalper', 'config/m1_params.json'),
    'M15': ('rsi_scalper', 'config/m15_params.json'),
    'LZ': ('liquidity_zones', 'config/lz_params.json'),
    'TICK': ('tick_scalper', 'config/tick_params.json'),
    'MOM': ('momentum', 'config/momentum_params.json'),
    'BRK': ('breakout', 'config/breakout_params.json'),
}


class BotManager:
    """Manages bot instances for the GUI."""

    def __init__(self):
        self.runners: dict[str, BotRunner] = {}

    def get_config_path(self, label: str) -> str:
        """Get the default config file path for a bot label."""
        if label in LEGACY_LABEL_MAP:
            return LEGACY_LABEL_MAP[label][1]
        return ''

    def start_from_config(
        self, config_path: str, instance_id: str | None = None,
        check_interval: int = 1, config_overrides: dict | None = None,
    ):
        """
        Start a bot from a config file. The config's bot_type field determines
        which bot/strategy classes to instantiate.

        This is the preferred way to start bots -- fully config-driven.
        """
        from src.core.config import load_config

        config = load_config(config_path)
        self._apply_overrides(config, config_overrides)

        bot_type = config.bot_type
        if bot_type not in BOT_REGISTRY:
            raise ValueError(
                f"Unknown bot_type '{bot_type}' in {config_path}. "
                f"Valid types: {list(BOT_REGISTRY.keys())}"
            )

        key = instance_id or config.bot_label
        if key in self.runners and self.runners[key].running:
            logger.warning(f"{key} bot is already running")
            return

        factory = BOT_REGISTRY[bot_type]
        bot = factory(config)

        if config_overrides:
            logger.info(f"[{key}] Config overrides from GUI:")
            for field, value in config_overrides.items():
                logger.info(f"  {field} = {value}")

        runner = BotRunner(bot)
        runner.start(check_interval)
        self.runners[key] = runner
        logger.info(f"Started {key} bot (type={bot_type}, config={config_path})")

    def start_bot(
        self, label: str, config_path: str | None = None, check_interval: int = 1,
        instance_id: str | None = None, config_overrides: dict | None = None,
    ):
        """
        Start a bot by legacy label (backward compatible).

        Internally maps labels to bot_type + config path, then delegates
        to start_from_config.
        """
        if label not in LEGACY_LABEL_MAP:
            raise ValueError(
                f"Unknown bot label: {label}. "
                f"Valid labels: {list(LEGACY_LABEL_MAP.keys())}"
            )

        bot_type, default_path = LEGACY_LABEL_MAP[label]
        path = config_path or default_path
        instance = instance_id or label

        self.start_from_config(
            config_path=path,
            instance_id=instance,
            check_interval=check_interval,
            config_overrides=config_overrides,
        )

    @staticmethod
    def _apply_overrides(config, overrides: dict | None):
        """Apply GUI overrides to a loaded TradingConfig (mutates in place)."""
        if not overrides:
            return
        import json as _json
        from src.core.config import TradingConfig
        for field_name, value in overrides.items():
            if field_name not in TradingConfig.__dataclass_fields__:
                logger.warning(f"Unknown config field: {field_name}")
                continue
            field_type = TradingConfig.__dataclass_fields__[field_name].type
            try:
                if field_type == 'float' or field_type is float:
                    value = float(value)
                elif field_type == 'int' or field_type is int:
                    value = int(value)
                elif field_type == 'bool' or field_type is bool:
                    if isinstance(value, str):
                        value = value.lower() in ('true', '1', 'yes')
                elif field_type == 'dict' or field_type is dict:
                    if isinstance(value, str):
                        value = _json.loads(value) if value.strip() else {}
                elif field_type == 'list' or field_type is list:
                    if isinstance(value, str):
                        value = _json.loads(value) if value.strip() else []
                setattr(config, field_name, value)
            except (ValueError, TypeError, _json.JSONDecodeError) as e:
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

    @staticmethod
    def list_available_configs() -> list[dict]:
        """
        Scan config/ directory for all JSON configs and return their metadata.

        Returns list of dicts with: path, config_name, bot_type, bot_label, timeframe
        """
        from src.core.paths import resolve_path
        import json

        config_dir = resolve_path('config')
        configs = []

        for f in sorted(config_dir.glob('*.json')):
            try:
                with open(f, 'r') as fp:
                    raw = json.load(fp)
                configs.append({
                    'path': str(f),
                    'filename': f.name,
                    'config_name': raw.get('config_name', f.stem),
                    'bot_type': raw.get('bot_type', 'unknown'),
                    'bot_label': raw.get('bot_label', ''),
                    'timeframe': raw.get('timeframe', ''),
                    'strategy': raw.get('strategy', ''),
                })
            except Exception:
                continue

        return configs
