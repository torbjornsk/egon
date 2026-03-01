"""
Live Trading Bot for Gold (XAUUSD) - Trend Following
Strategy: Multi-timeframe trend following with sentiment filter
Timeframes: H4 for trend, H1 for entry
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime, timedelta
import logging
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent))

from src.strategies.trend_following import TrendFollowingStrategy
from src.integrations.alpha_vantage import AlphaVantageSentiment, ManualSentiment
from src.integrations.mrktedge_scraper import MRKTedgeScraper

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot_trend.log'),
        logging.StreamHandler()
    ]
)

class TrendTradingBot:
    def __init__(self, config_path='config/trend_params.json'):
        """Initialize the trend trading bot"""
        self.magic_number = 234002  # Unique magic number for trend bot
        self.symbol = 'XAUUSD.p'
        self.timeframe = mt5.TIMEFRAME_H1
        self.positions = []
        self.load_config(config_path)
        self.max_positions = self.config.get('max_positions', 2)
        
        # Initialize strategy
        self.strategy = TrendFollowingStrategy(self.config)
        
        # Initialize sentiment analyzer
        self._init_sentiment()
        
        # Safety mechanisms
        self.starting_balance = None
        self.peak_balance = None
        self.trading_paused = False
        self.pause_reason = None
        self.consecutive_losses = 0
        self.max_consecutive_losses = 8
        self.daily_loss_limit_pct = 0.15
        self.emergency_equity_threshold_pct = 0.50
        
        # Tracking
        self.trade_log = []
        self.session_start = datetime.now()
        self.last_signal_check = None
        self.check_interval_minutes = 60  # Check for signals every hour
        
    def load_config(self, config_path):
        """Load trading configuration"""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        logging.info(f"Configuration loaded: {self.config['strategy']}")
        logging.info(f"Position Size: {self.config['position_size_pct']*100}%")
        logging.info(f"Leverage: {self.config['leverage']}x")
        logging.info(f"Max Positions: {self.config.get('max_positions', 2)}")
        
    def _init_sentiment(self):
        """Initialize sentiment analyzer based on config"""
        use_sentiment = self.config.get('use_sentiment_filter', False)
        
        if not use_sentiment:
            self.sentiment = None
            logging.info("Sentiment filter: DISABLED")
            return
        
        sentiment_source = self.config.get('sentiment_source', 'manual')
        
        if sentiment_source == 'mrktedge':
            self.sentiment = MRKTedgeScraper()
            logging.info("Sentiment filter: MRKTedge ENABLED")
        elif sentiment_source == 'alpha_vantage':
            api_key = self.config.get('alpha_vantage_api_key', '')
            if api_key:
                self.sentiment = AlphaVantageSentiment(api_key)
                logging.info("Sentiment filter: Alpha Vantage ENABLED")
            else:
                logging.warning("Alpha Vantage API key not set - using manual sentiment")
                self.sentiment = ManualSentiment()
        else:
            self.sentiment = ManualSentiment()
            logging.info("Sentiment filter: Manual ENABLED")
    
    def connect_mt5(self):
        """Connect to MetaTrader5"""
        if not mt5.initialize():
            logging.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        
        account_info = mt5.account_info()
        if account_info:
            logging.info(f"Connected to MT5")
            logging.info(f"Account: {account_info.login}")
            logging.info(f"Balance: ${account_info.balance:.2f}")
            
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
        account = mt5.account_info()
        if account is None:
            return None
        
        return {
            'balance': account.balance,
            'equity': account.equity,
            'margin': account.margin,
            'free_margin': account.margin_free,
            'margin_level': account.margin_level if account.margin > 0 else 0,
            'profit': account.profit
        }
    
    def get_open_positions(self):
        """Get all open positions for this bot"""
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None:
            return []
        
        # Filter by magic number
        return [p for p in positions if p.magic == self.magic_number]
    
    def get_market_data(self, bars=250):
        """Get H1 market data"""
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, bars)
        if rates is None or len(rates) == 0:
            logging.error(f"Failed to get market data: {mt5.last_error()}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    def check_safety_mechanisms(self):
        """Check if trading should be paused due to safety triggers"""
        account = self.get_account_info()
        if not account:
            return
        
        # Emergency equity threshold
        equity_pct = account['equity'] / self.starting_balance
        if equity_pct < self.emergency_equity_threshold_pct:
            self.pause_trading(f"EMERGENCY: Equity below {self.emergency_equity_threshold_pct*100}%")
            self.close_all_positions("Emergency equity threshold")
            return
        
        # Daily loss limit
        daily_loss_pct = (self.starting_balance - account['balance']) / self.starting_balance
        if daily_loss_pct > self.daily_loss_limit_pct:
            self.pause_trading(f"Daily loss limit exceeded: {daily_loss_pct*100:.1f}%")
            return
        
        # Consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.pause_trading(f"Max consecutive losses: {self.consecutive_losses}")
            return
        
        # Update peak balance
        if account['balance'] > self.peak_balance:
            self.peak_balance = account['balance']
    
    def pause_trading(self, reason):
        """Pause trading"""
        if not self.trading_paused:
            self.trading_paused = True
            self.pause_reason = reason
            logging.warning(f"TRADING PAUSED: {reason}")
    
    def resume_trading(self):
        """Resume trading"""
        if self.trading_paused:
            self.trading_paused = False
            self.pause_reason = None
            self.consecutive_losses = 0
            logging.info("Trading RESUMED")
    
    def check_for_signals(self):
        """Check for entry signals"""
        # Don't check too frequently
        if self.last_signal_check:
            time_since_check = (datetime.now() - self.last_signal_check).total_seconds() / 60
            if time_since_check < self.check_interval_minutes:
                return
        
        self.last_signal_check = datetime.now()
        
        # Check if we can open more positions
        open_positions = self.get_open_positions()
        if len(open_positions) >= self.max_positions:
            logging.info(f"Max positions reached ({len(open_positions)}/{self.max_positions})")
            return
        
        # Get market data
        data = self.get_market_data()
        if data is None:
            return
        
        # Generate signals
        signals = self.strategy.generate_signals(data)
        last_signal = signals.iloc[-1]
        
        if last_signal['signal'] == 0:
            return
        
        # Determine signal type
        signal_type = 'LONG' if last_signal['signal'] == 1 else 'SHORT'
        h4_trend = last_signal['h4_trend']
        
        logging.info(f"Signal detected: {signal_type} (H4: {h4_trend})")
        
        # Check sentiment filter
        if self.sentiment:
            should_trade, confidence = self.sentiment.should_trade(signal_type)
            if not should_trade:
                logging.info(f"Signal filtered by sentiment")
                return
            
            logging.info(f"Sentiment check passed (confidence: {confidence:.2f})")
        
        # Execute trade
        self.execute_trade(last_signal, signal_type)
    
    def execute_trade(self, signal_data, signal_type):
        """Execute a trade based on signal"""
        account = self.get_account_info()
        if not account:
            return
        
        # Calculate position size
        base_size = self.config['position_size_pct']
        
        # Adjust for sentiment if enabled
        if self.sentiment:
            base_size = self.sentiment.adjust_position_size(base_size)
        
        # Calculate lot size
        balance = account['balance']
        leverage = self.config['leverage']
        position_value = balance * base_size * leverage
        
        # Get current price
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            logging.error("Failed to get tick data")
            return
        
        price = tick.ask if signal_type == 'LONG' else tick.bid
        
        # Calculate lot size (gold: 1 lot = 100 oz)
        contract_size = 100
        lot_size = position_value / (price * contract_size)
        lot_size = round(lot_size, 2)  # Round to 2 decimals
        
        # Minimum lot size
        if lot_size < 0.01:
            logging.warning(f"Lot size too small: {lot_size}")
            return
        
        # Calculate SL and TP
        sl_distance = signal_data['sl_distance']
        tp_distance = signal_data['tp_distance']
        
        if signal_type == 'LONG':
            sl = price - sl_distance
            tp = price + tp_distance
            order_type = mt5.ORDER_TYPE_BUY
        else:
            sl = price + sl_distance
            tp = price - tp_distance
            order_type = mt5.ORDER_TYPE_SELL
        
        # Prepare order
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': self.symbol,
            'volume': lot_size,
            'type': order_type,
            'price': price,
            'sl': sl,
            'tp': tp,
            'magic': self.magic_number,
            'comment': f'Trend_{signal_type}',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Order failed: {result.retcode} - {result.comment}")
            return
        
        logging.info(f"✓ {signal_type} order executed: {lot_size} lots at {price:.2f}")
        logging.info(f"  SL: {sl:.2f}, TP: {tp:.2f}")
        
        # Log trade
        self.trade_log.append({
            'time': datetime.now(),
            'type': signal_type,
            'price': price,
            'lots': lot_size,
            'sl': sl,
            'tp': tp,
            'ticket': result.order
        })
    
    def check_exit_signals(self):
        """Check if any positions should be exited"""
        positions = self.get_open_positions()
        if not positions:
            return
        
        # Get current market data
        data = self.get_market_data()
        if data is None:
            return
        
        for position in positions:
            should_exit, reason = self.strategy.check_exit_signals(position, data)
            
            if should_exit:
                self.close_position(position, reason)
    
    def close_position(self, position, reason="Manual close"):
        """Close a position"""
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return
        
        # Determine close price
        close_price = tick.bid if position.type == 0 else tick.ask
        
        # Prepare close request
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': self.symbol,
            'volume': position.volume,
            'type': mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
            'position': position.ticket,
            'price': close_price,
            'magic': self.magic_number,
            'comment': f'Close: {reason}',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Close failed: {result.retcode}")
            return
        
        # Calculate profit
        profit = position.profit
        profit_pct = (profit / self.starting_balance) * 100
        
        logging.info(f"✓ Position closed: {position.ticket}")
        logging.info(f"  Reason: {reason}")
        logging.info(f"  Profit: ${profit:.2f} ({profit_pct:.2f}%)")
        
        # Update consecutive losses
        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Cleanup strategy tracking
        self.strategy.cleanup_position(position.ticket)
    
    def close_all_positions(self, reason="Close all"):
        """Close all open positions"""
        positions = self.get_open_positions()
        for position in positions:
            self.close_position(position, reason)
    
    def print_status(self):
        """Print current bot status"""
        account = self.get_account_info()
        positions = self.get_open_positions()
        
        print("\n" + "="*60)
        print(f"TREND BOT STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        if account:
            profit = account['balance'] - self.starting_balance
            profit_pct = (profit / self.starting_balance) * 100
            
            print(f"Balance: ${account['balance']:.2f} ({profit:+.2f}, {profit_pct:+.2f}%)")
            print(f"Equity: ${account['equity']:.2f}")
            print(f"Margin: ${account['margin']:.2f} / ${account['free_margin']:.2f} free")
        
        print(f"\nPositions: {len(positions)}/{self.max_positions}")
        for pos in positions:
            pos_type = "LONG" if pos.type == 0 else "SHORT"
            print(f"  {pos_type} {pos.volume} lots @ {pos.price_open:.2f} | P/L: ${pos.profit:.2f}")
        
        if self.trading_paused:
            print(f"\n⚠️  TRADING PAUSED: {self.pause_reason}")
        
        print("="*60 + "\n")
    
    def run(self):
        """Main bot loop"""
        if not self.connect_mt5():
            return
        
        logging.info("="*60)
        logging.info("TREND FOLLOWING BOT STARTED")
        logging.info("="*60)
        logging.info(f"Symbol: {self.symbol}")
        logging.info(f"Timeframe: H1 (entry) / H4 (trend)")
        logging.info(f"Strategy: {self.config['strategy']}")
        logging.info(f"Check interval: {self.check_interval_minutes} minutes")
        logging.info("="*60)
        
        # Print initial state on startup
        logging.info("\nFetching initial data...")
        h1_data = self.get_h1_data()
        h4_data = self.get_h4_data()
        
        if h1_data is not None and len(h1_data) > 0:
            latest_h1 = h1_data.iloc[-1]
            logging.info(f"\nCurrent Market State (H1):")
            logging.info(f"  Time: {latest_h1['time'].strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"  Close: {latest_h1['close']:.2f}")
            logging.info(f"  EMA 20: {latest_h1['ema_20']:.2f}")
            logging.info(f"  EMA 50: {latest_h1['ema_50']:.2f}")
            logging.info(f"  RSI: {latest_h1['rsi']:.2f}")
            logging.info(f"  MACD: {latest_h1['macd']:.3f}")
            
            # Check if data is fresh
            now = pd.Timestamp.now()
            age_minutes = (now - latest_h1['time']).total_seconds() / 60
            
            if age_minutes > 60:
                logging.info(f"\n  Market Status: CLOSED (last data {age_minutes:.0f} minutes ago)")
                logging.info(f"  Waiting for market to open...")
            else:
                logging.info(f"\n  Market Status: OPEN")
                logging.info(f"  Monitoring for signals...")
        
        if h4_data is not None and len(h4_data) > 0:
            latest_h4 = h4_data.iloc[-1]
            logging.info(f"\nH4 Trend:")
            logging.info(f"  EMA 50: {latest_h4['ema_50']:.2f}")
            logging.info(f"  EMA 200: {latest_h4['ema_200']:.2f}")
            logging.info(f"  ADX: {latest_h4['adx']:.2f}")
            
            if latest_h4['ema_50'] > latest_h4['ema_200'] and latest_h4['adx'] > 25:
                logging.info(f"  Trend: UPTREND")
            elif latest_h4['ema_50'] < latest_h4['ema_200'] and latest_h4['adx'] > 25:
                logging.info(f"  Trend: DOWNTREND")
            else:
                logging.info(f"  Trend: NO CLEAR TREND")
        
        logging.info("\n" + "="*60)
        
        try:
            iteration = 0
            while True:
                iteration += 1
                
                # Print status every 10 iterations (50 minutes)
                if iteration % 10 == 0:
                    self.print_status()
                else:
                    # Show we're alive every iteration
                    h1_data = self.get_h1_data()
                    if h1_data is not None and len(h1_data) > 0:
                        latest = h1_data.iloc[-1]
                        latest_time = latest['time']
                        latest_close = latest['close']
                        
                        # Check if market is likely closed
                        now = pd.Timestamp.now()
                        age_minutes = (now - latest_time).total_seconds() / 60
                        
                        if age_minutes > 60:
                            logging.info(f"[WAITING] Market closed - last H1: {latest_time.strftime('%Y-%m-%d %H:%M')}, {age_minutes:.0f}min ago")
                        else:
                            logging.info(f"[MONITORING] H1: {latest_time.strftime('%H:%M')}, price: {latest_close:.2f}")
                
                # Check safety mechanisms
                self.check_safety_mechanisms()
                
                if not self.trading_paused:
                    # Check for exit signals
                    self.check_exit_signals()
                    
                    # Check for entry signals
                    self.check_for_signals()
                
                # Sleep for 5 minutes
                time.sleep(300)
                
        except KeyboardInterrupt:
            logging.info("\nShutting down bot...")
            self.print_status()
            self.disconnect_mt5()
        except Exception as e:
            logging.error(f"Error in main loop: {e}", exc_info=True)
            self.disconnect_mt5()


if __name__ == '__main__':
    bot = TrendTradingBot()
    bot.run()
