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

    def update_pair_data(self, pair_symbol, strategy_dfs):
        if not strategy_dfs or Config.DISPLAY_STRATEGY not in strategy_dfs:
            return
        processed_data = strategy_dfs[Config.DISPLAY_STRATEGY]
        if processed_data is not None and not processed_data.empty:
            self.pair_data[pair_symbol] = processed_data
            self.last_update = datetime.now()

    def create_dashboard_layout(self):
        return html.Div([
            dcc.Interval(id='refresh-interval', interval=Config.REFRESH_INTERVAL * 1000, n_intervals=0),
            html.Div(id='dashboard-content')
        ])

    def register_callbacks(self):
        @self.app.callback(
            Output('dashboard-content', 'children'),
            Input('refresh-interval', 'n_intervals')
        )
        def update_dashboard_content(n):
            # This is a simplified dashboard layout. The full implementation is complex.
            header = self.create_header()
            return html.Div([
                html.H1(header['title']),
                html.P(f"Last Update: {header['last_update']}"),
                # In a real scenario, we'd have many more components here.
                # For now, this proves the structure works.
                html.H3("Active Trades"),
                html.Div(id='trades-table')
            ])

        @self.app.callback(
            Output('trades-table', 'children'),
            Input('refresh-interval', 'n_intervals')
        )
        def update_trades_table(n):
            trades = self.create_trade_data()
            if not trades:
                return html.P("No active trades.")

            table_header = [html.Thead(html.Tr([html.Th(col) for col in trades[0].keys()]))]
            table_body = [html.Tbody([
                html.Tr([html.Td(trade[col]) for col in trade.keys()]) for trade in trades
            ])]
            return dbc.Table(table_header + table_body, bordered=True, striped=True, hover=True)

    def create_header(self):
        return {
            'title': f"SNIPER BOT V1 ({'Paper' if Config.PAPER_TRADING else 'Live'})",
            'last_update': self.last_update.strftime('%H:%M:%S'),
        }

    def create_trade_data(self):
        trades_data = []
        if not hasattr(self.engine, 'active_trades'):
            return []
        for exchange, strats in self.engine.active_trades.items():
            for strat, trades in strats.items():
                for symbol, trade in trades.items():
                    # Simplified data for now
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
