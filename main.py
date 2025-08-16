import os
import sys
import logging
import pkg_resources

def check_dependencies():
    """
    Checks if all required packages from requirements.txt are installed.
    Provides a clear error and exits if dependencies are missing.
    """
    # Use a basic logger until the full logging is configured
    print("--- Checking Dependencies ---")
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        req_path = os.path.join(script_dir, 'requirements.txt')

        if not os.path.exists(req_path):
            print(f"--> FATAL ERROR: `requirements.txt` not found at the expected path: {req_path}")
            print("--> Please ensure `requirements.txt` is in the same directory as `main.py`.")
            sys.exit(1)

        with open(req_path) as f:
            requirements = f.read().splitlines()

        missing_packages = []
        for req in requirements:
            if req.strip() and not req.strip().startswith('#'):
                try:
                    # Clean up requirement string for pkg_resources
                    req_name = req.split(';')[0].split('==')[0].split('>')[0].split('<')[0].strip()
                    if req_name:
                        pkg_resources.require(req_name)
                except pkg_resources.DistributionNotFound:
                    missing_packages.append(req)

        if missing_packages:
            print("--> FATAL ERROR: The following required packages are not installed:")
            for pkg in missing_packages:
                print(f"    - {pkg}")
            print("\n--> Please install all required packages by running this command:")
            print("    pip install -r requirements.txt")
            sys.exit(1)

        print("--> All dependencies are satisfied.")

    except ImportError:
        print("--> FATAL ERROR: `pkg_resources` (part of `setuptools`) is not installed.")
        print("--> Please install it by running: pip install setuptools")
        sys.exit(1)
    except Exception as e:
        print(f"--> An unexpected error occurred during dependency check: {e}")
        sys.exit(1)

# Run dependency check before any other imports from our modules
check_dependencies()

import asyncio
import signal
import time
import threading
import json

from config.config import Config, TradingConfig
from core.database import DatabaseManager
from core.health_monitor import HealthMonitor, ConnectivityMonitor
from core.trading_engine import TradingEngine
from core.trailing_stop_manager import TrailingStopManager
from dashboard.display_manager import DisplayManager
from exchanges.factory import ExchangeAPIFactory
from utils import load_credentials

