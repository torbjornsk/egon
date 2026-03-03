"""
Live Trading Bot for Gold (XAUUSD) - M1 Scalping Version
Strategy: Aggressive M1 Scalping with 15% @ 25x leverage
Author: AI Assistant
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import time
import os
from datetime import datetime, timedelta
import logging
from pathlib import Path
import pytz
from src.timezone_utils import mt5_to_local, get_local_now

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)

class LiveTradingBot:
    def __init__(self, config_path='config/m1_params.json'):
        """Initialize the trading bot"""
        self.magic_number = 234001  # Unique magic number for M1 bot
        self.positions = []  # Track multiple positions
        self.max_positions = 2  # Allow 2 simultaneous positions
        self.load_config(config_path)
        self.starting_balance = None
        self.peak_balance = None
        self.trading_paused = False
        self.pause_reason = None  # Track why trading was paused
        self.trades_today = 0
        self.last_trade_time = None
        self.last_close_time = None  # Track when we last closed a position
        self.last_close_position_type = None  # Track type of last closed position (for smart cooldown)
        self.last_trade_profitable = False  # Track if last trade was a winner
        self.cooldown_candles = 2  # Wait 2 candles after closing before reopening
        self.last_candle_time = None  # Track last candle to detect gaps
        self.warmup_candles = 2  # Wait 2 candles after market open/gap before trading
        self.last_processed_candle = None  # Track last processed candle to avoid duplicates
        self.trade_log = []  # Track all trades for reporting
        self.session_start = get_local_now()  # Track when bot started
        self.position_open_times = {}  # Track when each position was opened (by ticket)
        self.peak_position_profits = {}  # Track peak profit for each position (for profit protection)
        self.rsi_confirmation_tracker = {}  # Track RSI confirmation for exits (prevent false spikes)
        self.entry_signal_count = {'LONG': 0, 'SHORT': 0}  # Track consecutive entry signals
        
        # Timezone handling: MT5 uses EET (Eastern European Time)
        # This automatically handles daylight savings (EET/EEST)
        self.mt5_timezone = pytz.timezone('Europe/Athens')  # EET/EEST (GMT+2/GMT+3)
        self.local_timezone = pytz.timezone('Europe/Berlin')  # CET/CEST (GMT+1/GMT+2)
        
        # Smart cooldown tracking
        self.recent_rsi_values = []  # Track recent RSI for momentum calculation
        self.recent_prices = []  # Track recent prices for momentum calculation
        
        # DEAD MAN'S SWITCH - Safety mechanisms
        self.consecutive_losses = 0
        self.max_consecutive_losses = 12  # Increased for 2 positions: 6 rounds of 2 losses each (was 7 for single position)
        self.daily_start_balance = None
        self.daily_loss_limit_pct = 0.15  # Pause if lose 15% in 24 hours
        self.rapid_loss_threshold_pct = 0.10  # Pause if lose 10% in 1 hour
        self.rapid_loss_window_minutes = 60
        self.balance_history = []  # Track balance over time for rapid loss detection
        self.emergency_equity_threshold_pct = 0.50  # Emergency close all if equity < 50% of starting
        
    def load_config(self, config_path):
        """Load trading configuration"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Adjust position size for multiple positions
        base_position_size = self.config['position_size_pct']
        self.config['position_size_pct'] = base_position_size / self.max_positions
        
        logging.info(f"Configuration loaded: {self.config['strategy']}")
        logging.info(f"Position Size: {base_position_size*100}% (split into {self.max_positions} positions of {self.config['position_size_pct']*100}% each)")
        logging.info(f"Leverage: {self.config['leverage']}x")
        logging.info(f"Effective Position: {self.config['position_size_pct']*self.config['leverage']*100}% per position, {base_position_size*self.config['leverage']*100}% total")
        
        # Log smart cooldown status
        if self.config.get('use_smart_cooldown', False):
            threshold = self.config.get('smart_cooldown_threshold', 3)
            logging.info(f"Smart Cooldown: ENABLED (threshold: {threshold}/4 conditions)")
        else:
            logging.info(f"Smart Cooldown: DISABLED (standard {self.cooldown_candles}-candle cooldown)")
    
    def should_skip_cooldown(self, df, position_type):
        """
        Determine if cooldown should be skipped based on smart rules (moderate aggressiveness)
        
        Skip cooldown when 3 out of 4 conditions met:
        1. RSI is extreme (< 43.4 for LONG, > 56.6 for SHORT)
        2. RSI momentum negative (RSI declining into exit)
        3. High volatility (big moves, not choppy)
        4. Strong price momentum (sharp move before reversal)
        
        Returns: (should_skip, reason)
        """
        if not self.config.get('use_smart_cooldown', False):
            return False, None
        
        if df is None or len(df) < 10:
            return False, None
        
        latest = df.iloc[-1]
        conditions_met = 0
        conditions_details = []
        threshold = self.config.get('smart_cooldown_threshold', 3)
        
        # 1. RSI is extreme
        if position_type == 'LONG':
            if latest['RSI'] < 43.4:
                conditions_met += 1
                conditions_details.append(f"RSI extreme ({latest['RSI']:.1f} < 43.4)")
        else:  # SHORT
            if latest['RSI'] > 56.6:
                conditions_met += 1
                conditions_details.append(f"RSI extreme ({latest['RSI']:.1f} > 56.6)")
        
        # 2. RSI momentum negative (declining into exit)
        if len(df) >= 4:
            rsi_3_candles_ago = df.iloc[-4]['RSI']
            rsi_momentum = latest['RSI'] - rsi_3_candles_ago
            if rsi_momentum < -4.7:
                conditions_met += 1
                conditions_details.append(f"RSI declining ({rsi_momentum:.1f})")
        
        # 3. High volatility (use ATR as proxy)
        # Volatility > 7.72 translates to roughly ATR > 0.15% of price
        atr_threshold = latest['close'] * 0.0015
        if latest['ATR'] > atr_threshold:
            conditions_met += 1
            conditions_details.append(f"High volatility (ATR {latest['ATR']:.2f})")
        
        # 4. Strong price momentum
        if len(df) >= 6:
            price_5_candles_ago = df.iloc[-6]['close']
            momentum = latest['close'] - price_5_candles_ago
            if abs(momentum) > 7.65:
                conditions_met += 1
                conditions_details.append(f"Strong momentum ({momentum:+.2f})")
        
        # Skip cooldown if threshold met
        if conditions_met >= threshold:
            reason = f"Smart cooldown: {conditions_met}/{threshold} conditions met - " + ", ".join(conditions_details)
            return True, reason
        
        return False, None
        
    def connect_mt5(self):
        """Connect to MetaTrader5"""
        if not mt5.initialize():
            logging.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        
        account_info = mt5.account_info()
        if account_info:
            logging.info(f"Connected to MT5")
            logging.info(f"Account: {account_info.login}")
            logging.info(f"Server: {account_info.server}")
            logging.info(f"Balance: ${account_info.balance:.2f}")
            logging.info(f"Leverage: 1:{account_info.leverage}")
            
            self.starting_balance = account_info.balance
            self.peak_balance = account_info.balance
            return True
        else:
            logging.error("Not logged in to MT5")
            return False
    
    def disconnect_mt5(self):
        """Disconnect from MetaTrader5"""
        mt5.shutdown()
        logging.info("Disconnected from MT5")
    
    def get_account_info(self):
        """Get current account information"""
        account_info = mt5.account_info()
        if account_info:
            return {
                'balance': account_info.balance,
                'equity': account_info.equity,
                'margin': account_info.margin,
                'free_margin': account_info.margin_free,
                'profit': account_info.profit
            }
        return None
    
    def get_historical_data(self, symbol='XAUUSD.p', timeframe=mt5.TIMEFRAME_M1, bars=500):
        """Get historical price data"""
        # Ensure symbol is visible
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Symbol {symbol} not found")
            return None
        
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logging.error(f"Failed to select {symbol}")
                return None
        
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None or len(rates) == 0:
            logging.error(f"Failed to get data: {mt5.last_error()}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    def compute_indicators(self, df):
        """Calculate technical indicators"""
        df = df.copy()
        
        # EMAs
        df['ema_fast'] = df['close'].ewm(span=self.config['fast_ema']).mean()
        df['ema_slow'] = df['close'].ewm(span=self.config['slow_ema']).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(self.config['rsi_period']).mean()
        loss = -delta.clip(upper=0).rolling(self.config['rsi_period']).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        
        # Trend
        df['ema_200'] = df['close'].ewm(span=200).mean()
        df['uptrend'] = (df['ema_fast'] > df['ema_slow'])
        df['downtrend'] = (df['ema_fast'] < df['ema_slow'])
        
        return df
    
    def check_drawdown(self, current_balance):
        """Check if drawdown limit exceeded"""
        if self.peak_balance is None:
            self.peak_balance = current_balance
        
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        drawdown = (self.peak_balance - current_balance) / self.peak_balance
        
        if drawdown >= self.config['max_drawdown_limit']:
            if not self.trading_paused:
                logging.warning(f"TRADING PAUSED: Drawdown {drawdown*100:.2f}% exceeds limit")
                self.trading_paused = True
                self.pause_reason = f"Drawdown limit ({drawdown*100:.1f}%)"
            return True
        
        return False
    
    def check_daily_loss_limit(self, current_balance):
        """Check if daily loss limit exceeded"""
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance
            return False
        
        # Reset daily tracking at midnight
        now = get_local_now()
        if now.date() > self.session_start.date():
            self.daily_start_balance = current_balance
            self.session_start = now
            return False
        
        daily_loss = (self.daily_start_balance - current_balance) / self.daily_start_balance
        
        if daily_loss >= self.daily_loss_limit_pct:
            if not self.trading_paused:
                logging.warning(f"TRADING PAUSED: Daily loss {daily_loss*100:.2f}% exceeds {self.daily_loss_limit_pct*100}% limit")
                self.trading_paused = True
                self.pause_reason = f"Daily loss limit ({daily_loss*100:.1f}%)"
            return True
        
        return False
    
    def check_rapid_loss(self, current_balance):
        """Check for rapid losses (circuit breaker for flash crashes)"""
        now = get_local_now()
        self.balance_history.append({'time': now, 'balance': current_balance})
        
        # Keep only last hour of data
        cutoff_time = now - timedelta(minutes=self.rapid_loss_window_minutes)
        self.balance_history = [h for h in self.balance_history if h['time'] > cutoff_time]
        
        if len(self.balance_history) < 2:
            return False
        
        # Check loss over the window
        start_balance = self.balance_history[0]['balance']
        rapid_loss = (start_balance - current_balance) / start_balance
        
        if rapid_loss >= self.rapid_loss_threshold_pct:
            if not self.trading_paused:
                logging.warning(f"TRADING PAUSED: Rapid loss {rapid_loss*100:.2f}% in {self.rapid_loss_window_minutes} minutes")
                self.trading_paused = True
                self.pause_reason = f"Rapid loss ({rapid_loss*100:.1f}% in {self.rapid_loss_window_minutes}min)"
            return True
        
        return False
    
    def check_consecutive_losses(self):
        """Check if too many consecutive losses"""
        if self.consecutive_losses >= self.max_consecutive_losses:
            if not self.trading_paused:
                logging.warning(f"TRADING PAUSED: {self.consecutive_losses} consecutive losses")
                self.trading_paused = True
                self.pause_reason = f"Consecutive losses ({self.consecutive_losses})"
            return True
        return False
    
    def emergency_close_all(self, symbol='XAUUSD.p'):
        """Emergency: Close all positions immediately"""
        logging.critical("EMERGENCY: Closing all positions!")
        
        positions = self.get_open_positions(symbol)
        for pos in positions:
            self.close_position(pos, emergency=True, reason="Emergency stop - equity threshold")
        
        self.trading_paused = True
        self.pause_reason = "Emergency equity threshold"
    
    def check_emergency_threshold(self):
        """Check if equity has dropped to emergency levels"""
        if self.starting_balance is None:
            return False
        
        account_info = self.get_account_info()
        if not account_info:
            return False
        
        equity_loss = (self.starting_balance - account_info['equity']) / self.starting_balance
        
        if equity_loss >= self.emergency_equity_threshold_pct:
            logging.critical(f"EMERGENCY THRESHOLD: Equity down {equity_loss*100:.1f}%!")
            self.emergency_close_all()
            return True
        
        return False
    
    def run_safety_checks(self):
        """Run all safety checks - DEAD MAN'S SWITCH"""
        account_info = self.get_account_info()
        if not account_info:
            return
        
        current_balance = account_info['balance']
        
        # Check all safety mechanisms
        self.check_emergency_threshold()  # Most critical - check first
        self.check_drawdown(current_balance)
        self.check_daily_loss_limit(current_balance)
        self.check_rapid_loss(current_balance)
        self.check_consecutive_losses()
        
        # Log status if paused
        if self.trading_paused and self.pause_reason:
            logging.info(f"Trading paused: {self.pause_reason}")
    
    def is_near_weekend_close(self, minutes_before=30):
        """
        Check if we're approaching weekend market close (Friday)
        Gold market closes Friday 5:00 PM EST, reopens Sunday 6:00 PM EST
        
        Returns: (is_closing, reason)
        """
        from datetime import datetime
        import pytz
        
        try:
            # Get current time in EST
            est = pytz.timezone('US/Eastern')
            now_est = datetime.now(est)
            
            # Check if it's Friday
            if now_est.weekday() == 4:  # Friday = 4
                # Market closes at 5:00 PM EST
                close_time = now_est.replace(hour=17, minute=0, second=0, microsecond=0)
                time_until_close = (close_time - now_est).total_seconds() / 60
                
                # If within specified minutes before close
                if 0 < time_until_close <= minutes_before:
                    return True, f"Weekend close in {time_until_close:.0f} minutes (Friday 5pm EST)"
                
                # If already past close time (in case bot runs late)
                if time_until_close <= 0 and time_until_close > -60:
                    return True, "Market closed for weekend (Friday 5pm EST passed)"
            
            return False, None
            
        except Exception as e:
            logging.error(f"Error checking weekend close: {e}")
            return False, None
    
    def detect_market_gap(self, df):
        """
        Detect if there's been a market gap (market close/reopen or data gap)
        Returns: (has_gap, gap_percentage, time_gap_minutes)
        """
        if len(df) < 2:
            return False, 0, 0
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Check time gap (normal is 5 minutes for M5 timeframe)
        time_gap = (latest['time'] - previous['time']).total_seconds() / 60
        
        # If gap is more than 15 minutes, consider it a market gap
        if time_gap > 15:
            # Calculate price gap
            gap_pct = abs(latest['open'] - previous['close']) / previous['close'] * 100
            logging.warning(f"Market gap detected: {time_gap:.0f} minutes, {gap_pct:.2f}% price change")
            return True, gap_pct, time_gap
        
        return False, 0, time_gap
    
    def get_adaptive_atr_multiplier(self, df):
        """
        Calculate adaptive ATR multiplier based on volatility regime
        
        Returns lower multiplier in high volatility to limit losses
        """
        current_atr = df.iloc[-1]['ATR']
        
        # Calculate ATR percentile over last 100 candles
        recent_atrs = df['ATR'].tail(100)
        atr_80th_percentile = recent_atrs.quantile(0.80)
        atr_median = recent_atrs.median()
        
        base_multiplier = self.config['atr_multiplier']  # 2.75 for M1
        
        # High volatility regime (top 20%)
        if current_atr > atr_80th_percentile:
            # Reduce multiplier by 27% in high volatility
            adjusted_multiplier = base_multiplier * 0.73  # 2.75 * 0.73 = 2.0
            regime = "HIGH VOLATILITY"
            logging.info(f"[VOLATILITY REGIME] {regime}: ATR ${current_atr:.2f} > 80th percentile ${atr_80th_percentile:.2f}")
            logging.info(f"[ADAPTIVE STOP] Reducing multiplier: {base_multiplier}x → {adjusted_multiplier:.2f}x to limit losses")
            return adjusted_multiplier
        
        # Normal volatility regime
        else:
            return base_multiplier
    
    def get_open_positions(self, symbol='XAUUSD.p'):
        """Get all open positions with this bot's magic number"""
        positions = mt5.positions_get(symbol=symbol)
        bot_positions = []
        if positions and len(positions) > 0:
            # Only return positions created by this bot
            for pos in positions:
                if pos.magic == self.magic_number:
                    bot_positions.append(pos)
        return bot_positions
    
    def simplify_exit_reason(self, reason):
        """Simplify exit reason for GUI display"""
        reason_lower = reason.lower()
        
        # Profit protection
        if 'profit protection' in reason_lower:
            return 'Profit protection'
        
        # RSI exits
        if 'rsi exit' in reason_lower:
            return 'RSI exit'
        
        # Weekend protection
        if 'weekend' in reason_lower:
            return 'Weekend close'
        
        # Emergency stops
        if 'emergency' in reason_lower:
            if 'consecutive loss' in reason_lower:
                return 'Emergency (losses)'
            elif 'daily loss' in reason_lower:
                return 'Emergency (daily loss)'
            elif 'rapid loss' in reason_lower:
                return 'Emergency (rapid loss)'
            elif 'equity' in reason_lower:
                return 'Emergency (equity)'
            else:
                return 'Emergency stop'
        
        # Default: return first 30 characters
        return reason[:30] + '...' if len(reason) > 30 else reason
    
    def save_exit_reason(self, ticket, reason, exit_time):
        """Save exit reason to JSON file for GUI display"""
        exit_reasons_file = 'data/exit_reasons_m1.json'
        
        # Create data directory if it doesn't exist
        os.makedirs('data', exist_ok=True)
        
        # Simplify reason for GUI display
        short_reason = self.simplify_exit_reason(reason)
        
        # Load existing reasons
        exit_reasons = {}
        if os.path.exists(exit_reasons_file):
            try:
                with open(exit_reasons_file, 'r') as f:
                    exit_reasons = json.load(f)
            except:
                pass
        
        # Add new reason
        exit_reasons[str(ticket)] = {
            'reason': short_reason,
            'full_reason': reason,  # Keep full reason for logs
            'exit_time': exit_time.isoformat(),
            'bot': 'M1'
        }
        
        # Keep only last 200 entries to prevent file from growing too large
        if len(exit_reasons) > 200:
            # Sort by exit time and keep most recent
            sorted_tickets = sorted(exit_reasons.items(), 
                                   key=lambda x: x[1].get('exit_time', ''), 
                                   reverse=True)
            exit_reasons = dict(sorted_tickets[:200])
        
        # Save to file
        try:
            with open(exit_reasons_file, 'w') as f:
                json.dump(exit_reasons, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save exit reason: {e}")
    
    def calculate_position_size(self, symbol, current_price, stop_loss_price):
        """Calculate position size based on configuration"""
        account_info = self.get_account_info()
        if not account_info:
            return None
        
        balance = account_info['balance']
        
        # Base position (percentage of balance)
        base_position_value = balance * self.config['position_size_pct']
        
        # Apply leverage
        leveraged_position_value = base_position_value * self.config['leverage']
        
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
        
        # Calculate lot size
        # Position value / current price = number of units
        # Number of units / contract size = lots
        units = leveraged_position_value / current_price
        lots = units / symbol_info.trade_contract_size
        
        # Round to symbol's volume step
        lots = round(lots / symbol_info.volume_step) * symbol_info.volume_step
        
        # Ensure within min/max limits
        lots = max(symbol_info.volume_min, min(lots, symbol_info.volume_max))
        
        return lots
    
    def place_order(self, symbol, order_type, volume, sl, tp):
        """Place an order with price validation"""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Symbol {symbol} not found")
            return None
        
        # Get current price with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            tick = mt5.symbol_info_tick(symbol)
            if tick is None or tick.ask == 0 or tick.bid == 0:
                if attempt < max_retries - 1:
                    logging.warning(f"No prices available (attempt {attempt+1}/{max_retries}), retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                else:
                    logging.error("Failed to get valid tick data after retries")
                    return None
            break
        
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        
        # Validate price is reasonable
        if price <= 0:
            logging.error(f"Invalid price: {price}")
            return None
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "m1_scalping",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            order_type_str = "LONG" if order_type == mt5.ORDER_TYPE_BUY else "SHORT"
            sl_distance = abs(price - sl)
            tp_distance = abs(tp - price)
            risk_reward = tp_distance / sl_distance if sl_distance > 0 else 0
            
            # Log trade opening
            trade_record = {
                'action': 'OPEN',
                'time': get_local_now(),
                'type': order_type_str,
                'entry_price': price,
                'sl': sl,
                'tp': tp,
                'volume': volume,
                'order_id': result.order
            }
            self.trade_log.append(trade_record)
            
            # Track position by ticket
            ticket = result.order
            self.position_open_times[ticket] = datetime.now(self.local_timezone)
            
            logging.info(f">>> TRADE OPENED [{order_type_str}]")
            logging.info(f"  Entry Price: ${price:.2f}")
            logging.info(f"  Stop Loss: ${sl:.2f} (${sl_distance:.2f} away)")
            logging.info(f"  Take Profit: ${tp:.2f} (${tp_distance:.2f} away)")
            logging.info(f"  Risk/Reward: 1:{risk_reward:.2f}")
            logging.info(f"  Volume: {volume} lots")
            logging.info(f"  Order ID: {result.order}")
            return result
        else:
            logging.error(f"Order failed: {result.retcode} - {result.comment}")
            return None
    
    def close_position(self, position, emergency=False, reason="Manual close"):
        """Close an open position
        
        Args:
            position: MT5 position object
            emergency: Whether this is an emergency close
            reason: Exit reason (e.g., "RSI exit", "Stop loss", "Profit protection")
        """
        symbol = position.symbol
        ticket = position.ticket
        volume = position.volume
        position_type = position.type
        
        # Opposite order type to close
        close_type = mt5.ORDER_TYPE_SELL if position_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logging.error("Failed to get tick data")
            return None
        
        price = tick.bid if position_type == mt5.ORDER_TYPE_BUY else tick.ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": "m1_emergency" if emergency else "m1_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            profit = position.profit
            entry_price = position.price_open
            exit_price = price
            position_type_str = "LONG" if position_type == mt5.ORDER_TYPE_BUY else "SHORT"
            price_change = exit_price - entry_price if position_type == mt5.ORDER_TYPE_BUY else entry_price - exit_price
            price_change_pct = (price_change / entry_price) * 100
            
            # Track consecutive losses for dead man's switch
            if profit < 0:
                self.consecutive_losses += 1
                self.last_trade_profitable = False
            else:
                self.consecutive_losses = 0  # Reset on win
                self.last_trade_profitable = True  # Track for cooldown skip
            
            # Log trade closing
            trade_record = {
                'action': 'CLOSE',
                'time': get_local_now(),
                'exit_time': get_local_now(),  # Add explicit exit time
                'type': position_type_str,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'profit': profit,
                'price_change_pct': price_change_pct,
                'ticket': ticket,
                'emergency': emergency,
                'exit_reason': reason  # Add exit reason
            }
            self.trade_log.append(trade_record)
            
            # Save exit reason to file for GUI
            self.save_exit_reason(ticket, reason, get_local_now())
            
            close_type_str = "EMERGENCY CLOSE" if emergency else "TRADE CLOSED"
            logging.info(f"<<< {close_type_str} [{position_type_str}] - {reason}")
            logging.info(f"  Entry: ${entry_price:.2f} -> Exit: ${exit_price:.2f}")
            logging.info(f"  Price Change: ${price_change:.2f} ({price_change_pct:+.3f}%)")
            logging.info(f"  Profit/Loss: ${profit:.2f}")
            logging.info(f"  Ticket: {ticket}")
            if self.consecutive_losses > 0:
                logging.info(f"  Consecutive losses: {self.consecutive_losses}")
            
            # Track close time to prevent immediate re-entry
            self.last_close_time = datetime.now(self.local_timezone)
            self.last_close_position_type = position_type_str  # Track for smart cooldown
            self.last_trade_profitable = (profit > 0)  # Track if profitable
            
            # Remove position tracking
            if ticket in self.position_open_times:
                del self.position_open_times[ticket]
            
            # Mark as bot-closed to prevent MT5 detection from logging it again
            if not hasattr(self, 'bot_closed_positions'):
                self.bot_closed_positions = set()
            self.bot_closed_positions.add(ticket)
            if ticket in self.peak_position_profits:
                del self.peak_position_profits[ticket]
            
            return result
        else:
            logging.error(f"Failed to close position: {result.retcode} - {result.comment}")
            return None
    
    def trading_logic(self):
        """Main trading logic"""
        symbol = 'XAUUSD.p'
        
        # Get account info
        account_info = self.get_account_info()
        if not account_info:
            logging.error("Failed to get account info")
            return
        
        # RUN ALL SAFETY CHECKS - DEAD MAN'S SWITCH
        self.run_safety_checks()
        
        # If trading is paused by any safety mechanism, skip trading logic
        if self.trading_paused:
            return
        
        # WEEKEND CLOSE PROTECTION - Close positions before Friday 5pm
        is_weekend_closing, close_reason = self.is_near_weekend_close(minutes_before=30)
        
        # Check for open positions
        open_positions = self.get_open_positions(symbol)
        
        if is_weekend_closing:
            if len(open_positions) > 0:
                logging.warning(f"WEEKEND CLOSE PROTECTION: {close_reason}")
                logging.warning(f"Closing {len(open_positions)} position(s) to avoid weekend gap risk")
                for pos in open_positions:
                    logging.warning(f"Position ticket {pos.ticket}: P/L ${pos.profit:.2f}")
                    self.close_position(pos, emergency=False, reason=f"Weekend protection - {close_reason}")
                return
            else:
                logging.info(f"Weekend close approaching - no new positions will be opened")
                return
        
        # Get historical data
        df = self.get_historical_data(symbol)
        if df is None or len(df) < 200:
            logging.error("Insufficient data")
            return
        
        # Detect market gaps
        has_gap, gap_pct, time_gap = self.detect_market_gap(df)
        
        gap_warmup_active = False
        if has_gap:
            # Reset last_close_time to trigger warm-up period for NEW entries
            self.last_close_time = get_local_now()
            gap_warmup_active = True
            logging.warning(f"Market gap detected - entering {self.warmup_candles} candle warm-up period for NEW entries")
            logging.warning(f"Gap details: {time_gap:.0f} min time gap, {gap_pct:.2f}% price change")
            logging.warning(f"Will continue managing existing positions during warmup")
        
        # Calculate indicators
        df = self.compute_indicators(df)
        latest = df.iloc[-1]
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return
        
        current_price = tick.bid
        
        # Get RSI for use in logging and trading logic
        rsi = latest['RSI']
        
        # ============================================================================
        # DIAGNOSTIC LOGGING - Show bot's "thought process" (COMPACT MODE)
        # ============================================================================
        
        # Only log key events, not every candle analysis
        log_this_candle = False
        
        # Log if we have positions
        if len(open_positions) > 0:
            log_this_candle = True
        
        # Log if there's an active signal
        if rsi < self.config['rsi_buy'] or (self.config['enable_shorts'] and rsi > self.config['rsi_sell'] and latest['downtrend']):
            log_this_candle = True
        
        # Log if gap warmup or cooldown active
        if gap_warmup_active or (self.last_close_time is not None and (get_local_now() - self.last_close_time).total_seconds() < self.warmup_candles * 60):
            log_this_candle = True
        
        if log_this_candle:
            logging.info("=" * 80)
            logging.info("BOT ANALYSIS - M1 Scalping Strategy")
            logging.info("=" * 80)
            
            # Market conditions
            logging.info(f"[MARKET DATA]")
            logging.info(f"   Price: ${current_price:.2f} | ATR: ${latest['ATR']:.2f}")
            logging.info(f"   EMA Fast (5): ${latest['ema_fast']:.2f} | EMA Slow (12): ${latest['ema_slow']:.2f}")
            
            # Trend analysis
            trend = "UPTREND ^" if latest['uptrend'] else "DOWNTREND v" if latest['downtrend'] else "SIDEWAYS -"
            logging.info(f"   Trend: {trend}")
            
            # RSI analysis with visual indicator
            rsi_bar = "#" * int(rsi / 5)  # Visual bar (20 chars = 100 RSI)
            rsi_status = ""
            if rsi < self.config['rsi_buy']:
                rsi_status = "[OVERSOLD - BUY ZONE]"
            elif rsi > self.config['rsi_sell']:
                rsi_status = "[OVERBOUGHT - SELL ZONE]"
            else:
                rsi_status = "[NEUTRAL]"
            
            logging.info(f"   RSI: {rsi:.1f} [{rsi_bar:<20}] {rsi_status}")
            logging.info(f"   Thresholds: Buy < {self.config['rsi_buy']} | Sell > {self.config['rsi_sell']}")
            
            # Position status
            logging.info(f"")
            logging.info(f"[POSITIONS]: {len(open_positions)}/{self.max_positions}")
            
            if len(open_positions) > 0:
                for pos in open_positions:
                    pos_type = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
                    profit_status = "PROFIT" if pos.profit > 0 else "LOSS" if pos.profit < 0 else "BREAKEVEN"
                    
                    # Calculate position details
                    if pos.ticket in self.position_open_times:
                        time_held = datetime.now(self.local_timezone) - self.position_open_times[pos.ticket]
                        minutes_held = time_held.total_seconds() / 60
                    else:
                        minutes_held = 0
                    
                    logging.info(f"   Ticket {pos.ticket} [{pos_type}]:")
                    logging.info(f"      Entry: ${pos.price_open:.2f} | Current: ${current_price:.2f}")
                    logging.info(f"      P/L: ${pos.profit:.2f} ({profit_status})")
                    logging.info(f"      Time Held: {minutes_held:.1f} min")
                    logging.info(f"      SL: ${pos.sl:.2f} | TP: ${pos.tp:.2f}")
            else:
                logging.info(f"   No open positions")
            
            # Entry logic analysis
            logging.info(f"")
            logging.info(f"[ENTRY LOGIC]")
            
            if len(open_positions) >= self.max_positions:
                logging.info(f"   [X] Max positions reached ({len(open_positions)}/{self.max_positions})")
            elif gap_warmup_active:
                logging.info(f"   [WAIT] Gap warmup active - waiting {self.warmup_candles} candles")
            elif self.last_close_time is not None:
                time_since_close = get_local_now() - self.last_close_time
                cooldown_seconds = self.warmup_candles * 1 * 60
                if not self.last_trade_profitable and time_since_close.total_seconds() < cooldown_seconds:
                    remaining = cooldown_seconds - time_since_close.total_seconds()
                    logging.info(f"   [WAIT] Cooldown active (after loss) - {remaining/60:.1f} min remaining")
                elif self.last_trade_profitable and time_since_close.total_seconds() < cooldown_seconds:
                    logging.info(f"   [OK] Cooldown skipped (after win) - ready for immediate re-entry")
                    
                    # Analyze entry conditions
                    if rsi < self.config['rsi_buy']:
                        logging.info(f"   >> LONG SIGNAL ACTIVE: RSI {rsi:.1f} < {self.config['rsi_buy']}")
                    elif self.config['enable_shorts'] and rsi > self.config['rsi_sell'] and latest['downtrend']:
                        logging.info(f"   >> SHORT SIGNAL ACTIVE: RSI {rsi:.1f} > {self.config['rsi_sell']} + Downtrend")
                    else:
                        logging.info(f"   -- No entry signal")
                        if rsi >= self.config['rsi_buy'] and rsi <= self.config['rsi_sell']:
                            logging.info(f"      RSI in neutral zone ({self.config['rsi_buy']}-{self.config['rsi_sell']})")
                else:
                    logging.info(f"   [OK] Ready for new entry")
                    
                    # Analyze entry conditions
                    if rsi < self.config['rsi_buy']:
                        logging.info(f"   >> LONG SIGNAL ACTIVE: RSI {rsi:.1f} < {self.config['rsi_buy']}")
                    elif self.config['enable_shorts'] and rsi > self.config['rsi_sell'] and latest['downtrend']:
                        logging.info(f"   >> SHORT SIGNAL ACTIVE: RSI {rsi:.1f} > {self.config['rsi_sell']} + Downtrend")
                    else:
                        logging.info(f"   -- No entry signal")
                        if rsi >= self.config['rsi_buy'] and rsi <= self.config['rsi_sell']:
                            logging.info(f"      RSI in neutral zone ({self.config['rsi_buy']}-{self.config['rsi_sell']})")
            else:
                logging.info(f"   [OK] Ready for new entry")
                
                # Analyze entry conditions
                if rsi < self.config['rsi_buy']:
                    logging.info(f"   >> LONG SIGNAL ACTIVE: RSI {rsi:.1f} < {self.config['rsi_buy']}")
                elif self.config['enable_shorts'] and rsi > self.config['rsi_sell'] and latest['downtrend']:
                    logging.info(f"   >> SHORT SIGNAL ACTIVE: RSI {rsi:.1f} > {self.config['rsi_sell']} + Downtrend")
                else:
                    logging.info(f"   -- No entry signal")
                    if rsi >= self.config['rsi_buy'] and rsi <= self.config['rsi_sell']:
                        logging.info(f"      RSI in neutral zone ({self.config['rsi_buy']}-{self.config['rsi_sell']})")
            
            # Exit logic analysis for each position
            if len(open_positions) > 0:
                logging.info(f"")
                logging.info(f"[EXIT LOGIC]")
                
                for pos in open_positions:
                    pos_type_str = "LONG" if pos.type == mt5.ORDER_TYPE_BUY else "SHORT"
                    logging.info(f"   Ticket {pos.ticket} [{pos_type_str}]:")
                    
                    # Check standard exits
                    exit_threshold = self.config.get('rsi_exit_long' if pos.type == mt5.ORDER_TYPE_BUY else 'rsi_exit_short',
                                                    self.config['rsi_sell'] if pos.type == mt5.ORDER_TYPE_BUY else self.config['rsi_buy'])
                    
                    if pos.type == mt5.ORDER_TYPE_BUY:
                        if rsi > exit_threshold:
                            logging.info(f"      [EXIT!] RSI: {rsi:.1f} > {exit_threshold} (overbought)")
                        else:
                            logging.info(f"      [HOLD] RSI {rsi:.1f} < {exit_threshold} exit threshold")
                    else:
                        if rsi < exit_threshold:
                            logging.info(f"      [EXIT!] RSI: {rsi:.1f} < {exit_threshold} (oversold)")
                        else:
                            logging.info(f"      [HOLD] RSI {rsi:.1f} > {exit_threshold} exit threshold")
            
            logging.info("=" * 80)
        
        # ============================================================================
        # END DIAGNOSTIC LOGGING
        # ============================================================================
        
        # Initialize position open times for existing positions if not set
        for pos in open_positions:
            if pos.ticket not in self.position_open_times:
                # Convert MT5 timestamp to local timezone (handles DST automatically)
                mt5_time = datetime.fromtimestamp(pos.time, tz=self.mt5_timezone)
                self.position_open_times[pos.ticket] = mt5_time.astimezone(self.local_timezone)
                logging.info(f"Detected existing position {pos.ticket}")
        
        # Check for new entry if we have room for more positions
        if len(open_positions) < self.max_positions:
            # Skip new entries if gap warmup is active
            if gap_warmup_active:
                logging.info(f"Gap warmup active - skipping new entries for {self.warmup_candles} candles")
            else:
                # Check cooldown/warm-up period after closing a position or market gap
                # Smart cooldown: Skip cooldown if conditions suggest genuine reversal
                can_enter = True
                if self.last_close_time is not None:
                    time_since_close = datetime.now(self.local_timezone) - self.last_close_time
                    
                    # Apply loss backoff if enabled
                    if self.config.get('use_loss_backoff', False) and self.consecutive_losses > 0:
                        # Get backoff multiplier based on consecutive losses
                        multipliers = self.config.get('loss_backoff_multipliers', [1, 3, 7, 15])
                        loss_index = min(self.consecutive_losses - 1, len(multipliers) - 1)
                        backoff_multiplier = multipliers[loss_index]
                        cooldown_seconds = self.warmup_candles * 1 * 60 * backoff_multiplier  # warmup_candles * 1 minute * 60 seconds * multiplier
                        
                        if time_since_close.total_seconds() < cooldown_seconds:
                            remaining = cooldown_seconds - time_since_close.total_seconds()
                            logging.info(f"Loss backoff active: {remaining/60:.1f} minutes remaining (after {self.consecutive_losses} losses, {backoff_multiplier}x multiplier)")
                            can_enter = False
                    else:
                        # Standard cooldown logic
                        cooldown_seconds = self.warmup_candles * 1 * 60  # warmup_candles * 1 minute * 60 seconds
                        
                        if time_since_close.total_seconds() < cooldown_seconds:
                            # Check if we should skip cooldown (smart cooldown)
                            should_skip, skip_reason = self.should_skip_cooldown(df, self.last_close_position_type)
                            
                            if should_skip:
                                logging.info(f"[SMART COOLDOWN SKIP] {skip_reason}")
                                can_enter = True
                            elif not self.last_trade_profitable:
                                remaining = cooldown_seconds - time_since_close.total_seconds()
                                logging.info(f"Cooldown active: {remaining/60:.1f} minutes remaining before next entry")
                                can_enter = False
                            else:
                                logging.info(f"Skipping cooldown after profitable trade - ready for immediate re-entry")
                                can_enter = True
                
                if can_enter:
                    # Check if we already have positions in opposite direction
                    has_long = any(pos.type == mt5.ORDER_TYPE_BUY for pos in open_positions)
                    has_short = any(pos.type == mt5.ORDER_TYPE_SELL for pos in open_positions)
                    
                    # Signal confirmation: require multiple consecutive signals when NO positions
                    # This prevents jumping on first RSI dip during larger downtrends
                    # When we have 1 position and adding 2nd, skip confirmation (faster re-entry)
                    required_confirmations = self.config.get('entry_signal_confirmations', 0)
                    
                    # Only skip confirmation if we're adding to existing positions (1 -> 2)
                    # Still require confirmation for first position (0 -> 1)
                    if len(open_positions) > 0:
                        required_confirmations = 0
                        confirmation_status = "skipped (adding to position)"
                    else:
                        confirmation_status = f"required ({required_confirmations + 1} candles)"
                    
                    # LONG ENTRY
                    if latest['RSI'] < self.config['rsi_buy']:
                        # Increment LONG signal count, reset SHORT
                        self.entry_signal_count['LONG'] += 1
                        self.entry_signal_count['SHORT'] = 0
                        
                        # If we have SHORT positions, skip this signal (BLOCK behavior)
                        if has_short:
                            logging.info(f"LONG signal detected but skipping - already have SHORT position(s)")
                        elif self.entry_signal_count['LONG'] <= required_confirmations:
                            # Need more confirmations
                            logging.info(f"LONG signal detected - waiting for confirmation ({self.entry_signal_count['LONG']}/{required_confirmations + 1} candles, {confirmation_status})")
                        else:
                            # Confirmed signal
                            if required_confirmations > 0:
                                logging.info(f"LONG SIGNAL CONFIRMED: RSI={latest['RSI']:.2f} ({self.entry_signal_count['LONG']} consecutive candles)")
                            else:
                                logging.info(f"LONG SIGNAL: RSI={latest['RSI']:.2f} ({confirmation_status})")
                            
                            # Calculate stop loss with adaptive multiplier based on volatility
                            adaptive_multiplier = self.get_adaptive_atr_multiplier(df)
                            stop_distance = latest['ATR'] * adaptive_multiplier
                            sl = current_price - stop_distance
                            tp = current_price + (current_price * self.config['profit_target_pct'])
                            
                            # Calculate position size
                            volume = self.calculate_position_size(symbol, current_price, sl)
                            
                            if volume:
                                logging.info(f"Placing LONG order: Volume={volume}, SL={sl:.2f}, TP={tp:.2f}")
                                result = self.place_order(symbol, mt5.ORDER_TYPE_BUY, volume, sl, tp)
                                if result:
                                    self.trades_today += 1
                                    self.last_trade_time = get_local_now()
                                    # Reset signal count after entry
                                    self.entry_signal_count['LONG'] = 0
                    
                    # SHORT ENTRY
                    elif self.config['enable_shorts'] and latest['RSI'] > self.config['rsi_sell'] and latest['downtrend']:
                        # Increment SHORT signal count, reset LONG
                        self.entry_signal_count['SHORT'] += 1
                        self.entry_signal_count['LONG'] = 0
                        
                        # If we have LONG positions, skip this signal (BLOCK behavior)
                        if has_long:
                            logging.info(f"SHORT signal detected but skipping - already have LONG position(s)")
                        elif self.entry_signal_count['SHORT'] <= required_confirmations:
                            # Need more confirmations
                            logging.info(f"SHORT signal detected - waiting for confirmation ({self.entry_signal_count['SHORT']}/{required_confirmations + 1} candles, {confirmation_status})")
                        else:
                            # Confirmed signal
                            if required_confirmations > 0:
                                logging.info(f"SHORT SIGNAL CONFIRMED: RSI={latest['RSI']:.2f} ({self.entry_signal_count['SHORT']} consecutive candles)")
                            else:
                                logging.info(f"SHORT SIGNAL: RSI={latest['RSI']:.2f} ({confirmation_status})")
                            
                            # Calculate stop loss with adaptive multiplier based on volatility
                            adaptive_multiplier = self.get_adaptive_atr_multiplier(df)
                            stop_distance = latest['ATR'] * adaptive_multiplier
                            sl = current_price + stop_distance
                            tp = current_price - (current_price * self.config['profit_target_pct'])
                            
                            volume = self.calculate_position_size(symbol, current_price, sl)
                            
                            if volume:
                                logging.info(f"Placing SHORT order: Volume={volume}, SL={sl:.2f}, TP={tp:.2f}")
                                result = self.place_order(symbol, mt5.ORDER_TYPE_SELL, volume, sl, tp)
                                if result:
                                    self.trades_today += 1
                                    self.last_trade_time = get_local_now()
                                    # Reset signal count after entry
                                    self.entry_signal_count['SHORT'] = 0
                    else:
                        # No signal - reset counters
                        self.entry_signal_count['LONG'] = 0
                        self.entry_signal_count['SHORT'] = 0
        
        # Check exit signals for all open positions
        for open_position in open_positions:
            position_type = open_position.type
            current_price = latest['close']
            ticket = open_position.ticket
            
            should_close = False
            reason = ""
            
            # PROFIT PROTECTION: Exit if profit drops significantly from peak
            if self.config.get('use_profit_protection', False):
                current_profit = open_position.profit
                
                # Track peak profit for this position
                if ticket not in self.peak_position_profits:
                    self.peak_position_profits[ticket] = max(0, current_profit)
                else:
                    self.peak_position_profits[ticket] = max(self.peak_position_profits[ticket], current_profit)
                
                peak_profit = self.peak_position_profits[ticket]
                
                # Calculate profit as percentage of position value
                position_value = open_position.volume * open_position.price_open * 100  # 100 oz per lot
                profit_pct = current_profit / position_value if position_value > 0 else 0
                peak_profit_pct = peak_profit / position_value if position_value > 0 else 0
                
                # Only protect if we've reached the threshold
                protection_threshold = self.config.get('profit_protection_threshold_pct', 0.003)
                if peak_profit_pct > protection_threshold and peak_profit > 0:
                    # Calculate drawdown from peak
                    profit_drawdown = (peak_profit - current_profit) / peak_profit
                    drawdown_limit = self.config.get('profit_protection_drawdown_limit_pct', 0.40)
                    
                    if profit_drawdown > drawdown_limit:
                        should_close = True
                        reason = f"Profit protection: profit dropped {profit_drawdown*100:.1f}% from peak ${peak_profit:.2f} to ${current_profit:.2f}"
                        logging.info(f"[PROFIT PROTECTION] Ticket {ticket}: Peak ${peak_profit:.2f} -> Current ${current_profit:.2f} ({profit_drawdown*100:.1f}% drop)")
            
            # Get previous candle for RSI confirmation
            previous = df.iloc[-2] if len(df) >= 2 else latest
            
            # Standard RSI-based exits with confirmation to prevent false spikes
            # M1 analysis showed 100% of RSI spikes are false signals (drop back within 3 min)
            use_confirmation = self.config.get('rsi_exit_confirmation', True)
            
            if not should_close:
                if position_type == mt5.ORDER_TYPE_BUY:
                    # LONG POSITION
                    exit_threshold = self.config.get('rsi_exit_long', self.config['rsi_sell'])
                    
                    if use_confirmation:
                        # Require 2 consecutive candles above threshold
                        current_above = latest['RSI'] > exit_threshold
                        previous_above = previous['RSI'] > exit_threshold
                        
                        if current_above and previous_above:
                            should_close = True
                            reason = f"RSI exit confirmed ({latest['RSI']:.2f} > {exit_threshold} for 2 candles)"
                        elif current_above:
                            # First candle above - wait for confirmation
                            if ticket not in self.rsi_confirmation_tracker:
                                self.rsi_confirmation_tracker[ticket] = 1
                                logging.info(f"RSI {latest['RSI']:.2f} > {exit_threshold} - waiting for confirmation (ticket {ticket})")
                        else:
                            # RSI dropped back - reset
                            if ticket in self.rsi_confirmation_tracker:
                                del self.rsi_confirmation_tracker[ticket]
                    else:
                        # No confirmation - immediate exit (old behavior)
                        if latest['RSI'] > exit_threshold:
                            should_close = True
                            reason = f"RSI exit threshold ({latest['RSI']:.2f} > {exit_threshold})"
                        
                else:
                    # SHORT POSITION
                    exit_threshold = self.config.get('rsi_exit_short', self.config['rsi_buy'])
                    
                    if use_confirmation:
                        # Require 2 consecutive candles below threshold
                        current_below = latest['RSI'] < exit_threshold
                        previous_below = previous['RSI'] < exit_threshold
                        
                        if current_below and previous_below:
                            should_close = True
                            reason = f"RSI exit confirmed ({latest['RSI']:.2f} < {exit_threshold} for 2 candles)"
                        elif current_below:
                            # First candle below - wait for confirmation
                            if ticket not in self.rsi_confirmation_tracker:
                                self.rsi_confirmation_tracker[ticket] = 1
                                logging.info(f"RSI {latest['RSI']:.2f} < {exit_threshold} - waiting for confirmation (ticket {ticket})")
                        else:
                            # RSI rose back - reset
                            if ticket in self.rsi_confirmation_tracker:
                                del self.rsi_confirmation_tracker[ticket]
                    else:
                        # No confirmation - immediate exit (old behavior)
                        if latest['RSI'] < exit_threshold:
                            should_close = True
                            reason = f"RSI exit threshold ({latest['RSI']:.2f} < {exit_threshold})"
            
            if should_close:
                current_profit = open_position.profit
                logging.info(f"EXIT SIGNAL (ticket {ticket}): {reason}, Current P/L: ${current_profit:.2f}")
                self.close_position(open_position, reason=reason)
    
    def get_time_based_drawdown_limit(self, position_open_time):
        """
        Calculate drawdown limit based on how long position has been held
        
        Tightens profit protection over time to encourage taking profits on long-held positions
        """
        if not self.config.get('profit_protection_time_based_tightening', False):
            # Time-based tightening disabled, use base limit
            return self.config.get('profit_protection_drawdown_limit_pct', 0.50)
        
        time_held_minutes = (get_local_now() - position_open_time).total_seconds() / 60
        
        base_limit = self.config.get('profit_protection_drawdown_limit_pct', 0.50)
        tightening_start = self.config.get('profit_protection_tightening_start_minutes', 10)
        tightening_interval = self.config.get('profit_protection_tightening_interval_minutes', 5)
        tightening_step = self.config.get('profit_protection_tightening_step_pct', 0.05)
        minimum_limit = self.config.get('profit_protection_minimum_drawdown_pct', 0.20)
        
        if time_held_minutes < tightening_start:
            return base_limit
        
        # Calculate how many intervals have passed since tightening started
        intervals_passed = int((time_held_minutes - tightening_start) / tightening_interval)
        
        # Reduce limit by step for each interval
        adjusted_limit = base_limit - (intervals_passed * tightening_step)
        
        # Don't go below minimum
        return max(adjusted_limit, minimum_limit)
    
    def check_profit_protection_continuous(self, symbol='XAUUSD.p'):
        """
        Check profit protection on ALL open positions (runs every second)
        
        This runs independently of candle closes to catch intra-candle profit swings.
        Example: Position goes from +$30 to -$10 to +$33 within one candle.
        Without continuous checking, we miss the exit opportunity at +$18.
        
        Uses time-based tightening: starts lenient, tightens over time to encourage profit taking.
        """
        if not self.config.get('use_profit_protection', False):
            return
        
        open_positions = self.get_open_positions(symbol)
        if len(open_positions) == 0:
            return
        
        for open_position in open_positions:
            ticket = open_position.ticket
            current_profit = open_position.profit
            
            # Track peak profit for this position
            if ticket not in self.peak_position_profits:
                self.peak_position_profits[ticket] = max(0, current_profit)
                # Calculate threshold as % of invested amount (not leveraged)
                account_info = self.get_account_info()
                if account_info:
                    balance = account_info['balance']
                    invested_amount = balance * self.config.get('position_size_pct', 0.075)
                    protection_threshold = self.config.get('profit_protection_threshold_pct', 0.02)
                    threshold_dollars = invested_amount * protection_threshold
                    logging.info(f"[PROFIT PROTECTION] Ticket {ticket}: Initialized peak at ${current_profit:.2f} (will activate at ${threshold_dollars:.2f})")
                else:
                    logging.info(f"[PROFIT PROTECTION] Ticket {ticket}: Initialized peak at ${current_profit:.2f}")
            else:
                old_peak = self.peak_position_profits[ticket]
                self.peak_position_profits[ticket] = max(self.peak_position_profits[ticket], current_profit)
                if self.peak_position_profits[ticket] > old_peak:
                    # Check if protection is already activated
                    if not hasattr(self, 'protection_activated'):
                        self.protection_activated = {}
                    
                    if ticket in self.protection_activated:
                        # Already activated - show exit trigger level
                        if ticket in self.position_open_times:
                            drawdown_limit = self.get_time_based_drawdown_limit(self.position_open_times[ticket])
                            trigger_at = self.peak_position_profits[ticket] * (1 - drawdown_limit)
                            logging.info(f"[PROFIT PROTECTION] Ticket {ticket}: New peak ${self.peak_position_profits[ticket]:.2f} (was ${old_peak:.2f}, will exit at ${trigger_at:.2f})")
                        else:
                            logging.info(f"[PROFIT PROTECTION] Ticket {ticket}: New peak ${self.peak_position_profits[ticket]:.2f} (was ${old_peak:.2f})")
                    else:
                        # Not yet activated - just show the peak
                        logging.info(f"[PROFIT PROTECTION] Ticket {ticket}: New peak ${self.peak_position_profits[ticket]:.2f} (was ${old_peak:.2f})")
            
            peak_profit = self.peak_position_profits[ticket]
            
            # Calculate profit as percentage of INVESTED amount (not leveraged position value)
            account_info = self.get_account_info()
            if account_info:
                balance = account_info['balance']
                invested_amount = balance * self.config.get('position_size_pct', 0.075)
                profit_pct = current_profit / invested_amount if invested_amount > 0 else 0
                peak_profit_pct = peak_profit / invested_amount if invested_amount > 0 else 0
            else:
                profit_pct = 0
                peak_profit_pct = 0
            
            # Only protect if we've reached the threshold (2% of invested amount)
            protection_threshold = self.config.get('profit_protection_threshold_pct', 0.02)
            
            # Check if we just crossed the threshold (activated protection)
            if not hasattr(self, 'protection_activated'):
                self.protection_activated = {}
            
            if ticket not in self.protection_activated:
                if peak_profit_pct > protection_threshold and peak_profit > 0:
                    # Calculate threshold in dollars (2% of invested amount)
                    account_info = self.get_account_info()
                    if account_info:
                        balance = account_info['balance']
                        invested_amount = balance * self.config.get('position_size_pct', 0.075)
                        threshold_dollars = invested_amount * protection_threshold
                        logging.info(f"[PROFIT PROTECTION ACTIVATED] Ticket {ticket}: Profit ${peak_profit:.2f} exceeded threshold ${threshold_dollars:.2f} ({protection_threshold*100:.2f}% of invested amount ${invested_amount:.2f})")
                    else:
                        logging.info(f"[PROFIT PROTECTION ACTIVATED] Ticket {ticket}: Profit ${peak_profit:.2f} exceeded threshold")
                    self.protection_activated[ticket] = True
            
            if peak_profit_pct > protection_threshold and peak_profit > 0:
                # Get time-based drawdown limit (tightens over time)
                if ticket in self.position_open_times:
                    drawdown_limit = self.get_time_based_drawdown_limit(self.position_open_times[ticket])
                    time_held = (get_local_now() - self.position_open_times[ticket]).total_seconds() / 60
                else:
                    drawdown_limit = self.config.get('profit_protection_drawdown_limit_pct', 0.50)
                    time_held = 0
                
                # Calculate drawdown from peak
                profit_drawdown = (peak_profit - current_profit) / peak_profit
                
                if profit_drawdown > drawdown_limit:
                    reason = f"Profit protection (continuous): profit dropped {profit_drawdown*100:.1f}% from peak ${peak_profit:.2f} to ${current_profit:.2f} (limit {drawdown_limit*100:.0f}% after {time_held:.0f}min)"
                    logging.info(f"[PROFIT PROTECTION - CONTINUOUS] Ticket {ticket}: Peak ${peak_profit:.2f} -> Current ${current_profit:.2f} ({profit_drawdown*100:.1f}% drop, limit {drawdown_limit*100:.0f}% after {time_held:.0f}min)")
                    logging.info(f"EXIT SIGNAL (ticket {ticket}): {reason}")
                    self.close_position(open_position, reason=reason)
    
    def check_mt5_closed_positions(self, symbol='XAUUSD.p'):
        """
        Check for positions that were closed by MT5 (stop loss hit) and record the exit reason.
        This runs every second to catch MT5-triggered exits.
        """
        if not hasattr(self, 'tracked_positions'):
            self.tracked_positions = set()
        if not hasattr(self, 'bot_closed_positions'):
            self.bot_closed_positions = set()
        
        # Get currently open positions
        current_positions = self.get_open_positions(symbol)
        current_tickets = {pos.ticket for pos in current_positions}
        
        # Update tracked positions with any new ones
        self.tracked_positions.update(current_tickets)
        
        # Find positions that were open but are now closed
        closed_tickets = self.tracked_positions - current_tickets
        
        if closed_tickets:
            # Check history for these closed positions
            for ticket in closed_tickets:
                # Skip if this was closed by the bot itself
                if ticket in self.bot_closed_positions:
                    self.bot_closed_positions.discard(ticket)
                    self.tracked_positions.discard(ticket)
                    continue
                
                # Get deal history for this position
                deals = mt5.history_deals_get(position=ticket)
                if deals and len(deals) > 0:
                    # Find the exit deal (OUT)
                    exit_deal = None
                    for deal in deals:
                        if deal.entry == mt5.DEAL_ENTRY_OUT:
                            exit_deal = deal
                            break
                    
                    if exit_deal:
                        # Check if this was a stop loss exit
                        # MT5 marks SL exits with specific comment or reason
                        reason_code = exit_deal.reason
                        profit = exit_deal.profit
                        
                        # Determine exit reason based on MT5 reason code
                        if reason_code == mt5.DEAL_REASON_SL:
                            exit_reason = "Stop loss"
                        elif reason_code == mt5.DEAL_REASON_TP:
                            exit_reason = "Take profit"
                        else:
                            # Could be manual close or other reason
                            exit_reason = "MT5 close"
                        
                        # Track consecutive losses for backoff (same as bot-triggered closes)
                        if profit < 0:
                            self.consecutive_losses += 1
                            self.last_trade_profitable = False
                            logging.info(f"[MT5 EXIT DETECTED] Ticket {ticket}: {exit_reason} (profit: ${profit:.2f}) - Consecutive losses: {self.consecutive_losses}")
                        else:
                            self.consecutive_losses = 0  # Reset on win
                            self.last_trade_profitable = True
                            logging.info(f"[MT5 EXIT DETECTED] Ticket {ticket}: {exit_reason} (profit: ${profit:.2f})")
                        
                        # Record the exit reason
                        self.save_exit_reason(ticket, exit_reason, get_local_now())
                
                # Remove from tracked positions
                self.tracked_positions.discard(ticket)
    
    def has_new_candle(self, symbol='XAUUSD.p', timeframe=mt5.TIMEFRAME_M1):
        """Check if a new candle has formed since last check"""
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 1)
        if rates is None or len(rates) == 0:
            return False, None
        
        latest_candle_time = pd.to_datetime(rates[0]['time'], unit='s')
        
        # First run - initialize
        if self.last_processed_candle is None:
            self.last_processed_candle = latest_candle_time
            return True, latest_candle_time
        
        # Check if we have a new candle
        if latest_candle_time > self.last_processed_candle:
            self.last_processed_candle = latest_candle_time
            return True, latest_candle_time
        
        return False, latest_candle_time
    
    def wait_for_next_candle(self, timeframe_minutes=5):
        """Wait until the next candle closes and return seconds waited"""
        now = get_local_now()
        
        # Calculate seconds into current candle
        seconds_into_candle = (now.minute % timeframe_minutes) * 60 + now.second
        
        # Calculate seconds until next candle
        seconds_until_next = (timeframe_minutes * 60) - seconds_into_candle
        
        # Add small buffer to ensure candle has closed
        seconds_until_next += 2
        
        return seconds_until_next
    
    def generate_report(self):
        """Generate a trading report for this session"""
        if not self.trade_log:
            return "No trades in this session"
        
        # Separate opens and closes
        opens = [t for t in self.trade_log if t['action'] == 'OPEN']
        closes = [t for t in self.trade_log if t['action'] == 'CLOSE']
        
        # Calculate statistics
        total_profit = sum(t['profit'] for t in closes)
        winning = [t for t in closes if t['profit'] > 0]
        losing = [t for t in closes if t['profit'] < 0]
        
        session_duration = (get_local_now() - self.session_start).total_seconds() / 3600
        
        report = []
        report.append("="*80)
        report.append("M1 BOT SESSION REPORT")
        report.append("="*80)
        report.append(f"Session Start: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Session Duration: {session_duration:.1f} hours")
        report.append(f"")
        report.append(f"TRADES:")
        report.append(f"  Total: {len(closes)}")
        report.append(f"  Winning: {len(winning)} ({len(winning)/len(closes)*100:.1f}%)" if closes else "  Winning: 0")
        report.append(f"  Losing: {len(losing)} ({len(losing)/len(closes)*100:.1f}%)" if closes else "  Losing: 0")
        report.append(f"  Total P/L: ${total_profit:.2f}")
        
        if winning:
            report.append(f"  Avg Win: ${sum(t['profit'] for t in winning)/len(winning):.2f}")
        if losing:
            report.append(f"  Avg Loss: ${sum(t['profit'] for t in losing)/len(losing):.2f}")
        
        report.append(f"")
        report.append(f"RECENT TRADES (Last 10):")
        report.append(f"{'Time':<12} | {'Action':<5} | {'Type':<5} | {'Price':>8} | {'P/L':>9}")
        report.append("="*80)
        
        for trade in self.trade_log[-20:]:  # Last 20 entries (10 open+close pairs)
            time_str = trade['time'].strftime('%H:%M:%S')
            if trade['action'] == 'OPEN':
                report.append(f"{time_str:<12} | OPEN  | {trade['type']:<5} | ${trade['entry_price']:>7.2f} | SL:${trade['sl']:.2f} TP:${trade['tp']:.2f}")
            else:
                pnl_str = f"${trade['profit']:+.2f}"
                report.append(f"{time_str:<12} | CLOSE | {trade['type']:<5} | ${trade['exit_price']:>7.2f} | {pnl_str:>9}")
        
        report.append("="*80)
        
        return "\n".join(report)
    
    def run(self, check_interval=1):
        """Run the trading bot"""
        logging.info("="*80)
        logging.info("LIVE TRADING BOT STARTED - M1 SCALPING")
        logging.info("="*80)
        logging.info(f"Strategy: {self.config['strategy']}")
        logging.info(f"Timeframe: M1 (1-minute candles)")
        logging.info(f"Checking every {check_interval} second(s) for new candles")
        logging.info("="*80)
        
        if not self.connect_mt5():
            logging.error("Failed to connect to MT5")
            return
        
        # Print initial state on startup
        logging.info("\nFetching initial data...")
        try:
            df = self.get_historical_data(bars=200)  # Need enough bars for indicators
            if df is not None and len(df) > 0:
                df = self.compute_indicators(df)
                if len(df) > 0:  # Check we have data after indicator calculation
                    latest = df.iloc[-1]
                    
                    logging.info(f"\nCurrent Market State:")
                    logging.info(f"  Time: {latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.info(f"  Close: {latest['close']:.2f}")
                    
                    # Check if indicators exist
                    if 'ema_5' in df.columns:
                        logging.info(f"  EMA 5: {latest['ema_5']:.2f}")
                        logging.info(f"  EMA 12: {latest['ema_12']:.2f}")
                        logging.info(f"  RSI: {latest['rsi']:.2f}")
                        logging.info(f"  ATR: {latest['atr']:.2f}")
                    
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
        
        # Track last status message time
        last_status_time = time.time()
        status_interval = 60  # Print status every 60 seconds when waiting
        
        try:
            while True:
                try:
                    # CONTINUOUS PROFIT PROTECTION - Check every second (not just on candle close)
                    # This catches intra-candle profit swings like +$30 -> -$10 -> +$33
                    self.check_profit_protection_continuous()
                    
                    # CHECK FOR MT5-CLOSED POSITIONS - Detect stop loss hits
                    self.check_mt5_closed_positions()
                    
                    # Check for new M1 candle
                    has_new, candle_time = self.has_new_candle()
                    
                    if has_new:
                        logging.info(f"\n{'='*60}")
                        logging.info(f"NEW M1 CANDLE: {candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        logging.info(f"{'='*60}")
                        
                        # Run trading logic
                        self.trading_logic()
                        
                        # Reset status timer after processing candle
                        last_status_time = time.time()
                    else:
                        # No new candle yet - print periodic status
                        current_time = time.time()
                        if current_time - last_status_time >= status_interval:
                            # Get latest data to show we're alive
                            df = self.get_historical_data(bars=10)
                            if df is not None and len(df) > 0:
                                latest = df.iloc[-1]
                                latest_time = latest['time']
                                latest_close = latest['close']
                                
                                # Check if market is likely closed
                                now = pd.Timestamp.now()
                                age_minutes = (now - latest_time).total_seconds() / 60
                                
                                if age_minutes > 10:
                                    logging.info(f"[WAITING] Market closed - last data: {latest_time.strftime('%Y-%m-%d %H:%M')}, {age_minutes:.0f}min ago")
                                else:
                                    logging.info(f"[MONITORING] Waiting for new candle - current: {latest_time.strftime('%H:%M')}, price: {latest_close:.2f}")
                            else:
                                logging.info(f"Waiting for new candle...")
                            
                            last_status_time = current_time
                    
                    # Sleep for check interval
                    time.sleep(check_interval)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logging.error(f"Error in trading loop: {e}", exc_info=True)
                    time.sleep(check_interval)
        
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
            logging.info("\n" + self.generate_report())
        finally:
            self.disconnect_mt5()
            logging.info("Bot shutdown complete")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Gold Trading Bot - M1 Scalping')
    parser.add_argument('--config', default='config/m1_params.json',
                       help='Path to configuration file')
    parser.add_argument('--interval', type=int, default=1,
                       help='Check interval in seconds (default: 1)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run in dry-run mode (no actual trades)')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logging.warning("DRY-RUN MODE: No actual trades will be placed")
    
    bot = LiveTradingBot(config_path=args.config)
    bot.run(check_interval=args.interval)

if __name__ == "__main__":
    main()
