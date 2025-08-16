import dash_bootstrap_components as dbc

class Config:
    """
    Master configuration class for the trading bot.
    These are default values that can be overridden by `bot_settings.json`.
    """
    # General Settings
    PAPER_TRADING = True
    AUTO_TRADING = True
    AUTO_OPEN_BROWSER = True
    SETTINGS_PASSWORD = "admin"
    REFRESH_INTERVAL = 15

    # Display & UI
    DISPLAY_STRATEGY = 'main_strategy'
    CANDLE_HISTORY_LIMIT = 200
    MIN_CANDLES_FOR_TRADING = 50
    CURRENT_THEME = 'dark'
    THEMES = {
        'dark': {'name': 'Dark Theme', 'stylesheet': dbc.themes.DARKLY, 'theme_class': 'theme-dark', 'bg_color': '#222', 'text_color': '#fff', 'card_bg': '#333', 'card_text': '#fff', 'table_bg': '#444', 'table_text': '#fff', 'table_header_bg': '#1a1a1a', 'table_header_text': '#fff', 'table_hover_bg': '#555', 'positive_color': '#00ff00', 'negative_color': '#ff0000', 'neutral_color': '#ffff00', 'link_color': '#0d6efd', 'hover_color': '#2a9fd6', 'font_family': "'Roboto', sans-serif", 'font_size': '14px', 'heading_font_family': "'Roboto Condensed', sans-serif", 'border_color': '#444'},
        'light': {'name': 'Light Theme', 'stylesheet': dbc.themes.LITERA, 'theme_class': 'theme-light', 'bg_color': '#fff', 'text_color': '#212529', 'card_bg': '#f8f9fa', 'card_text': '#212529', 'table_bg': '#fff', 'table_text': '#212529', 'table_header_bg': '#e9ecef', 'table_header_text': '#495057', 'table_hover_bg': '#f8f9fa', 'positive_color': '#198754', 'negative_color': '#dc3545', 'neutral_color': '#6c757d', 'link_color': '#0d6efd', 'hover_color': '#0a58ca', 'font_family': "'Open Sans', sans-serif", 'font_size': '14px', 'heading_font_family': "'Montserrat', sans-serif", 'border_color': '#dee2e6'},
        'blue': {'name': 'Blue Theme', 'stylesheet': dbc.themes.CYBORG, 'theme_class': 'theme-blue', 'bg_color': '#0d3a58', 'text_color': '#fff', 'card_bg': '#0a2d44', 'card_text': '#fff', 'table_bg': '#0a2d44', 'table_text': '#fff', 'table_header_bg': '#051c2c', 'table_header_text': '#fff', 'table_hover_bg': '#164b6e', 'positive_color': '#2a9fd6', 'negative_color': '#ff6b6b', 'neutral_color': '#f8f9fa', 'link_color': '#2a9fd6', 'hover_color': '#58b3d8', 'font_family': "'Source Sans Pro', sans-serif", 'font_size': '14px', 'heading_font_family': "'Lato', sans-serif", 'border_color': '#164b6e'}
    }
    CURRENT_TIMEFRAME = '15m'
    SUPPORTED_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d']
    TIMEFRAME_LABELS = {tf: tf.replace('m', ' Min').replace('h', ' Hr').replace('d', ' Day') for tf in SUPPORTED_TIMEFRAMES}
    FORCE_DATA_REFRESH_ON_TIMEFRAME_CHANGE = True

    # Trading Logic
    ACTIVE_STRATEGIES = ['main_strategy', 'trf_strategy']
    STRATEGIES = {
        'main_strategy': {'ema50_period': 50, 'ema200_period': 200, 'cci1_length': 100, 'cci2_length': 40, 'cci_long_level': 100, 'cci_short_level': -100, 'use_long_signals': True, 'use_short_signals': True, 'use_cci1': True, 'use_cci2': True, 'desired_take_profit': 7.0, 'desired_stop_loss': 5.0},
        'rsi_cci_strategy': {'rsi25_period': 25, 'rsi100_period': 100, 'cci40_period': 40, 'cci100_period': 100, 'rsi_cross_level': 60, 'cci40_cross_level': 200, 'cci100_cross_level': -45, 'ema14_period': 14, 'trail_percent': 12.0, 'use_long_signals': True, 'use_short_signals': False},
        'trf_strategy': {'per1': 27, 'mult1': 2, 'per2': 55, 'mult2': 3, 'use_long_signals': True, 'use_short_signals': True, 'desired_take_profit': 10.0, 'desired_stop_loss': 5.0, 'cci_length': 100, 'ema_length': 200, 'cci_long_level': 100, 'cci_short_level': -100, 'use_trending_signals': True, 'use_reversal_signals': True}
    }
    MANUAL_TRADING_PAIRS = []
    TP_SL_OVERRIDE_ENABLED = False
    OVERRIDE_TAKE_PROFIT = 7.0
    OVERRIDE_STOP_LOSS = 5.0

    # Exchange & API
    SELECTED_EXCHANGE = 'binance'
    SUPPORTED_EXCHANGES = ['coindcx', 'binance', 'bitget']
    ACTIVE_EXCHANGES = ['binance', 'bitget']
    EXCHANGE_CREDENTIALS = {}

    # Trailing Stop
    TRAILING_STOP_ENABLED = True
    TRAILING_METHOD = "percentage"
    TRAILING_ACTIVATION_PROFIT = 20.0
    INITIAL_TRAIL_DISTANCE = 10.0
    TRAIL_TIGHTENING_STEP = 6.0
    PROFIT_INCREMENT_THRESHOLD = 10.0

    # Health & Monitoring
    CONNECTIVITY_MONITORING_ENABLED = True
    CONNECTIVITY_TEST_INTERVAL = 60
    CONNECTIVITY_PING_TIMEOUT = 2000
    CONNECTIVITY_HTTP_TIMEOUT = 5
    CONNECTIVITY_FAILURE_THRESHOLD = 3
    CONNECTIVITY_NOTIFICATIONS_ENABLED = True

    # Data Freshness
    DATA_FRESHNESS_CHECK_ENABLED = True
    MAX_DATA_AGE_SECONDS = 300
    STALE_DATA_CIRCUIT_BREAKER_THRESHOLD = 5
    REQUIRE_FRESH_DATA_ON_STARTUP = True
    STARTUP_DATA_VALIDATION_TIMEOUT = 180
    MIN_DATA_FRESHNESS_FOR_TRADING = 600

    # Notifications
    ENABLE_SOUND_NOTIFICATIONS = True
    TELEGRAM_TOKEN = None
    TELEGRAM_CHAT_ID = None

    # Database
    DB_PATH = 'trading_bot.db'

class TradingConfig:
    """Contains trading-specific parameters."""
    DEFAULT_PAIRS = [
        "BTCUSDT", "ETHUSDT", "XRPUSDT", "LTCUSDT",
        "ADAUSDT", "SOLUSDT", "DOGEUSDT"
    ]
    LEVERAGE = 10
    MAX_RISK_USDT = 100
    RISK_PERCENT = 0.02
    MIN_ORDER_SIZE = 10

    @staticmethod
    def calculate_tp_sl(desired_tp, desired_sl, leverage, strategy_name):
        if leverage == 0: return (None, None)
        return desired_tp / 100 / leverage, desired_sl / 100 / leverage
