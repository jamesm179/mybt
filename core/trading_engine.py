import os
import asyncio
import logging
import pandas as pd
from datetime import datetime
import inspect

from config.config import Config, TradingConfig
from core.notification_manager import TelegramNotifier, NotificationManager
from core.performance_tracker import PerformanceTracker, AsyncTradeLogger
from core.emergency_kill_switch import EmergencyKillSwitch
from strategies.factory import get_strategy

class TradingEngine:
    def __init__(self, api_clients, pairs, display_manager):
        self.api_clients = api_clients
        self.active_trades = {exchange: {strat: {} for strat in Config.ACTIVE_STRATEGIES} for exchange in self.api_clients.keys()}
        self.telegram = TelegramNotifier(display_manager)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.trade_log_file = os.path.join('logs', f'trades_{timestamp}.csv')
        self.async_trade_logger = AsyncTradeLogger(self.trade_log_file)
        self._async_logger_started = False
        self.performance_tracker = PerformanceTracker(self.trade_log_file, display_manager)
        self.display = display_manager
        self.bot_start_time = datetime.now()
        self.signals_today = 0
        self.strategies = {strat: get_strategy(strat, Config.STRATEGIES.get(strat, {})) for strat in Config.ACTIVE_STRATEGIES}
        self.pairs = pairs
        self.balance = 1000.0
        if self.api_clients:
            first_client = next(iter(self.api_clients.values()))
            wallet_data = first_client.get_wallet_data()
            self.balance = float(next((item['balance'] for item in wallet_data if item.get('currency_short_name') == 'USDT'), '1000.0'))
        self.bot = None
        self.emergency_kill_switch = EmergencyKillSwitch(self)

    def set_bot(self, bot):
        self.bot = bot
        if hasattr(bot, 'telegram') and bot.telegram:
            self.emergency_kill_switch.notification_manager = bot.telegram

    async def send_startup_message(self):
        mode = "Paper Trading" if Config.PAPER_TRADING else "Live Trading"
        pair_list = ", ".join([p['symbol'] for p in self.pairs])
        startup_msg = (f"🚀 *Sniper Bot V1 Started ({mode})* 🚀\n"
                       f"*Time:* {self.bot_start_time.strftime('%Y-%m-%d %H:%M:%S')} IST\n"
                       f"*Pairs:* {pair_list}\n"
                       f"*Balance:* {self.balance:.2f} USDT")
        await self.telegram.send_message(startup_msg)

    async def process_data(self, data, pair_info=None):
        if data.empty: return None
        pair_name = pair_info["symbol"] if pair_info else "UNKNOWN_PAIR"
        df = data.copy()
        df['pair'] = pair_name.replace('B-', '').replace('_', '/')
        df['symbol'] = pair_name

        # ... (full datetime logic) ...

        strategy_dfs = {}
        # Pre-calculate shared indicators for performance
        shared_indicators = {}
        if hasattr(self.display, '_calculate_shared_indicators'):
            shared_indicators = self.display._calculate_shared_indicators(pair_name, df)

        async def process_strategy(strat_name, strategy, df_copy):
            try:
                sig = inspect.signature(strategy.get_indicators)
                if 'shared_indicators' in sig.parameters:
                    return strat_name, strategy.get_indicators(df_copy, shared_indicators)
                else:
                    return strat_name, strategy.get_indicators(df_copy)
            except Exception as e:
                logging.error(f"Error processing strategy {strat_name}: {e}")
                return strat_name, pd.DataFrame()

        tasks = [process_strategy(name, strat, df.copy()) for name, strat in self.strategies.items()]
        results = await asyncio.gather(*tasks)
        for strat_name, df_strat in results:
            strategy_dfs[strat_name] = df_strat
        return strategy_dfs

    async def check_signals(self, strategy_dfs):
        signals = {'signal_type': None, 'pair': None, 'symbol': None, 'price': None}
        for strat_name, df in strategy_dfs.items():
            if df is None or df.empty: continue
            latest_row = df.iloc[-1]
            # Get active trades for the correct exchange and strategy
            exchange = signals.get('exchange', Config.SELECTED_EXCHANGE)
            active_trades = self.active_trades.get(exchange, {}).get(strat_name, {})
            strat_signals = await self.strategies[strat_name].check_signals(latest_row, active_trades)
            if strat_signals.get('signal_type'):
                signals.update(strat_signals)
                signals['trigger_strategy'] = strat_name
                signals.update({'pair': latest_row['pair'], 'symbol': latest_row['symbol'], 'price': latest_row['close']})
                break
        return signals

    async def execute_trades(self, signals):
        # ... (full implementation from original script) ...
        pass

    async def execute_manual_trade(self, pair_symbol, action):
        # ... (full implementation from original script) ...
        pass

    async def exit_position(self, pair_symbol, strategy_name=None):
        # ... (full implementation from original script) ...
        pass

    def log_trade(self, exchange, action, pair, price, amount, balance, profit_pct, reason, direction, stop_loss_price=None, take_profit_price=None, trade_id=None, status="Active"):
        asyncio.create_task(self._ensure_async_logger_started())
        if self._async_logger_started:
            asyncio.create_task(self.async_trade_logger.log_trade_async(
                exchange, action, pair, price, amount, balance, profit_pct, reason, direction,
                stop_loss_price, take_profit_price, trade_id, status
            ))

    async def _ensure_async_logger_started(self):
        if not self._async_logger_started:
            try:
                await self.async_trade_logger.start()
                self._async_logger_started = True
            except Exception as e:
                logging.error(f"Failed to start AsyncTradeLogger: {e}")

    async def shutdown_async_logger(self):
        if self._async_logger_started and self.async_trade_logger:
            await self.async_trade_logger.stop()
