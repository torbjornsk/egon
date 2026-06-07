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
M15_MAGIC = 234015
LZ_MAGIC = 234100
M1S_MAGIC = 234101
M15S_MAGIC = 234115
M5S_MAGIC = 234050
TICK_MAGIC = 234200
MOM_MAGIC = 234300


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
        tf_map = {'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15}
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, bars)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = mt5_series_to_local(df['time'])
        return df

    def get_market_overview(self) -> dict:
        """Get multi-timeframe indicators for the market dashboard.

        Returns a dict with keys 'M1', 'M5', 'M15' each containing:
        rsi, atr, ema_fast, ema_slow, trend, spread, bid, ask
        """
        from src.core.indicators import compute_indicators
        from src.core.config import TradingConfig

        config = TradingConfig()  # Default RSI period 14 for dashboard
        result = {}
        tf_map = {
            'M1': (mt5.TIMEFRAME_M1, 200),
            'M5': (mt5.TIMEFRAME_M5, 200),
            'M15': (mt5.TIMEFRAME_M15, 200),
        }

        for label, (tf, bars) in tf_map.items():
            try:
                rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, bars)
                if rates is None or len(rates) < 100:
                    result[label] = None
                    continue
                df = pd.DataFrame(rates)
                df = compute_indicators(df, config)
                latest = df.iloc[-1]
                result[label] = {
                    'rsi': float(latest['RSI']),
                    'atr': float(latest['ATR']),
                    'ema_fast': float(latest['ema_fast']),
                    'ema_slow': float(latest['ema_slow']),
                    'uptrend': bool(latest['uptrend']),
                    'close': float(latest['close']),
                }
            except Exception as e:
                logger.error(f"Market overview {label} error: {e}")
                result[label] = None

        # Spread and tick info
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick:
            result['spread'] = tick.ask - tick.bid
            result['bid'] = tick.bid
            result['ask'] = tick.ask
        else:
            result['spread'] = 0
            result['bid'] = 0
            result['ask'] = 0

        return result

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
            elif entry_deal.magic == M15_MAGIC:
                bot = 'M15'
            elif entry_deal.magic == LZ_MAGIC:
                bot = 'LZ'
            elif entry_deal.magic == M5S_MAGIC:
                bot = 'M5S'
            elif entry_deal.magic == M1S_MAGIC:
                bot = 'M1S'
            elif entry_deal.magic == M15S_MAGIC:
                bot = 'M15S'
            elif entry_deal.magic == TICK_MAGIC:
                bot = 'TICK'
            elif entry_deal.magic == MOM_MAGIC:
                bot = 'MOM'
            else:
                continue
            direction = 'BUY' if entry_deal.type == mt5.DEAL_TYPE_BUY else 'SELL'
            # Infer exit reason from MT5 deal reason code
            if exit_deal.reason == 4:  # DEAL_REASON_SL
                exit_reason = 'Stop loss'
            elif exit_deal.reason == 5:  # DEAL_REASON_TP
                exit_reason = 'Take profit'
            elif exit_deal.reason == 3:  # DEAL_REASON_CLIENT (manual or bot close)
                exit_reason = 'Bot/Manual close'
            else:
                exit_reason = 'MT5 close'
            result.append({
                'ticket': exit_deal.ticket, 'position_id': pid, 'bot': bot,
                'type': direction, 'volume': entry_deal.volume,
                'entry_price': entry_deal.price, 'exit_price': exit_deal.price,
                'profit': exit_deal.profit,
                'entry_time': mt5_to_local(entry_deal.time),
                'exit_time': mt5_to_local(exit_deal.time),
                'exit_reason': exit_reason,
            })
        result.sort(key=lambda x: x['exit_time'], reverse=True)
        return result[:100]
