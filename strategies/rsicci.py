import pandas as pd
import talib
import logging
import numpy as np
from typing import Dict, Any

from strategies.base import Strategy

class RSICCIStrategy(Strategy):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.rsi25_period = config.get('rsi25_period', 25)
        self.rsi100_period = config.get('rsi100_period', 100)
        self.cci40_period = config.get('cci40_period', 40)
        self.cci100_period = config.get('cci100_period', 100)
        self.rsi_cross_level = config.get('rsi_cross_level', 60)
        self.cci40_cross_level = config.get('cci40_cross_level', 200)
        self.cci100_cross_level = config.get('cci100_cross_level', -45)
        self.ema14_period = config.get('ema14_period', 14)
        self.trail_percent = config.get('trail_percent', 12.0)
        self.use_long_signals = config.get('use_long_signals', True)
        self.use_short_signals = config.get('use_short_signals', False)

    def get_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        result = df.copy()
        required_length = max(self.rsi100_period, self.cci100_period, self.ema14_period)
        if len(result) < required_length:
            logging.warning(f"Insufficient data for RSICCIStrategy indicators: {len(result)} candles")
            return result

        required_cols = ['high', 'low', 'close']
        if result[required_cols].isna().any().any():
            result[required_cols] = result[required_cols].fillna(method='ffill')
            if result[required_cols].isna().any().any():
                result[required_cols] = result[required_cols].fillna(method='bfill')
            if result[required_cols].isna().any().any():
                result = result.dropna(subset=required_cols)
                if len(result) < required_length:
                    logging.warning(f"After dropping NaNs, insufficient data: {len(result)} candles")
                    return result

        close_array = result['close'].values
        high_array = result['high'].values
        low_array = result['low'].values

        shared_indicators = getattr(self, 'shared_indicators', None)
        if shared_indicators:
            result['rsi25'] = shared_indicators.get('rsi25', talib.RSI(close_array, timeperiod=self.rsi25_period))
            result['rsi100'] = shared_indicators.get('rsi100', talib.RSI(close_array, timeperiod=self.rsi100_period))
            result['cci40'] = shared_indicators.get('cci40', talib.CCI(high_array, low_array, close_array, timeperiod=self.cci40_period))
            result['cci100'] = shared_indicators.get('cci100', talib.CCI(high_array, low_array, close_array, timeperiod=self.cci100_period))
            result['ema14'] = shared_indicators.get('ema14', talib.EMA(close_array, timeperiod=self.ema14_period))
        else:
            result['rsi25'] = talib.RSI(close_array, timeperiod=self.rsi25_period)
            result['rsi100'] = talib.RSI(close_array, timeperiod=self.rsi100_period)
            result['cci40'] = talib.CCI(high_array, low_array, close_array, timeperiod=self.cci40_period)
            result['cci100'] = talib.CCI(high_array, low_array, close_array, timeperiod=self.cci100_period)
            result['ema14'] = talib.EMA(close_array, timeperiod=self.ema14_period)

        result[['rsi25', 'rsi100', 'cci40', 'cci100', 'ema14']] = result[['rsi25', 'rsi100', 'cci40', 'cci100', 'ema14']].ffill().bfill()

        rsi25_prev = result['rsi25'].shift(1)
        cci40_prev = result['cci40'].shift(1)
        cci100_prev = result['cci100'].shift(1)

        result['rsi25_cross_up'] = (result['rsi25'] > self.rsi_cross_level) & (rsi25_prev <= self.rsi_cross_level)
        result['cci40_cross_up'] = (result['cci40'] > self.cci40_cross_level) & (cci40_prev <= self.cci40_cross_level)
        result['cci100_cross_up'] = (result['cci100'] > self.cci100_cross_level) & (cci100_prev <= self.cci100_cross_level)

        result['rsi_condition'] = (result['rsi25'] > result['rsi100']).astype(int)
        result['filt'] = result['ema14']
        result['upward'] = (result['close'] > result['ema14']).astype(float)
        result['downward'] = (result['close'] < result['ema14']).astype(float)

        result['cond_ini'] = np.where(
            result['rsi_condition'] & result['rsi25_cross_up'] & result['cci40_cross_up'] & result['cci100_cross_up'],
            1, 0
        )
        return result

    async def check_signals(self, latest_row: pd.Series, active_trades: Dict) -> Dict[str, Any]:
        signals = {'signal_type': None, 'entry_reason': '', 'exit_reason': '', 'strategy_name': self.name}
        pair_symbol = latest_row.get('symbol', '')
        close_price = latest_row['close']
        rsi25 = latest_row.get('rsi25', 0)
        rsi100 = latest_row.get('rsi100', 0)
        cci40_cross_up = latest_row.get('cci40_cross_up', False)
        cci100_cross_up = latest_row.get('cci100_cross_up', False)
        rsi25_cross_up = latest_row.get('rsi25_cross_up', False)
        ema14 = latest_row.get('ema14', 0)

        long_condition = (
            self.use_long_signals and
            rsi25 > rsi100 and
            rsi25_cross_up and
            cci40_cross_up and
            cci100_cross_up
        )

        if long_condition:
            signals['signal_type'] = 'long'
            signals['entry_reason'] = f"Long: RSI25>{rsi25:.2f} > RSI100>{rsi100:.2f}, RSI/CCI Cross"

        if pair_symbol in active_trades:
            trade = active_trades[pair_symbol]
            is_long = trade.get('direction') == 'long'
            trade['bars_since_entry'] = trade.get('bars_since_entry', 0) + 1

            if is_long:
                current_profit_pct = ((close_price - trade['entry_price']) / trade['entry_price']) * 100 * trade.get('leverage', 1)
                if current_profit_pct >= self.trail_percent:
                    new_stop_loss = ema14
                    if new_stop_loss > trade['stop_loss_price']:
                        trade['stop_loss_price'] = new_stop_loss
                        trade['trail_updated'] = True
                        signals['exit_reason'] = f"Trailing stop updated to EMA14 low: {new_stop_loss:.4f}"

                if close_price <= trade['stop_loss_price']:
                    signals['signal_type'] = 'exit'
                    signals['exit_reason'] = "Trailing Stop Loss Hit"
                elif not (rsi25 > rsi100 and close_price > ema14):
                    signals['signal_type'] = 'exit'
                    signals['exit_reason'] = "RSI or EMA condition reversed"

        return signals
