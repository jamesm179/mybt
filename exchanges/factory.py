import logging

from exchanges.base import BaseExchangeAPI
from exchanges.coindcx import CoinDCXAPI
from exchanges.binance import BinanceAPI
from exchanges.bitget import BitgetAPI

class ExchangeAPIFactory:
    """Factory to create exchange-specific API clients."""
    @staticmethod
    def create_api(exchange_name, credentials, display, db_manager, config):
        """
        Creates an instance of an exchange API client.

        Args:
            exchange_name (str): The name of the exchange.
            credentials (dict): API credentials for the exchange.
            display: The display manager instance.
            db_manager: The database manager instance.
            config: The main config object.

        Returns:
            An instance of a BaseExchangeAPI subclass.
        """
        logging.info(f"Creating API client for '{exchange_name}'...")

        if exchange_name == 'coindcx':
            return CoinDCXAPI(credentials, display, db_manager, config)
        elif exchange_name == 'binance':
            return BinanceAPI(credentials, display, db_manager, config)
        elif exchange_name == 'bitget':
            return BitgetAPI(credentials, display, db_manager, config)
        else:
            logging.error(f"Attempted to create an unsupported exchange client: {exchange_name}")
            raise ValueError(f"Unsupported exchange: {exchange_name}")
