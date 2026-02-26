"""
Trading Bot GUI V3 - Reorganized Layout
- Center: Account info, price chart, trade history
- Left: M5 bot controls + log (horizontal layout)
- Right: M1 bot controls + log (horizontal layout)
"""

import tkinter as tk
from tkinter import ttk
import subprocess
import threading
import queue
import time
from datetime import datetime
import re
import os

try:
    import MetaTrader5 as mt5
    import pandas as pd
    import numpy as np
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    print("Warning: MetaTrader5 not available. Market data will not update.")

try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: Matplotlib not available. Price chart will not display.")

class BotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gold Trading Bot Dashboard V3")
        self.root.geometry("1920x1080")
        
        # Dark mode colors
        self.bg_dark = '#1e1e1e'
        self.bg_medium = '#2d2d2d'
        self.bg_light = '#3e3e3e'
        self.fg_color = '#e0e0e0'
        self.accent_color = '#007acc'
        self.success_color = '#4ec9b0'
        self.error_color = '#f48771'
        self.warning_color = '#dcdcaa'
        self.neutral_color = '#808080'
        
        # Configure root window
        self.root.configure(bg=self.bg_dark)
        
        # Configure ttk styles for dark mode
        self.setup_styles()
        
        # Bot processes
        self.m5_process = None
        self.m1_process = None
        
        # Output queues
        self.m5_queue = queue.Queue()
        self.m1_queue = queue.Queue()
        
        # MT5 connection
        self.mt5_connected = False
        self.mt5_symbol = 'XAUUSD'
        
        # Chart settings
        self.chart_timeframe = 'M5'  # Default to M5
        
        # Bot states
        self.m5_data = {
            'status': 'Stopped',
            'positions': 0,
            'position_details': [],
            'max_positions': False,
            'gap_warmup': False,
            'cooldown_active': False,
            'ready_for_entry': False,
            'has_signal': False,
            'signal': 'None'
        }
        
        self.m1_data = {
            'status': 'Stopped',
            'positions': 0,
            'position_details': [],
            'max_positions': False,
            'gap_warmup': False,
            'cooldown_active': False,
            'ready_for_entry': False,
            'has_signal': False,
            'signal': 'None'
        }
        
        # Market data
        self.market_data = {
            'balance': 0,
            'equity': 0,
            'price': 0,
            'atr_m5': 0,
            'atr_m1': 0,
            'ema_fast_m5': 0,
            'ema_slow_m5': 0,
            'ema_fast_m1': 0,
            'ema_slow_m1': 0,
            'rsi_m5': 0,
            'rsi_m1': 0,
            'trend_m5': 'N/A',
            'trend_m1': 'N/A'
        }
        
        # Trade history
        self.trade_history = []
        
        # Connect to MT5
        if MT5_AVAILABLE:
            self.connect_mt5()
        
        self.setup_ui()
        self.update_displays()
    
    def setup_styles(self):
        """Setup dark mode styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure('TFrame', background=self.bg_dark)
        style.configure('TLabelframe', background=self.bg_dark, foreground=self.fg_color, bordercolor=self.bg_light)
        style.configure('TLabelframe.Label', background=self.bg_dark, foreground=self.accent_color, font=('Arial', 9, 'bold'))
        style.configure('TLabel', background=self.bg_dark, foreground=self.fg_color)
        style.configure('TButton', background=self.bg_medium, foreground=self.fg_color, bordercolor=self.bg_light)
        style.map('TButton', background=[('active', self.accent_color)])
        
        # Configure Treeview (table) for dark mode
        style.configure('Treeview',
                       background=self.bg_medium,
                       foreground=self.fg_color,
                       fieldbackground=self.bg_medium,
                       borderwidth=0)
        style.configure('Treeview.Heading',
                       background=self.bg_light,
                       foreground=self.fg_color,
                       borderwidth=1)
        style.map('Treeview', background=[('selected', self.accent_color)])
        style.map('Treeview.Heading', background=[('active', self.accent_color)])
    
    def connect_mt5(self):
        """Connect to MT5 for real-time data"""
        if not MT5_AVAILABLE:
            return False
        
        if not mt5.initialize():
            print(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        
        self.mt5_connected = True
        print("Connected to MT5 for market data")
        return True
    
    def disconnect_mt5(self):
        """Disconnect from MT5"""
        if MT5_AVAILABLE and self.mt5_connected:
            mt5.shutdown()
            self.mt5_connected = False
    
    def fetch_trade_history(self):
        """Fetch last 100 closed positions from MT5 (grouped by position)"""
        if not self.mt5_connected:
            return
        
        try:
            # Get deals from last 30 days
            from_date = datetime.now() - pd.Timedelta(days=30)
            to_date = datetime.now() + pd.Timedelta(hours=1)
            deals = mt5.history_deals_get(from_date, to_date)
            
            if deals is None or len(deals) == 0:
                return
            
            # Group deals by position_id
            position_map = {}
            
            for deal in deals:
                # Only process XAUUSD deals from our bots
                if deal.symbol != 'XAUUSD' or deal.magic not in [234000, 234001]:
                    continue
                
                pos_id = deal.position_id
                
                if pos_id not in position_map:
                    position_map[pos_id] = {
                        'deals': [],
                        'bot': 'M5' if deal.magic == 234000 else 'M1'
                    }
                
                position_map[pos_id]['deals'].append(deal)
            
            # Convert to list of positions
            completed_positions = []
            for pos_id, data in position_map.items():
                deals_list = data['deals']
                
                # Sort deals by time
                deals_list.sort(key=lambda d: d.time)
                
                # Find entry and exit deals by type
                # For LONG: entry is BUY (type=0), exit is SELL (type=1)
                # For SHORT: entry is SELL (type=1), exit is BUY (type=0)
                buy_deals = [d for d in deals_list if d.type == 0]  # BUY
                sell_deals = [d for d in deals_list if d.type == 1]  # SELL
                
                if len(buy_deals) > 0 and len(sell_deals) > 0:
                    # Closed position - determine if LONG or SHORT
                    first_deal = deals_list[0]
                    
                    if first_deal.type == 0:  # First deal is BUY = LONG position
                        entry_deal = buy_deals[0]
                        exit_deal = sell_deals[0]
                        position_type = 'LONG'
                    else:  # First deal is SELL = SHORT position
                        entry_deal = sell_deals[0]
                        exit_deal = buy_deals[0]
                        position_type = 'SHORT'
                    
                    # Adjust timestamps for MT5 being 1 hour ahead
                    completed_positions.append({
                        'position_id': pos_id,
                        'bot': data['bot'],
                        'type': position_type,
                        'entry_time': datetime.fromtimestamp(entry_deal.time - 3600),
                        'exit_time': datetime.fromtimestamp(exit_deal.time - 3600),
                        'entry_price': entry_deal.price,
                        'exit_price': exit_deal.price,
                        'volume': entry_deal.volume,
                        'profit': exit_deal.profit,
                        'is_closed': True
                    })
                # Skip open positions - they don't appear in MT5 history
            
            # Sort by entry time descending and take last 100
            completed_positions.sort(key=lambda x: x['entry_time'], reverse=True)
            self.trade_history = completed_positions[:100]
            
        except Exception as e:
            print(f"Error fetching trade history: {e}")
            import traceback
            traceback.print_exc()
    
    def setup_ui(self):
        """Setup the new UI layout"""
        # Main container with 3 columns
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.bg_dark,
                                    sashwidth=5, sashrelief=tk.RAISED, bd=0)
        main_paned.pack(fill=tk.BOTH, expand=True)
        
        # === LEFT: M5 BOT ===
        m5_frame = self.setup_bot_side(main_paned, "M5", self.m5_data, self.m5_queue)
        main_paned.add(m5_frame, width=520, minsize=400, stretch="never")
        
        # === CENTER: ACCOUNT + CHART + TRADE HISTORY ===
        center_frame = self.setup_center_panel(main_paned)
        main_paned.add(center_frame, width=800, minsize=600, stretch="always")
        
        # === RIGHT: M1 BOT ===
        m1_frame = self.setup_bot_side(main_paned, "M1", self.m1_data, self.m1_queue)
        main_paned.add(m1_frame, width=520, minsize=400, stretch="never")
    
    def setup_bot_side(self, parent, bot_name, bot_data, log_queue):
        """Setup a bot panel on the side"""
        bot_frame = tk.Frame(parent, bg=self.bg_dark)
        # Don't add to parent here - return the frame instead
        
        # Title
        tk.Label(bot_frame, text=f"{bot_name} Bot", bg=self.bg_dark, fg=self.accent_color,
                font=('Arial', 12, 'bold')).pack(pady=(5, 3))
        
        # Store widgets
        if bot_name == "M5":
            self.m5_widgets = {}
            widgets = self.m5_widgets
        else:
            self.m1_widgets = {}
            widgets = self.m1_widgets
        
        # === INFO GRID (2 columns) ===
        info_container = tk.Frame(bot_frame, bg=self.bg_dark)
        info_container.pack(fill=tk.BOTH, expand=False, padx=8, pady=0)
        
        # Configure grid weights
        info_container.columnconfigure(0, weight=1)  # Left column
        info_container.columnconfigure(1, weight=1)  # Right column
        
        # === LEFT COLUMN ===
        left_column = tk.Frame(info_container, bg=self.bg_dark)
        left_column.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E), padx=(0, 4))
        
        # === CONTROLS ===
        controls_frame = ttk.LabelFrame(left_column, text="Controls", padding="5")
        controls_frame.pack(fill=tk.X, pady=(0, 3))
        
        controls = tk.Frame(controls_frame, bg=self.bg_dark)
        controls.pack(fill=tk.X)
        
        start_btn = ttk.Button(controls, text="Start",
                              command=lambda: self.start_m5() if bot_name == "M5" else self.start_m1(),
                              width=8)
        start_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        stop_btn = ttk.Button(controls, text="Stop",
                             command=lambda: self.stop_m5() if bot_name == "M5" else self.stop_m1(),
                             state=tk.DISABLED, width=8)
        stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        status_label = ttk.Label(controls, text="Stopped", foreground=self.neutral_color, font=('Arial', 9))
        status_label.pack(side=tk.LEFT)
        
        widgets['start_btn'] = start_btn
        widgets['stop_btn'] = stop_btn
        widgets['status_label'] = status_label
        
        # === MARKET INDICATORS ===
        market_frame = ttk.LabelFrame(left_column, text="Market", padding="4")
        market_frame.pack(fill=tk.X, pady=(0, 3))
        
        market_grid = tk.Frame(market_frame, bg=self.bg_dark)
        market_grid.pack(fill=tk.X)
        
        # Row 0: Trend and RSI
        tk.Label(market_grid, text="Trend:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 8)).grid(row=0, column=0, sticky=tk.W, padx=(0,2))
        trend_label = tk.Label(market_grid, text="N/A", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 9))
        trend_label.grid(row=0, column=1, sticky=tk.W, padx=(0,8))
        widgets['trend_label'] = trend_label
        
        tk.Label(market_grid, text="RSI:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 8)).grid(row=0, column=2, sticky=tk.W, padx=(0,2))
        rsi_label = tk.Label(market_grid, text="0.0", bg=self.bg_dark, fg=self.accent_color, font=('Arial', 9, 'bold'))
        rsi_label.grid(row=0, column=3, sticky=tk.W)
        widgets['rsi_label'] = rsi_label
        
        # Row 1: ATR
        tk.Label(market_grid, text="ATR:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 8)).grid(row=1, column=0, sticky=tk.W, padx=(0,2), pady=(2,0))
        atr_label = tk.Label(market_grid, text="$0.00", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 8))
        atr_label.grid(row=1, column=1, sticky=tk.W, pady=(2,0))
        widgets['atr_label'] = atr_label
        
        # Row 2: EMAs
        tk.Label(market_grid, text="EMA:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 8)).grid(row=2, column=0, sticky=tk.W, padx=(0,2), pady=(2,0))
        ema_fast_label = tk.Label(market_grid, text="$0.00", bg=self.bg_dark, fg=self.success_color, font=('Arial', 8))
        ema_fast_label.grid(row=2, column=1, sticky=tk.W, pady=(2,0))
        widgets['ema_fast_label'] = ema_fast_label
        
        tk.Label(market_grid, text="/", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 8)).grid(row=2, column=2, sticky=tk.W, padx=2, pady=(2,0))
        ema_slow_label = tk.Label(market_grid, text="$0.00", bg=self.bg_dark, fg=self.accent_color, font=('Arial', 8))
        ema_slow_label.grid(row=2, column=3, sticky=tk.W, pady=(2,0))
        widgets['ema_slow_label'] = ema_slow_label
        
        # === ENTRY CONDITIONS ===
        entry_frame = ttk.LabelFrame(left_column, text="Entry", padding="4")
        entry_frame.pack(fill=tk.X)
        
        entry_container = tk.Frame(entry_frame, bg=self.bg_dark)
        entry_container.pack(fill=tk.X)
        
        # Create labels for entry conditions
        widgets['entry_labels'] = []
        for i in range(5):  # 5 condition rows
            label = tk.Label(entry_container, text="", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 8), anchor=tk.W)
            label.pack(fill=tk.X, pady=0)
            widgets['entry_labels'].append(label)
        
        # === RIGHT COLUMN ===
        right_column = tk.Frame(info_container, bg=self.bg_dark)
        right_column.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.W, tk.E), padx=(4, 0))
        
        # === POSITIONS (2 STATIC CARDS) ===
        positions_frame = ttk.LabelFrame(right_column, text="Positions (0/2)", padding="4")
        positions_frame.pack(fill=tk.BOTH, expand=True)
        widgets['positions_frame'] = positions_frame
        
        # Container for 2 position cards
        positions_container = tk.Frame(positions_frame, bg=self.bg_dark)
        positions_container.pack(fill=tk.BOTH, expand=True)
        
        # Create 2 static position card slots
        widgets['position_cards'] = []
        for i in range(2):
            card_frame = tk.Frame(positions_container, bg=self.bg_light, relief=tk.RAISED, bd=1)
            card_frame.pack(fill=tk.X, pady=(0, 2) if i == 0 else 0)
            
            # Card content container
            card_content = tk.Frame(card_frame, bg=self.bg_light)
            card_content.pack(fill=tk.BOTH, expand=True, padx=4, pady=3)
            
            # Header (ticket + type + profit)
            header = tk.Frame(card_content, bg=self.bg_light)
            header.pack(fill=tk.X)
            
            ticket_label = tk.Label(header, text=f"Pos {i+1}: Empty", bg=self.bg_light, 
                                   fg=self.neutral_color, font=('Arial', 8, 'bold'))
            ticket_label.pack(side=tk.LEFT)
            
            profit_label = tk.Label(header, text="", bg=self.bg_light, fg=self.fg_color, 
                                   font=('Arial', 9, 'bold'))
            profit_label.pack(side=tk.RIGHT)
            
            # Entry info (entry price + time held)
            entry_info = tk.Label(card_content, text="", bg=self.bg_light, fg=self.fg_color, 
                                 font=('Arial', 8), anchor=tk.W)
            entry_info.pack(fill=tk.X, pady=(2,0))
            
            # Exit signals container
            exit_signals_frame = tk.Frame(card_content, bg=self.bg_light)
            exit_signals_frame.pack(fill=tk.X, pady=(3,0))
            
            exit_signals_label = tk.Label(exit_signals_frame, text="Exit:", 
                                         bg=self.bg_light, fg=self.neutral_color, 
                                         font=('Arial', 7, 'bold'))
            exit_signals_label.pack(anchor=tk.W)
            
            # Exit condition labels (will be populated dynamically)
            exit_labels = []
            for j in range(5):  # 5 exit conditions (price info + 4 conditions)
                label = tk.Label(exit_signals_frame, text="", bg=self.bg_light, 
                               fg=self.fg_color, font=('Arial', 7), anchor=tk.W)
                label.pack(fill=tk.X, pady=0)
                exit_labels.append(label)
            
            widgets['position_cards'].append({
                'frame': card_frame,
                'ticket_label': ticket_label,
                'profit_label': profit_label,
                'entry_info': entry_info,
                'exit_labels': exit_labels
            })
        
        # === LOG (MORE VERTICAL SPACE) ===
        log_frame = ttk.LabelFrame(bot_frame, text="Log", padding="4")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(3, 8))
        
        log_text = tk.Text(log_frame, wrap=tk.WORD, bg=self.bg_medium, fg=self.fg_color,
                          insertbackground=self.fg_color, font=('Consolas', 8))
        log_scrollbar = ttk.Scrollbar(log_frame, command=log_text.yview)
        log_text.config(yscrollcommand=log_scrollbar.set)
        
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        if bot_name == "M5":
            self.m5_log_widget = log_text
        else:
            self.m1_log_widget = log_text
        
        return bot_frame
    
    def setup_center_panel(self, parent):
        """Setup center panel with account info, chart, and trade history"""
        center_frame = tk.Frame(parent, bg=self.bg_dark)
        # Don't add to parent here - return the frame instead
        
        # Account info
        account_frame = ttk.LabelFrame(center_frame, text="Account", padding="5")
        account_frame.pack(fill=tk.X, padx=8, pady=(5, 3))
        
        acc_grid = tk.Frame(account_frame, bg=self.bg_dark)
        acc_grid.pack()
        
        tk.Label(acc_grid, text="Balance:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=(0,3))
        self.account_balance_label = tk.Label(acc_grid, text="$0.00", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 11, 'bold'))
        self.account_balance_label.grid(row=0, column=1, sticky=tk.W, padx=(0,15))
        
        tk.Label(acc_grid, text="Equity:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 9, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(0,3))
        self.account_equity_label = tk.Label(acc_grid, text="$0.00", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 11, 'bold'))
        self.account_equity_label.grid(row=0, column=3, sticky=tk.W, padx=(0,15))
        
        tk.Label(acc_grid, text="Price:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 9, 'bold')).grid(row=0, column=4, sticky=tk.W, padx=(0,3))
        self.shared_price_label = tk.Label(acc_grid, text="$0.00", bg=self.bg_dark, fg=self.warning_color, font=('Arial', 11, 'bold'))
        self.shared_price_label.grid(row=0, column=5, sticky=tk.W)
        
        # Price chart
        if MATPLOTLIB_AVAILABLE:
            chart_frame = ttk.LabelFrame(center_frame, text="Price Chart", padding="3")
            chart_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 3))
            
            # Chart controls
            chart_controls = tk.Frame(chart_frame, bg=self.bg_dark)
            chart_controls.pack(fill=tk.X, pady=(0, 3))
            
            tk.Label(chart_controls, text="Timeframe:", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 5))
            
            # Timeframe selector
            self.chart_tf_var = tk.StringVar(value='M5')
            m5_radio = ttk.Radiobutton(chart_controls, text='M5 (50 candles)', variable=self.chart_tf_var, value='M5',
                                      command=self.on_chart_timeframe_change)
            m5_radio.pack(side=tk.LEFT, padx=5)
            
            m1_radio = ttk.Radiobutton(chart_controls, text='M1 (100 candles)', variable=self.chart_tf_var, value='M1',
                                      command=self.on_chart_timeframe_change)
            m1_radio.pack(side=tk.LEFT, padx=5)
            
            self.fig = Figure(figsize=(8, 4), dpi=100, facecolor='#1e1e1e')
            self.ax = self.fig.add_subplot(111, facecolor='#2d2d2d')
            
            self.ax.tick_params(colors='#e0e0e0', labelsize=8)
            self.ax.spines['bottom'].set_color('#3e3e3e')
            self.ax.spines['top'].set_color('#3e3e3e')
            self.ax.spines['left'].set_color('#3e3e3e')
            self.ax.spines['right'].set_color('#3e3e3e')
            self.ax.grid(True, alpha=0.2, color='#3e3e3e')
            
            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Trade history
        history_frame = ttk.LabelFrame(center_frame, text="Trade History (Last 100 positions)", padding="3")
        history_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        
        # Create treeview for trade history
        columns = ('Entry Time', 'Bot', 'Type', 'Volume', 'Entry', 'Exit', 'Profit')
        self.trade_tree = ttk.Treeview(history_frame, columns=columns, show='headings', height=10)
        
        # Define headings
        self.trade_tree.heading('Entry Time', text='Entry Time')
        self.trade_tree.heading('Bot', text='Bot')
        self.trade_tree.heading('Type', text='Type')
        self.trade_tree.heading('Volume', text='Vol')
        self.trade_tree.heading('Entry', text='Entry')
        self.trade_tree.heading('Exit', text='Exit')
        self.trade_tree.heading('Profit', text='Profit')
        
        # Define column widths
        self.trade_tree.column('Entry Time', width=130)
        self.trade_tree.column('Bot', width=40)
        self.trade_tree.column('Type', width=50)
        self.trade_tree.column('Volume', width=50)
        self.trade_tree.column('Entry', width=80)
        self.trade_tree.column('Exit', width=80)
        self.trade_tree.column('Profit', width=80)
        
        # Scrollbar
        tree_scroll = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.trade_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        return center_frame
    
    def update_trade_history_display(self):
        """Update the trade history treeview"""
        # Clear existing items
        for item in self.trade_tree.get_children():
            self.trade_tree.delete(item)
        
        # Add closed positions only
        for pos in self.trade_history:
            entry_time_str = pos['entry_time'].strftime('%Y-%m-%d %H:%M')
            
            # All positions in history are closed
            exit_str = f"${pos['exit_price']:.2f}"
            profit_str = f"${pos['profit']:.2f}"
            
            # Color coding based on profit/loss
            if pos['profit'] > 0:
                tag = 'profit'  # Green for profit
            else:
                tag = 'loss'  # Red for loss
            
            values = (
                entry_time_str,
                pos['bot'],
                pos['type'],
                f"{pos['volume']:.2f}",
                f"${pos['entry_price']:.2f}",
                exit_str,
                profit_str
            )
            
            self.trade_tree.insert('', tk.END, values=values, tags=(tag,))
        
        # Configure tags with colors
        self.trade_tree.tag_configure('profit', foreground=self.success_color)  # Green
        self.trade_tree.tag_configure('loss', foreground=self.error_color)  # Red
    
    def update_displays(self):
        """Update all displays"""
        # Update M5 log
        if self.m5_log_widget:
            try:
                while True:
                    line = self.m5_queue.get_nowait()
                    self.m5_log_widget.insert(tk.END, line)
                    self.m5_log_widget.see(tk.END)
                    self.parse_m5_line(line)
            except queue.Empty:
                pass
        
        # Update M1 log
        if self.m1_log_widget:
            try:
                while True:
                    line = self.m1_queue.get_nowait()
                    self.m1_log_widget.insert(tk.END, line)
                    self.m1_log_widget.see(tk.END)
                    self.parse_m1_line(line)
            except queue.Empty:
                pass
        
        # Fetch fresh data from MT5
        if self.mt5_connected:
            self.fetch_market_data()
            self.update_price_chart()
            self.fetch_trade_history()
            self.update_trade_history_display()
        
        # Update account info
        self.account_balance_label.config(text=f"${self.market_data['balance']:.2f}")
        self.account_equity_label.config(text=f"${self.market_data['equity']:.2f}")
        self.shared_price_label.config(text=f"${self.market_data['price']:.2f}")
        
        # Update M5 display
        self.update_bot_display('M5', self.m5_data, self.m5_widgets, 
                               self.market_data['atr_m5'],
                               self.market_data['ema_fast_m5'], self.market_data['ema_slow_m5'],
                               self.market_data['rsi_m5'], self.market_data['trend_m5'])
        
        # Update M1 display
        self.update_bot_display('M1', self.m1_data, self.m1_widgets,
                               self.market_data['atr_m1'],
                               self.market_data['ema_fast_m1'], self.market_data['ema_slow_m1'],
                               self.market_data['rsi_m1'], self.market_data['trend_m1'])
        
        # Schedule next update
        self.root.after(1000, self.update_displays)
    
    def get_python_executable(self):
        """Get the correct Python executable (venv if available)"""
        venv_paths = [
            os.path.join('.venv', 'Scripts', 'python.exe'),
            os.path.join('venv', 'Scripts', 'python.exe'),
            'python'
        ]
        
        for path in venv_paths:
            if os.path.exists(path):
                return path
        
        return 'python'
    
    def read_m5_output(self):
        """Read M5 bot output"""
        try:
            for line in iter(self.m5_process.stdout.readline, ''):
                if line:
                    self.m5_queue.put(line)
        except:
            pass
    
    def read_m1_output(self):
        """Read M1 bot output"""
        try:
            for line in iter(self.m1_process.stdout.readline, ''):
                if line:
                    self.m1_queue.put(line)
        except:
            pass
    
    def start_m5(self):
        """Start M5 bot"""
        if self.m5_process is None:
            self.m5_log_widget.delete(1.0, tk.END)
            self.m5_log_widget.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] Starting M5 bot...\n")
            
            python_exe = self.get_python_executable()
            
            self.m5_process = subprocess.Popen(
                [python_exe, 'live_trading_bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            threading.Thread(target=self.read_m5_output, daemon=True).start()
            
            self.m5_widgets['start_btn'].config(state=tk.DISABLED)
            self.m5_widgets['stop_btn'].config(state=tk.NORMAL)
            self.m5_data['status'] = 'Running'
            self.m5_widgets['status_label'].config(text='Running', foreground=self.success_color)
    
    def stop_m5(self):
        """Stop M5 bot"""
        if self.m5_process:
            self.m5_process.terminate()
            self.m5_process = None
            self.m5_log_widget.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] M5 bot stopped\n")
            self.m5_widgets['start_btn'].config(state=tk.NORMAL)
            self.m5_widgets['stop_btn'].config(state=tk.DISABLED)
            self.m5_data['status'] = 'Stopped'
            self.m5_widgets['status_label'].config(text='Stopped', foreground=self.neutral_color)
    
    def start_m1(self):
        """Start M1 bot"""
        if self.m1_process is None:
            self.m1_log_widget.delete(1.0, tk.END)
            self.m1_log_widget.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] Starting M1 bot...\n")
            
            python_exe = self.get_python_executable()
            
            self.m1_process = subprocess.Popen(
                [python_exe, 'live_trading_bot_m1.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            threading.Thread(target=self.read_m1_output, daemon=True).start()
            
            self.m1_widgets['start_btn'].config(state=tk.DISABLED)
            self.m1_widgets['stop_btn'].config(state=tk.NORMAL)
            self.m1_data['status'] = 'Running'
            self.m1_widgets['status_label'].config(text='Running', foreground=self.success_color)
    
    def stop_m1(self):
        """Stop M1 bot"""
        if self.m1_process:
            self.m1_process.terminate()
            self.m1_process = None
            self.m1_log_widget.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] M1 bot stopped\n")
            self.m1_widgets['start_btn'].config(state=tk.NORMAL)
            self.m1_widgets['stop_btn'].config(state=tk.DISABLED)
            self.m1_data['status'] = 'Stopped'
            self.m1_widgets['status_label'].config(text='Stopped', foreground=self.neutral_color)
    
    def on_chart_timeframe_change(self):
        """Handle chart timeframe change"""
        self.chart_timeframe = self.chart_tf_var.get()
        self.update_price_chart()
    
    def update_price_chart(self):
        """Update the price chart with recent candles"""
        if not MATPLOTLIB_AVAILABLE or not self.mt5_connected:
            return
        
        try:
            # Get candles based on selected timeframe
            if self.chart_timeframe == 'M1':
                timeframe = mt5.TIMEFRAME_M1
                num_candles = 100
                tick_interval = 10  # Show timestamp every 10 minutes
            else:  # M5
                timeframe = mt5.TIMEFRAME_M5
                num_candles = 50
                tick_interval = 15  # Show timestamp every 15 minutes
            
            rates = mt5.copy_rates_from_pos(self.mt5_symbol, timeframe, 0, num_candles)
            if rates is None or len(rates) == 0:
                return
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            # Clear the axis
            self.ax.clear()
            
            # Plot candlesticks
            for i in range(len(df)):
                row = df.iloc[i]
                
                # Determine color
                color = '#4ec9b0' if row['close'] >= row['open'] else '#f48771'
                
                # Draw candle body
                body_height = abs(row['close'] - row['open'])
                body_bottom = min(row['open'], row['close'])
                
                rect = Rectangle((i - 0.3, body_bottom), 0.6, body_height, 
                               facecolor=color, edgecolor=color, alpha=0.8)
                self.ax.add_patch(rect)
                
                # Draw wicks
                self.ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=1, alpha=0.6)
            
            # Style
            self.ax.set_xlim(-1, len(df))
            self.ax.set_ylim(df['low'].min() * 0.9999, df['high'].max() * 1.0001)
            self.ax.tick_params(colors='#e0e0e0', labelsize=8)
            self.ax.spines['bottom'].set_color('#3e3e3e')
            self.ax.spines['top'].set_color('#3e3e3e')
            self.ax.spines['left'].set_color('#3e3e3e')
            self.ax.spines['right'].set_color('#3e3e3e')
            self.ax.grid(True, alpha=0.2, color='#3e3e3e')
            
            # Format y-axis to show price
            self.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.2f}'))
            
            # Format x-axis to show timestamps
            tick_positions = []
            tick_labels = []
            for i in range(len(df)):
                time = df.iloc[i]['time']
                minute = time.minute
                # Show labels at specified intervals
                if minute % tick_interval == 0:
                    tick_positions.append(i)
                    tick_labels.append(time.strftime('%H:%M'))
            
            if tick_positions:
                self.ax.set_xticks(tick_positions)
                self.ax.set_xticklabels(tick_labels, rotation=0, ha='center', fontsize=9)
            
            self.ax.tick_params(axis='x', colors='#e0e0e0', labelsize=9)
            
            # Redraw
            self.canvas.draw()
            
        except Exception as e:
            print(f"Error updating chart: {e}")
            
            self.ax.tick_params(axis='x', colors='#e0e0e0', labelsize=9)
            
            # Redraw
            self.canvas.draw()
            
        except Exception as e:
            print(f"Error updating chart: {e}")
    
    def fetch_market_data(self):
        """Fetch market data from MT5"""
        if not self.mt5_connected:
            return
        
        try:
            account = mt5.account_info()
            if account:
                self.market_data['balance'] = account.balance
                self.market_data['equity'] = account.equity
            
            tick = mt5.symbol_info_tick(self.mt5_symbol)
            if tick:
                self.market_data['price'] = tick.bid
            
            # Get M5 data
            rates_m5 = mt5.copy_rates_from_pos(self.mt5_symbol, mt5.TIMEFRAME_M5, 0, 100)
            if rates_m5 is not None and len(rates_m5) > 0:
                df_m5 = pd.DataFrame(rates_m5)
                df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
                
                # Calculate indicators for M5
                df_m5 = self.compute_indicators(df_m5, 9, 21, 14)
                latest_m5 = df_m5.iloc[-1]
                
                self.market_data['atr_m5'] = latest_m5['ATR']
                self.market_data['ema_fast_m5'] = latest_m5['ema_fast']
                self.market_data['ema_slow_m5'] = latest_m5['ema_slow']
                self.market_data['rsi_m5'] = latest_m5['RSI']
                
                if latest_m5['uptrend']:
                    self.market_data['trend_m5'] = 'UP ↑'
                elif latest_m5['downtrend']:
                    self.market_data['trend_m5'] = 'DOWN ↓'
                else:
                    self.market_data['trend_m5'] = 'SIDE →'
            
            # Get M1 data
            rates_m1 = mt5.copy_rates_from_pos(self.mt5_symbol, mt5.TIMEFRAME_M1, 0, 100)
            if rates_m1 is not None and len(rates_m1) > 0:
                df_m1 = pd.DataFrame(rates_m1)
                df_m1['time'] = pd.to_datetime(df_m1['time'], unit='s')
                
                # Calculate indicators for M1
                df_m1 = self.compute_indicators(df_m1, 5, 12, 14)
                latest_m1 = df_m1.iloc[-1]
                
                self.market_data['atr_m1'] = latest_m1['ATR']
                self.market_data['ema_fast_m1'] = latest_m1['ema_fast']
                self.market_data['ema_slow_m1'] = latest_m1['ema_slow']
                self.market_data['rsi_m1'] = latest_m1['RSI']
                
                if latest_m1['uptrend']:
                    self.market_data['trend_m1'] = 'UP ↑'
                elif latest_m1['downtrend']:
                    self.market_data['trend_m1'] = 'DOWN ↓'
                else:
                    self.market_data['trend_m1'] = 'SIDE →'
            
            # Get open positions
            positions = mt5.positions_get(symbol=self.mt5_symbol)
            
            if positions is not None and len(positions) > 0:
                m5_positions = [p for p in positions if p.magic == 234000]
                m1_positions = [p for p in positions if p.magic == 234001]
                
                self.m5_data['positions'] = len(m5_positions)
                self.m1_data['positions'] = len(m1_positions)
                
                # Update position details for M5
                self.m5_data['position_details'] = []
                for pos in m5_positions:
                    # Adjust for MT5 being 1 hour ahead of local time
                    # pos.time is in MT5 timezone, we need to subtract 1 hour from it to match local
                    time_held_minutes = (datetime.now().timestamp() - (pos.time - 3600)) / 60
                    self.m5_data['position_details'].append({
                        'ticket': str(pos.ticket),
                        'type': 'LONG' if pos.type == mt5.ORDER_TYPE_BUY else 'SHORT',
                        'entry': pos.price_open,
                        'current': pos.price_current,
                        'sl': pos.sl,
                        'tp': pos.tp,
                        'profit': pos.profit,
                        'time_held': time_held_minutes
                    })
                
                # Update position details for M1
                self.m1_data['position_details'] = []
                for pos in m1_positions:
                    # Adjust for MT5 being 1 hour ahead of local time
                    # pos.time is in MT5 timezone, we need to subtract 1 hour from it to match local
                    time_held_minutes = (datetime.now().timestamp() - (pos.time - 3600)) / 60
                    self.m1_data['position_details'].append({
                        'ticket': str(pos.ticket),
                        'type': 'LONG' if pos.type == mt5.ORDER_TYPE_BUY else 'SHORT',
                        'entry': pos.price_open,
                        'current': pos.price_current,
                        'sl': pos.sl,
                        'tp': pos.tp,
                        'profit': pos.profit,
                        'time_held': time_held_minutes
                    })
            else:
                self.m5_data['positions'] = 0
                self.m1_data['positions'] = 0
                self.m5_data['position_details'] = []
                self.m1_data['position_details'] = []
                self.m5_data['position_details'] = []
                self.m1_data['position_details'] = []
                
        except Exception as e:
            print(f"Error fetching market data: {e}")
    
    def compute_indicators(self, df, ema_fast_period, ema_slow_period, rsi_period):
        """Compute technical indicators"""
        # EMAs
        df['ema_fast'] = df['close'].ewm(span=ema_fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=ema_slow_period, adjust=False).mean()
        
        # Trend
        df['uptrend'] = df['ema_fast'] > df['ema_slow']
        df['downtrend'] = df['ema_fast'] < df['ema_slow']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['ATR'] = df['tr'].rolling(window=14).mean()
        
        return df
    
    def parse_m5_line(self, line):
        """Parse M5 log line to extract bot status"""
        # Extract signal
        if 'LONG SIGNAL ACTIVE' in line:
            self.m5_data['signal'] = 'LONG'
            self.m5_data['has_signal'] = True
        elif 'SHORT SIGNAL ACTIVE' in line:
            self.m5_data['signal'] = 'SHORT'
            self.m5_data['has_signal'] = True
        elif 'No entry signal' in line:
            self.m5_data['signal'] = 'None'
            self.m5_data['has_signal'] = False
        
        # Extract entry status
        if '[X] Max positions reached' in line:
            self.m5_data['max_positions'] = True
            self.m5_data['ready_for_entry'] = False
        elif '[WAIT] Gap warmup active' in line:
            self.m5_data['gap_warmup'] = True
            self.m5_data['ready_for_entry'] = False
        elif '[WAIT] Cooldown active' in line:
            self.m5_data['cooldown_active'] = True
            self.m5_data['ready_for_entry'] = False
        elif '[OK] Ready for new entry' in line or '[OK] Cooldown skipped' in line:
            self.m5_data['ready_for_entry'] = True
            self.m5_data['gap_warmup'] = False
            self.m5_data['cooldown_active'] = False
            self.m5_data['max_positions'] = False
    
    def parse_m1_line(self, line):
        """Parse M1 log line to extract bot status"""
        # Extract signal
        if 'LONG SIGNAL ACTIVE' in line:
            self.m1_data['signal'] = 'LONG'
            self.m1_data['has_signal'] = True
        elif 'SHORT SIGNAL ACTIVE' in line:
            self.m1_data['signal'] = 'SHORT'
            self.m1_data['has_signal'] = True
        elif 'No entry signal' in line:
            self.m1_data['signal'] = 'None'
            self.m1_data['has_signal'] = False
        
        # Extract entry status
        if '[X] Max positions reached' in line:
            self.m1_data['max_positions'] = True
            self.m1_data['ready_for_entry'] = False
        elif '[WAIT] Gap warmup active' in line:
            self.m1_data['gap_warmup'] = True
            self.m1_data['ready_for_entry'] = False
        elif '[WAIT] Cooldown active' in line:
            self.m1_data['cooldown_active'] = True
            self.m1_data['ready_for_entry'] = False
        elif '[OK] Ready for new entry' in line or '[OK] Cooldown skipped' in line:
            self.m1_data['ready_for_entry'] = True
            self.m1_data['gap_warmup'] = False
            self.m1_data['cooldown_active'] = False
            self.m1_data['max_positions'] = False
    
    def update_bot_display(self, bot_name, data, widgets, atr, ema_fast, ema_slow, rsi, trend):
        """Update display for a specific bot"""
        # Status
        status_color = self.success_color if data['status'] == 'Running' else self.neutral_color
        widgets['status_label'].config(text=data['status'], foreground=status_color)
        
        # Market indicators
        trend_color = self.success_color if 'UP' in trend else self.error_color if 'DOWN' in trend else self.neutral_color
        widgets['trend_label'].config(text=trend, fg=trend_color)
        
        # RSI with color coding
        buy_threshold = 25 if bot_name == "M5" else 35
        sell_threshold = 70 if bot_name == "M5" else 75
        
        if rsi < buy_threshold:
            rsi_color = self.success_color
        elif rsi > sell_threshold:
            rsi_color = self.error_color
        else:
            rsi_color = self.accent_color
        
        widgets['rsi_label'].config(text=f"{rsi:.1f}", fg=rsi_color)
        widgets['atr_label'].config(text=f"${atr:.2f}")
        widgets['ema_fast_label'].config(text=f"${ema_fast:.2f}")
        widgets['ema_slow_label'].config(text=f"${ema_slow:.2f}")
        
        # Entry conditions
        price = self.market_data['price']
        
        # Get thresholds
        if bot_name == "M5":
            rsi_buy = 25
            rsi_sell = 75
        else:
            rsi_buy = 35
            rsi_sell = 65
        
        conditions = []
        
        # 1. RSI condition for LONG
        if rsi < rsi_buy:
            conditions.append(f"✅ RSI: {rsi:.1f} < {rsi_buy} (Buy zone)")
        else:
            conditions.append(f"❌ RSI: {rsi:.1f} >= {rsi_buy} (Not oversold)")
        
        # 2. Trend condition
        if 'UP' in trend:
            conditions.append(f"✅ Trend: Uptrend (EMA {ema_fast:.2f} > {ema_slow:.2f})")
        elif 'DOWN' in trend:
            conditions.append(f"⚠ Trend: Downtrend (EMA {ema_fast:.2f} < {ema_slow:.2f})")
        else:
            conditions.append(f"⚠ Trend: Sideways")
        
        # 3. Position availability
        if data['positions'] < 2:
            conditions.append(f"✅ Positions: {data['positions']}/2 available")
        else:
            conditions.append(f"❌ Positions: {data['positions']}/2 (Max reached)")
        
        # 4. Bot readiness
        if data['gap_warmup']:
            conditions.append(f"❌ Status: Gap warmup active")
        elif data['cooldown_active']:
            conditions.append(f"❌ Status: Cooldown after loss")
        else:
            conditions.append(f"✅ Status: Ready to trade")
        
        # 5. Overall signal
        if data['has_signal']:
            signal_type = data['signal']
            conditions.append(f"🔔 Signal: {signal_type} active")
        else:
            conditions.append(f"⚪ Signal: None")
        
        # Update labels
        for i, condition in enumerate(conditions):
            if i < len(widgets['entry_labels']):
                widgets['entry_labels'][i].config(text=condition)
        
        # Positions - update position count in frame title
        widgets['positions_frame'].config(text=f"Positions ({data['positions']}/2)")
        
        self.update_position_cards(widgets['position_cards'], data['position_details'], price, rsi, bot_name)
    
    def update_position_cards(self, cards, positions, current_price, rsi, bot_name):
        """Update 2 static position cards with exit signals"""
        # Get exit thresholds
        if bot_name == "M5":
            rsi_exit_long = 75
            rsi_exit_short = 25
        else:
            rsi_exit_long = 75
            rsi_exit_short = 25
        
        # Update each card slot
        for i in range(2):
            card = cards[i]
            
            if i < len(positions):
                # Position exists
                pos = positions[i]
                
                # Update header
                type_color = self.success_color if pos['type'] == 'LONG' else self.error_color
                card['ticket_label'].config(
                    text=f"#{pos['ticket']} {pos['type']}", 
                    fg=type_color
                )
                
                # Update profit
                profit_color = self.success_color if pos['profit'] > 0 else self.error_color if pos['profit'] < 0 else self.fg_color
                card['profit_label'].config(
                    text=f"${pos['profit']:.2f}", 
                    fg=profit_color
                )
                
                # Update entry info
                card['entry_info'].config(
                    text=f"Entry: ${pos['entry']:.2f} | Held: {pos['time_held']:.0f} min"
                )
                
                # Calculate exit signals
                exit_conditions = []
                
                # 0. Price info (Current, SL, TP)
                price_info = f"Current: ${pos.get('current', current_price):.2f}"
                if pos.get('sl', 0) > 0:
                    price_info += f" | SL: ${pos['sl']:.2f}"
                if pos.get('tp', 0) > 0:
                    price_info += f" | TP: ${pos['tp']:.2f}"
                exit_conditions.append(price_info)
                
                if pos['type'] == 'LONG':
                    # LONG exit conditions
                    # 1. RSI exit
                    if rsi >= rsi_exit_long:
                        exit_conditions.append(f"✅ RSI Exit: {rsi:.1f} >= {rsi_exit_long}")
                    else:
                        exit_conditions.append(f"❌ RSI Exit: {rsi:.1f} < {rsi_exit_long}")
                    
                    # 2. Profit target
                    target_pct = 0.008 if bot_name == "M1" else 0.015
                    target_price = pos['entry'] * (1 + target_pct)
                    if current_price >= target_price:
                        exit_conditions.append(f"✅ TP Hit: ${current_price:.2f} >= ${target_price:.2f}")
                    else:
                        exit_conditions.append(f"❌ TP: ${current_price:.2f} < ${target_price:.2f}")
                    
                    # 3. Time-based exit (M1 only)
                    if bot_name == "M1":
                        if pos['time_held'] >= 10 and current_price < pos['entry']:
                            exit_conditions.append(f"⚠ Time: Will exit if still losing at 10 min")
                        elif pos['time_held'] >= 10:
                            exit_conditions.append(f"✅ Time: Holding winner past 10 min")
                        else:
                            time_remaining = 10 - pos['time_held']
                            exit_conditions.append(f"⏱ Time: {time_remaining:.0f} min until auto-exit check")
                    
                    # 4. Current P/L
                    pnl_pct = ((current_price - pos['entry']) / pos['entry']) * 100
                    exit_conditions.append(f"P/L: {pnl_pct:+.2f}%")
                
                else:  # SHORT
                    # SHORT exit conditions
                    # 1. RSI exit
                    if rsi <= rsi_exit_short:
                        exit_conditions.append(f"✅ RSI Exit: {rsi:.1f} <= {rsi_exit_short}")
                    else:
                        exit_conditions.append(f"❌ RSI Exit: {rsi:.1f} > {rsi_exit_short}")
                    
                    # 2. Profit target
                    target_pct = 0.008 if bot_name == "M1" else 0.015
                    target_price = pos['entry'] * (1 - target_pct)
                    if current_price <= target_price:
                        exit_conditions.append(f"✅ TP Hit: ${current_price:.2f} <= ${target_price:.2f}")
                    else:
                        exit_conditions.append(f"❌ TP: ${current_price:.2f} > ${target_price:.2f}")
                    
                    # 3. Time-based exit (M1 only)
                    if bot_name == "M1":
                        if pos['time_held'] >= 10 and current_price > pos['entry']:
                            exit_conditions.append(f"⚠ Time: Will exit if still losing at 10 min")
                        elif pos['time_held'] >= 10:
                            exit_conditions.append(f"✅ Time: Holding winner past 10 min")
                        else:
                            time_remaining = 10 - pos['time_held']
                            exit_conditions.append(f"⏱ Time: {time_remaining:.0f} min until auto-exit check")
                    
                    # 4. Current P/L
                    pnl_pct = ((pos['entry'] - current_price) / pos['entry']) * 100
                    exit_conditions.append(f"P/L: {pnl_pct:+.2f}%")
                
                # Update exit labels
                for j, condition in enumerate(exit_conditions):
                    if j < len(card['exit_labels']):
                        card['exit_labels'][j].config(text=condition)
                
                # Clear any unused exit labels
                for j in range(len(exit_conditions), len(card['exit_labels'])):
                    card['exit_labels'][j].config(text="")
                
            else:
                # No position - show empty
                card['ticket_label'].config(
                    text=f"Pos {i+1}: Empty", 
                    fg=self.neutral_color
                )
                card['profit_label'].config(text="")
                card['entry_info'].config(text="")
                
                # Clear all exit labels
                for label in card['exit_labels']:
                    label.config(text="")
    
    def on_closing(self):
        """Handle window closing"""
        if self.m5_process:
            self.m5_process.terminate()
        if self.m1_process:
            self.m1_process.terminate()
        self.disconnect_mt5()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = BotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
