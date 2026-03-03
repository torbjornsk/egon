"""
Egon Trading Dashboard 🎩

The GUI consumes bot state directly via BotManager.get_state().
No independent MT5 calls for bot-specific data, no log parsing for signals.
What the bot knows is what the GUI shows  --  single source of truth.

Layout: Left (M5 bot) | Center (account, chart, history) | Right (M1 bot)
"""

import tkinter as tk
from tkinter import ttk
import os
import json
import logging

from src.gui.theme import (
    BG_DARK, BG_MEDIUM, BG_LIGHT, FG, ACCENT, SUCCESS, ERROR, WARNING, NEUTRAL,
    setup_styles,
)
from src.services.bot_manager import BotManager
from src.services.market_data import MarketDataService
from src.services.trade_history import load_exit_reasons

logger = logging.getLogger(__name__)

# Optional imports
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


class EgonGUI:
    """Main GUI application  --  reads all bot data from BotManager.get_state()."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Egon Trading Dashboard 🎩")
        self.root.geometry("1920x1080")
        self.root.configure(bg=BG_DARK)

        setup_styles()

        # Services
        self.bot_manager = BotManager()
        self.market = MarketDataService()
        self.market.connect()

        # Chart state
        self.chart_timeframe = 'M5'

        # Widget refs
        self.m5_widgets: dict = {}
        self.m1_widgets: dict = {}

        self._build_ui()
        self._update_loop()

    # ── UI Construction ─────────────────────────────────────────────────

    def _build_ui(self):
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_DARK,
                               sashwidth=5, sashrelief=tk.RAISED, bd=0)
        paned.pack(fill=tk.BOTH, expand=True)

        m5_frame = self._build_bot_panel(paned, 'M5')
        paned.add(m5_frame, width=520, minsize=400, stretch="never")

        center = self._build_center(paned)
        paned.add(center, width=800, minsize=600, stretch="always")

        m1_frame = self._build_bot_panel(paned, 'M1')
        paned.add(m1_frame, width=520, minsize=400, stretch="never")

    def _build_bot_panel(self, parent, label: str) -> tk.Frame:
        """Build a bot panel (controls, market, entry conditions, positions, log)."""
        widgets = {}
        frame = tk.Frame(parent, bg=BG_DARK)

        # Title
        tk.Label(frame, text=f"{label} Bot", bg=BG_DARK, fg=ACCENT,
                 font=('Arial', 12, 'bold')).pack(pady=(5, 3))

        # Two-column info area
        info = tk.Frame(frame, bg=BG_DARK)
        info.pack(fill=tk.BOTH, expand=False, padx=8)
        info.columnconfigure(0, weight=1)
        info.columnconfigure(1, weight=1)

        left = tk.Frame(info, bg=BG_DARK)
        left.grid(row=0, column=0, sticky='nswe', padx=(0, 4))

        right = tk.Frame(info, bg=BG_DARK)
        right.grid(row=0, column=1, sticky='nswe', padx=(4, 0))

        # ── Controls ────────────────────────────────────────────────────
        ctrl_frame = ttk.LabelFrame(left, text="Controls", padding="5")
        ctrl_frame.pack(fill=tk.X, pady=(0, 3))
        ctrl = tk.Frame(ctrl_frame, bg=BG_DARK)
        ctrl.pack(fill=tk.X)

        start_btn = ttk.Button(ctrl, text="Start",
                               command=lambda: self._start_bot(label), width=8)
        start_btn.pack(side=tk.LEFT, padx=(0, 3))

        stop_btn = ttk.Button(ctrl, text="Stop",
                              command=lambda: self._stop_bot(label),
                              state=tk.DISABLED, width=8)
        stop_btn.pack(side=tk.LEFT, padx=(0, 5))

        status_lbl = ttk.Label(ctrl, text="Stopped", foreground=NEUTRAL, font=('Arial', 9))
        status_lbl.pack(side=tk.LEFT)

        widgets['start_btn'] = start_btn
        widgets['stop_btn'] = stop_btn
        widgets['status_label'] = status_lbl

        # ── Market indicators (from bot state) ─────────────────────────
        mkt_frame = ttk.LabelFrame(left, text="Market", padding="4")
        mkt_frame.pack(fill=tk.X, pady=(0, 3))
        mkt = tk.Frame(mkt_frame, bg=BG_DARK)
        mkt.pack(fill=tk.X)

        tk.Label(mkt, text="Trend:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 8)).grid(row=0, column=0, sticky=tk.W)
        widgets['trend_label'] = tk.Label(mkt, text="N/A", bg=BG_DARK, fg=FG, font=('Arial', 9))
        widgets['trend_label'].grid(row=0, column=1, sticky=tk.W, padx=(0, 8))

        tk.Label(mkt, text="RSI:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 8)).grid(row=0, column=2, sticky=tk.W)
        widgets['rsi_label'] = tk.Label(mkt, text="0.0", bg=BG_DARK, fg=ACCENT, font=('Arial', 9, 'bold'))
        widgets['rsi_label'].grid(row=0, column=3, sticky=tk.W)

        tk.Label(mkt, text="ATR:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 8)).grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        widgets['atr_label'] = tk.Label(mkt, text="$0.00", bg=BG_DARK, fg=FG, font=('Arial', 8))
        widgets['atr_label'].grid(row=1, column=1, sticky=tk.W, pady=(2, 0))

        tk.Label(mkt, text="EMA:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 8)).grid(row=2, column=0, sticky=tk.W, pady=(2, 0))
        widgets['ema_fast_label'] = tk.Label(mkt, text="$0.00", bg=BG_DARK, fg=SUCCESS, font=('Arial', 8))
        widgets['ema_fast_label'].grid(row=2, column=1, sticky=tk.W, pady=(2, 0))
        tk.Label(mkt, text="/", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 8)).grid(row=2, column=2, pady=(2, 0))
        widgets['ema_slow_label'] = tk.Label(mkt, text="$0.00", bg=BG_DARK, fg=ACCENT, font=('Arial', 8))
        widgets['ema_slow_label'].grid(row=2, column=3, sticky=tk.W, pady=(2, 0))

        # ── Entry conditions ────────────────────────────────────────────
        entry_frame = ttk.LabelFrame(left, text="Entry", padding="4")
        entry_frame.pack(fill=tk.X)
        entry_cont = tk.Frame(entry_frame, bg=BG_DARK)
        entry_cont.pack(fill=tk.X)

        widgets['entry_labels'] = []
        for _ in range(5):
            lbl = tk.Label(entry_cont, text="", bg=BG_DARK, fg=FG, font=('Arial', 8), anchor=tk.W)
            lbl.pack(fill=tk.X)
            widgets['entry_labels'].append(lbl)

        # ── Positions (2 cards) ─────────────────────────────────────────
        pos_frame = ttk.LabelFrame(right, text="Positions (0/2)", padding="4")
        pos_frame.pack(fill=tk.BOTH, expand=True)
        widgets['positions_frame'] = pos_frame

        pos_cont = tk.Frame(pos_frame, bg=BG_DARK)
        pos_cont.pack(fill=tk.BOTH, expand=True)

        widgets['position_cards'] = []
        for i in range(2):
            card = self._build_position_card(pos_cont, i)
            widgets['position_cards'].append(card)

        # ── Log ─────────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(frame, text="Log", padding="4")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(3, 8))

        log_text = tk.Text(log_frame, wrap=tk.WORD, bg=BG_MEDIUM, fg=FG,
                           insertbackground=FG, font=('Consolas', 8))
        scroll = ttk.Scrollbar(log_frame, command=log_text.yview)
        log_text.config(yscrollcommand=scroll.set)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        widgets['log_text'] = log_text

        if label == 'M5':
            self.m5_widgets = widgets
        else:
            self.m1_widgets = widgets

        return frame

    def _build_position_card(self, parent, index: int) -> dict:
        """Build a single position card with profit protection display."""
        card_frame = tk.Frame(parent, bg=BG_LIGHT, relief=tk.RAISED, bd=1)
        card_frame.pack(fill=tk.X, pady=(0, 2) if index == 0 else 0)

        content = tk.Frame(card_frame, bg=BG_LIGHT)
        content.pack(fill=tk.BOTH, expand=True, padx=4, pady=3)

        # Header
        header = tk.Frame(content, bg=BG_LIGHT)
        header.pack(fill=tk.X)
        ticket_lbl = tk.Label(header, text=f"Pos {index+1}: Empty", bg=BG_LIGHT,
                              fg=NEUTRAL, font=('Arial', 8, 'bold'))
        ticket_lbl.pack(side=tk.LEFT)
        profit_lbl = tk.Label(header, text="", bg=BG_LIGHT, fg=FG, font=('Arial', 9, 'bold'))
        profit_lbl.pack(side=tk.RIGHT)

        # Entry info
        entry_lbl = tk.Label(content, text="", bg=BG_LIGHT, fg=FG, font=('Arial', 8), anchor=tk.W)
        entry_lbl.pack(fill=tk.X, pady=(2, 0))

        # Profit protection info (NEW  --  replaces log output)
        prot_frame = tk.Frame(content, bg=BG_LIGHT)
        prot_frame.pack(fill=tk.X, pady=(3, 0))

        prot_labels = []
        for _ in range(4):
            lbl = tk.Label(prot_frame, text="", bg=BG_LIGHT, fg=FG, font=('Arial', 7), anchor=tk.W)
            lbl.pack(fill=tk.X)
            prot_labels.append(lbl)

        return {
            'frame': card_frame,
            'ticket_label': ticket_lbl,
            'profit_label': profit_lbl,
            'entry_info': entry_lbl,
            'protection_labels': prot_labels,
        }

    def _build_center(self, parent) -> tk.Frame:
        """Build center panel: account, chart, trade history."""
        frame = tk.Frame(parent, bg=BG_DARK)

        # Account bar
        acc_frame = ttk.LabelFrame(frame, text="Account", padding="5")
        acc_frame.pack(fill=tk.X, padx=8, pady=(5, 3))
        acc = tk.Frame(acc_frame, bg=BG_DARK)
        acc.pack()

        tk.Label(acc, text="Balance:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=(0, 3))
        self.balance_lbl = tk.Label(acc, text="$0.00", bg=BG_DARK, fg=FG, font=('Arial', 11, 'bold'))
        self.balance_lbl.grid(row=0, column=1, sticky=tk.W, padx=(0, 15))

        tk.Label(acc, text="Equity:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 9, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(0, 3))
        self.equity_lbl = tk.Label(acc, text="$0.00", bg=BG_DARK, fg=FG, font=('Arial', 11, 'bold'))
        self.equity_lbl.grid(row=0, column=3, sticky=tk.W, padx=(0, 15))

        tk.Label(acc, text="Price:", bg=BG_DARK, fg=NEUTRAL, font=('Arial', 9, 'bold')).grid(row=0, column=4, sticky=tk.W, padx=(0, 3))
        self.price_lbl = tk.Label(acc, text="$0.00", bg=BG_DARK, fg=WARNING, font=('Arial', 11, 'bold'))
        self.price_lbl.grid(row=0, column=5, sticky=tk.W)

        # Chart
        if HAS_MATPLOTLIB:
            chart_frame = ttk.LabelFrame(frame, text="Price Chart", padding="3")
            chart_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 3))

            chart_ctrl = tk.Frame(chart_frame, bg=BG_DARK)
            chart_ctrl.pack(fill=tk.X, pady=(0, 3))
            tk.Label(chart_ctrl, text="Timeframe:", bg=BG_DARK, fg=FG, font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))

            self.chart_tf_var = tk.StringVar(value='M5')
            ttk.Radiobutton(chart_ctrl, text='M5', variable=self.chart_tf_var, value='M5',
                            command=self._on_tf_change).pack(side=tk.LEFT, padx=5)
            ttk.Radiobutton(chart_ctrl, text='M1', variable=self.chart_tf_var, value='M1',
                            command=self._on_tf_change).pack(side=tk.LEFT, padx=5)

            self.fig = Figure(figsize=(8, 4), dpi=100, facecolor=BG_DARK)
            self.ax = self.fig.add_subplot(111, facecolor=BG_MEDIUM)
            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Trade history
        hist_frame = ttk.LabelFrame(frame, text="Trade History (Last 100)", padding="3")
        hist_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        cols = ('Exit Time', 'Entry Time', 'Bot', 'Type', 'Vol', 'Entry', 'Exit', 'Profit', 'Reason')
        self.trade_tree = ttk.Treeview(hist_frame, columns=cols, show='headings', height=10)
        for c in cols:
            self.trade_tree.heading(c, text=c)
        self.trade_tree.column('Exit Time', width=130)
        self.trade_tree.column('Entry Time', width=130)
        self.trade_tree.column('Bot', width=40)
        self.trade_tree.column('Type', width=50)
        self.trade_tree.column('Vol', width=50)
        self.trade_tree.column('Entry', width=70)
        self.trade_tree.column('Exit', width=70)
        self.trade_tree.column('Profit', width=70)
        self.trade_tree.column('Reason', width=250)

        tree_scroll = ttk.Scrollbar(hist_frame, orient=tk.VERTICAL, command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=tree_scroll.set)
        self.trade_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.trade_tree.tag_configure('profit', foreground=SUCCESS)
        self.trade_tree.tag_configure('loss', foreground=ERROR)

        return frame

    # ── Bot start/stop ──────────────────────────────────────────────────

    def _start_bot(self, label: str):
        interval = 1 if label == 'M1' else 15
        self.bot_manager.start_bot(label, check_interval=interval)
        w = self.m5_widgets if label == 'M5' else self.m1_widgets
        w['start_btn'].config(state=tk.DISABLED)
        w['stop_btn'].config(state=tk.NORMAL)

    def _stop_bot(self, label: str):
        self.bot_manager.stop_bot(label)
        w = self.m5_widgets if label == 'M5' else self.m1_widgets
        w['start_btn'].config(state=tk.NORMAL)
        w['stop_btn'].config(state=tk.DISABLED)

    def _on_tf_change(self):
        self.chart_timeframe = self.chart_tf_var.get()

    # ── Update loop (1 second) ──────────────────────────────────────────

    def _update_loop(self):
        try:
            self._update_account()
            self._update_bot_panel('M5', self.m5_widgets)
            self._update_bot_panel('M1', self.m1_widgets)
            if HAS_MATPLOTLIB:
                self._update_chart()
            self._update_trade_history()
        except Exception as e:
            logger.error(f"GUI update error: {e}")

        self.root.after(1000, self._update_loop)

    def _update_account(self):
        info = self.market.get_account_info()
        price = self.market.get_price()
        self.balance_lbl.config(text=f"${info.get('balance', 0):.2f}")
        self.equity_lbl.config(text=f"${info.get('equity', 0):.2f}")
        self.price_lbl.config(text=f"${price:.2f}")

    # ── Bot panel update (reads from bot.get_state()) ───────────────────

    def _update_bot_panel(self, label: str, widgets: dict):
        """Update an entire bot panel from the bot's state dict."""
        if not widgets:
            return

        state = self.bot_manager.get_state(label)

        # Status
        status = state.get('status', 'Stopped')
        color = SUCCESS if status == 'Running' else ERROR if status == 'Paused' else NEUTRAL
        widgets['status_label'].config(text=status, foreground=color)

        # Indicators (from the bot's own computation  --  single source of truth)
        ind = state.get('indicators', {})
        rsi = ind.get('rsi', 0)
        atr = ind.get('atr', 0)
        ema_f = ind.get('ema_fast', 0)
        ema_s = ind.get('ema_slow', 0)
        uptrend = ind.get('uptrend', False)
        downtrend = ind.get('downtrend', False)

        trend_str = 'UP ↑' if uptrend else 'DOWN ↓' if downtrend else 'SIDE →'
        trend_color = SUCCESS if uptrend else ERROR if downtrend else NEUTRAL
        widgets['trend_label'].config(text=trend_str, fg=trend_color)

        rsi_color = SUCCESS if rsi < 35 else ERROR if rsi > 65 else ACCENT
        widgets['rsi_label'].config(text=f"{rsi:.1f}", fg=rsi_color)
        widgets['atr_label'].config(text=f"${atr:.2f}")
        widgets['ema_fast_label'].config(text=f"${ema_f:.2f}")
        widgets['ema_slow_label'].config(text=f"${ema_s:.2f}")

        # Entry conditions (derived from bot state, not independent computation)
        positions = state.get('positions', [])
        max_pos = state.get('max_positions', 2)
        cooldown = state.get('cooldown', {})

        conditions = []
        # RSI
        if rsi > 0:
            if rsi < 38:
                conditions.append(f"✅ RSI: {rsi:.1f} (Buy zone)")
            elif rsi > 62:
                conditions.append(f"⚠ RSI: {rsi:.1f} (Sell zone)")
            else:
                conditions.append(f"❌ RSI: {rsi:.1f} (Neutral)")
        else:
            conditions.append("⚪ RSI: N/A")

        # Trend
        conditions.append(f"{'✅' if uptrend else '⚠'} Trend: {trend_str}")

        # Positions
        n = len(positions)
        if n < max_pos:
            conditions.append(f"✅ Positions: {n}/{max_pos}")
        else:
            conditions.append(f"❌ Positions: {n}/{max_pos} (Max)")

        # Cooldown
        if cooldown.get('active'):
            remaining = cooldown.get('remaining_minutes', 0)
            conditions.append(f"❌ {cooldown.get('reason', 'Cooldown')}: {remaining:.1f}min")
        else:
            conditions.append(f"✅ {cooldown.get('reason', 'Ready')}")

        # Consecutive losses
        losses = state.get('consecutive_losses', 0)
        if losses > 0:
            conditions.append(f"⚠ Consecutive losses: {losses}")
        else:
            conditions.append(f"✅ No consecutive losses")

        for i, cond in enumerate(conditions):
            if i < len(widgets['entry_labels']):
                widgets['entry_labels'][i].config(text=cond)

        # Positions frame title
        widgets['positions_frame'].config(text=f"Positions ({n}/{max_pos})")

        # Position cards  --  data comes directly from bot state
        self._update_position_cards(widgets['position_cards'], positions)

        # Log (append new content)
        logs = self.bot_manager.get_logs(label)
        log_widget = widgets.get('log_text')
        if log_widget and logs:
            current = log_widget.get('1.0', tk.END)
            if len(logs) > len(current):
                new_text = logs[len(current)-1:]
                if new_text.strip():
                    log_widget.insert(tk.END, new_text)
                    log_widget.see(tk.END)

    def _update_position_cards(self, cards: list[dict], positions: list[dict]):
        """
        Update position cards with data from bot state.

        Profit protection info is shown directly in the card instead of being logged.
        """
        for i, card in enumerate(cards):
            if i < len(positions):
                pos = positions[i]
                direction = pos.get('direction', '?')
                ticket = pos.get('ticket', 0)
                profit = pos.get('profit', 0)
                entry = pos.get('entry_price', 0)
                minutes = pos.get('minutes_held', 0)
                sl = pos.get('sl', 0)
                tp = pos.get('tp', 0)
                current = pos.get('current_price', 0)

                # Header
                type_color = SUCCESS if direction == 'LONG' else ERROR
                card['ticket_label'].config(text=f"#{ticket} {direction}", fg=type_color)

                profit_color = SUCCESS if profit > 0 else ERROR if profit < 0 else FG
                card['profit_label'].config(text=f"${profit:.2f}", fg=profit_color)

                # Entry info
                card['entry_info'].config(
                    text=f"Entry: ${entry:.2f} | Now: ${current:.2f} | Held: {minutes:.0f}min"
                )

                # Profit protection info (THE KEY CHANGE  --  from bot state, not logs)
                prot = pos.get('protection', {})
                prot_labels = card['protection_labels']

                if prot.get('enabled'):
                    peak = prot.get('peak_profit', 0)
                    threshold = prot.get('threshold_dollars', 0)
                    activated = prot.get('activated', False)
                    dd_limit = prot.get('drawdown_limit_pct', 0)
                    dd_current = prot.get('current_drawdown_pct', 0)
                    trigger_at = prot.get('exit_trigger_at', 0)

                    if activated:
                        # Protection is active  --  show live exit trigger
                        prot_labels[0].config(
                            text=f"🛡 Protection ACTIVE",
                            fg=SUCCESS,
                        )
                        prot_labels[1].config(
                            text=f"Peak: ${peak:.2f} | Exit at: ${trigger_at:.2f}",
                            fg=WARNING,
                        )
                        prot_labels[2].config(
                            text=f"Drawdown: {dd_current*100:.1f}% / {dd_limit*100:.0f}% limit",
                            fg=ERROR if dd_current > dd_limit * 0.8 else FG,
                        )
                        prot_labels[3].config(
                            text=f"SL: ${sl:.2f} | TP: ${tp:.2f}",
                            fg=NEUTRAL,
                        )
                    else:
                        # Not yet activated  --  show threshold
                        prot_labels[0].config(
                            text=f"🔒 Protection: waiting",
                            fg=NEUTRAL,
                        )
                        prot_labels[1].config(
                            text=f"Activates at: ${threshold:.2f} profit",
                            fg=NEUTRAL,
                        )
                        prot_labels[2].config(
                            text=f"Current: ${profit:.2f} | Peak: ${peak:.2f}",
                            fg=FG,
                        )
                        prot_labels[3].config(
                            text=f"SL: ${sl:.2f} | TP: ${tp:.2f}",
                            fg=NEUTRAL,
                        )
                else:
                    prot_labels[0].config(text=f"SL: ${sl:.2f} | TP: ${tp:.2f}", fg=NEUTRAL)
                    for j in range(1, 4):
                        prot_labels[j].config(text="")
            else:
                # Empty slot
                card['ticket_label'].config(text=f"Pos {i+1}: Empty", fg=NEUTRAL)
                card['profit_label'].config(text="")
                card['entry_info'].config(text="")
                for lbl in card['protection_labels']:
                    lbl.config(text="")

    # ── Chart ───────────────────────────────────────────────────────────

    def _update_chart(self):
        if not self.market.connected:
            return

        try:
            bars = 100 if self.chart_timeframe == 'M1' else 50
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
            self.ax.tick_params(colors=FG, labelsize=8)
            for spine in self.ax.spines.values():
                spine.set_color(BG_LIGHT)
            self.ax.grid(True, alpha=0.2, color=BG_LIGHT)
            self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))

            # X-axis timestamps
            interval = 10 if self.chart_timeframe == 'M1' else 15
            ticks, labels = [], []
            for i in range(len(df)):
                t = df.iloc[i]['time']
                if t.minute % interval == 0:
                    ticks.append(i)
                    labels.append(t.strftime('%H:%M'))
            if ticks:
                self.ax.set_xticks(ticks)
                self.ax.set_xticklabels(labels, fontsize=9)

            self.canvas.draw()
        except Exception as e:
            logger.error(f"Chart error: {e}")

    # ── Trade history ───────────────────────────────────────────────────

    def _update_trade_history(self):
        history = self.market.get_trade_history()
        exit_reasons = load_exit_reasons()

        for item in self.trade_tree.get_children():
            self.trade_tree.delete(item)

        for pos in history:
            ticket_str = str(pos.get('ticket', ''))
            pid_str = str(pos.get('position_id', ''))

            reason = None
            if ticket_str in exit_reasons:
                reason = exit_reasons[ticket_str].get('reason')
            elif pid_str in exit_reasons:
                reason = exit_reasons[pid_str].get('reason')
            if not reason:
                reason = 'Unknown'

            tag = 'profit' if pos['profit'] > 0 else 'loss'

            self.trade_tree.insert('', tk.END, values=(
                pos['exit_time'].strftime('%Y-%m-%d %H:%M'),
                pos['entry_time'].strftime('%Y-%m-%d %H:%M'),
                pos['bot'],
                pos['type'],
                f"{pos['volume']:.2f}",
                f"${pos['entry_price']:.2f}",
                f"${pos['exit_price']:.2f}",
                f"${pos['profit']:.2f}",
                reason,
            ), tags=(tag,))

    # ── Cleanup ─────────────────────────────────────────────────────────

    def on_closing(self):
        self.bot_manager.stop_all()
        self.market.disconnect()
        self.root.destroy()
