import pandas as pd
from datetime import datetime, timezone

class BaseExchangeAPI:
    """Abstract base class for exchange API interactions."""
    def __init__(self, credentials, display, db_manager, config):
        self.key = credentials.get('key') if credentials else None
        self.secret = credentials.get('secret') if credentials else None
        self.display = display
        self.db = db_manager
        self.config = config
        self.public_url = ""
        self.private_url = ""

    def get_historical_data(self, pair, interval, limit=200, force_fresh=False):
        raise NotImplementedError("Subclasses must implement get_historical_data.")

    def get_wallet_data(self):
        # In a real implementation, this would fetch from the exchange.
        return [{'currency_short_name': 'USDT', 'balance': '1000.0'}]

    def _format_pair(self, pair, separator=''):
        """Joins the pair with a separator if needed."""
        # This base implementation assumes the pair is already in the correct format
        # or can be simply joined. Specific exchanges can override this.
        if '_' in pair:
            return pair.replace('_', separator)
        return pair

    def _format_dataframe(self, df, column_map):
        """Formats a DataFrame to the bot's standard column names and types."""
        df = df[list(column_map.keys())].rename(columns=column_map)
        for col in df.columns:
            if col != 'open_time':
                df[col] = pd.to_numeric(df[col], errors='coerce')
        # Ensure open_time is parsed correctly
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', errors='coerce')
        return df

    def validate_data_freshness(self, data, pair_symbol, max_age_seconds=None):
        """Generic data freshness validation logic."""
        if not self.config.DATA_FRESHNESS_CHECK_ENABLED:
            return {'is_fresh': True, 'message': 'Freshness check disabled.'}

        max_age = max_age_seconds or self.config.MAX_DATA_AGE_SECONDS
        if data.empty or 'open_time' not in data.columns:
            return {'is_fresh': False, 'message': 'No data or timestamp column.'}

        latest_timestamp = pd.to_datetime(data['open_time'].iloc[-1])
        if latest_timestamp.tzinfo is None:
            latest_timestamp = latest_timestamp.tz_localize('UTC')

        age = (datetime.now(timezone.utc) - latest_timestamp).total_seconds()
        is_fresh = age <= max_age

        return {
            'is_fresh': is_fresh,
            'data_age_seconds': int(age),
            'last_timestamp': latest_timestamp,
            'circuit_breaker_active': False, # This logic would be in HealthMonitor
            'message': f"Data is {'fresh' if is_fresh else 'stale'} ({int(age)}s old)."
        }
