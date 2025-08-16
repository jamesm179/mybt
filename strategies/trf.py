import pandas as pd
import talib
import logging
import numpy as np
from typing import Dict, Any

from strategies.base import Strategy
from config.config import Config

class TRFStrategy(Strategy):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.per1 = config.get('per1', 27)
        self.mult1 = config.get('mult1', 2)
        self.per2 = config.get('per2', 55)
        self.mult2 = config.get('mult2', 3)
        self.use_long_signals = config.get('use_long_signals', True)
        self.use_short_signals = config.get('use_short_signals', True)
        self.desired_take_profit = config.get('desired_take_profit', 10.0)
        self.desired_stop_loss = config.get('desired_stop_loss', 5.0)
        self.cci_length = config.get('cci_length', 100)
        self.ema_length = config.get('ema_length', 200)
        self.cci_long_level = config.get('cci_long_level', 100)
        self.cci_short_level = config.get('cci_short_level', -100)
        self.use_trending_signals = config.get('use_trending_signals', True)
        self.use_reversal_signals = config.get('use_reversal_signals', True)

    def smooth_range(self, series, period, multiplier):
        if len(series) < period * 2:
            return pd.Series(np.zeros(len(series)), index=series.index)
        wper = period * 2 - 1
        values = series.values
        abs_diff = np.abs(np.diff(values, prepend=values[0]))
        abs_diff_series = pd.Series(abs_diff, index=series.index)
        avg_range = abs_diff_series.ewm(span=period, adjust=False, min_periods=period).mean()
        smooth_range = avg_range.ewm(span=wper, adjust=False, min_periods=wper).mean() * multiplier
        return smooth_range

    def range_filter(self, series, range_series):
        result = series.copy()
        for i in range(1, len(series)):
            prev_val = result.iloc[i-1]
            curr_val = series.iloc[i]
            curr_range = range_series.iloc[i]
            if curr_val > prev_val:
                if curr_val - curr_range < prev_val:
                    result.iloc[i] = prev_val
                else:
                    result.iloc[i] = curr_val - curr_range
            else:
                if curr_val + curr_range > prev_val:
                    result.iloc[i] = prev_val
                else:
                    result.iloc[i] = curr_val + curr_range
        return result

    def get_indicators(self, df: pd.DataFrame, shared_indicators=None) -> pd.DataFrame:
        if df.empty:
            return df
        result = df.copy()
        required_length = max(self.per1 * 2, self.per2 * 2, self.ema_length, self.cci_length)
        if len(result) < required_length:
            logging.warning(f"Insufficient data for TRF strategy: {len(result)} candles")
            return result
        source = result['close']
        if shared_indicators and 'ema200' in shared_indicators and 'cci100' in shared_indicators:
            result['ema4'] = shared_indicators['ema200']
            result['CCI'] = shared_indicators['cci100']
        else:
            close_array = result['close'].values
            high_array = result['high'].values
            low_array = result['low'].values
            result['ema4'] = talib.EMA(close_array, timeperiod=self.ema_length)
            result['CCI'] = talib.CCI(high_array, low_array, close_array, timeperiod=self.cci_length)
        result['smrng1'] = self.smooth_range(source, self.per1, self.mult1)
        result['smrng2'] = self.smooth_range(source, self.per2, self.mult2)
        result['smrng'] = (result['smrng1'] + result['smrng2']) / 2
        result['filt'] = source.copy()
        filt_values = result['filt'].values
        source_values = source.values
        smrng_values = result['smrng'].values
        for i in range(1, len(result)):
            prev_filt = filt_values[i-1]
            curr_source = source_values[i]
            curr_range = smrng_values[i]
            if curr_source > prev_filt:
                if curr_source - curr_range < prev_filt:
                    filt_values[i] = prev_filt
                else:
                    filt_values[i] = curr_source - curr_range
            else:
                if curr_source + curr_range > prev_filt:
                    filt_values[i] = prev_filt
                else:
                    filt_values[i] = curr_source + curr_range
        result['filt'] = filt_values
        upward = np.zeros(len(result))
        downward = np.zeros(len(result))
        for i in range(1, len(result)):
            curr_filt = filt_values[i]
            prev_filt = filt_values[i-1]
            if curr_filt > prev_filt:
                upward[i] = upward[i-1] + 1
                downward[i] = 0
            elif curr_filt < prev_filt:
                upward[i] = 0
                downward[i] = downward[i-1] + 1
            else:
                upward[i] = upward[i-1]
                downward[i] = downward[i-1]
        result['upward'] = upward
        result['downward'] = downward
        result['hband'] = result['filt'] + result['smrng']
        result['lband'] = result['filt'] - result['smrng']
        source_shift = source.shift(1)
        result['long_cond'] = ((source > result['filt']) & (source > source_shift) & (result['upward'] > 0)) | ((source > result['filt']) & (source < source_shift) & (result['upward'] > 0))
        result['short_cond'] = ((source < result['filt']) & (source < source_shift) & (result['downward'] > 0)) | ((source < result['filt']) & (source > source_shift) & (result['downward'] > 0))
        cond_ini = np.zeros(len(result))
        for i in range(1, len(result)):
            if result['long_cond'].iloc[i]:
                cond_ini[i] = 1
            elif result['short_cond'].iloc[i]:
                cond_ini[i] = -1
            else:
                cond_ini[i] = cond_ini[i-1]
        result['cond_ini'] = cond_ini
        result['Cl_1'] = self.cci_long_level
        result['Clp_1'] = self.cci_short_level
        result['long_signal'] = result['long_cond'] & (result['cond_ini'].shift(1) == -1)
        result['short_signal'] = result['short_cond'] & (result['cond_ini'].shift(1) == 1)
        result['rlong'] = (result['close'] < result['ema4']) & (result['CCI'] > result['Clp_1']) & result['long_cond'] & (result['cond_ini'].shift(1) == -1)
        result['rshort'] = (result['close'] > result['ema4']) & (result['CCI'] < result['Cl_1']) & result['short_cond'] & (result['cond_ini'].shift(1) == 1)
        result['tlong'] = (result['close'] > result['ema4']) & (result['CCI'] > result['Clp_1']) & result['long_cond'] & (result['cond_ini'].shift(1) == -1)
        result['tshort'] = (result['close'] < result['ema4']) & (result['CCI'] < result['Cl_1']) & result['short_cond'] & (result['cond_ini'].shift(1) == 1)
        return result

    async def check_signals(self, latest_row: pd.Series, active_trades: Dict) -> Dict[str, Any]:
        signals = {'signal_type': None, 'entry_reason': '', 'exit_reason': '', 'strategy_name': self.name}
        pair_symbol = latest_row.get('symbol', '')
        close_price = latest_row['close']
        if self.use_long_signals and self.use_trending_signals and latest_row.get('tlong', False):
            signals['signal_type'] = 'long'
            signals['entry_reason'] = f"TRF Trending Long: Price({close_price:.4f}) > EMA({latest_row['ema4']:.4f}), CCI({latest_row['CCI']:.1f}) > {latest_row['Clp_1']}"
        elif self.use_long_signals and self.use_reversal_signals and latest_row.get('rlong', False):
            signals['signal_type'] = 'long'
            signals['entry_reason'] = f"TRF Reversal Long: Price({close_price:.4f}) < EMA({latest_row['ema4']:.4f}), CCI({latest_row['CCI']:.1f}) > {latest_row['Clp_1']}"
        elif self.use_short_signals and self.use_trending_signals and latest_row.get('tshort', False):
            signals['signal_type'] = 'short'
            signals['entry_reason'] = f"TRF Trending Short: Price({close_price:.4f}) < EMA({latest_row['ema4']:.4f}), CCI({latest_row['CCI']:.1f}) < {latest_row['Cl_1']}"
        elif self.use_short_signals and self.use_reversal_signals and latest_row.get('rshort', False):
            signals['signal_type'] = 'short'
            signals['entry_reason'] = f"TRF Reversal Short: Price({close_price:.4f}) > EMA({latest_row['ema4']:.4f}), CCI({latest_row['CCI']:.1f}) < {latest_row['Cl_1']}"
        elif self.use_long_signals and latest_row.get('long_signal', False):
            signals['signal_type'] = 'long'
            signals['entry_reason'] = f"TRF Basic Long: Price({close_price:.4f}) > Filter({latest_row['filt']:.4f})"
        elif self.use_short_signals and latest_row.get('short_signal', False):
            signals['signal_type'] = 'short'
            signals['entry_reason'] = f"TRF Basic Short: Price({close_price:.4f}) < Filter({latest_row['filt']:.4f})"

        if pair_symbol in active_trades:
            trade = active_trades[pair_symbol]
            is_long = trade.get('direction') == 'long'
            entry_price = trade.get('entry_price', 0)
            leverage = trade.get('leverage', 1)
            trade['bars_since_entry'] = trade.get('bars_since_entry', 0) + 1
            current_profit_pct = ((close_price - entry_price) / entry_price) * 100 * leverage if is_long else ((entry_price - close_price) / entry_price) * 100 * leverage

            if hasattr(Config, 'TP_SL_OVERRIDE_ENABLED') and Config.TP_SL_OVERRIDE_ENABLED:
                override_tp_decimal = Config.OVERRIDE_TAKE_PROFIT / leverage / 100
                override_sl_decimal = Config.OVERRIDE_STOP_LOSS / leverage / 100
                take_profit_price = entry_price * (1 + override_tp_decimal) if is_long else entry_price * (1 - override_tp_decimal)
                stop_loss_price = entry_price * (1 - override_sl_decimal) if is_long else entry_price * (1 + override_sl_decimal)
            else:
                take_profit_price = trade.get('take_profit_price', 0)
                stop_loss_price = trade.get('stop_loss_price', 0)

            if (is_long and close_price >= take_profit_price) or (not is_long and close_price <= take_profit_price):
                signals['signal_type'] = 'exit'
                signals['exit_reason'] = f"Take Profit Hit: Price({close_price:.4f}) vs TP({take_profit_price:.4f}), P/L: {current_profit_pct:.2f}%"
            elif (is_long and close_price <= stop_loss_price) or (not is_long and close_price >= stop_loss_price):
                signals['signal_type'] = 'exit'
                signals['exit_reason'] = f"Stop Loss Hit: Price({close_price:.4f}) vs SL({stop_loss_price:.4f}), P/L: {current_profit_pct:.2f}%"
            elif (is_long and close_price < latest_row['filt']) or (not is_long and close_price > latest_row['filt']):
                signals['signal_type'] = 'exit'
                signals['exit_reason'] = f"TRF Exit: Price crossed Filter({latest_row['filt']:.4f}), P/L: {current_profit_pct:.2f}%"
        return signals
