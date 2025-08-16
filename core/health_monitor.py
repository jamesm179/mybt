import logging
import platform
import subprocess
import threading
import time
from datetime import datetime, timedelta
import requests
import asyncio
from config.config import Config

class HealthMonitor:
    """Monitors the operational health of the trading bot."""
    def __init__(self):
        self.bot = None
        self.api_failures = {}
        self.db_failures = 0
        self.pair_blacklist = {}
        self.last_successful_cycle = datetime.now()

    def set_bot(self, bot):
        self.bot = bot

    def record_api_failure(self, pair_symbol, count=1):
        self.api_failures[pair_symbol] = self.api_failures.get(pair_symbol, 0) + count
        if self.api_failures[pair_symbol] > 10:
            self.pair_blacklist[pair_symbol] = datetime.now() + timedelta(minutes=30)
            if self.bot and hasattr(self.bot, 'display'):
                self.bot.display.add_log(f"BLACKLISTED {pair_symbol} for 30 mins due to repeated API failures.")

    def record_db_failure(self):
        self.db_failures += 1

    def record_successful_cycle(self):
        self.last_successful_cycle = datetime.now()

    def is_pair_blacklisted(self, pair_symbol):
        if pair_symbol in self.pair_blacklist:
            if datetime.now() < self.pair_blacklist[pair_symbol]:
                return True
            else:
                del self.pair_blacklist[pair_symbol]
                self.api_failures[pair_symbol] = 0
                return False
        return False

    def check_blacklist(self):
        expired = [p for p, t in self.pair_blacklist.items() if datetime.now() >= t]
        for p in expired:
            del self.pair_blacklist[p]
            self.api_failures[p] = 0
            if self.bot and hasattr(self.bot, 'display'):
                self.bot.display.add_log(f"{p} removed from blacklist.")

    def check_process_health(self, refresh_interval):
        time_since_success = (datetime.now() - self.last_successful_cycle).total_seconds()
        if time_since_success > refresh_interval * 5:
            if self.bot and hasattr(self.bot, 'display'):
                self.bot.display.add_log("HEALTH WARNING: No successful data cycle in the last 5 intervals.")

class ConnectivityMonitor:
    """Monitors internet connectivity."""
    def __init__(self, bot=None, notification_manager=None, telegram_notifier=None):
        self.bot = bot
        self.notification_manager = notification_manager
        self.telegram_notifier = telegram_notifier
        self.current_status = "Unknown"
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_test_time = None
        self.last_ping_time = None
        self.response_times = []
        self.monitoring_thread = None
        self.stop_monitoring_flag = threading.Event()
        self.status_lock = threading.Lock()
        self.ping_targets = ["8.8.8.8", "1.1.1.1"]
        self.http_targets = ["https://www.google.com", "https://api.binance.com"]
        self.ping_command = self._get_ping_command()

    def _get_ping_command(self):
        system = platform.system().lower()
        if system == "windows":
            return ["ping", "-n", "1", "-w", str(Config.CONNECTIVITY_PING_TIMEOUT)]
        else:
            timeout_seconds = Config.CONNECTIVITY_PING_TIMEOUT // 1000
            return ["ping", "-c", "1", "-W", str(max(1, timeout_seconds))]

    def start_monitoring(self):
        if not Config.CONNECTIVITY_MONITORING_ENABLED: return
        if self.monitoring_thread and self.monitoring_thread.is_alive(): return
        self.stop_monitoring_flag.clear()
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()

    def stop_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.stop_monitoring_flag.set()
            self.monitoring_thread.join(timeout=5)

    def _monitoring_loop(self):
        while not self.stop_monitoring_flag.is_set():
            try:
                self._perform_connectivity_test()
                sleep_interval = 10 if self.current_status == "Lost" else Config.CONNECTIVITY_TEST_INTERVAL
                time.sleep(sleep_interval)
            except Exception as e:
                logging.error(f"Error in connectivity monitoring loop: {e}")
                time.sleep(5)

    def _perform_connectivity_test(self):
        ping_result = self._test_ping()
        if not ping_result or ping_result['status'] == 'Failed':
            http_result = self._test_http()
            self._analyze_test_results([http_result] if http_result else [])
        else:
            self._analyze_test_results([ping_result])

    def _test_ping(self):
        # Simplified for brevity
        return {'method': 'ping', 'status': 'Success', 'response_time': 50}

    def _test_http(self):
        # Simplified for brevity
        return {'method': 'http', 'status': 'Success', 'response_time': 200}

    def _analyze_test_results(self, test_results):
        if not test_results or test_results[0]['status'] == 'Failed':
            self._update_status("Lost", None, "Connection test failed")
        else:
            response_time = test_results[0]['response_time']
            if response_time <= 100: new_status = "Normal"
            elif response_time <= 1000: new_status = "Slow"
            else: new_status = "Poor"
            self._update_status(new_status, response_time, f"Test via {test_results[0]['method']}")

    def _update_status(self, new_status, response_time, details):
        with self.status_lock:
            # Logic simplified for brevity
            if self.current_status != new_status:
                logging.info(f"Connectivity status changed: {self.current_status} -> {new_status}")
                self.current_status = new_status

    def get_status(self):
        with self.status_lock:
            return {'status': self.current_status}

    def set_bot(self, bot):
        self.bot = bot

    def set_notification_manager(self, notification_manager):
        self.notification_manager = notification_manager

    def set_telegram_notifier(self, telegram_notifier):
        self.telegram_notifier = telegram_notifier
