import requests
import logging
import pandas as pd
from exchanges.base import BaseExchangeAPI

class CoinDCXAPI(BaseExchangeAPI):
    """API client for CoinDCX."""
    def __init__(self, credentials, display, db_manager, config):
        super().__init__(credentials, display, db_manager, config)
        self.public_url = "https://public.coindcx.com"

    def get_historical_data(self, pair, interval, limit=200, force_fresh=False):
        # CoinDCX pair format is 'BTCUSDT', but the API endpoint uses 'B-BTC_USDT' for some pairs
        # The public candles endpoint uses the format 'BTC_USDT'
        formatted_pair = self._format_pair(pair, '_')
        url = f"{self.public_url}/market_data/candles?pair={formatted_pair}&interval={interval}&limit={limit}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data:
                logging.warning(f"CoinDCX: No data returned for {pair}")
                return pd.DataFrame()

            df = pd.DataFrame(data)
            df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
            df.rename(columns={'time': 'open_time'}, inplace=True)
            for col in df.columns:
                if col != 'open_time':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            # CoinDCX timestamps are in seconds
            df['open_time'] = pd.to_datetime(df['open_time'], unit='s')
            return df.sort_values('open_time').reset_index(drop=True)
        except requests.exceptions.RequestException as e:
            logging.error(f"CoinDCX API Request Error for {pair}: {e}")
        except Exception as e:
            logging.error(f"CoinDCX API Processing Error for {pair}: {e}")

        return pd.DataFrame()
