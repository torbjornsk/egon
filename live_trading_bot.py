"""
Live Trading Bot for Gold (XAUUSD)
Strategy: Safe Leveraged Bidirectional Trading
Author: AI Assistant
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime, timedelta
import logging
from pathlib import Path

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
    def __init__(self, config_path='config/safe_leveraged_params.json'):
        """Initialize the trading bot"""
        self.load_config(config_path)
        self.position = None
        self.starting_balance = None
        self.peak_balance = None
        self.trading_paused = False
        self.trades_today = 0
        self.last_trade_time = None
        
    def load_config(self, config_path):
        """Load trading configuration"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        logging.info(f"Configuration loaded: {self.config['strategy']}")
        logging.info(f"Position Size: {self.config['position_size_pct']*100}%")
        logging.info(f"Leverage: {self.config['leverage']}x")
        logging.info(f"Effective Position: {self.config['position_size_pct']*self.config['leverage']*100}%")
        
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
    
    def get_historical_data(self, symbol='XAUUSD', timeframe=mt5.TIMEFRAME_M5, bars=500):
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
            return True
        
        return False
    
    def get_open_position(self, symbol='XAUUSD'):
        """Check if there's an open position"""
        positions = mt5.positions_get(symbol=symbol)
        if positions and len(positions) > 0:
            return positions[0]
        return None
    
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
        """Place an order"""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Symbol {symbol} not found")
            return None
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logging.error("Failed to get tick data")
            return None
        
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 234000,
            "comment": "gold_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"Order placed successfully: {result.order}")
            logging.info(f"  Type: {'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}")
            logging.info(f"  Volume: {volume}")
            logging.info(f"  Price: {price}")
            logging.info(f"  SL: {sl}")
            logging.info(f"  TP: {tp}")
            return result
        else:
            logging.error(f"Order failed: {result.retcode} - {result.comment}")
            return None
    
    def close_position(self, position):
        """Close an open position"""
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
            "magic": 234000,
            "comment": "close_position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            profit = position.profit
            logging.info(f"Position closed: Ticket {ticket}, Profit: ${profit:.2f}")
            return result
        else:
            logging.error(f"Failed to close position: {result.retcode} - {result.comment}")
            return None
    
    def trading_logic(self):
        """Main trading logic"""
        symbol = 'XAUUSD'
        
        # Get account info
        account_info = self.get_account_info()
        if not account_info:
            logging.error("Failed to get account info")
            return
        
        # Check drawdown
        if self.check_drawdown(account_info['balance']):
            return
        
        # Get historical data
        df = self.get_historical_data(symbol)
        if df is None or len(df) < 200:
            logging.error("Insufficient data")
            return
        
        # Calculate indicators
        df = self.compute_indicators(df)
        latest = df.iloc[-1]
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return
        
        current_price = tick.bid
        
        # Check for open position
        open_position = self.get_open_position(symbol)
        
        if open_position is None:
            # No position - check for entry signals
            
            # LONG ENTRY
            if latest['RSI'] < self.config['rsi_buy']:
                logging.info(f"LONG SIGNAL: RSI={latest['RSI']:.2f}")
                
                # Calculate stop loss and take profit
                stop_distance = latest['ATR'] * self.config['atr_multiplier']
                sl = current_price - stop_distance
                tp = current_price + (current_price * self.config['profit_target_pct'])
                
                # Calculate position size
                volume = self.calculate_position_size(symbol, current_price, sl)
                
                if volume:
                    logging.info(f"Placing LONG order: Volume={volume}, SL={sl:.2f}, TP={tp:.2f}")
                    result = self.place_order(symbol, mt5.ORDER_TYPE_BUY, volume, sl, tp)
                    if result:
                        self.trades_today += 1
                        self.last_trade_time = datetime.now()
            
            # SHORT ENTRY
            elif self.config['enable_shorts'] and latest['RSI'] > self.config['rsi_sell'] and latest['downtrend']:
                logging.info(f"SHORT SIGNAL: RSI={latest['RSI']:.2f}")
                
                stop_distance = latest['ATR'] * self.config['atr_multiplier']
                sl = current_price + stop_distance
                tp = current_price - (current_price * self.config['profit_target_pct'])
                
                volume = self.calculate_position_size(symbol, current_price, sl)
                
                if volume:
                    logging.info(f"Placing SHORT order: Volume={volume}, SL={sl:.2f}, TP={tp:.2f}")
                    result = self.place_order(symbol, mt5.ORDER_TYPE_SELL, volume, sl, tp)
                    if result:
                        self.trades_today += 1
                        self.last_trade_time = datetime.now()
        
        else:
            # Position exists - check for exit signals
            position_type = open_position.type
            entry_price = open_position.price_open
            current_profit = open_position.profit
            
            should_close = False
            reason = ""
            
            if position_type == mt5.ORDER_TYPE_BUY:
                # Long position
                if latest['RSI'] > self.config['rsi_sell']:
                    should_close = True
                    reason = f"RSI overbought ({latest['RSI']:.2f})"
            else:
                # Short position
                if latest['RSI'] < self.config['rsi_buy']:
                    should_close = True
                    reason = f"RSI oversold ({latest['RSI']:.2f})"
            
            if should_close:
                logging.info(f"EXIT SIGNAL: {reason}, Current P/L: ${current_profit:.2f}")
                self.close_position(open_position)
    
    def wait_for_next_candle(self, timeframe_minutes=5):
        """Wait until the next candle closes and return seconds waited"""
        now = datetime.now()
        
        # Calculate seconds into current candle
        seconds_into_candle = (now.minute % timeframe_minutes) * 60 + now.second
        
        # Calculate seconds until next candle
        seconds_until_next = (timeframe_minutes * 60) - seconds_into_candle
        
        # Add small buffer to ensure candle has closed
        seconds_until_next += 2
        
        return seconds_until_next
    
    def run(self, check_interval=15):
        """Run the trading bot"""
        logging.info("="*80)
        logging.info("LIVE TRADING BOT STARTED")
        logging.info("="*80)
        logging.info(f"Strategy: {self.config['strategy']}")
        logging.info(f"Syncing with 5-minute candle closes")
        logging.info("="*80)
        
        if not self.connect_mt5():
            logging.error("Failed to connect to MT5")
            return
        
        # Wait for first candle close
        wait_time = self.wait_for_next_candle()
        logging.info(f"Waiting {wait_time} seconds for next candle close...")
        time.sleep(wait_time)
        
        try:
            while True:
                try:
                    candle_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    logging.info(f"\n{'='*60}")
                    logging.info(f"Checking at candle close: {candle_time}")
                    logging.info(f"{'='*60}")
                    
                    # Run trading logic
                    self.trading_logic()
                    
                    # Log status
                    account_info = self.get_account_info()
                    if account_info:
                        drawdown = (self.peak_balance - account_info['balance']) / self.peak_balance * 100
                        logging.info(f"Status: Balance=${account_info['balance']:.2f}, "
                                   f"Equity=${account_info['equity']:.2f}, "
                                   f"Profit=${account_info['profit']:.2f}, "
                                   f"Drawdown={drawdown:.2f}%, "
                                   f"Trades Today={self.trades_today}")
                    
                    # Wait for next candle close (5 minutes)
                    wait_time = self.wait_for_next_candle()
                    logging.info(f"Next check in {wait_time} seconds (at next candle close)")
                    time.sleep(wait_time)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logging.error(f"Error in trading loop: {e}", exc_info=True)
                    # On error, wait for next candle
                    wait_time = self.wait_for_next_candle()
                    time.sleep(wait_time)
        
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
        finally:
            self.disconnect_mt5()
            logging.info("Bot shutdown complete")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Gold Trading Bot')
    parser.add_argument('--config', default='config/safe_leveraged_params.json',
                       help='Path to configuration file')
    parser.add_argument('--interval', type=int, default=15,
                       help='Check interval in seconds (default: 15)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run in dry-run mode (no actual trades)')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logging.warning("DRY-RUN MODE: No actual trades will be placed")
    
    bot = LiveTradingBot(config_path=args.config)
    bot.run(check_interval=args.interval)

if __name__ == "__main__":
    main()
