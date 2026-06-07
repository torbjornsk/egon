"""
Egon Trading Dashboard v2

Layout: Left panel (bot instances + account) | Right panel (detail/config + tabs)
Bottom: Chart + Trade history + Log + Market + Sizing Calculator

Bot instances are config-file driven. Select a config, edit parameters inline,
Save/Save As to create new variants. No hardcoded bot types in the GUI.
"""

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
from pathlib import Path

from src.gui.theme import (
    BG_DARK, BG_MEDIUM, BG_LIGHT, FG, ACCENT, SUCCESS, ERROR, WARNING, NEUTRAL,
    setup_styles,
)
from src.services.bot_manager import BotManager
from src.services.market_data import MarketDataService
from src.services.trade_history import load_exit_reasons

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class BotInstancePanel:
    """Left panel: list of bot instances with status, plus account info."""

    def __init__(self, parent, bot_manager: BotManager, on_select_callback):
        self.bot_manager = bot_manager
        self.on_select = on_select_callback
        self.instances: list[dict] = []  # [{config_path, instance_id, running}]
        self.selected_index: int | None = None

        self.frame = tk.Frame(parent, bg=BG_DARK)
        self._build()

    def _build(self):
        f = self.frame

        # Account summary at top
        acc = tk.Frame(f, bg=BG_MEDIUM, padx=8, pady=6)
        acc.pack(fill=tk.X, padx=4, pady=(4, 6))

        self.balance_lbl = tk.Label(acc, text="Balance: --", bg=BG_MEDIUM, fg=FG,
                                    font=('Consolas', 10, 'bold'), anchor=tk.W)
        self.balance_lbl.pack(fill=tk.X)
        self.equity_lbl = tk.Label(acc, text="Equity: --", bg=BG_MEDIUM, fg=FG,
                                   font=('Consolas', 9), anchor=tk.W)
        self.equity_lbl.pack(fill=tk.X)
        self.price_lbl = tk.Label(acc, text="Price: --", bg=BG_MEDIUM, fg=WARNING,
                                  font=('Consolas', 9), anchor=tk.W)
        self.price_lbl.pack(fill=tk.X)

        # Separator
        tk.Frame(f, bg=BG_LIGHT, height=1).pack(fill=tk.X, padx=4)

        # Instance list header
        header = tk.Frame(f, bg=BG_DARK)
        header.pack(fill=tk.X, padx=4, pady=(6, 2))
        tk.Label(header, text="Bot Instances", bg=BG_DARK, fg=ACCENT,
                 font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        ttk.Button(header, text="+ New", command=self._new_instance, width=6).pack(side=tk.RIGHT)

        # Scrollable instance list
        list_frame = tk.Frame(f, bg=BG_DARK)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self.list_canvas = tk.Canvas(list_frame, bg=BG_DARK, highlightthickness=0)
        self.list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                            command=self.list_canvas.yview)
        self.list_inner = tk.Frame(self.list_canvas, bg=BG_DARK)

        self.list_inner.bind('<Configure>',
                            lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox('all')))
        self.list_canvas.create_window((0, 0), window=self.list_inner, anchor='nw')
        self.list_canvas.configure(yscrollcommand=self.list_scrollbar.set)

        self.list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.instance_widgets: list[tk.Frame] = []

    def refresh_config_list(self):
        """Scan config/ and rebuild the instance list from available configs."""
        configs = self.bot_manager.list_available_configs()
        self.instances = []
        for cfg in configs:
            # Only show configs with a recognized bot_type
            if cfg['bot_type'] in ('sniper', 'rsi_scalper', 'liquidity_zones',
                                   'tick_scalper', 'momentum'):
                instance_id = cfg['bot_label'] or cfg['filename']
                self.instances.append({
                    'config_path': cfg['path'],
                    'filename': cfg['filename'],
                    'config_name': cfg['config_name'],
                    'bot_type': cfg['bot_type'],
                    'bot_label': cfg['bot_label'],
                    'timeframe': cfg['timeframe'],
                    'instance_id': instance_id,
                })
        self._rebuild_list_widgets()

    def _rebuild_list_widgets(self):
        """Rebuild the instance list UI."""
        for w in self.instance_widgets:
            w.destroy()
        self.instance_widgets.clear()

        for i, inst in enumerate(self.instances):
            row = tk.Frame(self.list_inner, bg=BG_MEDIUM, padx=6, pady=4, cursor='hand2')
            row.pack(fill=tk.X, pady=(0, 2))
            row.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            # Status indicator
            is_running = self.bot_manager.is_running(inst['instance_id'])
            status_color = SUCCESS if is_running else NEUTRAL

            # First line: name + status dot
            top = tk.Frame(row, bg=BG_MEDIUM)
            top.pack(fill=tk.X)
            top.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            tk.Label(top, text="\u25cf", bg=BG_MEDIUM, fg=status_color,
                     font=('Arial', 10)).pack(side=tk.LEFT, padx=(0, 4))
            tk.Label(top, text=inst['config_name'], bg=BG_MEDIUM, fg=FG,
                     font=('Arial', 9, 'bold'), anchor=tk.W).pack(side=tk.LEFT)

            # Second line: type + timeframe + P/L
            if is_running:
                state = self.bot_manager.get_state(inst['instance_id'])
                positions = state.get('positions', [])
                total_pl = sum(p.get('profit', 0) for p in positions)
                n_pos = len(positions)
                pl_color = SUCCESS if total_pl > 0 else ERROR if total_pl < 0 else NEUTRAL
                detail = f"{inst['timeframe']} | {n_pos} pos | ${total_pl:+.2f}"
            else:
                detail = f"{inst['bot_type']} | {inst['timeframe']}"
                pl_color = NEUTRAL

            bottom = tk.Frame(row, bg=BG_MEDIUM)
            bottom.pack(fill=tk.X)
            bottom.bind('<Button-1>', lambda e, idx=i: self._select(idx))
            tk.Label(bottom, text=detail, bg=BG_MEDIUM, fg=pl_color,
                     font=('Consolas', 8), anchor=tk.W).pack(side=tk.LEFT, padx=(16, 0))

            # Highlight selected
            if self.selected_index == i:
                row.config(bg=BG_LIGHT)
                for child in row.winfo_children():
                    child.config(bg=BG_LIGHT)
                    for subchild in child.winfo_children():
                        subchild.config(bg=BG_LIGHT)

            self.instance_widgets.append(row)

    def _select(self, index: int):
        self.selected_index = index
        self._rebuild_list_widgets()
        if index < len(self.instances):
            self.on_select(self.instances[index])

    def _new_instance(self):
        """Create a new config file from a template."""
        self.on_select({'_new': True})

    def update_account(self, info: dict, price: float):
        self.balance_lbl.config(text=f"Balance: ${info.get('balance', 0):,.2f}")
        self.equity_lbl.config(text=f"Equity: ${info.get('equity', 0):,.2f}")
        self.price_lbl.config(text=f"Price: ${price:.2f}")

    def get_selected(self) -> dict | None:
        if self.selected_index is not None and self.selected_index < len(self.instances):
            return self.instances[self.selected_index]
        return None


