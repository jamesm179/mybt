import logging
import pandas as pd
from binance.um_futures import UMFutures as BinanceFuturesClient
from exchanges.base import BaseExchangeAPI

class BinanceAPI(BaseExchangeAPI):
    """API client for Binance Futures."""
    def __init__(self, credentials, display, db_manager, config):
        super().__init__(credentials, display, db_manager, config)
        self.client = BinanceFuturesClient(key=self.key, secret=self.secret)

    def get_historical_data(self, pair, interval, limit=200, force_fresh=False):
        # Futures symbols are typically just 'BTCUSDT'
        formatted_pair = self._format_pair(pair)
        try:
            klines = self.client.klines(symbol=formatted_pair, interval=interval, limit=limit)
            if not klines:
                logging.warning(f"Binance Futures: No data returned for {pair}")
                return pd.DataFrame()

            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
            for col in df.columns:
                if col != 'open_time':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            return df.sort_values('open_time').reset_index(drop=True)
        except Exception as e:
            logging.error(f"Binance Futures API Error for {pair}: {e}")
            return pd.DataFrame()
