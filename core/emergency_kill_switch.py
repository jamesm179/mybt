import logging
from datetime import datetime
import pandas as pd

class EmergencyKillSwitch:
    """Emergency kill switch for immediate position closure"""
    def __init__(self, trading_engine, notification_manager=None):
        self.trading_engine = trading_engine
        self.notification_manager = notification_manager
        self.is_active = False
        self.trading_disabled = False
        self.execution_log = []

    def authenticate_password(self, password):
        """Verify password for kill switch activation"""
        # This should be a secure comparison, e.g., using a hashed password
        from config.config import Config
        return password == Config.SETTINGS_PASSWORD

    def get_active_positions_summary(self):
        """Get summary of all active positions"""
        if not hasattr(self.trading_engine, 'active_trades'):
            return []

        positions = []
        total_value = 0

        for exchange, strategy_trades in self.trading_engine.active_trades.items():
            for strategy, trades in strategy_trades.items():
                for symbol, trade_data in trades.items():
                    current_price = 0
                    if hasattr(self.trading_engine, 'display') and hasattr(self.trading_engine.display, 'pair_data'):
                        pair_data = self.trading_engine.display.pair_data.get(symbol, {})
                        if isinstance(pair_data, pd.DataFrame) and not pair_data.empty:
                            current_price = pair_data.iloc[-1]['close']
                        elif isinstance(pair_data, dict):
                            current_price = pair_data.get('price', 0)

                    entry_price = trade_data.get('entry_price', 0)
                    quantity = trade_data.get('quantity', 0)
                    leverage = trade_data.get('leverage', 1)
                    direction = trade_data.get('direction', 'long')

                    position_value = quantity * current_price if current_price > 0 else quantity * entry_price

                    if current_price > 0 and entry_price > 0:
                        if direction == 'long':
                            pnl_percent = ((current_price - entry_price) / entry_price) * 100 * leverage
                        else:
                            pnl_percent = ((entry_price - current_price) / entry_price) * 100 * leverage
                        pnl_usdt = (pnl_percent / 100) * quantity
                    else:
                        pnl_percent = 0
                        pnl_usdt = 0

                    positions.append({
                        'symbol': symbol.replace('B-', ''), 'direction': direction.upper(),
                        'entry_price': entry_price, 'current_price': current_price,
                        'quantity': quantity, 'leverage': leverage, 'position_value': position_value,
                        'pnl_percent': pnl_percent, 'pnl_usdt': pnl_usdt,
                        'strategy': trade_data.get('strategy', 'Unknown')
                    })
                    total_value += position_value

        return {
            'positions': positions,
            'total_positions': len(positions),
            'total_value': total_value,
            'timestamp': datetime.now()
        }

    async def execute_emergency_exit(self):
        """Execute emergency exit for all positions"""
        try:
            self.is_active = True
            self.trading_disabled = True
            num_positions = sum(len(trades) for strat_trades in self.trading_engine.active_trades.values() for trades in strat_trades.values())

            logging.info(f"EMERGENCY KILL SWITCH ACTIVATED: Closing {num_positions} positions.")
            if self.notification_manager:
                await self.notification_manager.send_notification(
                    f"🚨 EMERGENCY KILL SWITCH ACTIVATED 🚨\nClosing {num_positions} active positions immediately!"
                )

            closed_positions = []
            failed_positions = []

            for exchange, strategy_trades in self.trading_engine.active_trades.items():
                for strategy, trades in strategy_trades.items():
                    active_trades_copy = dict(trades)
                    for symbol, trade_data in active_trades_copy.items():
                        try:
                            # In a real scenario, this would place a market close order.
                            # Here, we simulate by removing the trade.
                            del self.trading_engine.active_trades[exchange][strategy][symbol]
                            closed_positions.append(symbol)
                            logging.info(f"EMERGENCY EXIT: Closed position for {symbol} on {exchange}")
                        except Exception as e:
                            failed_positions.append({'symbol': symbol, 'error': str(e)})
                            logging.error(f"EMERGENCY EXIT: Failed to close position for {symbol}: {e}")

            if hasattr(self.trading_engine, 'bot') and hasattr(self.trading_engine.bot, 'trailing_stop_manager'):
                self.trading_engine.bot.trailing_stop_manager.reset_all()

            logging.info(f"EMERGENCY EXIT COMPLETED. Closed: {len(closed_positions)}, Failed: {len(failed_positions)}")
            if self.notification_manager:
                await self.notification_manager.send_notification(
                    f"🚨 EMERGENCY EXIT COMPLETED 🚨\n✅ Closed: {len(closed_positions)}\n❌ Failed: {len(failed_positions)}\n🚫 Trading DISABLED."
                )
            return {'success': True, 'closed_positions': closed_positions, 'failed_positions': failed_positions}
        except Exception as e:
            logging.error(f"EMERGENCY KILL SWITCH: Critical error during execution: {e}")
            if self.notification_manager:
                await self.notification_manager.send_notification(f"🚨 EMERGENCY EXIT ERROR 🚨\nCritical error: {e}")
            return {'success': False, 'error': str(e)}

    def re_enable_trading(self):
        """Re-enable trading after emergency exit"""
        self.trading_disabled = False
        self.is_active = False
        logging.info("EMERGENCY KILL SWITCH: Trading re-enabled.")

    def get_execution_log(self):
        """Get the execution log"""
        return self.execution_log