class BotDetailPanel:
    """Right panel: config editing, controls, positions, indicators for selected bot."""

    def __init__(self, parent, bot_manager: BotManager, instance_panel: BotInstancePanel):
        self.bot_manager = bot_manager
        self.instance_panel = instance_panel
        self.current_instance: dict | None = None
        self.config_vars: dict[str, tk.StringVar] = {}
        self.loaded_config = None
        self.loaded_path: str = ''

        self.frame = tk.Frame(parent, bg=BG_DARK)
        self._build()

    def _build(self):
        f = self.frame

        # ── Header: config name + controls ──────────────────────────
        header = tk.Frame(f, bg=BG_DARK)
        header.pack(fill=tk.X, padx=6, pady=(6, 4))

        self.name_lbl = tk.Label(header, text="No bot selected", bg=BG_DARK, fg=ACCENT,
                                 font=('Arial', 11, 'bold'), anchor=tk.W)
        self.name_lbl.pack(side=tk.LEFT)

        self.status_lbl = tk.Label(header, text="", bg=BG_DARK, fg=NEUTRAL,
                                   font=('Arial', 9))
        self.status_lbl.pack(side=tk.LEFT, padx=(12, 0))

        # Control buttons
        ctrl = tk.Frame(f, bg=BG_DARK)
        ctrl.pack(fill=tk.X, padx=6, pady=(0, 4))

        self.start_btn = ttk.Button(ctrl, text="Start", command=self._start, width=7)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self._stop, width=6)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.mode_btn = ttk.Button(ctrl, text="Mode: Both", command=self._toggle_mode, width=10)
        self.mode_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.pp_btn = ttk.Button(ctrl, text="PP: Auto", command=self._toggle_pp, width=8)
        self.pp_btn.pack(side=tk.LEFT, padx=(0, 4))

        # Separator
        tk.Frame(f, bg=BG_LIGHT, height=1).pack(fill=tk.X, padx=6, pady=4)

        # ── Positions ───────────────────────────────────────────────
        self.pos_frame = tk.Frame(f, bg=BG_DARK)
        self.pos_frame.pack(fill=tk.X, padx=6, pady=(0, 4))
        self.pos_labels: list[tk.Label] = []

        # ── Indicators ──────────────────────────────────────────────
        self.ind_frame = tk.Frame(f, bg=BG_DARK)
        self.ind_frame.pack(fill=tk.X, padx=6, pady=(0, 4))
        self.ind_lbl = tk.Label(self.ind_frame, text="", bg=BG_DARK, fg=FG,
                                font=('Consolas', 9), anchor=tk.W, justify=tk.LEFT)
        self.ind_lbl.pack(fill=tk.X)

        # Separator
        tk.Frame(f, bg=BG_LIGHT, height=1).pack(fill=tk.X, padx=6, pady=4)

        # ── Config editing ──────────────────────────────────────────
        config_header = tk.Frame(f, bg=BG_DARK)
        config_header.pack(fill=tk.X, padx=6, pady=(0, 2))
        tk.Label(config_header, text="Configuration", bg=BG_DARK, fg=ACCENT,
                 font=('Arial', 9, 'bold')).pack(side=tk.LEFT)

        btn_frame = tk.Frame(config_header, bg=BG_DARK)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Save", command=self._save_config, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Save As", command=self._save_as_config, width=7).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Reload", command=self._reload_config, width=6).pack(side=tk.LEFT, padx=2)

        # Scrollable config fields
        config_container = tk.Frame(f, bg=BG_DARK)
        config_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        self.config_canvas = tk.Canvas(config_container, bg=BG_DARK, highlightthickness=0)
        self.config_scrollbar = ttk.Scrollbar(config_container, orient=tk.VERTICAL,
                                              command=self.config_canvas.yview)
        self.config_inner = tk.Frame(self.config_canvas, bg=BG_DARK)

        self.config_inner.bind('<Configure>',
                               lambda e: self.config_canvas.configure(
                                   scrollregion=self.config_canvas.bbox('all')))
        self.config_canvas.create_window((0, 0), window=self.config_inner, anchor='nw')
        self.config_canvas.configure(yscrollcommand=self.config_scrollbar.set)

        self.config_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.config_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel scrolling
        self.config_canvas.bind('<MouseWheel>',
                                lambda e: self.config_canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

    def show_instance(self, instance: dict):
        """Load and display a bot instance's config."""
        if instance.get('_new'):
            self._create_new_config()
            return

        self.current_instance = instance
        self.loaded_path = instance['config_path']
        self.name_lbl.config(text=instance['config_name'])
        self._load_config_fields()
        self._update_controls()

    def _load_config_fields(self):
        """Load config from file and build editable fields."""
        from src.core.config import load_config, TradingConfig

        self.config_vars.clear()
        for w in self.config_inner.winfo_children():
            w.destroy()

        if not self.loaded_path:
            return

        try:
            self.loaded_config = load_config(self.loaded_path)
        except Exception as e:
            logger.error(f"Failed to load {self.loaded_path}: {e}")
            self.loaded_config = TradingConfig()

        # Group fields by category
        field_groups = self._get_field_groups()

        for group_name, fields in field_groups.items():
            # Group header
            tk.Label(self.config_inner, text=group_name, bg=BG_DARK, fg=ACCENT,
                     font=('Consolas', 8, 'bold'), anchor=tk.W).pack(fill=tk.X, pady=(6, 2))

            for field_name in fields:
                if not hasattr(self.loaded_config, field_name):
                    continue
                value = getattr(self.loaded_config, field_name)

                row = tk.Frame(self.config_inner, bg=BG_DARK)
                row.pack(fill=tk.X, pady=1)

                tk.Label(row, text=f"{field_name}:", bg=BG_DARK, fg=NEUTRAL,
                         font=('Consolas', 8), width=30, anchor=tk.W).pack(side=tk.LEFT)

                # Serialize dicts and lists as JSON for display
                if isinstance(value, (dict, list)):
                    display_value = json.dumps(value) if value else '{}'
                    width = max(14, min(50, len(display_value)))
                else:
                    display_value = str(value)
                    width = 14

                var = tk.StringVar(value=display_value)
                entry = tk.Entry(row, textvariable=var, bg=BG_MEDIUM, fg=FG,
                                 font=('Consolas', 9), width=width, insertbackground=FG)
                entry.pack(side=tk.LEFT)
                self.config_vars[field_name] = var

    def _get_field_groups(self) -> dict[str, list[str]]:
        """Return config fields grouped by category for display."""
        config = self.loaded_config
        if not config:
            return {}

        bot_type = config.bot_type

        # Identity (always shown)
        identity = ['config_name', 'bot_type', 'timeframe', 'symbol', 'magic_number',
                    'bot_label', 'order_comment']

        # Sizing
        sizing = ['sizing_mode', 'risk_per_trade_pct', 'fixed_lots',
                  'position_size_pct', 'leverage', 'max_positions']

        # Entry/exit RSI (for sniper and rsi_scalper)
        rsi_fields = ['rsi_period', 'rsi_buy', 'rsi_sell', 'rsi_exit_long', 'rsi_exit_short']

        # Sniper-specific
        sniper_fields = ['sniper_rsi_offset', 'sniper_rsi_min', 'sniper_rsi_max',
                         'exit_rsi_trend_threshold', 'exit_rsi_trend_shift']

        # Breakeven & trailing
        trailing = ['breakeven_atr_trigger', 'breakeven_offset',
                    'trail_atr_after_breakeven', 'trail_atr_before_breakeven',
                    'tp_fallback_atr_mult']

        # ATR / stops
        atr_fields = ['atr_multiplier', 'atr_high_volatility_multiplier']

        # Direction control
        direction = ['enable_shorts', 'short_requires_downtrend', 'trading_mode', 'trend_filter']

        # Risk / protection
        risk = ['max_drawdown_limit', 'use_profit_protection',
                'profit_protection_auto_volatility', 'profit_protection_threshold_pct',
                'profit_protection_drawdown_limit_pct']

        # Loss backoff
        backoff = ['use_loss_backoff', 'loss_backoff_sl_only',
                   'loss_backoff_sl_threshold', 'loss_backoff_sl_candles',
                   'sl_tightening_factor']

        # Other
        other = ['data_refresh_interval_seconds', 'profit_target_pct',
                 'fast_ema', 'slow_ema']

        if bot_type == 'sniper':
            return {
                'Identity': identity,
                'Position Sizing': sizing,
                'RSI Entry/Exit': rsi_fields,
                'Sniper Limits': sniper_fields,
                'Breakeven & Trail': trailing,
                'ATR / Stops': atr_fields,
                'Direction': direction,
                'Risk Management': risk,
                'Loss Backoff': backoff,
                'Schedule & Guards': ['schedule', 'volatility_guard'],
                'Other': other,
            }
        elif bot_type == 'rsi_scalper':
            return {
                'Identity': identity,
                'Position Sizing': sizing,
                'RSI Entry/Exit': rsi_fields,
                'ATR / Stops': atr_fields,
                'Breakeven': ['breakeven_atr_trigger', 'breakeven_offset'],
                'Direction': direction,
                'Risk Management': risk,
                'Loss Backoff': backoff,
                'Other': other,
            }
        elif bot_type == 'tick_scalper':
            tick_fields = ['tick_entry_threshold', 'tick_exit_threshold',
                           'tick_cooldown_seconds', 'tick_max_trades_per_day']
            return {
                'Identity': identity,
                'Position Sizing': sizing,
                'Tick Parameters': tick_fields,
                'Risk Management': risk,
            }
        elif bot_type == 'momentum':
            mom_fields = ['entry_threshold', 'hold_threshold', 'signal_window',
                          'sl_atr_mult', 'cooldown_seconds', 'max_trades_per_day']
            return {
                'Identity': identity,
                'Position Sizing': sizing,
                'Momentum Parameters': mom_fields,
                'Risk Management': risk,
            }
        elif bot_type == 'liquidity_zones':
            zone_fields = ['zone_rr_ratio', 'zone_min_strength', 'zone_max_distance_atr',
                           'zone_lookback', 'zone_order_max_age_minutes']
            return {
                'Identity': identity,
                'Position Sizing': sizing,
                'Zone Parameters': zone_fields,
                'ATR / Stops': atr_fields,
                'Risk Management': risk,
            }
        else:
            # Fallback: show all
            return {'All': list(self.config_vars.keys())}

    def _save_config(self):
        """Save current GUI values back to the loaded config file."""
        if not self.loaded_path:
            return
        self._write_config_to_file(self.loaded_path)
        self.instance_panel.refresh_config_list()

    def _save_as_config(self):
        """Save current config to a new file."""
        from src.core.paths import resolve_path
        config_dir = str(resolve_path('config'))

        path = filedialog.asksaveasfilename(
            initialdir=config_dir,
            defaultextension='.json',
            filetypes=[('JSON files', '*.json')],
            title='Save Config As',
        )
        if path:
            self._write_config_to_file(path)
            self.loaded_path = path
            self.instance_panel.refresh_config_list()

    def _write_config_to_file(self, path: str):
        """Write current GUI field values to a JSON file."""
        from src.core.config import TradingConfig

        data = {}
        for field_name, var in self.config_vars.items():
            raw = var.get().strip()
            field_info = TradingConfig.__dataclass_fields__.get(field_name)
            if not field_info:
                data[field_name] = raw
                continue

            # Cast to correct type
            field_type = field_info.type
            try:
                if field_type == 'float' or field_type is float:
                    data[field_name] = float(raw)
                elif field_type == 'int' or field_type is int:
                    data[field_name] = int(raw)
                elif field_type == 'bool' or field_type is bool:
                    data[field_name] = raw.lower() in ('true', '1', 'yes')
                elif field_type == 'dict' or field_type is dict:
                    # Parse JSON string back to dict
                    if raw and raw != '{}':
                        data[field_name] = json.loads(raw)
                    else:
                        data[field_name] = {}
                elif field_type == 'list' or field_type is list:
                    if raw and raw != '[]':
                        data[field_name] = json.loads(raw)
                    else:
                        data[field_name] = []
                else:
                    data[field_name] = raw
            except (ValueError, TypeError, json.JSONDecodeError):
                data[field_name] = raw

        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Config saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            messagebox.showerror("Save Error", f"Failed to save: {e}")

    def _reload_config(self):
        """Reload config from file, discarding edits."""
        if self.loaded_path:
            self._load_config_fields()

    def _create_new_config(self):
        """Create a new config from a sniper template."""
        from src.core.paths import resolve_path
        from src.core.config import TradingConfig

        template = TradingConfig()
        template.config_name = "New Sniper Config"
        template.bot_type = "sniper"
        template.timeframe = "M5"
        template.magic_number = 234900  # Pick an unused magic number
        template.bot_label = "NEW"
        template.order_comment = "new_sniper"

        config_dir = str(resolve_path('config'))
        path = filedialog.asksaveasfilename(
            initialdir=config_dir,
            defaultextension='.json',
            filetypes=[('JSON files', '*.json')],
            title='Create New Config',
            initialfile='sniper_new.json',
        )
        if not path:
            return

        # Write template
        import dataclasses
        data = {}
        for field in dataclasses.fields(template):
            val = getattr(template, field.name)
            if not isinstance(val, (list, dict)):
                data[field.name] = val

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        self.loaded_path = path
        self.current_instance = {
            'config_path': path,
            'config_name': template.config_name,
            'bot_type': 'sniper',
            'instance_id': 'NEW',
        }
        self._load_config_fields()
        self.name_lbl.config(text=template.config_name)
        self.instance_panel.refresh_config_list()

    def _update_controls(self):
        """Update button states based on whether the bot is running."""
        if not self.current_instance:
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            return

        iid = self.current_instance.get('instance_id', '')
        is_running = self.bot_manager.is_running(iid)
        self.start_btn.config(state=tk.DISABLED if is_running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if is_running else tk.DISABLED)

    def _start(self):
        if not self.current_instance or not self.loaded_path:
            return
        iid = self.current_instance.get('instance_id', '')

        # Collect all config values from GUI as overrides
        overrides = {}
        for name, var in self.config_vars.items():
            overrides[name] = var.get().strip()

        self.bot_manager.start_from_config(
            config_path=self.loaded_path,
            instance_id=iid,
            check_interval=1,
            config_overrides=overrides,
        )
        self._update_controls()
        self.instance_panel._rebuild_list_widgets()

    def _stop(self):
        if not self.current_instance:
            return
        iid = self.current_instance.get('instance_id', '')
        self.bot_manager.stop_bot(iid)
        self._update_controls()
        self.instance_panel._rebuild_list_widgets()

    def _toggle_mode(self):
        if not self.current_instance:
            return
        iid = self.current_instance.get('instance_id', '')
        self.bot_manager.toggle_trading_mode(iid)

    def _toggle_pp(self):
        if not self.current_instance:
            return
        iid = self.current_instance.get('instance_id', '')
        self.bot_manager.toggle_profit_protection(iid)

    def update(self):
        """Update live state display for the selected bot."""
        if not self.current_instance:
            return

        iid = self.current_instance.get('instance_id', '')
        state = self.bot_manager.get_state(iid)

        # Status
        status = state.get('status', 'Stopped')
        color = SUCCESS if status == 'Running' else ERROR if status == 'Paused' else NEUTRAL
        self.status_lbl.config(text=status, foreground=color)
        self._update_controls()

        # Mode and PP buttons
        trading_mode = state.get('trading_mode', 'both')
        mode_short = {'both': 'Both', 'long_only': 'Long', 'short_only': 'Short'}
        self.mode_btn.config(text=f"Mode: {mode_short.get(trading_mode, 'Both')}")

        pp_override = state.get('pp_override')
        pp_text = 'Auto' if pp_override is None else 'ON' if pp_override else 'OFF'
        self.pp_btn.config(text=f"PP: {pp_text}")

        # Indicators
        ind = state.get('indicators', {})
        rsi = ind.get('rsi', 0)
        atr = ind.get('atr', 0)
        uptrend = ind.get('uptrend', False)
        trend = 'UP' if uptrend else 'DN' if ind.get('downtrend', False) else '--'
        dd = state.get('drawdown_pct', 0)
        trades = state.get('trades_today', 0)
        losses = state.get('consecutive_losses', 0)

        sniper = state.get('sniper', {})
        sniper_text = ""
        if sniper.get('buy_level'):
            sniper_text += f"  Sniper Buy: ${sniper['buy_level']:.2f}"
        if sniper.get('sell_level'):
            sniper_text += f"  Sniper Sell: ${sniper['sell_level']:.2f}"

        ind_text = (
            f"RSI: {rsi:.1f}  ATR: ${atr:.2f}  Trend: {trend}\n"
            f"DD: {dd:.1f}%  Trades: {trades}  Losses: {losses}"
        )
        if sniper_text:
            ind_text += f"\n{sniper_text}"

        # Schedule info
        sched = state.get('schedule', {})
        if sched.get('enabled'):
            if sched.get('paused'):
                ind_text += f"\nSchedule: PAUSED - {sched.get('next_resume', '')}"
            else:
                ind_text += "\nSchedule: Active"

        # Volatility guard info
        vg = state.get('volatility_guard', {})
        if vg.get('enabled'):
            if vg.get('paused'):
                ratio = vg.get('ratio', 0)
                ind_text += f"\nVol Guard: PAUSED (ATR {ratio:.1f}x median)"
            else:
                ratio = vg.get('ratio', 0)
                if ratio > 0:
                    ind_text += f"\nVol Guard: OK (ATR {ratio:.1f}x median)"

        self.ind_lbl.config(text=ind_text)

        # Positions
        positions = state.get('positions', [])
        max_pos = state.get('max_positions', 1)
        needed = max(max_pos, len(positions))

        while len(self.pos_labels) < needed:
            lbl = tk.Label(self.pos_frame, text="", bg=BG_LIGHT, fg=FG,
                           font=('Consolas', 9), anchor=tk.W, relief=tk.RAISED, padx=4, pady=2)
            lbl.pack(fill=tk.X, pady=(0, 1))
            self.pos_labels.append(lbl)

        for i, lbl in enumerate(self.pos_labels):
            if i < len(positions):
                pos = positions[i]
                d = pos.get('direction', '?')
                profit = pos.get('profit', 0)
                entry = pos.get('entry_price', 0)
                sl = pos.get('sl', 0)
                vol = pos.get('volume', 0)
                p_color = SUCCESS if profit > 0 else ERROR if profit < 0 else FG
                lbl.config(
                    text=f"{d} @ ${entry:.2f}  SL:${sl:.2f}  Vol:{vol}  P/L: ${profit:+.2f}",
                    fg=p_color,
                )
                lbl.pack(fill=tk.X, pady=(0, 1))
            elif i < needed:
                lbl.config(text="-- empty --", fg=NEUTRAL)
                lbl.pack(fill=tk.X, pady=(0, 1))
            else:
                lbl.pack_forget()


class SizingCalculator:
    """Position size calculator tab."""

    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=BG_DARK)
        self._build()

    def _build(self):
        f = self.frame
        f.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(f, text="Position Size Calculator", bg=BG_DARK, fg=ACCENT,
                 font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 8))

        # Input fields
        inputs = tk.Frame(f, bg=BG_DARK)
        inputs.pack(fill=tk.X, pady=(0, 8))

        self.vars = {}
        fields = [
            ('balance', 'Account Balance ($)', '10000'),
            ('risk_pct', 'Risk Per Trade (%)', '2.0'),
            ('sl_distance', 'Stop Loss Distance ($)', '2.50'),
            ('contract_size', 'Contract Size (oz/lot)', '100'),
        ]
        for field_id, label, default in fields:
            row = tk.Frame(inputs, bg=BG_DARK)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, bg=BG_DARK, fg=FG,
                     font=('Consolas', 9), width=24, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            var.trace_add('write', lambda *a: self._calculate())
            entry = tk.Entry(row, textvariable=var, bg=BG_MEDIUM, fg=FG,
                             font=('Consolas', 10), width=12, insertbackground=FG)
            entry.pack(side=tk.LEFT)
            self.vars[field_id] = var

        # Results
        tk.Frame(f, bg=BG_LIGHT, height=1).pack(fill=tk.X, pady=8)
        self.result_lbl = tk.Label(f, text="", bg=BG_DARK, fg=SUCCESS,
                                   font=('Consolas', 10), anchor=tk.W, justify=tk.LEFT)
        self.result_lbl.pack(fill=tk.X)
        self._calculate()

    def _calculate(self):
        try:
            balance = float(self.vars['balance'].get())
            risk_pct = float(self.vars['risk_pct'].get()) / 100.0
            sl_distance = float(self.vars['sl_distance'].get())
            contract_size = float(self.vars['contract_size'].get())

            if sl_distance <= 0 or contract_size <= 0:
                self.result_lbl.config(text="Invalid input", fg=ERROR)
                return

            risk_amount = balance * risk_pct
            lots = risk_amount / (sl_distance * contract_size)
            lots_rounded = round(lots / 0.01) * 0.01
            actual_risk = lots_rounded * sl_distance * contract_size

            text = (
                f"Risk Amount:  ${risk_amount:.2f}\n"
                f"Lot Size:     {lots_rounded:.2f} lots\n"
                f"Actual Risk:  ${actual_risk:.2f}\n"
                f"Per $1 Move:  ${lots_rounded * contract_size:.2f}\n"
                f"\n"
                f"If SL hits: lose ${actual_risk:.2f} ({actual_risk/balance*100:.2f}% of account)"
            )
            self.result_lbl.config(text=text, fg=SUCCESS)
        except (ValueError, ZeroDivisionError):
            self.result_lbl.config(text="Enter valid numbers", fg=NEUTRAL)


