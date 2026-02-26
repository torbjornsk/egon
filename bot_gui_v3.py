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
        
        # Bot states
        self.m5_data = {
            'status': 'Stopped',
            'positions': 0,
            'position_details': [],
        }
        
        self.m1_data = {
            'status': 'Stopped',
            'positions': 0,
            'position_details': [],
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
        """Fetch last 100 trades from MT5"""
        if not self.mt5_connected:
            return
        
        try:
            # Get deals from last 30 days
            from_date = datetime.now() - pd.Timedelta(days=30)
            deals = mt5.history_deals_get(from_date, datetime.now())
            
            if deals is None or len(deals) == 0:
                return
            
            # Filter for XAUUSD and our magic numbers
            filtered_deals = []
            for deal in deals:
                if deal.symbol == 'XAUUSD' and deal.magic in [234000, 234001]:
                    filtered_deals.append({
                        'time': datetime.fromtimestamp(deal.time),
                        'ticket': deal.ticket,
                        'type': 'BUY' if deal.type == mt5.ORDER_TYPE_BUY else 'SELL',
                        'volume': deal.volume,
                        'price': deal.price,
                        'profit': deal.profit,
                        'bot': 'M5' if deal.magic == 234000 else 'M1'
                    })
            
            # Sort by time descending and take last 100
            filtered_deals.sort(key=lambda x: x['time'], reverse=True)
            self.trade_history = filtered_deals[:100]
            
        except Exception as e:
            print(f"Error fetching trade history: {e}")
    
    def setup_ui(self):
        """Setup the new UI layout"""
        # Main container with 3 columns
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.bg_dark,
                                    sashwidth=5, sashrelief=tk.RAISED, bd=0)
        main_paned.pack(fill=tk.BOTH, expand=True)
        
        # === LEFT: M5 BOT ===
        self.setup_bot_side(main_paned, "M5", self.m5_data, self.m5_queue)
        
        # === CENTER: ACCOUNT + CHART + TRADE HISTORY ===
        self.setup_center_panel(main_paned)
        
        # === RIGHT: M1 BOT ===
        self.setup_bot_side(main_paned, "M1", self.m1_data, self.m1_queue)
    
    def setup_bot_side(self, parent, bot_name, bot_data, log_queue):
        """Setup a bot panel on the side"""
        bot_frame = tk.Frame(parent, bg=self.bg_dark)
        parent.add(bot_frame, width=500, minsize=400)
        
        # Title
        tk.Label(bot_frame, text=f"{bot_name} Bot", bg=self.bg_dark, fg=self.accent_color,
                font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Bot controls and info (horizontal layout)
        info_frame = ttk.LabelFrame(bot_frame, text="Controls & Status", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Controls
        controls = tk.Frame(info_frame, bg=self.bg_dark)
        controls.pack(fill=tk.X, pady=5)
        
        start_btn = ttk.Button(controls, text="Start",
                              command=lambda: self.start_m5() if bot_name == "M5" else self.start_m1(),
                              width=10)
        start_btn.pack(side=tk.LEFT, padx=5)
        
        stop_btn = ttk.Button(controls, text="Stop",
                             command=lambda: self.stop_m5() if bot_name == "M5" else self.stop_m1(),
                             state=tk.DISABLED, width=10)
        stop_btn.pack(side=tk.LEFT, padx=5)
        
        status_label = ttk.Label(controls, text="Stopped", foreground=self.neutral_color)
        status_label.pack(side=tk.LEFT, padx=10)
        
        # Store widgets
        if bot_name == "M5":
            self.m5_widgets = {'start_btn': start_btn, 'stop_btn': stop_btn, 'status_label': status_label}
            self.m5_log_widget = None
        else:
            self.m1_widgets = {'start_btn': start_btn, 'stop_btn': stop_btn, 'status_label': status_label}
            self.m1_log_widget = None
        
        # Log
        log_frame = ttk.LabelFrame(bot_frame, text="Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
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
    
    def setup_center_panel(self, parent):
        """Setup center panel with account info, chart, and trade history"""
        center_frame = tk.Frame(parent, bg=self.bg_dark)
        parent.add(center_frame, width=800, minsize=600)
        
        # Account info
        account_frame = ttk.LabelFrame(center_frame, text="Account", padding="10")
        account_frame.pack(fill=tk.X, padx=10, pady=5)
        
        acc_grid = tk.Frame(account_frame, bg=self.bg_dark)
        acc_grid.pack()
        
        tk.Label(acc_grid, text="Balance:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=(0,5))
        self.account_balance_label = tk.Label(acc_grid, text="$0.00", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 11, 'bold'))
        self.account_balance_label.grid(row=0, column=1, sticky=tk.W, padx=(0,20))
        
        tk.Label(acc_grid, text="Equity:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 9, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(0,5))
        self.account_equity_label = tk.Label(acc_grid, text="$0.00", bg=self.bg_dark, fg=self.fg_color, font=('Arial', 11, 'bold'))
        self.account_equity_label.grid(row=0, column=3, sticky=tk.W, padx=(0,20))
        
        tk.Label(acc_grid, text="Price:", bg=self.bg_dark, fg=self.neutral_color, font=('Arial', 9, 'bold')).grid(row=0, column=4, sticky=tk.W, padx=(0,5))
        self.shared_price_label = tk.Label(acc_grid, text="$0.00", bg=self.bg_dark, fg=self.warning_color, font=('Arial', 11, 'bold'))
        self.shared_price_label.grid(row=0, column=5, sticky=tk.W)
        
        # Price chart
        if MATPLOTLIB_AVAILABLE:
            chart_frame = ttk.LabelFrame(center_frame, text="Price Chart (Last 50 M5 candles)", padding="5")
            chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
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
        history_frame = ttk.LabelFrame(center_frame, text="Trade History (Last 100 trades)", padding="5")
        history_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create treeview for trade history
        columns = ('Time', 'Bot', 'Type', 'Volume', 'Price', 'Profit')
        self.trade_tree = ttk.Treeview(history_frame, columns=columns, show='headings', height=10)
        
        # Define headings
        self.trade_tree.heading('Time', text='Time')
        self.trade_tree.heading('Bot', text='Bot')
        self.trade_tree.heading('Type', text='Type')
        self.trade_tree.heading('Volume', text='Volume')
        self.trade_tree.heading('Price', text='Price')
        self.trade_tree.heading('Profit', text='Profit')
        
        # Define column widths
        self.trade_tree.column('Time', width=150)
        self.trade_tree.column('Bot', width=50)
        self.trade_tree.column('Type', width=60)
        self.trade_tree.column('Volume', width=80)
        self.trade_tree.column('Price', width=100)
        self.trade_tree.column('Profit', width=100)
        
        # Scrollbar
        tree_scroll = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.trade_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
    def update_trade_history_display(self):
        """Update the trade history treeview"""
        # Clear existing items
        for item in self.trade_tree.get_children():
            self.trade_tree.delete(item)
        
        # Add trades
        for trade in self.trade_history:
            profit_str = f"${trade['profit']:.2f}"
            values = (
                trade['time'].strftime('%Y-%m-%d %H:%M:%S'),
                trade['bot'],
                trade['type'],
                f"{trade['volume']:.2f}",
                f"${trade['price']:.2f}",
                profit_str
            )
            
            # Color code by profit
            tag = 'profit' if trade['profit'] > 0 else 'loss' if trade['profit'] < 0 else 'neutral'
            self.trade_tree.insert('', tk.END, values=values, tags=(tag,))
        
        # Configure tags
        self.trade_tree.tag_configure('profit', foreground=self.success_color)
        self.trade_tree.tag_configure('loss', foreground=self.error_color)
        self.trade_tree.tag_configure('neutral', foreground=self.fg_color)
    
    def update_displays(self):
        """Update all displays"""
        # Update M5 log
        if self.m5_log_widget:
            try:
                while True:
                    line = self.m5_queue.get_nowait()
                    self.m5_log_widget.insert(tk.END, line)
                    self.m5_log_widget.see(tk.END)
            except queue.Empty:
                pass
        
        # Update M1 log
        if self.m1_log_widget:
            try:
                while True:
                    line = self.m1_queue.get_nowait()
                    self.m1_log_widget.insert(tk.END, line)
                    self.m1_log_widget.see(tk.END)
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
    
    def update_price_chart(self):
        """Update the price chart with recent candles"""
        if not MATPLOTLIB_AVAILABLE or not self.mt5_connected:
            return
        
        try:
            # Get last 50 M5 candles
            rates = mt5.copy_rates_from_pos(self.mt5_symbol, mt5.TIMEFRAME_M5, 0, 50)
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
            
            # Format x-axis to show timestamps every 15 minutes
            tick_positions = []
            tick_labels = []
            for i in range(len(df)):
                time = df.iloc[i]['time']
                minute = time.minute
                if minute % 15 == 0:
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
        except Exception as e:
            print(f"Error fetching market data: {e}")
    
    def start_m5(self):
        """Start M5 bot"""
        pass  # Implement bot starting logic
    
    def stop_m5(self):
        """Stop M5 bot"""
        pass
    
    def start_m1(self):
        """Start M1 bot"""
        pass
    
    def stop_m1(self):
        """Stop M1 bot"""
        pass
    
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
