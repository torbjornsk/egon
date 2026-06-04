"""
Egon Trading Dashboard

Layout: 3 resizable columns (left bots | center chart+history | right bots)
Each side column has 2 resizable rows for bot slots (4 bots total).
Each bot slot: selector dropdown, controls, indicators, positions, toggle log.
"""

import tkinter as tk
from tkinter import ttk
import logging

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

# Available bot types
BOT_TYPES = ['-- None --', 'M5 RSI', 'LZ Zones', 'M5 Sniper', 'Tick Scalper', 'Momentum', 'M15 RSI']
BOT_LABELS = {'M5 RSI': 'M5', 'LZ Zones': 'LZ', 'M5 Sniper': 'M5S',
              'Tick Scalper': 'TICK', 'Momentum': 'MOM', 'M15 RSI': 'M15'}


class BotSlot:
    """A single bot slot in the GUI — can host any bot type with its own config."""

    # Key config fields to show per bot type
    CONFIG_FIELDS = {
        'M5': ['rsi_buy', 'rsi_sell', 'atr_multiplier', 'leverage', 'position_size_pct', 'max_positions'],
        'LZ': ['zone_rr_ratio', 'zone_min_strength', 'leverage', 'position_size_pct', 'max_positions'],
        'M5S': ['rsi_buy', 'rsi_sell', 'atr_multiplier', 'leverage', 'position_size_pct', 'breakeven_atr_trigger'],
        'TICK': ['tick_entry_threshold', 'tick_exit_threshold', 'tick_cooldown_seconds', 'leverage', 'position_size_pct'],
        'MOM': ['entry_threshold', 'hold_threshold', 'signal_window', 'sl_atr_mult', 'leverage', 'position_size_pct'],
        'M15': ['rsi_buy', 'rsi_sell', 'atr_multiplier', 'leverage', 'position_size_pct', 'max_positions'],
    }

    def __init__(self, parent, slot_id: int, bot_manager: BotManager):
        self.slot_id = slot_id
        self.bot_manager = bot_manager
        self.active_label: str | None = None
        self.instance_id: str | None = None
        self.config_vars: dict[str, tk.StringVar] = {}

        self.frame = tk.Frame(parent, bg=BG_DARK)
        self._build()

    def _build(self):
        f = self.frame

        # ── Header: selector + controls ─────────────────────────────
        header = tk.Frame(f, bg=BG_DARK)
        header.pack(fill=tk.X, padx=4, pady=(4, 2))

        # Bot type selector
        self.bot_var = tk.StringVar(value='-- None --')
        selector = ttk.Combobox(header, textvariable=self.bot_var, values=BOT_TYPES,
                                state='readonly', width=12)
        selector.pack(side=tk.LEFT, padx=(0, 4))
        selector.bind('<<ComboboxSelected>>', self._on_bot_selected)

        self.start_btn = ttk.Button(header, text="Start", command=self._start, width=6)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 2))
        self.start_btn.config(state=tk.DISABLED)

        self.stop_btn = ttk.Button(header, text="Stop", command=self._stop, width=5)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.stop_btn.config(state=tk.DISABLED)

        self.status_lbl = ttk.Label(header, text="", foreground=NEUTRAL, font=('Arial', 8))
        self.status_lbl.pack(side=tk.LEFT, padx=(0, 4))

        self.mode_btn = ttk.Button(header, text="Both", command=self._toggle_mode, width=5)
        self.mode_btn.pack(side=tk.RIGHT)

        self.pp_btn = ttk.Button(header, text="PP", command=self._toggle_pp, width=4)
        self.pp_btn.pack(side=tk.RIGHT, padx=(0, 2))

        # ── Info row: indicators + status ───────────────────────────
        info = tk.Frame(f, bg=BG_DARK)
        info.pack(fill=tk.X, padx=4, pady=(0, 2))

        self.info_labels = []
        for _ in range(4):
            lbl = tk.Label(info, text="", bg=BG_DARK, fg=FG, font=('Consolas', 8), anchor=tk.W)
            lbl.pack(fill=tk.X)
            self.info_labels.append(lbl)

        # ── Positions ───────────────────────────────────────────────
        self.pos_frame = tk.Frame(f, bg=BG_DARK)
        self.pos_frame.pack(fill=tk.X, padx=4, pady=(0, 2))
        self.pos_labels: list[tk.Label] = []

        # ── Signal bar (for Momentum bot) ──────────────────────────
        self.signal_frame = tk.Frame(f, bg=BG_DARK)
        self.signal_frame.pack(fill=tk.X, padx=4, pady=(0, 2))
        self.signal_canvas = tk.Canvas(self.signal_frame, height=20, bg=BG_MEDIUM,
                                       highlightthickness=0)
        self.signal_canvas.pack(fill=tk.X)
        self.signal_frame.pack_forget()  # Hidden by default

        # ── Config fields (shown when bot selected) ────────────────
        self.config_frame = tk.Frame(f, bg=BG_DARK)
        self.config_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

    def _on_bot_selected(self, event=None):
        selected = self.bot_var.get()
        if selected == '-- None --':
            self.active_label = None
            self.instance_id = None
            self.start_btn.config(state=tk.DISABLED)
            self._clear_config_fields()
        else:
            self.active_label = BOT_LABELS.get(selected)
            self.instance_id = f"{self.active_label}_{self.slot_id}"
            self.start_btn.config(state=tk.NORMAL)
            self._show_config_fields()
        self.stop_btn.config(state=tk.DISABLED)

    def _show_config_fields(self):
        """Show editable config fields for the selected bot type."""
        self._clear_config_fields()
        if not self.active_label:
            return

        fields = self.CONFIG_FIELDS.get(self.active_label, [])
        from src.core.config import TradingConfig
        defaults = TradingConfig()

        for field_name in fields:
            default_val = getattr(defaults, field_name, '')
            row = tk.Frame(self.config_frame, bg=BG_DARK)
            row.pack(fill=tk.X, pady=1)

            tk.Label(row, text=f"{field_name}:", bg=BG_DARK, fg=NEUTRAL,
                     font=('Consolas', 7), width=20, anchor=tk.W).pack(side=tk.LEFT)

            var = tk.StringVar(value=str(default_val))
            entry = tk.Entry(row, textvariable=var, bg=BG_MEDIUM, fg=FG,
                             font=('Consolas', 8), width=8, insertbackground=FG)
            entry.pack(side=tk.LEFT)
            self.config_vars[field_name] = var

    def _clear_config_fields(self):
        """Remove config field widgets."""
        for widget in self.config_frame.winfo_children():
            widget.destroy()
        self.config_vars.clear()

    def _start(self):
        if self.active_label and self.instance_id:
            self.bot_manager.start_bot(self.active_label, check_interval=1,
                                       instance_id=self.instance_id)
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)

    def _stop(self):
        if self.instance_id:
            self.bot_manager.stop_bot(self.instance_id)
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)

    def _toggle_pp(self):
        if self.instance_id:
            self.bot_manager.toggle_profit_protection(self.instance_id)

    def _toggle_mode(self):
        if self.instance_id:
            self.bot_manager.toggle_trading_mode(self.instance_id)

    def update(self):
        """Update this slot from bot state."""
        if not self.instance_id:
            self.status_lbl.config(text="")
            for lbl in self.info_labels:
                lbl.config(text="")
            for lbl in self.pos_labels:
                lbl.config(text="")
            return

        state = self.bot_manager.get_state(self.instance_id)
        status = state.get('status', 'Stopped')
        color = SUCCESS if status == 'Running' else ERROR if status == 'Paused' else NEUTRAL
        self.status_lbl.config(text=status, foreground=color)

        # Indicators
        ind = state.get('indicators', {})
        rsi = ind.get('rsi', 0)
        atr = ind.get('atr', 0)

        # Tick scalper specific
        long_s = ind.get('long_score', 0)
        short_s = ind.get('short_score', 0)
        exit_s = ind.get('exit_score', 0)
        entry_state = ind.get('entry_state', '')

        positions = state.get('positions', [])
        max_pos = state.get('max_positions', 1)
        trading_mode = state.get('trading_mode', 'both')
        pp_active = state.get('pp_active', False)

        # Info lines
        if self.active_label == 'MOM':
            # Momentum scalper display
            signal = ind.get('signal_score', 0)
            consistency = ind.get('consistency', 0)
            long_raw = ind.get('long_raw', 0)
            short_raw = ind.get('short_raw', 0)
            direction = ind.get('direction', 'NEUTRAL')
            samples = ind.get('samples', 0)

            dir_color = SUCCESS if direction == 'LONG' else ERROR if direction == 'SHORT' else NEUTRAL
            lines = [
                f"Signal: {signal:+.3f} [{direction}] Consistency:{consistency:.2f}",
                f"Raw L={long_raw:.2f} S={short_raw:.2f} Spread:${ind.get('spread', 0):.3f}",
                f"Samples:{samples} SpreadRatio:{ind.get('spread_ratio', 1):.1f}x",
                f"Pos:{len(positions)}/{max_pos} Trades:{state.get('trades_today', 0)} DD:{state.get('drawdown_pct', 0):.1f}%",
            ]

            # Show and update signal bar
            self.signal_frame.pack(fill=tk.X, padx=4, pady=(0, 2))
            self._draw_signal_bar(signal, consistency)

        elif long_s or short_s or entry_state:
            # Tick scalper display
            lines = [
                f"RSI:{rsi:.0f} ATR:${atr:.2f} Spread:${ind.get('spread', 0):.2f}",
                f"Entry L={long_s:.2f} S={short_s:.2f} [{entry_state}]",
                f"Exit:{exit_s:.2f} Vel:{ind.get('velocity_ratio', 0):.2f}",
                f"Pos:{len(positions)}/{max_pos} Trades:{state.get('trades_today', 0)} DD:{state.get('drawdown_pct', 0):.1f}%",
            ]
            self.signal_frame.pack_forget()
        else:
            uptrend = ind.get('uptrend', False)
            trend = 'UP' if uptrend else 'DN' if ind.get('downtrend', False) else '--'
            lines = [
                f"RSI:{rsi:.1f} ATR:${atr:.2f} Trend:{trend}",
                f"Pos:{len(positions)}/{max_pos} Trades:{state.get('trades_today', 0)}",
                f"DD:{state.get('drawdown_pct', 0):.1f}% PP:{'ON' if pp_active else 'OFF'}",
                f"Mode:{trading_mode} Losses:{state.get('consecutive_losses', 0)}",
            ]
            self.signal_frame.pack_forget()

        for i, line in enumerate(lines):
            if i < len(self.info_labels):
                self.info_labels[i].config(text=line)

        # Mode/PP buttons
        mode_short = {'both': 'Both', 'long_only': 'Long', 'short_only': 'Short'}
        self.mode_btn.config(text=mode_short.get(trading_mode, 'Both'))
        pp_override = state.get('pp_override')
        pp_text = 'Auto' if pp_override is None else 'ON' if pp_override else 'OFF'
        self.pp_btn.config(text=pp_text)

        # Positions
        # Rebuild position labels if count changed
        needed = max(max_pos, len(positions))
        while len(self.pos_labels) < needed:
            lbl = tk.Label(self.pos_frame, text="", bg=BG_LIGHT, fg=FG,
                           font=('Consolas', 8), anchor=tk.W, relief=tk.RAISED, padx=3, pady=1)
            lbl.pack(fill=tk.X, pady=(0, 1))
            self.pos_labels.append(lbl)

        for i, lbl in enumerate(self.pos_labels):
            if i < len(positions):
                pos = positions[i]
                d = pos.get('direction', '?')
                profit = pos.get('profit', 0)
                entry = pos.get('entry_price', 0)
                sl = pos.get('sl', 0)
                p_color = SUCCESS if profit > 0 else ERROR if profit < 0 else FG
                lbl.config(
                    text=f"{d} ${entry:.2f} P/L:${profit:.2f} SL:${sl:.2f}",
                    fg=p_color,
                )
            elif i < needed:
                lbl.config(text=f"Slot {i+1}: empty", fg=NEUTRAL)
            else:
                lbl.config(text="")

    def _draw_signal_bar(self, signal: float, consistency: float):
        """
        Draw a horizontal signal bar showing directional pressure.

        Bar goes from -1 (left, red) to +1 (right, green).
        Center is neutral. Fill width and color show signal strength.
        Opacity/brightness shows consistency.
        """
        canvas = self.signal_canvas
        canvas.delete("all")

        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 10:
            w = 300  # Default before first render

        mid_x = w / 2

        # Background: dark center line
        canvas.create_line(mid_x, 0, mid_x, h, fill=NEUTRAL, width=1)

        # Threshold markers
        entry_thresh = 0.45  # From config
        hold_thresh = 0.15
        for thresh in [entry_thresh, hold_thresh]:
            # Right side (long)
            x_r = mid_x + thresh * mid_x
            canvas.create_line(x_r, 0, x_r, h, fill=BG_LIGHT, dash=(2, 2))
            # Left side (short)
            x_l = mid_x - thresh * mid_x
            canvas.create_line(x_l, 0, x_l, h, fill=BG_LIGHT, dash=(2, 2))

        # Signal fill
        if abs(signal) > 0.01:
            fill_width = abs(signal) * mid_x
            # Color: green for long, red for short, brightness scales with consistency
            if signal > 0:
                # Green bar extending right from center
                alpha = int(100 + 155 * consistency)
                color = f"#{0:02x}{alpha:02x}{0:02x}"
                canvas.create_rectangle(mid_x, 2, mid_x + fill_width, h - 2,
                                        fill=color, outline="")
            else:
                # Red bar extending left from center
                alpha = int(100 + 155 * consistency)
                color = f"#{alpha:02x}{0:02x}{0:02x}"
                canvas.create_rectangle(mid_x - fill_width, 2, mid_x, h - 2,
                                        fill=color, outline="")

        # Score text
        dir_char = "+" if signal > 0 else "" if signal == 0 else ""
        canvas.create_text(w - 40, h / 2, text=f"{dir_char}{signal:.2f}",
                           fill=FG, font=('Consolas', 8), anchor=tk.E)


