import sqlite3
import queue
import threading
import time
import asyncio
import logging
import pandas as pd
from contextlib import contextmanager

class DatabaseConnectionPool:
    """High-performance database connection pool with proper resource management"""

    def __init__(self, db_path, max_connections=50, timeout=15):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self.pool = queue.Queue(maxsize=max_connections)
        self.active_connections = 0
        self.pool_lock = threading.Lock()
        self.stats = {
            'total_requests': 0, 'pool_hits': 0, 'pool_misses': 0,
            'connections_created': 0, 'connections_closed': 0,
            'timeouts': 0, 'emergency_connections': 0
        }
        self._initialize_pool()

    def _initialize_pool(self):
        for _ in range(min(3, self.max_connections)):
            try:
                conn = self._create_optimized_connection()
                self.pool.put(conn, block=False)
                self.active_connections += 1
                self.stats['connections_created'] += 1
            except Exception as e:
                logging.error(f"Error initializing connection pool: {e}")
                break

    def _create_optimized_connection(self):
        conn = sqlite3.connect(
            self.db_path, timeout=5, check_same_thread=False, isolation_level=None
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-30000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def get_connection(self):
        try:
            return self.pool.get(block=False)
        except queue.Empty:
            with self.pool_lock:
                if self.active_connections < self.max_connections:
                    self.active_connections += 1
                    return self._create_optimized_connection()
            try:
                return self.pool.get(timeout=self.timeout)
            except queue.Empty:
                raise Exception(f"Database connection timeout after {self.timeout}s")

    def return_connection(self, conn):
        if conn:
            try:
                self.pool.put(conn, block=False)
            except queue.Full:
                self._close_connection(conn)

    def _close_connection(self, conn):
        try:
            conn.close()
            with self.pool_lock:
                self.active_connections -= 1
        except Exception as e:
            logging.error(f"Error closing database connection: {e}")

    def close_all(self):
        while not self.pool.empty():
            try:
                conn = self.pool.get(block=False)
                self._close_connection(conn)
            except queue.Empty:
                break

    @contextmanager
    def get_connection_context(self):
        """Context manager for database connections."""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                self.return_connection(conn)

class DatabaseManager:
    """Manages all database interactions for the trading bot."""
    def __init__(self, db_path, display=None):
        self.pool = DatabaseConnectionPool(db_path)
        self.display = display
        self._initialize_db()

    def _initialize_db(self):
        """Creates necessary tables if they don't exist."""
        try:
            with self.pool.get_connection_context() as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS candles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pair TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        open_time DATETIME NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL NOT NULL,
                        UNIQUE(pair, timeframe, open_time)
                    )
                ''')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_candles_pair_tf_time ON candles(pair, timeframe, open_time DESC)')

                conn.execute('''
                    CREATE TABLE IF NOT EXISTS connectivity_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status TEXT NOT NULL,
                        response_time_ms INTEGER,
                        test_method TEXT,
                        target TEXT,
                        error_message TEXT
                    )
                ''')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_connectivity_timestamp ON connectivity_history(timestamp)')

                logging.info("Database initialized successfully.")
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            if self.display:
                self.display.add_log(f"DB Init Error: {e}")

    def save_candle_data(self, pair, timeframe, df):
        """Saves a DataFrame of candle data to the database."""
        if df.empty:
            return
        try:
            with self.pool.get_connection_context() as conn:
                df_copy = df.copy()
                df_copy['pair'] = pair
                df_copy['timeframe'] = timeframe
                df_copy['open_time'] = pd.to_datetime(df_copy['open_time'])

                # Use a transaction for bulk inserts
                cur = conn.cursor()
                tuples = [tuple(x) for x in df_copy[['pair', 'timeframe', 'open_time', 'open', 'high', 'low', 'close', 'volume']].to_numpy()]
                cur.executemany("INSERT OR IGNORE INTO candles (pair, timeframe, open_time, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)", tuples)
                conn.commit()
        except Exception as e:
            logging.error(f"Error saving candle data for {pair} ({timeframe}): {e}")

    def get_candle_data(self, pair, timeframe, limit=200):
        """Retrieves candle data from the database."""
        try:
            with self.pool.get_connection_context() as conn:
                query = "SELECT * FROM candles WHERE pair = ? AND timeframe = ? ORDER BY open_time DESC LIMIT ?"
                df = pd.read_sql_query(query, conn, params=(pair, timeframe, limit))
                if not df.empty:
                    df['open_time'] = pd.to_datetime(df['open_time'])
                    return df.sort_values('open_time').reset_index(drop=True)
        except Exception as e:
            logging.error(f"Error getting candle data for {pair} ({timeframe}): {e}")
        return pd.DataFrame()

    def get_latest_candle_time(self, pair_symbol, timeframe='15m'):
        """Gets the timestamp of the most recent candle for a pair."""
        try:
            with self.pool.get_connection_context() as conn:
                cursor = conn.execute("SELECT MAX(open_time) FROM candles WHERE pair = ? AND timeframe = ?", (pair_symbol, timeframe))
                result = cursor.fetchone()
                return pd.to_datetime(result[0]) if result and result[0] else None
        except Exception as e:
            logging.error(f"Error getting latest candle time for {pair_symbol}: {e}")
            return None

    def get_dashboard_data_batch(self, all_pairs, timeframe, limit=100):
        """Optimized batch query for dashboard data."""
        candles = []
        try:
            with self.pool.get_connection_context() as conn:
                for pair in all_pairs:
                    query = "SELECT * FROM candles WHERE pair = ? AND timeframe = ? ORDER BY open_time DESC LIMIT ?"
                    df = pd.read_sql_query(query, conn, params=(pair, timeframe, limit))
                    if not df.empty:
                        candles.extend(df.to_dict('records'))
        except Exception as e:
            logging.error(f"Error in dashboard batch query: {e}")

        return {'candles': candles, 'trades': []}

    def clear_cache_for_pair(self, pair_symbol):
        """This is a placeholder as caching is not at the DB level."""
        logging.info(f"DB cache clear called for {pair_symbol} (no action taken).")
        return 0
