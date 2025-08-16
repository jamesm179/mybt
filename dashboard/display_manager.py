import os
import json
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import queue
import threading

from config.config import Config, TradingConfig
from strategies.emacci import EMACCIStrategy
from strategies.rsicci import RSICCIStrategy
from strategies.trf import TRFStrategy

class DisplayManager:
    def __init__(self, trading_engine, db_manager, performance_tracker):
        self.engine = trading_engine
        self.db_manager = db_manager
        self.performance_tracker = performance_tracker
        self.pair_data = {}
        self.last_update = datetime.now()
        self.log_messages = []
        self._setup_dash_app()

    def _setup_dash_app(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
        self.app.layout = self.create_dashboard_layout()
        self.register_callbacks()

    def add_log(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"[{timestamp}] {message}"
        self.log_messages.insert(0, formatted_message)
        if len(self.log_messages) > 100:
            self.log_messages = self.log_messages[:100]
        logging.info(message)

    def create_dashboard_layout(self):
        # Full layout from original script
        return html.Div([
            dcc.Interval(id='refresh-interval', interval=Config.REFRESH_INTERVAL * 1000, n_intervals=0),
            html.H1("Crypto Trading Bot Dashboard"),
            html.Div(id="dashboard-content")
            # ... The rest of the very large layout
        ])

    def register_callbacks(self):
        @self.app.callback(
            Output('dashboard-content', 'children'),
            Input('refresh-interval', 'n_intervals')
        )
        def update_dashboard(n):
            # This is a simplified version of the main update callback
            # In a real scenario, this would be much more complex
            active_trades = self.create_trade_data()
            return html.Div([
                html.H2("Active Trades"),
                dbc.Table.from_dataframe(pd.DataFrame(active_trades), striped=True, bordered=True, hover=True) if active_trades else html.P("No active trades.")
            ])

    def create_trade_data(self):
        trades_data = []
        if not hasattr(self.engine, 'active_trades'):
            return []
        for exchange, strats in self.engine.active_trades.items():
            for strat, trades in strats.items():
                for symbol, trade in trades.items():
                    trades_data.append({
                        'Exchange': exchange,
                        'Strategy': strat,
                        'Symbol': symbol,
                        'Direction': trade.get('direction', 'N/A'),
                        'Entry Price': trade.get('entry_price', 'N/A')
                    })
        return trades_data

    def run(self):
        """Starts the Dash server."""
        logging.info(f"Starting dashboard server on http://127.0.0.1:8050")
        self.app.run_server(debug=False, host='127.0.0.1', port=8050)