class EgonGUI:
    """Main GUI with 4 bot slots and center chart/history."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Egon Trading Dashboard")
        self.root.geometry("1920x1080")
        self.root.configure(bg=BG_DARK)

        setup_styles()

        self.bot_manager = BotManager()
        self.market = MarketDataService()
        self.market.connect()

        self.chart_timeframe = 'M5'
        self.slots: list[BotSlot] = []

        self._build_ui()
        self._update_loop()

    def _build_ui(self):
        # Main horizontal paned window (3 columns)
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_DARK,
                                    sashwidth=4, sashrelief=tk.RAISED)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # Left column (2 bot slots stacked)
        left_paned = tk.PanedWindow(main_paned, orient=tk.VERTICAL, bg=BG_DARK,
                                    sashwidth=4, sashrelief=tk.RAISED)
        main_paned.add(left_paned, width=420, minsize=320)

        slot0 = BotSlot(left_paned, 0, self.bot_manager)
        left_paned.add(slot0.frame, minsize=200, height=400)
        self.slots.append(slot0)

        slot1 = BotSlot(left_paned, 1, self.bot_manager)
        left_paned.add(slot1.frame, minsize=200, height=400)
        self.slots.append(slot1)

        # Center column (account + chart + history)
        center = self._build_center(main_paned)
        main_paned.add(center, width=800, minsize=500)

        # Right column (2 bot slots stacked)
        right_paned = tk.PanedWindow(main_paned, orient=tk.VERTICAL, bg=BG_DARK,
                                     sashwidth=4, sashrelief=tk.RAISED)
        main_paned.add(right_paned, width=420, minsize=320)

        slot2 = BotSlot(right_paned, 2, self.bot_manager)
        right_paned.add(slot2.frame, minsize=200, height=400)
        self.slots.append(slot2)

        slot3 = BotSlot(right_paned, 3, self.bot_manager)
        right_paned.add(slot3.frame, minsize=200, height=400)
        self.slots.append(slot3)

    def _build_center(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG_DARK)

        # Account bar
        acc = tk.Frame(frame, bg=BG_DARK)
        acc.pack(fill=tk.X, padx=6, pady=(4, 2))

        tk.Label(acc, text="Balance:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 9)).pack(side=tk.LEFT)
        self.balance_lbl = tk.Label(acc, text="$0", bg=BG_DARK, fg=FG, font=('Arial', 11, 'bold'))
        self.balance_lbl.pack(side=tk.LEFT, padx=(2, 12))

        tk.Label(acc, text="Equity:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 9)).pack(side=tk.LEFT)
        self.equity_lbl = tk.Label(acc, text="$0", bg=BG_DARK, fg=FG, font=('Arial', 11, 'bold'))
        self.equity_lbl.pack(side=tk.LEFT, padx=(2, 12))

        tk.Label(acc, text="Price:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 9)).pack(side=tk.LEFT)
        self.price_lbl = tk.Label(acc, text="$0", bg=BG_DARK, fg=WARNING, font=('Arial', 11, 'bold'))
        self.price_lbl.pack(side=tk.LEFT, padx=(2, 0))

        # Chart
        if HAS_MATPLOTLIB:
            chart_frame = tk.Frame(frame, bg=BG_DARK)
            chart_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 2))

            chart_ctrl = tk.Frame(chart_frame, bg=BG_DARK)
            chart_ctrl.pack(fill=tk.X)
            self.chart_tf_var = tk.StringVar(value='M5')
            for tf in ['M1', 'M5', 'M15']:
                ttk.Radiobutton(chart_ctrl, text=tf, variable=self.chart_tf_var, value=tf,
                                command=lambda: setattr(self, 'chart_timeframe', self.chart_tf_var.get())
                                ).pack(side=tk.LEFT, padx=3)

            self.fig = Figure(figsize=(8, 3), dpi=100, facecolor=BG_DARK)
            self.ax = self.fig.add_subplot(111, facecolor=BG_MEDIUM)
            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Trade history + Log (tabbed)
        bottom_notebook = ttk.Notebook(frame)
        bottom_notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        # Trade history tab
        hist_frame = tk.Frame(bottom_notebook, bg=BG_DARK)
        bottom_notebook.add(hist_frame, text=" Trades ")

        cols = ('Time', 'Bot', 'Type', 'Entry', 'Exit', 'Profit', 'Reason')
        self.trade_tree = ttk.Treeview(hist_frame, columns=cols, show='headings', height=8)
        for c in cols:
            self.trade_tree.heading(c, text=c)
        self.trade_tree.column('Time', width=100)
        self.trade_tree.column('Bot', width=40)
        self.trade_tree.column('Type', width=40)
        self.trade_tree.column('Entry', width=65)
        self.trade_tree.column('Exit', width=65)
        self.trade_tree.column('Profit', width=60)
        self.trade_tree.column('Reason', width=180)

        tree_scroll = ttk.Scrollbar(hist_frame, orient=tk.VERTICAL, command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=tree_scroll.set)
        self.trade_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.trade_tree.tag_configure('profit', foreground=SUCCESS)
        self.trade_tree.tag_configure('loss', foreground=ERROR)

        # Log tab (shows logs from all running bots)
        log_frame = tk.Frame(bottom_notebook, bg=BG_DARK)
        bottom_notebook.add(log_frame, text=" Log ")

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, bg=BG_MEDIUM, fg=FG,
                                font=('Consolas', 8), height=10)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        return frame

    # ── Update loop ─────────────────────────────────────────────────

    def _update_loop(self):
        try:
            self._update_account()
            for slot in self.slots:
                slot.update()
            if HAS_MATPLOTLIB:
                self._update_chart()
            self._update_trade_history()
            self._update_log()
        except Exception as e:
            logger.error(f"GUI update error: {e}")
        self.root.after(1000, self._update_loop)

    def _update_account(self):
        info = self.market.get_account_info()
        price = self.market.get_price()
        self.balance_lbl.config(text=f"${info.get('balance', 0):.2f}")
        self.equity_lbl.config(text=f"${info.get('equity', 0):.2f}")
        self.price_lbl.config(text=f"${price:.2f}")

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
        for pos in history[:40]:
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
        """Collect logs from all active bots into the center log tab."""
        all_logs = ""
        for slot in self.slots:
            if slot.instance_id:
                new = self.bot_manager.get_logs(slot.instance_id)
                if new:
                    all_logs += new
        if all_logs:
            self.log_text.insert(tk.END, all_logs)
            line_count = int(self.log_text.index('end-1c').split('.')[0])
            if line_count > 2000:
                self.log_text.delete('1.0', f'{line_count - 1500}.0')
            self.log_text.see(tk.END)

    def on_closing(self):
        self.bot_manager.stop_all()
        self.market.disconnect()
        self.root.destroy()
