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
        # Bitget uses format like BTCUSDT
        formatted_pair = self._format_pair(pair) + "USDT"

        # Bitget interval format mapping
        interval_map = {
            '1m': '1min', '5m': '5min', '15m': '15min', '30m': '30min',
            '1h': '1H', '4h': '4H', '1d': '1D'
        }
        formatted_interval = interval_map.get(interval)
        if not formatted_interval:
            logging.error(f"Bitget: Unsupported interval format '{interval}'")
            return pd.DataFrame()

        url = f"{self.base_url}/api/v2/spot/market/candles?symbol={formatted_pair}&granularity={formatted_interval}&limit={limit}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('code') != '00000':
                logging.error(f"Bitget API Error for {pair}: {data.get('msg')}")
                return pd.DataFrame()

            candle_data = data.get('data', [])
            if not candle_data:
                logging.warning(f"Bitget: No data returned for {pair}")
                return pd.DataFrame()

            df = pd.DataFrame(candle_data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume'])
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
            for col in df.columns:
                if col != 'open_time':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            # Bitget timestamps are in milliseconds
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            return df.sort_values('open_time').reset_index(drop=True)
        except requests.exceptions.RequestException as e:
            logging.error(f"Bitget API Request Error for {pair}: {e}")
        except Exception as e:
            logging.error(f"Bitget API Processing Error for {pair}: {e}")

        return pd.DataFrame()
