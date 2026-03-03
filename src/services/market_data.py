"""Market data service for GUI -- account, chart, trade history."""
import logging
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd
from src.core.timezone import MT5_TZ, LOCAL_TZ, mt5_to_local, mt5_series_to_local

logger = logging.getLogger(__name__)
SYMBOL = 'XAUUSD.p'
M5_MAGIC = 234000
M1_MAGIC = 234001


class MarketDataService:
    """Provides shared market data for the GUI (account, chart, history)."""

    def __init__(self):
        self.connected = False

    def connect(self) -> bool:
        if not mt5.initialize():
            logger.error("MT5 init failed: %s", mt5.last_error())
            return False
        self.connected = True
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def get_account_info(self) -> dict:
        info = mt5.account_info()
        if not info:
            return {'balance': 0, 'equity': 0, 'margin': 0, 'free_margin': 0, 'profit': 0}
        return {
            'balance': info.balance, 'equity': info.equity,
            'margin': info.margin, 'free_margin': info.margin_free,
            'profit': info.profit,
        }

    def get_price(self) -> float:
        tick = mt5.symbol_info_tick(SYMBOL)
        return tick.bid if tick else 0.0

    def get_chart_data(self, timeframe='M5', bars=50):
        """Get OHLCV data for chart rendering. Timestamps converted to local."""
        tf = mt5.TIMEFRAME_M1 if timeframe == 'M1' else mt5.TIMEFRAME_M5
        rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, bars)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = mt5_series_to_local(df['time'])
        return df

    def get_trade_history(self, days=7):
        """Get closed trades for both M1 and M5 bots."""
        # Add 3h buffer to now() so we never miss recent deals due to
        # timezone offset between local time and MT5 internal time.
        # This is what the old GUI did and it worked reliably.
        from_date = datetime.now() - timedelta(days=days)
        to_date = datetime.now() + timedelta(hours=3)
        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None:
            return []
        positions = {}
        for deal in deals:
            pid = deal.position_id
            if pid == 0:
                continue
            # Filter to our symbol
            if SYMBOL not in deal.symbol:
                continue
            if deal.entry == mt5.DEAL_ENTRY_IN:
                positions.setdefault(pid, {})['entry'] = deal
            elif deal.entry == mt5.DEAL_ENTRY_OUT:
                positions.setdefault(pid, {})['exit'] = deal
        result = []
        for pid, pair in positions.items():
            if 'entry' not in pair or 'exit' not in pair:
                continue
            entry_deal = pair['entry']
            exit_deal = pair['exit']
            if entry_deal.magic == M1_MAGIC:
                bot = 'M1'
            elif entry_deal.magic == M5_MAGIC:
                bot = 'M5'
            else:
                continue
            direction = 'BUY' if entry_deal.type == mt5.DEAL_TYPE_BUY else 'SELL'
            result.append({
                'ticket': exit_deal.ticket, 'position_id': pid, 'bot': bot,
                'type': direction, 'volume': entry_deal.volume,
                'entry_price': entry_deal.price, 'exit_price': exit_deal.price,
                'profit': exit_deal.profit,
                'entry_time': mt5_to_local(entry_deal.time),
                'exit_time': mt5_to_local(exit_deal.time),
            })
        result.sort(key=lambda x: x['exit_time'], reverse=True)
        return result[:100]
