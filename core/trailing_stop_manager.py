import logging
from config.config import Config

class TrailingStopManager:
    """Manages dynamic trailing stop-loss functionality"""

    def __init__(self):
        self.trailing_data = {}  # Store trailing stop data for each position

    def calculate_trailing_stop(self, position, current_price, method="percentage"):
        try:
            pair = position.get('pair', '')
            entry_price = float(position.get('entry_price', 0))
            direction = position.get('direction', 'long')
            position_id = position.get('id', f"{pair}_{direction}")

            if entry_price == 0: return None

            profit_pct = ((current_price - entry_price) / entry_price) * 100 if direction == 'long' else ((entry_price - current_price) / entry_price) * 100

            if profit_pct < Config.TRAILING_ACTIVATION_PROFIT: return None

            if position_id not in self.trailing_data:
                self.trailing_data[position_id] = {
                    'activated': True, 'highest_profit': profit_pct,
                    'current_trail_distance': Config.INITIAL_TRAIL_DISTANCE,
                    'last_trail_level': None, 'method': method
                }

            trail_info = self.trailing_data[position_id]
            if profit_pct > trail_info['highest_profit']:
                trail_info['highest_profit'] = profit_pct
                if method == "percentage":
                    profit_above_activation = profit_pct - Config.TRAILING_ACTIVATION_PROFIT
                    tightening_steps = int(profit_above_activation / Config.PROFIT_INCREMENT_THRESHOLD)
                    new_trail_distance = Config.INITIAL_TRAIL_DISTANCE - (tightening_steps * Config.TRAIL_TIGHTENING_STEP)
                    trail_info['current_trail_distance'] = max(new_trail_distance, 1.0)

            if method == "percentage":
                if direction == 'long':
                    high_price = entry_price * (1 + trail_info['highest_profit'] / 100)
                    new_trail_level = high_price * (1 - trail_info['current_trail_distance'] / 100)
                else:
                    low_price = entry_price * (1 - trail_info['highest_profit'] / 100)
                    new_trail_level = low_price * (1 + trail_info['current_trail_distance'] / 100)
            else: # ema
                new_trail_level = current_price * (0.95 if direction == 'long' else 1.05)

            if trail_info['last_trail_level'] is not None:
                if direction == 'long':
                    new_trail_level = max(new_trail_level, trail_info['last_trail_level'])
                else:
                    new_trail_level = min(new_trail_level, trail_info['last_trail_level'])

            trail_info['last_trail_level'] = new_trail_level
            return trail_info
        except Exception as e:
            logging.error(f"Error calculating trailing stop for {position.get('pair', 'unknown')}: {e}")
            return None

    def check_trailing_exit(self, position, current_price):
        try:
            position_id = position.get('id', f"{position.get('pair', '')}_{position.get('direction', 'long')}")
            if position_id not in self.trailing_data: return False
            trail_level = self.trailing_data[position_id].get('last_trail_level')
            if trail_level is None: return False
            return current_price <= trail_level if position.get('direction', 'long') == 'long' else current_price >= trail_level
        except Exception as e:
            logging.error(f"Error checking trailing exit for {position.get('pair', 'unknown')}: {e}")
            return False

    def remove_position(self, position_id):
        if position_id in self.trailing_data:
            del self.trailing_data[position_id]

    def reset_all(self):
        self.trailing_data.clear()
