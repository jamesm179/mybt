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
import asyncio

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
        # This is the full layout from the original script
        return html.Div([
            dcc.Interval(id='refresh-interval', interval=Config.REFRESH_INTERVAL * 1000, n_intervals=0),
            html.H1("Crypto Trading Bot Dashboard"),
            html.Div(id="dashboard-content"),
            html.Div(id='trades-table'),
            html.Div(id='header-title'),
            html.Div(id='last-update-time'),
            html.Div(id='status-indicator'),
            html.Div(id='bot-status-card'),
            html.Div(id='performance-card'),
            html.Div(id='api-status-card'),
            html.Div(id='technicals-table'),
            html.Div(id='candles-table'),
            html.Div(id='log-container'),
            html.Div(id='dashboard-data-store'),
        ])

    def register_callbacks(self):
        @self.app.callback(
            [Output('header-title', 'children'),
             Output('last-update-time', 'children'),
             Output('status-indicator', 'children'),
             Output('bot-status-card', 'children'),
             Output('performance-card', 'children'),
             Output('api-status-card', 'children'),
             Output('technicals-table', 'children'),
             Output('trades-table', 'children'),
             Output('candles-table', 'children'),
             Output('log-container', 'children'),
             Output('dashboard-data-store', 'children')],
            [Input('refresh-interval', 'n_intervals')]
        )
        def update_dashboard(n):
            # Simplified logic, but with all outputs to prevent KeyError
            header = self.create_header()
            trades = self.create_trade_data()
            logs = self.create_logs_data()

            header_title = header.get('title', 'Bot')
            last_update = header.get('last_update', 'N/A')
            status = "OK"
            bot_status = html.P("Bot is running.")
            performance = html.P("Performance data...")
            api_status = html.P("API status...")
            technicals = html.P("Technicals...")
            trades_table = dbc.Table.from_dataframe(pd.DataFrame(trades), striped=True) if trades else html.P("No trades.")
            candles = html.P("Candles...")
            log_div = html.Pre("\n".join(logs))
            data_store = "{}"

            return header_title, last_update, status, bot_status, performance, api_status, technicals, trades_table, candles, log_div, data_store

    def create_header(self):
        return {'title': 'SNIPER BOT V1', 'last_update': datetime.now().strftime('%H:%M:%S')}

    def create_trade_data(self):
        trades_data = []
        if hasattr(self.engine, 'active_trades'):
            for exchange, strats in self.engine.active_trades.items():
                for strat, trades in strats.items():
                    for symbol, trade in trades.items():
                        trades_data.append({'Symbol': symbol, 'Direction': trade.get('direction', 'N/A')})
        return trades_data

    def create_logs_data(self):
        return self.log_messages

    def run(self):
        """Starts the Dash server."""
        logging.info(f"Starting dashboard server on http://127.0.0.1:8050")
        self.app.run_server(debug=False, host='127.0.0.1', port=8050)
