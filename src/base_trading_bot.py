"""
Base Trading Bot - Unified infrastructure for all scalping bots
Handles MT5 connection, logging, safety checks, position management
Strategy-specific logic is delegated to strategy classes
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

class BaseTradingBot:
    """Base class for all trading bots with shared infrastructure"""
    
    def __init__(self, config_path, magic_number, strategy_name):
        """Initialize base bot
        
        Args:
            config_path: Path to config JSON file
            magic_number: Unique magic number for this bot
            strategy_name: Name of the strategy (for logging)
        """
        self.config_path = config_path
        self.magic_number = magic_number
        self.strategy_name = strategy_name
        self.symbol = 'XAUUSD.p'
        
        # Load configuration
        self.load_config(config_path)
        
        # Safety tracking
        self.starting_balance = None
        self.peak_balance = None
        self.daily_start_balance = None
        self.daily_start_date = None
        self.trades_today = 0
        self.consecutive_losses = 0
        self.last_trade_time = None
        self.trading_paused = False
        self.pause_reason = None
        self.last_candle_time = None
        
        # Setup logging
        log_file = f'trading_bot_{strategy_name.lower()}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        logging.info(f"="*80)
        logging.info(f"{strategy_name} Bot Initialized")
        logging.info(f"="*80)
        logging.info(f"Configuration loaded: {self.config['strategy']}")
        logging.info(f"Position Size: {self.config['position_size_pct']*100}%")
        logging.info(f"Leverage: {self.config['leverage']}x")
        logging.info(f"="*80)
    
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
    
    def connect_mt5(self):
        """Connect to MT5"""
        if not mt5.initialize():
            error = mt5.last_error()
            logging.error(f"MT5 initialization failed: {error}")
            return False
        
        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            logging.error("Failed to get account info")
            return False
        
        logging.info(f"Connected to MT5")
        logging.info(f"Account: {account_info.login}")
        logging.info(f"Server: {account_info.server}")
        logging.info(f"Balance: ${account_info.balance:,.2f}")
        logging.info(f"Leverage: 1:{account_info.leverage}")
        
        # Initialize balance tracking
        self.starting_balance = account_info.balance
        self.peak_balance = account_info.balance
        self.daily_start_balance = account_info.balance
        self.daily_start_date = datetime.now().date()
        
        return True
    
    def disconnect_mt5(self):
        """Disconnect from MT5"""
        mt5.shutdown()
        logging.info("Disconnected from MT5")
    
    def get_account_info(self):
        """Get current account information"""
        account_info = mt5.account_info()
        if account_info is None:
            return None
        
        return {
            'balance': account_info.balance,
            'equity': account_info.equity,
            'margin': account_info.margin,
            'free_margin': account_info.margin_free,
            'profit': account_info.profit,
            'leverage': account_info.leverage
        }
    
    def get_historical_data(self, symbol=None, timeframe=None, bars=500):
        """Get historical price data
        
        Args:
            symbol: Trading symbol (default: self.symbol)
            timeframe: MT5 timeframe constant (default: from config)
            bars: Number of bars to fetch
        
        Returns:
            DataFrame with OHLCV data and time column
        """
        if symbol is None:
            symbol = self.symbol
        if timeframe is None:
            timeframe = self.get_timeframe()
        
        # Ensure symbol is visible
        if not mt5.symbol_select(symbol, True):
            logging.error(f"Failed to select symbol {symbol}")
            return None
        
        # Fetch data
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        
        if rates is None or len(rates) == 0:
            logging.error(f"Failed to get historical data: {mt5.last_error()}")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        return df
    
    def get_timeframe(self):
        """Get MT5 timeframe constant - override in subclass"""
        raise NotImplementedError("Subclass must implement get_timeframe()")
    
    def compute_indicators(self, df):
        """Compute technical indicators - override in subclass"""
        raise NotImplementedError("Subclass must implement compute_indicators()")
    
    def get_open_positions(self, symbol=None):
        """Get all open positions for this bot"""
        if symbol is None:
            symbol = self.symbol
        
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        
        # Filter by magic number
        return [pos for pos in positions if pos.magic == self.magic_number]
    
    def check_drawdown(self, current_balance):
        """Check if drawdown limit exceeded"""
        if self.peak_balance is None:
            self.peak_balance = current_balance
        
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        drawdown = (self.peak_balance - current_balance) / self.peak_balance
        max_drawdown = self.config.get('max_drawdown_limit', 0.35)
        
        if drawdown >= max_drawdown:
            logging.critical(f"DRAWDOWN LIMIT EXCEEDED: {drawdown*100:.2f}% >= {max_drawdown*100:.2f}%")
            self.trading_paused = True
            self.pause_reason = f"Drawdown limit ({drawdown*100:.1f}%)"
            return True
        
        return False
    
    def check_daily_loss_limit(self, current_balance):
        """Check if daily loss limit exceeded"""
        # Reset daily tracking if new day
        today = datetime.now().date()
        if today != self.daily_start_date:
            self.daily_start_balance = current_balance
            self.daily_start_date = today
            self.trades_today = 0
            logging.info(f"New trading day - Daily balance reset to ${current_balance:,.2f}")
        
        # Check daily loss
        daily_loss = (self.daily_start_balance - current_balance) / self.daily_start_balance
        max_daily_loss = self.config.get('max_daily_loss', 0.10)
        
        if daily_loss >= max_daily_loss:
            logging.critical(f"DAILY LOSS LIMIT EXCEEDED: {daily_loss*100:.2f}% >= {max_daily_loss*100:.2f}%")
            self.trading_paused = True
            self.pause_reason = f"Daily loss limit ({daily_loss*100:.1f}%)"
            return True
        
        return False
    
    def check_consecutive_losses(self):
        """Check if too many consecutive losses"""
        max_consecutive = self.config.get('max_consecutive_losses', 5)
        
        if self.consecutive_losses >= max_consecutive:
            logging.critical(f"TOO MANY CONSECUTIVE LOSSES: {self.consecutive_losses}")
            self.trading_paused = True
            self.pause_reason = f"Consecutive losses ({self.consecutive_losses})"
            return True
        
        return False
    
    def run_safety_checks(self):
        """Run all safety checks"""
        account_info = self.get_account_info()
        if not account_info:
            return
        
        # Check drawdown
        if self.check_drawdown(account_info['balance']):
            self.emergency_close_all()
            return
        
        # Check daily loss
        if self.check_daily_loss_limit(account_info['balance']):
            self.emergency_close_all()
            return
        
        # Check consecutive losses
        if self.check_consecutive_losses():
            return
    
    def emergency_close_all(self, symbol=None):
        """Emergency: Close all positions immediately"""
        if symbol is None:
            symbol = self.symbol
        
        logging.critical("EMERGENCY: Closing all positions!")
        
        positions = self.get_open_positions(symbol)
        for pos in positions:
            self.close_position(pos, emergency=True)
    
    def close_position(self, position, emergency=False):
        """Close a position"""
        symbol = position.symbol
        ticket = position.ticket
        volume = position.volume
        position_type = position.type
        
        # Determine close type
        if position_type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
        
        # Create close request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "emergency_close" if emergency else "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result is None:
            logging.error(f"Close failed: {mt5.last_error()}")
            return False
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Close failed: {result.comment}")
            return False
        
        # Update consecutive loss tracking
        if position.profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        self.trades_today += 1
        
        logging.info(f"Position closed: Ticket={ticket}, Profit=${position.profit:.2f}")
        return True
    
    def is_near_weekend_close(self, minutes_before=30):
        """Check if we're approaching weekend close"""
        now = datetime.now()
        
        # Friday after 4:30 PM EST (market closes at 5 PM)
        if now.weekday() == 4:  # Friday
            close_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
            time_until_close = (close_time - now).total_seconds() / 60
            
            if 0 < time_until_close <= minutes_before:
                return True, f"Market closes in {time_until_close:.0f} minutes"
        
        return False, None
    
    def has_new_candle(self, symbol=None, timeframe=None):
        """Check if a new candle has formed"""
        if symbol is None:
            symbol = self.symbol
        if timeframe is None:
            timeframe = self.get_timeframe()
        
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 1)
        
        if rates is None or len(rates) == 0:
            return False, None
        
        candle_time = pd.to_datetime(rates[0]['time'], unit='s')
        
        if self.last_candle_time is None:
            self.last_candle_time = candle_time
            return True, candle_time
        
        if candle_time > self.last_candle_time:
            self.last_candle_time = candle_time
            return True, candle_time
        
        return False, candle_time
    
    def print_startup_state(self):
        """Print initial market state on startup"""
        logging.info("\nFetching initial data...")
        try:
            df = self.get_historical_data(bars=200)
            if df is not None and len(df) > 0:
                df = self.compute_indicators(df)
                if len(df) > 0:
                    latest = df.iloc[-1]
                    
                    logging.info(f"\nCurrent Market State:")
                    logging.info(f"  Time: {latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.info(f"  Close: {latest['close']:.2f}")
                    
                    # Print strategy-specific indicators
                    self.print_indicators(latest, df)
                    
                    # Check if data is fresh
                    now = pd.Timestamp.now()
                    age_minutes = (now - latest['time']).total_seconds() / 60
                    
                    if age_minutes > 10:
                        logging.info(f"\n  Market Status: CLOSED (last data {age_minutes:.0f} minutes ago)")
                        logging.info(f"  Waiting for market to open...")
                    else:
                        logging.info(f"\n  Market Status: OPEN")
                        logging.info(f"  Monitoring for signals...")
        except Exception as e:
            logging.warning(f"Could not fetch initial data: {e}")
        
        logging.info("\n" + "="*80)
    
    def print_indicators(self, latest, df):
        """Print strategy-specific indicators - override in subclass"""
        pass
    
    def trading_logic(self):
        """Main trading logic - override in subclass"""
        raise NotImplementedError("Subclass must implement trading_logic()")
    
    def run(self, check_interval=1):
        """Main bot loop"""
        logging.info("="*80)
        logging.info(f"{self.strategy_name} BOT STARTED")
        logging.info("="*80)
        logging.info(f"Strategy: {self.config['strategy']}")
        logging.info(f"Checking every {check_interval} second(s) for new candles")
        logging.info("="*80)
        
        if not self.connect_mt5():
            logging.error("Failed to connect to MT5")
            return
        
        # Print initial state
        self.print_startup_state()
        
        # Track last status message time
        last_status_time = time.time()
        status_interval = 60  # Print status every 60 seconds when waiting
        
        try:
            while True:
                try:
                    # Check for new candle
                    has_new, candle_time = self.has_new_candle()
                    
                    if has_new:
                        logging.info(f"\n{'='*60}")
                        logging.info(f"NEW CANDLE: {candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        logging.info(f"{'='*60}")
                        
                        # Run trading logic
                        self.trading_logic()
                        
                        # Reset status timer
                        last_status_time = time.time()
                    else:
                        # No new candle - print periodic status
                        current_time = time.time()
                        if current_time - last_status_time >= status_interval:
                            df = self.get_historical_data(bars=10)
                            if df is not None and len(df) > 0:
                                latest = df.iloc[-1]
                                latest_time = latest['time']
                                latest_close = latest['close']
                                
                                now = pd.Timestamp.now()
                                age_minutes = (now - latest_time).total_seconds() / 60
                                
                                if age_minutes > 10:
                                    logging.info(f"[WAITING] Market closed - last data: {latest_time.strftime('%Y-%m-%d %H:%M')}, {age_minutes:.0f}min ago")
                                else:
                                    logging.info(f"[MONITORING] Waiting for new candle - current: {latest_time.strftime('%H:%M')}, price: {latest_close:.2f}")
                            
                            last_status_time = current_time
                    
                    # Sleep
                    time.sleep(check_interval)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logging.error(f"Error in trading loop: {e}", exc_info=True)
                    time.sleep(check_interval)
        
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
        finally:
            self.disconnect_mt5()
            logging.info("Bot shutdown complete")
