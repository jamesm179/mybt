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
        try:
            exchange_name = signals['exchange']
            pair = signals['pair']
            symbol = signals['symbol']
            price = signals['price']
            time_ist = signals.get('time_ist', datetime.now().strftime('%Y%m%d_%H%M%S'))
            trigger_strategy = signals.get('trigger_strategy', 'unknown')

            # Process exits first
            if signals.get('should_exit'):
                if symbol in self.active_trades[exchange_name].get(trigger_strategy, {}):
                    trade = self.active_trades[exchange_name][trigger_strategy][symbol]
                    profit_pct = ((price - trade['entry_price']) / trade['entry_price']) * 100 * trade['leverage'] if trade['direction'] == 'long' else ((trade['entry_price'] - price) / trade['entry_price']) * 100 * trade['leverage']
                    amount = trade['amount']
                    self.balance += amount * (1 + profit_pct / 100)
                    self.log_trade(exchange_name, "SELL" if trade['direction'] == 'long' else "BUY", pair, price, amount, self.balance, profit_pct, signals.get('exit_reason', 'Exit Signal'), trade['direction'], trade['stop_loss_price'], trade['take_profit_price'], trade['trade_id'], "Closed (Signal)")
                    del self.active_trades[exchange_name][trigger_strategy][symbol]
                    return True

            # Process entries
            if (signals.get('should_buy') or signals.get('should_sell')) and Config.AUTO_TRADING and not self.emergency_kill_switch.trading_disabled:
                if any(symbol in trades for strategy_trades in self.active_trades[exchange_name].values() for symbol in strategy_trades):
                    return False

                risk_amount = min(TradingConfig.MAX_RISK_USDT, self.balance * TradingConfig.RISK_PERCENT, self.balance)
                if risk_amount < TradingConfig.MIN_ORDER_SIZE: return False

                strategy_config = Config.STRATEGIES.get(trigger_strategy, {})
                desired_tp = strategy_config.get('desired_take_profit', 7.0)
                desired_sl = strategy_config.get('desired_stop_loss', 5.0)
                take_profit, stop_loss = TradingConfig.calculate_tp_sl(desired_tp, desired_sl, TradingConfig.LEVERAGE, trigger_strategy)
                if take_profit is None or stop_loss is None: return False

                direction = "long" if signals.get('should_buy') else "short"
                action = "BUY" if direction == "long" else "SELL"
                stop_loss_price = price * (1 - stop_loss) if direction == "long" else price * (1 + stop_loss)
                take_profit_price = price * (1 + take_profit) if direction == "long" else price * (1 - take_profit)

                trade_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{pair}_{direction}"
                self.balance -= risk_amount
                self.active_trades[exchange_name][trigger_strategy][symbol] = {
                    'entry_price': price, 'entry_time': time_ist, 'highest_price': price,
                    'leverage': TradingConfig.LEVERAGE, 'amount': risk_amount,
                    'stop_loss_price': stop_loss_price, 'take_profit_price': take_profit_price,
                    'trade_id': trade_id, 'direction': direction, 'bars_since_entry': 0
                }
                self.log_trade(exchange_name, action, pair, price, risk_amount, self.balance, None, signals.get('entry_reason', 'Signal'), direction, stop_loss_price, take_profit_price, trade_id, "Active")
                await self.telegram.send_signal(pair, action, price, risk_amount, self.balance, signals.get('entry_reason', 'Signal'), direction, stop_loss_price, take_profit_price)
                self.signals_today += 1
                return True

            return False
        except Exception as e:
            logging.error(f"Trade execution error for {signals.get('pair', 'UNKNOWN')}: {e}", exc_info=True)
            return False

    async def execute_manual_trade(self, pair_symbol, action):
        """Execute a manual trade for a specific pair."""
        try:
            # Find the pair info
            pair_info = next((p for p in self.pairs if p['symbol'] == pair_symbol), None)
            if not pair_info:
                self.display.add_log(f"Invalid pair symbol for manual trade: {pair_symbol}")
                return False

            if pair_symbol not in self.display.pair_data or self.display.pair_data[pair_symbol].empty:
                self.display.add_log(f"No data available for {pair_symbol}")
                return False

            df = self.display.pair_data[pair_symbol]
            latest_row = df.iloc[-1]
            price = latest_row['close']
            pair = latest_row['pair']
            time_ist = latest_row['time_ist']

            # Use the first active strategy and selected exchange for manual trades
            trigger_strategy = Config.ACTIVE_STRATEGIES[0]
            exchange_name = Config.SELECTED_EXCHANGE

            if any(pair_symbol in trades for trades in self.active_trades[exchange_name].values()):
                self.display.add_log(f"Already have an active trade for {pair}")
                return False

            risk_amount = min(TradingConfig.MAX_RISK_USDT, self.balance * TradingConfig.RISK_PERCENT, self.balance)
            if risk_amount < TradingConfig.MIN_ORDER_SIZE:
                self.display.add_log(f"Insufficient balance for manual trade: {self.balance}")
                return False

            strategy_config = Config.STRATEGIES.get(trigger_strategy, {})
            desired_tp = strategy_config.get('desired_take_profit', 7.0)
            desired_sl = strategy_config.get('desired_stop_loss', 5.0)
            take_profit, stop_loss = TradingConfig.calculate_tp_sl(desired_tp, desired_sl, TradingConfig.LEVERAGE, trigger_strategy)

            direction = "long" if action == "BUY" else "short"
            stop_loss_price = price * (1 - stop_loss) if direction == "long" else price * (1 + stop_loss)
            take_profit_price = price * (1 + take_profit) if direction == "long" else price * (1 - take_profit)

            trade_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{pair}_{direction}_manual"
            self.balance -= risk_amount
            self.active_trades[exchange_name][trigger_strategy][pair_symbol] = {
                'entry_price': price, 'entry_time': time_ist, 'highest_price': price,
                'leverage': TradingConfig.LEVERAGE, 'amount': risk_amount,
                'stop_loss_price': stop_loss_price, 'take_profit_price': take_profit_price,
                'trade_id': trade_id, 'direction': direction, 'bars_since_entry': 0
            }

            reason = f"Manual {direction.upper()} trade"
            self.log_trade(exchange_name, action, pair, price, risk_amount, self.balance, None, reason, direction, stop_loss_price, take_profit_price, trade_id, "Active")
            await self.telegram.send_signal(pair, action, price, risk_amount, self.balance, reason, direction, stop_loss_price, take_profit_price)
            self.signals_today += 1
            self.display.add_log(f"Manual {action} executed for {pair} at {price}")
            return True
        except Exception as e:
            self.display.add_log(f"Manual trade execution error for {pair_symbol}: {e}")
            return False

    async def exit_position(self, pair_symbol, strategy_name=None):
        """Manually exit a position for a specific pair."""
        try:
            exchange_name = Config.SELECTED_EXCHANGE
            found_strategy = None
            if strategy_name and strategy_name in self.active_trades[exchange_name] and pair_symbol in self.active_trades[exchange_name][strategy_name]:
                found_strategy = strategy_name
            else:
                for strat_name in self.active_trades[exchange_name]:
                    if pair_symbol in self.active_trades[exchange_name][strat_name]:
                        found_strategy = strat_name
                        break

            if not found_strategy:
                self.display.add_log(f"No active position found for {pair_symbol} on {exchange_name}")
                return False

            if pair_symbol not in self.display.pair_data or self.display.pair_data[pair_symbol].empty:
                self.display.add_log(f"No price data for {pair_symbol} to exit position.")
                return False

            current_price = self.display.pair_data[pair_symbol].iloc[-1]['close']
            trade = self.active_trades[exchange_name][found_strategy][pair_symbol]
            is_long = trade['direction'] == 'long'

            profit_pct = ((current_price - trade['entry_price']) / trade['entry_price']) * 100 * trade['leverage'] if is_long else ((trade['entry_price'] - current_price) / trade['entry_price']) * 100 * trade['leverage']
            amount = trade['amount']
            self.balance += amount * (1 + profit_pct / 100)

            action = "SELL" if is_long else "BUY"
            pair_display = pair_symbol.replace('B-', '').replace('_', '/')

            self.log_trade(exchange_name, action, pair_display, current_price, amount, self.balance, profit_pct, "Manual Exit", trade['direction'], trade['stop_loss_price'], trade['take_profit_price'], trade['trade_id'], "Closed (Manual)")
            await self.telegram.send_signal(pair_display, action, current_price, amount, self.balance, f"Manual Exit | P/L: {profit_pct:.2f}%", trade['direction'], trade['stop_loss_price'], trade['take_profit_price'], profit_pct)

            del self.active_trades[exchange_name][found_strategy][pair_symbol]
            self.display.add_log(f"Manually exited {trade['direction']} position for {pair_display} with P/L: {profit_pct:.2f}%")
            return True
        except Exception as e:
            self.display.add_log(f"Error exiting position for {pair_symbol}: {e}")
            return False

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
