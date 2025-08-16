import logging
import pandas as pd
from binance.spot import Spot as BinanceSpotClient
from exchanges.base import BaseExchangeAPI

class BinanceAPI(BaseExchangeAPI):
    """API client for Binance."""
    def __init__(self, credentials, display, db_manager, config):
        super().__init__(credentials, display, db_manager, config)
        self.client = BinanceSpotClient(api_key=self.key, api_secret=self.secret, base_url="https://api.binance.com")

    def get_historical_data(self, pair, interval, limit=200, force_fresh=False):
        formatted_pair = self._format_pair(pair)
        try:
            # Binance API uses '1m', '5m', '1h', '4h', '1d' etc. which matches our format
            klines = self.client.klines(symbol=formatted_pair, interval=interval, limit=limit)
            if not klines:
                logging.warning(f"Binance: No data returned for {pair}")
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
            # Binance timestamps are in milliseconds
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            return df.sort_values('open_time').reset_index(drop=True)
        except Exception as e:
            # The binance connector can raise various exceptions
            logging.error(f"Binance API Error for {pair}: {e}")
            return pd.DataFrame()
