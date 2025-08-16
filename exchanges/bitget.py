import requests
import logging
import pandas as pd
from exchanges.base import BaseExchangeAPI

class BitgetAPI(BaseExchangeAPI):
    """API client for Bitget."""
    def __init__(self, credentials, display, db_manager, config):
        super().__init__(credentials, display, db_manager, config)
        self.base_url = "https://api.bitget.com"

    def get_historical_data(self, pair, interval, limit=200, force_fresh=False):
        # Bitget futures symbols are like BTCUSDT
        formatted_pair = self._format_pair(pair)

        # Granularity mapping for Bitget Futures API
        granularity_map = {
            '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1H', '4h': '4H', '12h': '12H', '1d': '1D'
        }
        granularity = granularity_map.get(interval)
        if not granularity:
            logging.error(f"Bitget Futures: Unsupported interval format '{interval}'")
            return pd.DataFrame()

        # Endpoint for USDT-M Futures
        url = f"{self.base_url}/api/v2/mix/market/candles"
        params = {
            "symbol": formatted_pair,
            "productType": "usdt-futures",
            "granularity": granularity,
            "limit": limit
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if str(data.get('code')) != '00000':
                logging.error(f"Bitget Futures API Error for {pair}: {data.get('msg')}")
                return pd.DataFrame()

            candle_data = data.get('data', [])
            if not candle_data:
                logging.warning(f"Bitget Futures: No data returned for {pair}")
                return pd.DataFrame()

            df = pd.DataFrame(candle_data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'])
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
            for col in df.columns:
                if col != 'open_time':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            return df.sort_values('open_time').reset_index(drop=True)
        except requests.exceptions.RequestException as e:
            logging.error(f"Bitget Futures API Request Error for {pair}: {e}")
        except Exception as e:
            logging.error(f"Bitget Futures API Processing Error for {pair}: {e}")

        return pd.DataFrame()