class CryptoBot:
    def __init__(self):
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

        Config.EXCHANGE_CREDENTIALS = load_credentials()

        self.health_monitor = HealthMonitor()
        self.trailing_stop_manager = TrailingStopManager()
        self.connectivity_monitor = ConnectivityMonitor()
        self.display = DisplayManager(None, None, None)
        self.db_manager = DatabaseManager(Config.DB_PATH, self.display)

        self.api_clients = {
            name: ExchangeAPIFactory.create_api(name, Config.EXCHANGE_CREDENTIALS.get(name, {}), self.display, self.db_manager, Config)
            for name in Config.ACTIVE_EXCHANGES
        }

        if not self.api_clients:
            raise ValueError("No valid API clients could be initialized.")

        self.pairs = [{"symbol": pair, "color": "white", "weight": i} for i, pair in enumerate(TradingConfig.DEFAULT_PAIRS)]

        self.engine = TradingEngine(self.api_clients, self.pairs, self.display)

        self.display.engine = self.engine
        self.display.db_manager = self.db_manager
        self.display.performance_tracker = self.engine.performance_tracker
        self.health_monitor.set_bot(self)
        self.engine.set_bot(self)
        self.connectivity_monitor.set_bot(self)

        self.running = True
        self.bot_initialized = False
        self.initialization_lock = threading.Lock()
        self.initialization_stats = {}

    def update_trading_pairs(self):
        """Update the trading pairs list with manual pairs from config for futures."""
        logging.info(f"Updating trading pairs for futures. Manual pairs: {Config.MANUAL_TRADING_PAIRS}")

        all_pairs = set(TradingConfig.DEFAULT_PAIRS)
        for manual_pair in Config.MANUAL_TRADING_PAIRS:
            # Convert display format like "GALA/USDT" to API format "GALAUSDT"
            api_pair = manual_pair.replace('/', '').upper()
            all_pairs.add(api_pair)

        self.pairs = [{"symbol": pair, "color": "white", "weight": i} for i, pair in enumerate(sorted(list(all_pairs)))]
        self.engine.pairs = self.pairs # Update engine's pair list

        if hasattr(self.display, 'price_history'):
            for pair_info in self.pairs:
                if pair_info["symbol"] not in self.display.price_history:
                    self.display.price_history[pair_info["symbol"]] = []

        self.display.add_log(f"Trading pairs updated: {len(self.pairs)} pairs active.")
        logging.info(f"Trading pairs updated. Total active pairs: {len(self.pairs)}")

    async def initialize_bot_data(self):
        if not Config.REQUIRE_FRESH_DATA_ON_STARTUP:
            self.bot_initialized = True
            return True
        with self.initialization_lock:
            if self.bot_initialized: return True
            logging.info("BOT INITIALIZATION: Starting data validation sequence.")
            tasks = [self._initialize_pair_on_exchange(p, name, client) for name, client in self.api_clients.items() for p in self.pairs]
            results = await asyncio.gather(*tasks)
            successful = sum(1 for r in results if r)
            total = len(tasks)
            success_rate = (successful / total) * 100 if total > 0 else 0
            if success_rate >= 70:
                self.bot_initialized = True
                logging.info(f"BOT INITIALIZATION: SUCCESSFUL ({success_rate:.1f}%)")
                return True
            else:
                logging.error(f"BOT INITIALIZATION: FAILED ({success_rate:.1f}%)")
                return False

    async def _initialize_pair_on_exchange(self, pair_info, exchange_name, api_client):
        pair_symbol = pair_info["symbol"]
        try:
            data = api_client.get_historical_data(pair_symbol, Config.CURRENT_TIMEFRAME, limit=500)
            if data.empty or len(data) < Config.MIN_CANDLES_FOR_TRADING: return False
            freshness = api_client.validate_data_freshness(data, pair_symbol)
            if not freshness['is_fresh']: return False
            await self.engine.process_data(data, pair_info)
            return True
        except Exception as e:
            logging.error(f"Error initializing {pair_symbol} on {exchange_name}: {e}")
            return False

    def switch_exchange(self, exchange_name: str):
        if exchange_name not in Config.SUPPORTED_EXCHANGES:
            logging.error(f"Attempted to switch to unsupported exchange: {exchange_name}")
            return False
        Config.SELECTED_EXCHANGE = exchange_name
        self.display.save_settings()
        logging.info(f"Switched selected display exchange to {exchange_name}")
        return True

    async def run(self):
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        dash_thread = threading.Thread(target=self.display.run, daemon=True)
        dash_thread.start()

        self.connectivity_monitor.start_monitoring()
        await self.engine.send_startup_message()

        await self.initialize_bot_data()

        while self.running:
            start_time = time.time()
            active_pairs = [p for p in self.pairs if not self.health_monitor.is_pair_blacklisted(p["symbol"])]

            for exchange_name, api_client in self.api_clients.items():
                tasks = [self.process_pair(exchange_name, api_client, pair_info) for pair_info in active_pairs]
                await asyncio.gather(*tasks)

            elapsed = time.time() - start_time
            await asyncio.sleep(max(0, Config.REFRESH_INTERVAL - elapsed))

    async def process_pair(self, exchange_name, api_client, pair_info):
        pair_symbol = pair_info["symbol"]
        try:
            data = api_client.get_historical_data(pair_symbol, Config.CURRENT_TIMEFRAME)
            if data.empty or len(data) < Config.MIN_CANDLES_FOR_TRADING: return
            strategy_dfs = await self.engine.process_data(data, pair_info)
            self.display.update_pair_data(pair_symbol, strategy_dfs)
            signals = await self.engine.check_signals(strategy_dfs)
            signals['exchange'] = exchange_name
            if signals and (signals.get('should_buy') or signals.get('should_sell') or signals.get('should_exit')):
                await self.engine.execute_trades(signals)
        except Exception as e:
            logging.error(f"Error processing {pair_symbol} on {exchange_name}: {e}")

    def shutdown(self, signum, frame):
        self.running = False
        self.connectivity_monitor.stop_monitoring()
        logging.info("Shutting down bot...")

if __name__ == "__main__":
    if sys.platform == 'win32' and sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    bot = CryptoBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
    except Exception as e:
        logging.critical(f"Fatal error in bot execution: {e}", exc_info=True)
        sys.exit(1)
