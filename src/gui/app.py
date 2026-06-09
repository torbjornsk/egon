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

# Fields that should render as dropdowns with specific choices
DROPDOWN_FIELDS: dict[str, list[str]] = {
    'sizing_mode': ['risk_pct', 'fixed', 'atr_adaptive'],
    'trading_mode': ['both', 'long_only', 'short_only'],
    'timeframe': ['M1', 'M5', 'M15', 'H1'],
    'trend_filter': ['none', 'ema_cross', 'ema_200'],
    'bot_type': ['sniper', 'rsi_scalper', 'liquidity_zones', 'tick_scalper', 'momentum', 'breakout'],
    'breakeven_mode': ['first_pip', 'atr_threshold'],
    'rhythm_mode': ['manual', 'gated', 'dynamic'],
    'rhythm_htf_timeframe': ['M5', 'M15', 'H1', 'H4'],
}

# Human-readable labels for config fields
FIELD_LABELS: dict[str, str] = {
    'config_name': 'Config Name',
    'bot_type': 'Bot Type',
    'timeframe': 'Timeframe',
    'symbol': 'Symbol',
    'magic_number': 'Magic Number',
    'bot_label': 'Bot Label',
    'sizing_mode': 'Sizing Mode',
    'risk_per_trade_pct': 'Risk Per Trade (%)',
    'fixed_lots': 'Fixed Lots',
    'atr_damping': 'ATR Damping',
    'max_positions': 'Max Positions',
    'rsi_period': 'RSI Period',
    'rsi_buy': 'Buy Below RSI',
    'rsi_sell': 'Sell Above RSI',
    'sniper_rsi_offset': 'Limit Order Offset',
    'exit_rsi': 'Exit RSI (legacy)',
    'exit_rsi_long': 'Exit RSI Long (>=)',
    'exit_rsi_short': 'Exit RSI Short (<=)',
    'tp_rsi_long': 'TP Order RSI Long (spike)',
    'tp_rsi_short': 'TP Order RSI Short (spike)',
    'tp_fallback_atr_mult': 'TP Fallback (x ATR)',
    'adaptive_exit_enabled': 'Adaptive Exit',
    'exit_rsi_trend_threshold': 'Trend Threshold (ATR)',
    'exit_rsi_trend_shift': 'Trend Shift (RSI pts)',
    'atr_multiplier': 'SL Distance (x ATR)',
    'atr_high_volatility_multiplier': 'High-Vol SL Scale',
    'breakeven_atr_trigger': 'BE Trigger (x ATR)',
    'breakeven_offset': 'BE Offset (x ATR)',
    'trail_atr_after_breakeven': 'Trail After BE (ATR)',
    'trail_atr_before_breakeven': 'Trail Before BE (ATR)',
    'enable_shorts': 'Enable Shorts',
    'trading_mode': 'Trading Mode',
    'max_drawdown_limit': 'Max Drawdown (%)',
    'use_profit_protection': 'Profit Protection',
    'fast_ema': 'Fast EMA',
    'slow_ema': 'Slow EMA',
    'schedule': 'Schedule (JSON)',
    'volatility_guard': 'Volatility Guard (JSON)',
    'schedule_enabled': 'Schedule Enabled',
    'schedule_mon': 'Monday Hours',
    'schedule_tue': 'Tuesday Hours',
    'schedule_wed': 'Wednesday Hours',
    'schedule_thu': 'Thursday Hours',
    'schedule_fri': 'Friday Hours',
    'schedule_sat': 'Saturday Hours',
    'schedule_sun': 'Sunday Hours',
    'schedule_closed': 'Closed Windows',
    'vg_enabled': 'Vol Guard Enabled',
    'vg_atr_spike_multiplier': 'Spike Threshold (x)',
    'vg_cooldown_minutes': 'Cooldown (min)',
    'vg_resume_below_multiplier': 'Resume Below (x)',
    'breakout_bars': 'Breakout Bars (N)',
    'breakout_entry_buffer_atr': 'Entry Buffer (x ATR)',
    'breakout_min_atr': 'Min ATR ($)',
    'breakout_re_entry_bars': 'Re-entry Cooldown (bars)',
    'breakout_sl_atr_mult': 'SL Distance (x ATR)',
    'breakout_trail_atr_mult': 'Trail Distance (x ATR)',
    'breakout_max_daily_loss_pct': 'Max Daily Loss (%)',
    'breakout_max_daily_trades': 'Max Daily Trades',
    'breakout_max_drawdown_pct': 'Max Total Drawdown (%)',
    'breakeven_mode': 'Breakeven Mode',
    'reentry_cooldown_bars': 'Reentry Pause (bars)',
    'trail_interval_ms': 'Trail Update (ms)',
    'rhythm_enabled': 'Rhythm Enabled',
    'rhythm_mode': 'Rhythm Mode',
    'rhythm_min_amplitude_atr': 'Min Amplitude (x ATR)',
    'rhythm_max_cycle_bars': 'Max Cycle (bars)',
    'rhythm_min_cycle_bars': 'Min Cycle (bars)',
    'rhythm_dead_atr_factor': 'Dead ATR Factor',
    'rhythm_htf_timeframe': 'HTF Timeframe',
    'rhythm_support_aware_sniper': 'Support-Aware Sniper',
    'shield_enabled': 'Shield Enabled',
    'shield_rapid_sl_candles': 'Rapid SL Threshold (bars)',
    'shield_reduced_size_factor': 'Post-Shield Size Factor',
    'shield_reduced_size_trades': 'Reduced Size Trades',
}

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

        # Mouse wheel scrolling for the instance list
        self.list_canvas.bind('<MouseWheel>',
                              lambda e: self.list_canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

        self.instance_widgets: list[tk.Frame] = []
        self._row_refs: list[dict] = []

    def refresh_config_list(self):
        """Scan config/ and rebuild the instance list from available configs."""
        from src.services.bot_manager import BOT_REGISTRY
        configs = self.bot_manager.list_available_configs()
        self.instances = []
        for cfg in configs:
            # Only show configs with a recognized bot_type (registered in BOT_REGISTRY)
            if cfg['bot_type'] in BOT_REGISTRY:
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
        """Build the instance list UI. Called once on config load and on selection change."""
        for w in self.instance_widgets:
            w.destroy()
        self.instance_widgets.clear()
        self._row_refs = []  # Store references to mutable labels per row

        for i, inst in enumerate(self.instances):
            bg = BG_LIGHT if self.selected_index == i else BG_MEDIUM

            row = tk.Frame(self.list_inner, bg=bg, padx=6, pady=4, cursor='hand2')
            row.pack(fill=tk.X, pady=(0, 2))
            row.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            # First line: status dot + name
            top = tk.Frame(row, bg=bg)
            top.pack(fill=tk.X)
            top.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            dot_lbl = tk.Label(top, text="\u25cf", bg=bg, fg=NEUTRAL,
                               font=('Arial', 10))
            dot_lbl.pack(side=tk.LEFT, padx=(0, 4))
            dot_lbl.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            name_lbl = tk.Label(top, text=inst['config_name'], bg=bg, fg=FG,
                                font=('Arial', 9, 'bold'), anchor=tk.W)
            name_lbl.pack(side=tk.LEFT)
            name_lbl.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            # Second line: detail (updated live)
            bottom = tk.Frame(row, bg=bg)
            bottom.pack(fill=tk.X)
            bottom.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            detail_lbl = tk.Label(bottom, text=f"{inst['bot_type']} | {inst['timeframe']}",
                                  bg=bg, fg=NEUTRAL, font=('Consolas', 8), anchor=tk.W)
            detail_lbl.pack(side=tk.LEFT, padx=(16, 0))
            detail_lbl.bind('<Button-1>', lambda e, idx=i: self._select(idx))

            self.instance_widgets.append(row)
            self._row_refs.append({
                'row': row, 'top': top, 'bottom': bottom,
                'dot': dot_lbl, 'name': name_lbl, 'detail': detail_lbl,
            })

        # Initial status update
        self.update_status()

    def update_status(self):
        """Update status dots and detail text without rebuilding widgets."""
        for i, inst in enumerate(self.instances):
            if i >= len(self._row_refs):
                break
            refs = self._row_refs[i]

            is_running = self.bot_manager.is_running(inst['instance_id'])
            status_color = SUCCESS if is_running else NEUTRAL
            refs['dot'].config(fg=status_color)

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

            refs['detail'].config(text=detail, fg=pl_color)

    def _select(self, index: int):
        self.selected_index = index
        # Update highlight colors without full rebuild
        for i, refs in enumerate(self._row_refs):
            bg = BG_LIGHT if i == index else BG_MEDIUM
            refs['row'].config(bg=bg)
            refs['top'].config(bg=bg)
            refs['bottom'].config(bg=bg)
            refs['dot'].config(bg=bg)
            refs['name'].config(bg=bg)
            refs['detail'].config(bg=bg)
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
    """A single bot detail column: config editing, controls, positions, indicators."""

    def __init__(self, parent, bot_manager: BotManager, instance_panel, on_close_callback, instance: dict):
        self.bot_manager = bot_manager
        self.instance_panel = instance_panel
        self.on_close = on_close_callback
        self.current_instance: dict = instance
        self.config_vars: dict[str, tk.StringVar] = {}
        self.loaded_config = None
        self.loaded_path: str = instance.get('config_path', '')

        # Fixed-width column frame
        self.frame = tk.Frame(parent, bg=BG_DARK, width=420, relief=tk.GROOVE, borderwidth=1)
        self.frame.pack_propagate(False)
        self._build()
        self._load_config_fields()
        self._update_controls()

    def _build(self):
        f = self.frame

        # ── Header: config name + close button ──────────────────────
        header = tk.Frame(f, bg=BG_DARK)
        header.pack(fill=tk.X, padx=6, pady=(6, 4))

        self.name_lbl = tk.Label(header, text=self.current_instance.get('config_name', ''),
                                 bg=BG_DARK, fg=ACCENT,
                                 font=('Arial', 10, 'bold'), anchor=tk.W)
        self.name_lbl.pack(side=tk.LEFT)

        # Close button (stops bot + removes panel)
        close_btn = tk.Label(header, text="\u2715", bg=BG_DARK, fg=ERROR,
                             font=('Arial', 12, 'bold'), cursor='hand2')
        close_btn.pack(side=tk.RIGHT, padx=(4, 0))
        close_btn.bind('<Button-1>', lambda e: self._close())

        self.status_lbl = tk.Label(header, text="", bg=BG_DARK, fg=NEUTRAL,
                                   font=('Arial', 9))
        self.status_lbl.pack(side=tk.RIGHT, padx=(0, 8))

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

    def _close(self):
        """Close this panel: stop the bot if running, then remove."""
        iid = self.current_instance.get('instance_id', '')
        if self.bot_manager.is_running(iid):
            self.bot_manager.stop_bot(iid)
        self.on_close(self)

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

                # Field label
                label_text = FIELD_LABELS.get(field_name, field_name)
                tk.Label(row, text=f"{label_text}:", bg=BG_DARK, fg=NEUTRAL,
                         font=('Consolas', 8), width=28, anchor=tk.W).pack(side=tk.LEFT)

                # Read-only fields
                readonly = field_name in ('bot_type', 'magic_number')

                # Determine widget type
                dropdown_options = DROPDOWN_FIELDS.get(field_name)
                is_bool = isinstance(value, bool)

                var = tk.StringVar(value=str(value))

                if dropdown_options or is_bool:
                    # Dropdown (Combobox)
                    options = dropdown_options if dropdown_options else ['True', 'False']
                    display_val = str(value)
                    if is_bool:
                        display_val = 'True' if value else 'False'
                    var.set(display_val)
                    state = 'disabled' if readonly else 'readonly'
                    combo = ttk.Combobox(row, textvariable=var, values=options,
                                        state=state, width=14)
                    combo.pack(side=tk.LEFT)
                elif isinstance(value, (dict, list)):
                    # JSON field (wider entry)
                    display_value = json.dumps(value) if value else '{}'
                    width = max(14, min(50, len(display_value)))
                    var.set(display_value)
                    entry = tk.Entry(row, textvariable=var, bg=BG_MEDIUM, fg=FG,
                                     font=('Consolas', 9), width=width, insertbackground=FG)
                    entry.pack(side=tk.LEFT)
                else:
                    # Normal text entry
                    var.set(str(value))
                    state = 'disabled' if readonly else 'normal'
                    fg_color = NEUTRAL if readonly else FG
                    entry = tk.Entry(row, textvariable=var, bg=BG_MEDIUM, fg=fg_color,
                                     font=('Consolas', 9), width=14, insertbackground=FG,
                                     state=state, disabledbackground=BG_DARK,
                                     disabledforeground=NEUTRAL)
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
                'Identity': ['config_name', 'bot_type', 'timeframe', 'symbol',
                             'magic_number', 'bot_label', 'order_comment'],
                'Position Sizing': ['sizing_mode', 'risk_per_trade_pct', 'fixed_lots',
                                    'atr_damping', 'max_positions'],
                'RSI Entry': ['rsi_period', 'rsi_buy', 'rsi_sell', 'sniper_rsi_offset'],
                'RSI Exit': ['exit_rsi_long', 'exit_rsi_short', 'adaptive_exit_enabled',
                             'exit_rsi_trend_threshold', 'exit_rsi_trend_shift',
                             'tp_rsi_long', 'tp_rsi_short', 'tp_fallback_atr_mult'],
                'Stop Loss': ['atr_multiplier', 'atr_high_volatility_multiplier'],
                'Trailing Stop': ['breakeven_atr_trigger', 'breakeven_offset',
                                  'trail_atr_after_breakeven', 'trail_atr_before_breakeven'],
                'Direction': ['enable_shorts', 'short_requires_downtrend', 'trading_mode'],
                'Risk Management': ['max_drawdown_limit', 'use_profit_protection'],
                'Trend Detection (EMA)': ['fast_ema', 'slow_ema'],
                'Market Rhythm': ['rhythm_enabled', 'rhythm_mode',
                                  'rhythm_min_amplitude_atr', 'rhythm_max_cycle_bars',
                                  'rhythm_min_cycle_bars', 'rhythm_dead_atr_factor',
                                  'rhythm_htf_timeframe', 'rhythm_support_aware_sniper'],
                'Breakout Shield': ['shield_enabled', 'shield_rapid_sl_candles'],
                'Schedule & Guards': ['schedule_enabled', 'schedule_mon', 'schedule_tue',
                                    'schedule_wed', 'schedule_thu', 'schedule_fri',
                                    'schedule_sat', 'schedule_sun', 'schedule_closed',
                                    'vg_enabled', 'vg_atr_spike_multiplier',
                                    'vg_cooldown_minutes', 'vg_resume_below_multiplier'],
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
        elif bot_type == 'breakout':
            breakout_fields = ['breakout_bars', 'breakout_entry_buffer_atr',
                               'breakout_min_atr',
                               'breakout_re_entry_bars', 'breakout_sl_atr_mult',
                               'breakout_trail_atr_mult']
            breakout_risk = ['max_drawdown_limit', 'breakout_max_daily_loss_pct',
                             'breakout_max_daily_trades', 'breakout_max_drawdown_pct']
            return {
                'Identity': ['config_name', 'bot_type', 'timeframe', 'symbol',
                             'magic_number', 'bot_label', 'order_comment'],
                'Position Sizing': ['sizing_mode', 'risk_per_trade_pct', 'fixed_lots',
                                    'max_positions'],
                'Breakout Entry': breakout_fields,
                'Trend Filter (EMA)': ['fast_ema', 'slow_ema'],
                'Trailing Stop': ['breakeven_mode', 'breakeven_atr_trigger',
                                  'breakeven_offset', 'trail_atr_after_breakeven',
                                  'trail_atr_before_breakeven', 'trail_interval_ms'],
                'Cooldown': ['reentry_cooldown_bars', 'use_loss_backoff',
                             'loss_backoff_sl_only', 'loss_backoff_sl_threshold',
                             'loss_backoff_sl_candles'],
                'Direction': ['enable_shorts', 'short_requires_downtrend', 'trading_mode'],
                'Risk Management': breakout_risk,
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
        self.instance_panel.update_status()

    def _stop(self):
        if not self.current_instance:
            return
        iid = self.current_instance.get('instance_id', '')
        self.bot_manager.stop_bot(iid)
        self._update_controls()
        self.instance_panel.update_status()

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

        # Strategy-specific state (breakout levels, etc.)
        strat_state = ind.get('strategy_state', {})

        sniper = state.get('sniper', {})
        sniper_text = ""
        if sniper.get('buy_level'):
            sniper_text += f"  Sniper Buy: ${sniper['buy_level']:.2f}"
        if sniper.get('sell_level'):
            sniper_text += f"  Sniper Sell: ${sniper['sell_level']:.2f}"

        # Build indicator text based on bot type
        bot_type = self.current_instance.get('bot_type', '')

        if bot_type == 'breakout':
            # Breakout-specific display (never show RSI)
            if strat_state:
                brk_high = strat_state.get('breakout_high', 0)
                brk_low = strat_state.get('breakout_low', 0)
                buy_stop = strat_state.get('buy_stop_price', 0)
                sell_stop = strat_state.get('sell_stop_price', 0)
                dist_high = strat_state.get('dist_to_high', 0)
                dist_low = strat_state.get('dist_to_low', 0)
                atr_ok = strat_state.get('atr_filter_ok', False)
                pending_buy = strat_state.get('pending_buy', False)
                pending_sell = strat_state.get('pending_sell', False)

                # Build order status line
                orders_line = ""
                if buy_stop:
                    status = "ACTIVE" if pending_buy else "armed"
                    orders_line += f"  Buy Stop: ${buy_stop:.2f} [{status}]\n"
                if sell_stop:
                    status = "ACTIVE" if pending_sell else "armed"
                    orders_line += f"  Sell Stop: ${sell_stop:.2f} [{status}]\n"

                ind_text = (
                    f"ATR: ${atr:.2f}  Trend: {trend}  ATR Filter: {'OK' if atr_ok else 'LOW'}\n"
                    f"Breakout High: ${brk_high:.2f} (${dist_high:.2f} away)\n"
                    f"Breakout Low:  ${brk_low:.2f} (${dist_low:.2f} away)\n"
                    f"{orders_line}"
                    f"DD: {dd:.1f}%  Trades: {trades}  Losses: {losses}"
                )
            else:
                ind_text = (
                    f"ATR: ${atr:.2f}  Trend: {trend}\n"
                    f"DD: {dd:.1f}%  Trades: {trades}  Losses: {losses}"
                )
        else:
            # Default display (sniper, rsi_scalper, etc.)
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

        # Rhythm info
        rhythm = state.get('rhythm', {})
        if rhythm.get('enabled'):
            regime = rhythm.get('regime', '?')
            tradeable = rhythm.get('tradeable', True)
            if not tradeable:
                ind_text += f"\nRhythm: BLOCKED ({regime})"
            else:
                mode = rhythm.get('mode', 'gated')
                if mode == 'dynamic':
                    sz = rhythm.get('sizing_scale', 1.0)
                    sl = rhythm.get('sl_scale', 1.0)
                    offset = rhythm.get('sniper_offset', 0)
                    cycle = rhythm.get('full_cycle_bars', 0)
                    amp = rhythm.get('amplitude_dollars', 0)
                    ind_text += (
                        f"\nRhythm: {regime} | cycle={cycle:.0f}bars amp=${amp:.1f}"
                        f"\n  sizing={sz:.0%} SL={sl:.2f}x offset={offset:.1f}"
                    )
                else:
                    ind_text += f"\nRhythm: {regime}"

        # Shield info
        shield = state.get('shield', {})
        if shield.get('enabled'):
            long_sh = shield.get('long_shield', {})
            short_sh = shield.get('short_shield', {})
            parts = []
            if long_sh.get('active'):
                sev = long_sh.get('severity', '?')
                needed_signals = long_sh.get('signals_needed', 0)
                got = long_sh.get('signals_collected', [])
                parts.append(f"L:{sev}({len(got)}/{len(got)+needed_signals})")
            if short_sh.get('active'):
                sev = short_sh.get('severity', '?')
                needed_signals = short_sh.get('signals_needed', 0)
                got = short_sh.get('signals_collected', [])
                parts.append(f"S:{sev}({len(got)}/{len(got)+needed_signals})")
            if parts:
                ind_text += f"\nShield: {' '.join(parts)}"

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


class BotDetailContainer:
    """Horizontally scrollable container for multiple BotDetailPanel columns."""

    def __init__(self, parent, bot_manager: BotManager, instance_panel):
        self.bot_manager = bot_manager
        self.instance_panel = instance_panel
        self.panels: list[BotDetailPanel] = []

        self.frame = tk.Frame(parent, bg=BG_DARK)

        # Horizontal scrollable area
        self.canvas = tk.Canvas(self.frame, bg=BG_DARK, highlightthickness=0)
        self.h_scrollbar = ttk.Scrollbar(self.frame, orient=tk.HORIZONTAL,
                                         command=self.canvas.xview)
        self.inner = tk.Frame(self.canvas, bg=BG_DARK)

        self.inner.bind('<Configure>',
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self._canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set)

        # Make inner frame fill canvas height
        self.canvas.bind('<Configure>', self._on_canvas_configure)

        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Placeholder when no panels open
        self.placeholder = tk.Label(self.inner, text="Click a bot in the list to open it here",
                                    bg=BG_DARK, fg=NEUTRAL, font=('Arial', 10))
        self.placeholder.pack(padx=20, pady=40)

    def _on_canvas_configure(self, event):
        """Keep inner frame height matching the canvas height."""
        self.canvas.itemconfig(self._canvas_window, height=event.height)

    def open_instance(self, instance: dict):
        """Open a bot detail panel for the given instance."""
        if instance.get('_new'):
            # Handle new config creation (delegate to first panel or create special)
            self._create_new_config()
            return

        # Don't open duplicates
        iid = instance.get('instance_id', '')
        for panel in self.panels:
            if panel.current_instance.get('instance_id') == iid:
                return  # Already open

        # Hide placeholder
        self.placeholder.pack_forget()

        panel = BotDetailPanel(
            self.inner, self.bot_manager, self.instance_panel,
            on_close_callback=self._on_panel_closed,
            instance=instance,
        )
        panel.frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 2))
        self.panels.append(panel)

    def _on_panel_closed(self, panel: BotDetailPanel):
        """Remove a panel from the container."""
        panel.frame.destroy()
        self.panels.remove(panel)
        self.instance_panel.update_status()

        if not self.panels:
            self.placeholder.pack(padx=20, pady=40)

    def _create_new_config(self):
        """Show dialog to pick bot type + name, then auto-create config file."""
        from src.core.paths import resolve_path
        from src.core.config import TradingConfig
        from src.services.bot_manager import BOT_REGISTRY
        import dataclasses
        import random

        # Dialog window
        dialog = tk.Toplevel()
        dialog.title("New Bot Profile")
        dialog.geometry("350x180")
        dialog.configure(bg=BG_DARK)
        dialog.transient()
        dialog.grab_set()

        tk.Label(dialog, text="Create New Bot Profile", bg=BG_DARK, fg=ACCENT,
                 font=('Arial', 10, 'bold')).pack(pady=(12, 8))

        # Bot type selector
        type_frame = tk.Frame(dialog, bg=BG_DARK)
        type_frame.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(type_frame, text="Bot Type:", bg=BG_DARK, fg=FG,
                 font=('Consolas', 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        bot_types = list(BOT_REGISTRY.keys())
        type_var = tk.StringVar(value='sniper')
        type_combo = ttk.Combobox(type_frame, textvariable=type_var, values=bot_types,
                                  state='readonly', width=18)
        type_combo.pack(side=tk.LEFT)

        # Name input
        name_frame = tk.Frame(dialog, bg=BG_DARK)
        name_frame.pack(fill=tk.X, padx=20, pady=4)
        tk.Label(name_frame, text="Name:", bg=BG_DARK, fg=FG,
                 font=('Consolas', 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        name_var = tk.StringVar(value='')
        name_entry = tk.Entry(name_frame, textvariable=name_var, bg=BG_MEDIUM, fg=FG,
                              font=('Consolas', 9), width=20, insertbackground=FG)
        name_entry.pack(side=tk.LEFT)
        name_entry.focus_set()

        result = {'created': False}

        def _do_create():
            bot_type = type_var.get()
            name = name_var.get().strip()
            if not name:
                name = f"New {bot_type.replace('_', ' ').title()}"

            # Generate unique magic number (random in 235000-239999 range)
            existing_magics = set()
            for cfg in self.bot_manager.list_available_configs():
                # Read magic from file
                try:
                    with open(cfg['path'], 'r') as fp:
                        raw = json.load(fp)
                    existing_magics.add(raw.get('magic_number', 0))
                except Exception:
                    pass

            magic = random.randint(235000, 239999)
            while magic in existing_magics:
                magic = random.randint(235000, 239999)

            # Create template config
            template = TradingConfig()
            template.config_name = name
            template.bot_type = bot_type
            template.magic_number = magic
            template.bot_label = f"{bot_type[:3].upper()}{magic % 1000}"
            template.order_comment = f"{bot_type}_{magic}"

            # Auto-generate filename
            safe_name = name.lower().replace(' ', '_')[:20]
            filename = f"{bot_type}_{safe_name}_{magic}.json"
            config_dir = resolve_path('config')
            path = str(config_dir / filename)

            # Write config
            data = {}
            for field in dataclasses.fields(template):
                val = getattr(template, field.name)
                if isinstance(val, (dict, list)):
                    data[field.name] = val
                else:
                    data[field.name] = val

            with open(path, 'w') as f:
                json.dump(data, f, indent=2)

            result['created'] = True
            result['path'] = path
            result['instance'] = {
                'config_path': path,
                'config_name': name,
                'bot_type': bot_type,
                'bot_label': template.bot_label,
                'timeframe': template.timeframe,
                'instance_id': template.bot_label,
                'filename': filename,
            }
            dialog.destroy()

        # Buttons
        btn_frame = tk.Frame(dialog, bg=BG_DARK)
        btn_frame.pack(pady=(12, 0))
        ttk.Button(btn_frame, text="Create", command=_do_create, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=8).pack(side=tk.LEFT, padx=4)

        # Wait for dialog to close
        dialog.wait_window()

        if result['created']:
            self.instance_panel.refresh_config_list()
            self.open_instance(result['instance'])

    def update(self):
        """Update all open panels."""
        for panel in self.panels:
            panel.update()


class EgonGUI:
    """Main GUI: left instance list, right multi-panel detail, bottom chart/history/log."""

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

        # Global log buffer (shared by both log panels)
        import io
        self._global_log_buffer = io.StringIO()
        handler = logging.StreamHandler(self._global_log_buffer)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

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
        top_paned.add(self.instance_panel.frame, width=280, minsize=220)

        # Right: multi-panel detail container
        self.detail_container = BotDetailContainer(
            top_paned, self.bot_manager, self.instance_panel
        )
        top_paned.add(self.detail_container.frame, width=900, minsize=400)

        # Bottom: two side-by-side tabbed panels
        bottom_paned = tk.PanedWindow(main_paned, orient=tk.HORIZONTAL, bg=BG_DARK,
                                      sashwidth=4, sashrelief=tk.RAISED)
        main_paned.add(bottom_paned, minsize=200)

        # Left bottom notebook
        self.bottom_left = self._build_tabbed_panel(bottom_paned)
        bottom_paned.add(self.bottom_left['notebook'], width=700, minsize=300)

        # Right bottom notebook
        self.bottom_right = self._build_tabbed_panel(bottom_paned)
        bottom_paned.add(self.bottom_right['notebook'], width=700, minsize=300)

        # Load configs
        self.instance_panel.refresh_config_list()

    def _on_instance_selected(self, instance: dict):
        self.detail_container.open_instance(instance)

    def _build_tabbed_panel(self, parent) -> dict:
        """Build a complete tabbed panel (chart, trades, log, market, calc). Returns state dict."""
        import io

        notebook = ttk.Notebook(parent)
        panel = {'notebook': notebook}

        # Chart tab
        if HAS_MATPLOTLIB:
            chart_frame = tk.Frame(notebook, bg=BG_DARK)
            notebook.add(chart_frame, text=" Chart ")

            chart_ctrl = tk.Frame(chart_frame, bg=BG_DARK)
            chart_ctrl.pack(fill=tk.X, padx=6, pady=(4, 0))
            tf_var = tk.StringVar(value='M5')
            for tf in ['M1', 'M5', 'M15']:
                ttk.Radiobutton(chart_ctrl, text=tf, variable=tf_var, value=tf).pack(side=tk.LEFT, padx=3)

            fig = Figure(figsize=(10, 3), dpi=100, facecolor=BG_DARK)
            ax = fig.add_subplot(111, facecolor=BG_MEDIUM)
            canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 4))

            panel['chart'] = {'fig': fig, 'ax': ax, 'canvas': canvas, 'tf_var': tf_var}

        # Trade history tab
        hist_frame = tk.Frame(notebook, bg=BG_DARK)
        notebook.add(hist_frame, text=" Trades ")

        cols = ('Time', 'Bot', 'Type', 'Vol', 'Entry', 'Exit', 'Profit', 'Reason')
        tree = ttk.Treeview(hist_frame, columns=cols, show='headings', height=10)
        for c in cols:
            tree.heading(c, text=c)
        tree.column('Time', width=100)
        tree.column('Bot', width=50)
        tree.column('Type', width=45)
        tree.column('Vol', width=40)
        tree.column('Entry', width=70)
        tree.column('Exit', width=70)
        tree.column('Profit', width=65)
        tree.column('Reason', width=180)
        tree_scroll = ttk.Scrollbar(hist_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=4)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 6), pady=4)
        tree.tag_configure('profit', foreground=SUCCESS)
        tree.tag_configure('loss', foreground=ERROR)
        panel['trade_tree'] = tree

        # Log tab
        log_frame = tk.Frame(notebook, bg=BG_DARK)
        notebook.add(log_frame, text=" Log ")

        log_text = tk.Text(log_frame, wrap=tk.WORD, bg=BG_MEDIUM, fg=FG,
                           font=('Consolas', 8), height=12)
        log_scroll = ttk.Scrollbar(log_frame, command=log_text.yview)
        log_text.config(yscrollcommand=log_scroll.set)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=4)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 6), pady=4)

        # Each log panel gets its own position tracker on the shared global buffer
        panel['log_text'] = log_text
        panel['log_pos'] = 0

        # Market tab
        market_frame = tk.Frame(notebook, bg=BG_DARK)
        notebook.add(market_frame, text=" Market ")
        market_labels = self._build_market_widgets(market_frame)
        panel['market_labels'] = market_labels['grid']
        panel['spread_lbl'] = market_labels['spread']
        panel['bid_lbl'] = market_labels['bid']
        panel['ask_lbl'] = market_labels['ask']

        # Sizing calculator tab
        calc_frame = tk.Frame(notebook, bg=BG_DARK)
        notebook.add(calc_frame, text=" Sizing Calc ")
        SizingCalculator(calc_frame)

        return panel

    def _build_market_widgets(self, parent) -> dict:
        """Build market dashboard widgets, return label references."""
        grid_frame = tk.Frame(parent, bg=BG_DARK)
        grid_frame.pack(fill=tk.X, padx=6, pady=(6, 4))

        headers = ['', 'RSI', 'ATR', 'Trend', 'EMA9', 'EMA21', 'Close']
        for col, h in enumerate(headers):
            tk.Label(grid_frame, text=h, bg=BG_DARK, fg=ACCENT,
                     font=('Consolas', 9, 'bold'), width=10, anchor=tk.CENTER
                     ).grid(row=0, column=col, padx=2, pady=(0, 4))

        market_grid = {}
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
            market_grid[tf] = labels

        tk.Frame(parent, bg=BG_LIGHT, height=1).pack(fill=tk.X, padx=6, pady=4)
        spread_row = tk.Frame(parent, bg=BG_DARK)
        spread_row.pack(fill=tk.X, padx=6, pady=(0, 4))

        tk.Label(spread_row, text="Spread:", bg=BG_DARK, fg=NEUTRAL,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        spread_lbl = tk.Label(spread_row, text="--", bg=BG_DARK, fg=WARNING,
                              font=('Consolas', 9, 'bold'))
        spread_lbl.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(spread_row, text="Bid:", bg=BG_DARK, fg=NEUTRAL,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        bid_lbl = tk.Label(spread_row, text="--", bg=BG_DARK, fg=FG,
                           font=('Consolas', 9))
        bid_lbl.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(spread_row, text="Ask:", bg=BG_DARK, fg=NEUTRAL,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        ask_lbl = tk.Label(spread_row, text="--", bg=BG_DARK, fg=FG,
                           font=('Consolas', 9))
        ask_lbl.pack(side=tk.LEFT)

        return {'grid': market_grid, 'spread': spread_lbl, 'bid': bid_lbl, 'ask': ask_lbl}

    # ── Update loop ─────────────────────────────────────────────────

    def _update_loop(self):
        try:
            self._update_account()
            self.detail_container.update()
            self.instance_panel.update_status()

            if HAS_MATPLOTLIB:
                self._update_charts()
            self._update_trade_histories()
            self._update_logs()

            self._market_update_counter += 1
            if self._market_update_counter >= 5:
                self._market_update_counter = 0
                self._update_markets()
        except Exception as e:
            logger.error(f"GUI update error: {e}")
        self.root.after(1000, self._update_loop)

    def _update_account(self):
        info = self.market.get_account_info()
        price = self.market.get_price()
        self.instance_panel.update_account(info, price)

    def _update_charts(self):
        """Update charts in both bottom panels."""
        if not self.market.connected:
            return
        for panel in [self.bottom_left, self.bottom_right]:
            chart = panel.get('chart')
            if not chart:
                continue
            try:
                tf = chart['tf_var'].get()
                bars = 100 if tf == 'M1' else 60 if tf == 'M15' else 50
                df = self.market.get_chart_data(tf, bars)
                if df is None or len(df) == 0:
                    continue
                ax = chart['ax']
                ax.clear()
                for i in range(len(df)):
                    row = df.iloc[i]
                    color = SUCCESS if row['close'] >= row['open'] else ERROR
                    body_h = abs(row['close'] - row['open'])
                    body_b = min(row['open'], row['close'])
                    rect = Rectangle((i - 0.3, body_b), 0.6, body_h,
                                     facecolor=color, edgecolor=color, alpha=0.8)
                    ax.add_patch(rect)
                    ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=1, alpha=0.6)

                # Mark levels if a bot is selected
                selected = self.instance_panel.get_selected()
                if selected:
                    state = self.bot_manager.get_state(selected.get('instance_id', ''))
                    bot_type = selected.get('bot_type', '')

                    if bot_type == 'breakout':
                        # Show breakout high/low levels
                        strat_state = state.get('indicators', {}).get('strategy_state', {})
                        if strat_state.get('breakout_high'):
                            ax.axhline(strat_state['breakout_high'], color=SUCCESS,
                                       linestyle='--', alpha=0.7, linewidth=1.2,
                                       label=f"High ${strat_state['breakout_high']:.2f}")
                        if strat_state.get('breakout_low'):
                            ax.axhline(strat_state['breakout_low'], color=ERROR,
                                       linestyle='--', alpha=0.7, linewidth=1.2,
                                       label=f"Low ${strat_state['breakout_low']:.2f}")
                        # Show stop order levels (solid, slightly different color)
                        if strat_state.get('buy_stop_price'):
                            ax.axhline(strat_state['buy_stop_price'], color='#00ff88',
                                       linestyle='-', alpha=0.9, linewidth=1.5,
                                       label=f"Buy Stop ${strat_state['buy_stop_price']:.2f}")
                        if strat_state.get('sell_stop_price'):
                            ax.axhline(strat_state['sell_stop_price'], color='#ff6644',
                                       linestyle='-', alpha=0.9, linewidth=1.5,
                                       label=f"Sell Stop ${strat_state['sell_stop_price']:.2f}")
                    else:
                        # Show sniper levels for RSI-based bots
                        sniper = state.get('sniper', {})
                        if sniper.get('buy_level'):
                            ax.axhline(sniper['buy_level'], color=SUCCESS, linestyle='--',
                                       alpha=0.6, linewidth=1)
                        if sniper.get('sell_level'):
                            ax.axhline(sniper['sell_level'], color=ERROR, linestyle='--',
                                       alpha=0.6, linewidth=1)

                ax.set_xlim(-1, len(df))
                ax.set_ylim(df['low'].min() * 0.9999, df['high'].max() * 1.0001)
                ax.tick_params(colors=FG, labelsize=7)
                for spine in ax.spines.values():
                    spine.set_color(BG_LIGHT)
                ax.grid(True, alpha=0.2, color=BG_LIGHT)
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
                chart['canvas'].draw()
            except Exception as e:
                logger.error(f"Chart error: {e}")

    def _update_trade_histories(self):
        """Update trade history trees in both panels."""
        history = self.market.get_trade_history()
        exit_reasons = load_exit_reasons()
        for panel in [self.bottom_left, self.bottom_right]:
            tree = panel.get('trade_tree')
            if not tree:
                continue
            for item in tree.get_children():
                tree.delete(item)
            for pos in history[:50]:
                ticket_str = str(pos.get('ticket', ''))
                pid_str = str(pos.get('position_id', ''))
                reason = exit_reasons.get(pid_str, {}).get('reason') or \
                         exit_reasons.get(ticket_str, {}).get('reason') or \
                         pos.get('exit_reason', 'Unknown')
                tag = 'profit' if pos['profit'] > 0 else 'loss'
                tree.insert('', tk.END, values=(
                    pos['exit_time'].strftime('%m-%d %H:%M'),
                    pos['bot'], pos['type'],
                    f"{pos.get('volume', 0):.2f}",
                    f"${pos['entry_price']:.2f}", f"${pos['exit_price']:.2f}",
                    f"${pos['profit']:.2f}", reason,
                ), tags=(tag,))

    def _update_logs(self):
        """Read new log output and push to both log panels."""
        content = self._global_log_buffer.getvalue()

        for panel in [self.bottom_left, self.bottom_right]:
            log_text = panel.get('log_text')
            if not log_text:
                continue
            pos = panel.get('log_pos', 0)
            new_content = content[pos:]
            panel['log_pos'] = len(content)

            if new_content:
                log_text.insert(tk.END, new_content)
                line_count = int(log_text.index('end-1c').split('.')[0])
                if line_count > 3000:
                    log_text.delete('1.0', f'{line_count - 2000}.0')
                log_text.see(tk.END)

        # Trim shared buffer if too large
        if len(content) > 500_000:
            trimmed = content[-100_000:]
            self._global_log_buffer.truncate(0)
            self._global_log_buffer.seek(0)
            self._global_log_buffer.write(trimmed)
            # Reset both panel positions
            for panel in [self.bottom_left, self.bottom_right]:
                panel['log_pos'] = len(trimmed)

    def _update_markets(self):
        """Update market dashboards in both panels."""
        try:
            overview = self.market.get_market_overview()
        except Exception as e:
            logger.error(f"Market dashboard error: {e}")
            return

        for panel in [self.bottom_left, self.bottom_right]:
            market_labels = panel.get('market_labels')
            if not market_labels:
                continue

            for tf in ['M1', 'M5', 'M15']:
                data = overview.get(tf)
                labels = market_labels.get(tf, {})
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
            panel['spread_lbl'].config(text=f"${spread:.3f}", fg=spread_color)
            panel['bid_lbl'].config(text=f"${overview.get('bid', 0):.2f}")
            panel['ask_lbl'].config(text=f"${overview.get('ask', 0):.2f}")

    def on_closing(self):
        self.bot_manager.stop_all()
        self.market.disconnect()
        self.root.destroy()
