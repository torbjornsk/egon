"""
Live Trading Bot for Gold (XAUUSD) - M5 Strategy
Refactored to use BaseTradingBot and M5ScalpingStrategy
"""

import MetaTrader5 as mt5
import argparse
import logging
from datetime import datetime
from src.base_trading_bot import BaseTradingBot
from src.strategies.m5_scalping import M5ScalpingStrategy

class M5TradingBot(BaseTradingBot):
    """M5 scalping bot using base infrastructure"""
    
    def __init__(self, config_path='config/m5_params.json'):
        # Initialize base bot
        super().__init__(
            config_path=config_path,
            magic_number=234000,
            strategy_name='M5 Scalping'
        )
        
        # Initialize strategy
        self.strategy = M5ScalpingStrategy(self.config)
        
        # M5-specific tracking
        self.max_positions = 2
        self.position_open_times = {}
        self.peak_position_profits = {}
        self.cooldown_candles = 2
        self.warmup_candles = 2
        
        # Adjust position size for multiple positions
        base_position_size = self.config['position_size_pct']
        self.config['position_size_pct'] = base_position_size / self.max_positions
        
        logging.info(f"Position Size: {base_position_size*100}% (split into {self.max_positions} positions of {self.config['position_size_pct']*100}% each)")
    
    def get_timeframe(self):
        """Get MT5 timeframe constant"""
        return self.strategy.get_timeframe()
    
    def compute_indicators(self, df):
        """Compute technical indicators using strategy"""
        return self.strategy.compute_indicators(df)
    
    def print_indicators(self, latest, df):
        """Print strategy-specific indicators"""
        self.strategy.print_indicators(latest, df, logging)
    
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
            "magic": self.magic_number,
            "comment": "m5_strategy",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            order_type_str = "LONG" if order_type == mt5.ORDER_TYPE_BUY else "SHORT"
            sl_distance = abs(price - sl)
            tp_distance = abs(tp - price)
            risk_reward = tp_distance / sl_distance if sl_distance > 0 else 0
            
            # Track position
            ticket = result.order
            self.position_open_times[ticket] = datetime.now()
            self.peak_position_profits[ticket] = 0
            
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
    
    def trading_logic(self):
        """Main trading logic"""
        symbol = self.symbol
        
        # Get account info
        account_info = self.get_account_info()
        if not account_info:
            logging.error("Failed to get account info")
            return
        
        # Run safety checks
        self.run_safety_checks()
        
        # If trading is paused, skip
        if self.trading_paused:
            return
        
        # Weekend close protection
        is_weekend_closing, close_reason = self.is_near_weekend_close(minutes_before=30)
        
        # Check for open positions
        open_positions = self.get_open_positions(symbol)
        
        if is_weekend_closing:
            if len(open_positions) > 0:
                logging.warning(f"WEEKEND CLOSE PROTECTION: {close_reason}")
                logging.warning(f"Closing {len(open_positions)} position(s) to avoid weekend gap risk")
                for pos in open_positions:
                    logging.warning(f"Position ticket {pos.ticket}: P/L ${pos.profit:.2f}")
                    self.close_position(pos, emergency=False)
                return
            else:
                logging.info(f"Weekend close approaching - no new positions will be opened")
                return
        
        # Get historical data
        df = self.get_historical_data(symbol, bars=500)
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
        
        # Initialize position tracking for existing positions
        for pos in open_positions:
            if pos.ticket not in self.peak_position_profits:
                self.peak_position_profits[pos.ticket] = max(0, pos.profit)
                self.position_open_times[pos.ticket] = datetime.fromtimestamp(pos.time)
        
        # Check for new entry if we have room
        if len(open_positions) < self.max_positions:
            # Check cooldown period
            can_enter = True
            if self.last_close_time is not None:
                time_since_close = datetime.now() - self.last_close_time
                cooldown_seconds = self.warmup_candles * 5 * 60
                
                if time_since_close.total_seconds() < cooldown_seconds:
                    remaining = cooldown_seconds - time_since_close.total_seconds()
                    logging.info(f"Warm-up/cooldown active: {remaining/60:.1f} minutes remaining")
                    can_enter = False
            
            if can_enter:
                # Check for entry signal
                signal_type, sl, tp = self.strategy.check_entry_signal(df, current_price)
                
                if signal_type:
                    logging.info(f"{signal_type} SIGNAL: RSI={latest['RSI']:.2f}")
                    
                    # Calculate position size
                    volume = self.calculate_position_size(symbol, current_price, sl)
                    
                    if volume:
                        order_type = mt5.ORDER_TYPE_BUY if signal_type == 'LONG' else mt5.ORDER_TYPE_SELL
                        logging.info(f"Placing {signal_type} order: Volume={volume}, SL={sl:.2f}, TP={tp:.2f}")
                        result = self.place_order(symbol, order_type, volume, sl, tp)
                        if result:
                            self.trades_today += 1
                            self.last_trade_time = datetime.now()
        
        # Check exit signals for all open positions
        for open_position in open_positions:
            should_close, reason = self.strategy.check_exit_signal(
                open_position, df, self.position_open_times, 
                self.peak_position_profits, logging
            )
            
            if should_close:
                logging.info(f"EXIT SIGNAL (ticket {open_position.ticket}): {reason}, Current P/L: ${open_position.profit:.2f}")
                self.close_position(open_position)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Live Gold Trading Bot - M5 Strategy')
    parser.add_argument('--config', default='config/m5_params.json',
                       help='Path to configuration file')
    parser.add_argument('--interval', type=int, default=15,
                       help='Check interval in seconds (default: 15)')
    
    args = parser.parse_args()
    
    bot = M5TradingBot(config_path=args.config)
    bot.run(check_interval=args.interval)

if __name__ == "__main__":
    main()
