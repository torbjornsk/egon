import json
import logging
import time
from datetime import datetime, timedelta
import MetaTrader5 as mt5
from mt5_connector import MT5Connector
from risk_management import RiskManager
from strategies.scalping import ScalpingStrategy

class GoldTradingBot:
    def __init__(self, trading_config_path='config/trading_params.json', 
                 bot_config_path='config/bot_config.json'):
        
        # Load configurations
        with open(trading_config_path, 'r') as f:
            self.trading_config = json.load(f)
        
        with open(bot_config_path, 'r') as f:
            self.bot_config = json.load(f)
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.bot_config['logging_level']),
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Initialize components
        self.mt5 = MT5Connector(
            account=self.bot_config.get('account_id'),
            password=self.bot_config.get('password'),
            server=self.bot_config.get('server')
        )
        
        self.risk_manager = RiskManager(self.trading_config)
        
        # Initialize strategy
        strategy_params = self.trading_config[self.trading_config['strategy']]
        self.strategy = ScalpingStrategy(strategy_params)
        
        self.symbol = self.trading_config['symbol']
        self.timeframe = self.trading_config['timeframe']
        self.is_running = False
        
    def start(self):
        """Start the trading bot"""
        if not self.mt5.connect():
            logging.error("Failed to connect to MT5")
            return
        
        logging.info(f"Bot started in {self.bot_config['mode']} mode")
        self.is_running = True
        
        # Reset daily tracking
        account_info = self.mt5.get_account_info()
        self.risk_manager.reset_daily_tracking(account_info['balance'])
        
        try:
            while self.is_running:
                self.trading_loop()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
        finally:
            self.stop()
    
    def trading_loop(self):
        """Main trading logic"""
        try:
            # Get account info
            account_info = self.mt5.get_account_info()
            if account_info is None:
                logging.error("Failed to get account info")
                return
            
            # Check daily loss limit
            if self.risk_manager.check_daily_loss_limit(account_info['balance']):
                logging.warning("Daily loss limit reached. Stopping trading for today.")
                return
            
            # Get current positions
            open_positions = self.mt5.get_open_positions(self.symbol)
            
            # Check if we can open new positions
            if not self.risk_manager.can_open_position(len(open_positions)):
                logging.info(f"Max positions reached: {len(open_positions)}")
                return
            
            # Get recent data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            data = self.mt5.get_historical_data(self.symbol, self.timeframe, start_date, end_date)
            
            if data is None or len(data) < 50:
                logging.warning("Insufficient data for analysis")
                return
            
            # Generate signals
            signals_df = self.strategy.generate_signals(data)
            latest_signal = signals_df.iloc[-1]
            
            # Execute trade if signal present
            if latest_signal['signal'] != 0:
                self.execute_trade(latest_signal, account_info)
            
        except Exception as e:
            logging.error(f"Error in trading loop: {e}")
    
    def execute_trade(self, signal, account_info):
        """Execute a trade based on signal"""
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            logging.error(f"Failed to get symbol info for {self.symbol}")
            return
        
        # Calculate position size
        sl_distance_pips = signal['sl_distance'] / symbol_info.point
        position_size = self.risk_manager.calculate_position_size(
            account_info['balance'],
            sl_distance_pips,
            symbol_info
        )
        
        # Determine order type
        if signal['signal'] == 1:  # Buy
            order_type = mt5.ORDER_TYPE_BUY
            entry_price = mt5.symbol_info_tick(self.symbol).ask
            sl = entry_price - signal['sl_distance']
            tp = entry_price + signal['tp_distance']
        else:  # Sell
            order_type = mt5.ORDER_TYPE_SELL
            entry_price = mt5.symbol_info_tick(self.symbol).bid
            sl = entry_price + signal['sl_distance']
            tp = entry_price - signal['tp_distance']
        
        # Place order
        logging.info(f"Placing {('BUY' if signal['signal'] == 1 else 'SELL')} order: "
                    f"Size={position_size}, Entry={entry_price}, SL={sl}, TP={tp}")
        
        result = self.mt5.place_order(
            symbol=self.symbol,
            order_type=order_type,
            volume=position_size,
            sl=sl,
            tp=tp,
            magic=self.bot_config['magic_number']
        )
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"Order executed successfully: {result.order}")
        else:
            logging.error(f"Order failed: {result}")
    
    def stop(self):
        """Stop the trading bot"""
        self.is_running = False
        self.mt5.disconnect()
        logging.info("Bot stopped")

if __name__ == "__main__":
    bot = GoldTradingBot()
    bot.start()