class EgonGUI:
    """Main GUI: left instance list, right detail, bottom chart/history/log."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Egon Trading Dashboard")
        self.root.geometry("1600x900")
        self.root.configure(bg=BG_DARK)

        setup_styles()

        self.bot_manager = BotManager()
        self.market = MarketDataService()
        self.market.connect()

        self.chart_timeframe = 'M5'
        self._market_update_counter = 0

        self._build_ui()
        self._update_loop()

    def _build_ui(self):
        # Main vertical split: top (instances + detail) | bottom (chart/history/log)
        main_paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg=BG_DARK,
                                    sashwidth=4, sashrelief=tk.RAISED)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # Top: horizontal split (instance list | bot detail)
        top_paned = tk.PanedWindow(main_paned, orient=tk.HORIZONTAL, bg=BG_DARK,
                                   sashwidth=4, sashrelief=tk.RAISED)
        main_paned.add(top_paned, height=420, minsize=250)

        # Left: instance list panel
        self.instance_panel = BotInstancePanel(
            top_paned, self.bot_manager, self._on_instance_selected
        )
        top_paned.add(self.instance_panel.frame, width=320, minsize=250)

        # Right: detail panel
        self.detail_panel = BotDetailPanel(top_paned, self.bot_manager, self.instance_panel)
        top_paned.add(self.detail_panel.frame, width=500, minsize=350)

        # Bottom: tabbed area (chart, trades, log, market, calculator)
        bottom = ttk.Notebook(main_paned)
        main_paned.add(bottom, minsize=200)

        # Chart tab
        if HAS_MATPLOTLIB:
            chart_frame = tk.Frame(bottom, bg=BG_DARK)
            bottom.add(chart_frame, text=" Chart ")
            self._build_chart(chart_frame)

        # Trade history tab
        hist_frame = tk.Frame(bottom, bg=BG_DARK)
        bottom.add(hist_frame, text=" Trades ")
        self._build_trade_history(hist_frame)

        # Log tab
        log_frame = tk.Frame(bottom, bg=BG_DARK)
        bottom.add(log_frame, text=" Log ")
        self._build_log(log_frame)

        # Market tab
        market_frame = tk.Frame(bottom, bg=BG_DARK)
        bottom.add(market_frame, text=" Market ")
        self._build_market_tab(market_frame)

        # Sizing calculator tab
        calc_frame = tk.Frame(bottom, bg=BG_DARK)
        bottom.add(calc_frame, text=" Sizing Calc ")
        self.sizing_calc = SizingCalculator(calc_frame)

        # Load configs
        self.instance_panel.refresh_config_list()

    def _on_instance_selected(self, instance: dict):
        self.detail_panel.show_instance(instance)

    # ── Chart ───────────────────────────────────────────────────────

    def _build_chart(self, parent):
        chart_ctrl = tk.Frame(parent, bg=BG_DARK)
        chart_ctrl.pack(fill=tk.X, padx=6, pady=(4, 0))
        self.chart_tf_var = tk.StringVar(value='M5')
        for tf in ['M1', 'M5', 'M15']:
            ttk.Radiobutton(chart_ctrl, text=tf, variable=self.chart_tf_var, value=tf,
                            command=lambda: setattr(self, 'chart_timeframe', self.chart_tf_var.get())
                            ).pack(side=tk.LEFT, padx=3)

        self.fig = Figure(figsize=(10, 3), dpi=100, facecolor=BG_DARK)
        self.ax = self.fig.add_subplot(111, facecolor=BG_MEDIUM)
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 4))

    # ── Trade history ───────────────────────────────────────────────

    def _build_trade_history(self, parent):
        cols = ('Time', 'Bot', 'Type', 'Entry', 'Exit', 'Profit', 'Reason')
        self.trade_tree = ttk.Treeview(parent, columns=cols, show='headings', height=10)
        for c in cols:
            self.trade_tree.heading(c, text=c)
        self.trade_tree.column('Time', width=100)
        self.trade_tree.column('Bot', width=50)
        self.trade_tree.column('Type', width=45)
        self.trade_tree.column('Entry', width=70)
        self.trade_tree.column('Exit', width=70)
        self.trade_tree.column('Profit', width=65)
        self.trade_tree.column('Reason', width=200)

        tree_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=tree_scroll.set)
        self.trade_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=4)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 6), pady=4)
        self.trade_tree.tag_configure('profit', foreground=SUCCESS)
        self.trade_tree.tag_configure('loss', foreground=ERROR)

    # ── Log ─────────────────────────────────────────────────────────

    def _build_log(self, parent):
        self.log_text = tk.Text(parent, wrap=tk.WORD, bg=BG_MEDIUM, fg=FG,
                                font=('Consolas', 8), height=12)
        log_scroll = ttk.Scrollbar(parent, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=4)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 6), pady=4)

    # ── Market dashboard ────────────────────────────────────────────

    def _build_market_tab(self, parent):
        grid_frame = tk.Frame(parent, bg=BG_DARK)
        grid_frame.pack(fill=tk.X, padx=6, pady=(6, 4))

        headers = ['', 'RSI', 'ATR', 'Trend', 'EMA9', 'EMA21', 'Close']
        for col, h in enumerate(headers):
            tk.Label(grid_frame, text=h, bg=BG_DARK, fg=ACCENT,
                     font=('Consolas', 9, 'bold'), width=10, anchor=tk.CENTER
                     ).grid(row=0, column=col, padx=2, pady=(0, 4))

        self.market_labels: dict[str, dict[str, tk.Label]] = {}
        for row, tf in enumerate(['M1', 'M5', 'M15'], start=1):
            tk.Label(grid_frame, text=tf, bg=BG_DARK, fg=FG,
                     font=('Consolas', 9, 'bold')).grid(row=row, column=0, padx=2)
            labels = {}
            for col, key in enumerate(['rsi', 'atr', 'trend', 'ema_fast', 'ema_slow', 'close'], start=1):
                lbl = tk.Label(grid_frame, text="--", bg=BG_MEDIUM, fg=FG,
                               font=('Consolas', 9), width=10, anchor=tk.CENTER,
                               relief=tk.FLAT, padx=3, pady=2)
                lbl.grid(row=row, column=col, padx=2, pady=1)
                labels[key] = lbl
            self.market_labels[tf] = labels

        # Spread info
        tk.Frame(parent, bg=BG_LIGHT, height=1).pack(fill=tk.X, padx=6, pady=4)
        spread_row = tk.Frame(parent, bg=BG_DARK)
        spread_row.pack(fill=tk.X, padx=6, pady=(0, 4))

        tk.Label(spread_row, text="Spread:", bg=BG_DARK, fg=NEUTRAL,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        self.spread_lbl = tk.Label(spread_row, text="--", bg=BG_DARK, fg=WARNING,
                                   font=('Consolas', 9, 'bold'))
        self.spread_lbl.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(spread_row, text="Bid:", bg=BG_DARK, fg=NEUTRAL,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        self.bid_lbl = tk.Label(spread_row, text="--", bg=BG_DARK, fg=FG,
                                font=('Consolas', 9))
        self.bid_lbl.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(spread_row, text="Ask:", bg=BG_DARK, fg=NEUTRAL,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        self.ask_lbl = tk.Label(spread_row, text="--", bg=BG_DARK, fg=FG,
                                font=('Consolas', 9))
        self.ask_lbl.pack(side=tk.LEFT)

    # ── Update loop ─────────────────────────────────────────────────

    def _update_loop(self):
        try:
            self._update_account()
            self.detail_panel.update()
            self.instance_panel._rebuild_list_widgets()

            if HAS_MATPLOTLIB:
                self._update_chart()
            self._update_trade_history()
            self._update_log()

            self._market_update_counter += 1
            if self._market_update_counter >= 5:
                self._market_update_counter = 0
                self._update_market()
        except Exception as e:
            logger.error(f"GUI update error: {e}")
        self.root.after(1000, self._update_loop)

    def _update_account(self):
        info = self.market.get_account_info()
        price = self.market.get_price()
        self.instance_panel.update_account(info, price)

    def _update_chart(self):
        if not self.market.connected:
            return
        try:
            bars = 100 if self.chart_timeframe == 'M1' else 60 if self.chart_timeframe == 'M15' else 50
            df = self.market.get_chart_data(self.chart_timeframe, bars)
            if df is None or len(df) == 0:
                return
            self.ax.clear()
            for i in range(len(df)):
                row = df.iloc[i]
                color = SUCCESS if row['close'] >= row['open'] else ERROR
                body_h = abs(row['close'] - row['open'])
                body_b = min(row['open'], row['close'])
                rect = Rectangle((i - 0.3, body_b), 0.6, body_h,
                                 facecolor=color, edgecolor=color, alpha=0.8)
                self.ax.add_patch(rect)
                self.ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=1, alpha=0.6)

            # Mark sniper levels if a sniper bot is selected
            selected = self.instance_panel.get_selected()
            if selected:
                state = self.bot_manager.get_state(selected.get('instance_id', ''))
                sniper = state.get('sniper', {})
                if sniper.get('buy_level'):
                    self.ax.axhline(sniper['buy_level'], color=SUCCESS, linestyle='--',
                                    alpha=0.6, linewidth=1)
                if sniper.get('sell_level'):
                    self.ax.axhline(sniper['sell_level'], color=ERROR, linestyle='--',
                                    alpha=0.6, linewidth=1)

            self.ax.set_xlim(-1, len(df))
            self.ax.set_ylim(df['low'].min() * 0.9999, df['high'].max() * 1.0001)
            self.ax.tick_params(colors=FG, labelsize=7)
            for spine in self.ax.spines.values():
                spine.set_color(BG_LIGHT)
            self.ax.grid(True, alpha=0.2, color=BG_LIGHT)
            self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
            self.canvas.draw()
        except Exception as e:
            logger.error(f"Chart error: {e}")

    def _update_trade_history(self):
        history = self.market.get_trade_history()
        exit_reasons = load_exit_reasons()
        for item in self.trade_tree.get_children():
            self.trade_tree.delete(item)
        for pos in history[:50]:
            ticket_str = str(pos.get('ticket', ''))
            pid_str = str(pos.get('position_id', ''))
            reason = exit_reasons.get(ticket_str, {}).get('reason') or \
                     exit_reasons.get(pid_str, {}).get('reason') or 'Unknown'
            tag = 'profit' if pos['profit'] > 0 else 'loss'
            self.trade_tree.insert('', tk.END, values=(
                pos['exit_time'].strftime('%m-%d %H:%M'),
                pos['bot'], pos['type'],
                f"${pos['entry_price']:.2f}", f"${pos['exit_price']:.2f}",
                f"${pos['profit']:.2f}", reason,
            ), tags=(tag,))

    def _update_log(self):
        """Collect logs from all running bots."""
        all_logs = ""
        for key, runner in self.bot_manager.runners.items():
            if runner.running:
                new = runner.get_recent_logs()
                if new:
                    all_logs += new
        if all_logs:
            self.log_text.insert(tk.END, all_logs)
            line_count = int(self.log_text.index('end-1c').split('.')[0])
            if line_count > 2000:
                self.log_text.delete('1.0', f'{line_count - 1500}.0')
            self.log_text.see(tk.END)

    def _update_market(self):
        try:
            overview = self.market.get_market_overview()
        except Exception as e:
            logger.error(f"Market dashboard error: {e}")
            return

        for tf in ['M1', 'M5', 'M15']:
            data = overview.get(tf)
            labels = self.market_labels.get(tf, {})
            if not data:
                for lbl in labels.values():
                    lbl.config(text="--", fg=NEUTRAL)
                continue

            rsi = data['rsi']
            if rsi < 30:
                rsi_color = SUCCESS
            elif rsi < 40:
                rsi_color = '#66cc66'
            elif rsi > 70:
                rsi_color = ERROR
            elif rsi > 60:
                rsi_color = '#cc6666'
            else:
                rsi_color = FG
            labels['rsi'].config(text=f"{rsi:.1f}", fg=rsi_color)
            labels['atr'].config(text=f"${data['atr']:.2f}", fg=FG)

            if data['uptrend']:
                labels['trend'].config(text="UP", fg=SUCCESS)
            else:
                labels['trend'].config(text="DOWN", fg=ERROR)

            labels['ema_fast'].config(text=f"${data['ema_fast']:.2f}", fg=FG)
            labels['ema_slow'].config(text=f"${data['ema_slow']:.2f}", fg=FG)
            labels['close'].config(text=f"${data['close']:.2f}", fg=FG)

        spread = overview.get('spread', 0)
        spread_color = SUCCESS if spread < 0.30 else WARNING if spread < 0.50 else ERROR
        self.spread_lbl.config(text=f"${spread:.3f}", fg=spread_color)
        self.bid_lbl.config(text=f"${overview.get('bid', 0):.2f}")
        self.ask_lbl.config(text=f"${overview.get('ask', 0):.2f}")

    def on_closing(self):
        self.bot_manager.stop_all()
        self.market.disconnect()
        self.root.destroy()
