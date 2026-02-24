import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import logging

class MT5Connector:
    def __init__(self, account=None, password=None, server=None):
        self.account = account
        self.password = password
        self.server = server
        self.connected = False
        
    def connect(self):
        if not mt5.initialize():
            logging.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        
        if self.account and self.password and self.server:
            authorized = mt5.login(self.account, password=self.password, server=self.server)
            if not authorized:
                logging.error(f"MT5 login failed: {mt5.last_error()}")
                return False
        
        self.connected = True
        logging.info("MT5 connected successfully")
        return True
    
    def disconnect(self):
        mt5.shutdown()
        self.connected = False
        
    def get_historical_data(self, symbol, timeframe, start_date, end_date):
        if not self.connected:
            raise ConnectionError("Not connected to MT5")
        
        # Ensure symbol is visible/selected
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Symbol {symbol} not found")
            return None
        
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logging.error(f"Failed to select symbol {symbol}")
                return None
        
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15, 'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1
        }
        
        # Request maximum available bars (50000 is the limit for M5)
        # This gets the most recent bars working backwards
        rates = mt5.copy_rates_from_pos(symbol, timeframe_map[timeframe], 0, 50000)
        
        if rates is None or len(rates) == 0:
            logging.error(f"Failed to get data: {mt5.last_error()}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Filter to requested date range if specified
        if start_date:
            df = df[df['time'] >= start_date]
        if end_date:
            df = df[df['time'] <= end_date]
        
        return df
    
    def place_order(self, symbol, order_type, volume, price=None, sl=None, tp=None, magic=234000):
        if not self.connected:
            raise ConnectionError("Not connected to MT5")
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Symbol {symbol} not found")
            return None
        
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                logging.error(f"Failed to select {symbol}")
                return None
        
        point = symbol_info.point
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "magic": magic,
            "comment": "gold_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if price:
            request["price"] = price
        else:
            request["price"] = mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
        
        if sl:
            request["sl"] = sl
        if tp:
            request["tp"] = tp
        
        result = mt5.order_send(request)
        return result
    
    def get_account_info(self):
        if not self.connected:
            raise ConnectionError("Not connected to MT5")
        
        account_info = mt5.account_info()
        if account_info is None:
            return None
        
        return {
            'balance': account_info.balance,
            'equity': account_info.equity,
            'margin': account_info.margin,
            'free_margin': account_info.margin_free,
            'profit': account_info.profit
        }
    
    def get_open_positions(self, symbol=None):
        if not self.connected:
            raise ConnectionError("Not connected to MT5")
        
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        return list(positions) if positions else []
