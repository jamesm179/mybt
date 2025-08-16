import os
import pandas as pd
import logging
from datetime import datetime, timedelta
import asyncio
import csv

AIOFILES_AVAILABLE = True
try:
    import aiofiles
except ImportError:
    AIOFILES_AVAILABLE = False

class PerformanceTracker:
    def __init__(self, trade_log_file, display_manager):
        self.trade_log_file = trade_log_file
        self.display = display_manager
        self.trade_logs_dir = 'logs'

    def get_pair_performance(self):
        try:
            if not os.path.exists(self.trade_log_file):
                return {}
            df = pd.read_csv(self.trade_log_file)
            if 'Status' not in df.columns or 'P/L%' not in df.columns or 'Pair' not in df.columns:
                return {}

            df['Status'] = df['Status'].astype(str)
            closed_trades = df[df['Status'].str.contains('Closed', case=False, na=False)].copy()
            if closed_trades.empty:
                return {}

            pair_performance = {}
            for pair, group in closed_trades.groupby('Pair'):
                try:
                    group['P/L%'] = pd.to_numeric(group['P/L%'], errors='coerce')
                    pair_performance[pair] = {
                        'avg_pl': group['P/L%'].mean(),
                        'num_trades': len(group)
                    }
                except Exception as e:
                    logging.error(f"Error calculating performance for {pair}: {e}")
            return pair_performance
        except Exception as e:
            logging.error(f"Error getting pair performance: {e}")
            return {}

    def get_all_trade_history(self, days_limit=30):
        try:
            all_files = [os.path.join(self.trade_logs_dir, f) for f in os.listdir(self.trade_logs_dir) if f.startswith('trades_') and f.endswith('.csv')]
            all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            cutoff_date = datetime.now() - timedelta(days=days_limit)

            all_trades = []
            for file_path in all_files:
                if datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff_date:
                    continue
                try:
                    df = pd.read_csv(file_path)
                    df['log_file'] = os.path.basename(file_path)
                    all_trades.append(df)
                except Exception as e:
                    logging.error(f"Error reading trade log file {file_path}: {e}")

            if not all_trades:
                return pd.DataFrame()

            combined_df = pd.concat(all_trades, ignore_index=True)
            if 'Timestamp' in combined_df.columns:
                combined_df['Timestamp'] = pd.to_datetime(combined_df['Timestamp'])
                combined_df = combined_df.sort_values('Timestamp', ascending=False)

            if 'Reason' in combined_df.columns:
                combined_df['Strategy'] = combined_df['Reason'].apply(
                    lambda x: x.split(':')[0] if isinstance(x, str) and ':' in x else 'Unknown'
                )
            return combined_df
        except Exception as e:
            logging.error(f"Error getting trade history: {e}")
            return pd.DataFrame()

class AsyncTradeLogger:
    def __init__(self, log_file_path):
        self.log_file = log_file_path
        self.write_queue = asyncio.Queue()
        self.worker_task = None
        self.is_running = False
        self._headers_written = False
        self.headers = ["Trade ID", "Timestamp", "Exchange", "Action", "Pair", "Price", "Amount", "Balance", "P/L%", "Reason", "Direction", "SL", "TP", "Status"]
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    async def start(self):
        if self.is_running: return
        self.is_running = True
        if not self._headers_written:
            try:
                if AIOFILES_AVAILABLE:
                    async with aiofiles.open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                        await f.write(','.join(f'"{h}"' for h in self.headers) + '\n')
                else:
                    with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                        csv.writer(f).writerow(self.headers)
                self._headers_written = True
            except Exception as e:
                logging.error(f"Failed to initialize trade log file: {e}")
                raise
        self.worker_task = asyncio.create_task(self._write_worker())

    async def stop(self):
        if not self.is_running: return
        self.is_running = False
        if not self.write_queue.empty():
            await self.write_queue.join()
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def log_trade_async(self, exchange, action, pair, price, amount, balance, profit_pct, reason, direction, stop_loss_price=None, take_profit_price=None, trade_id=None, status="Active"):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        trade_data = {
            'trade_id': trade_id or f"{timestamp}_{pair}_{action}", 'timestamp': timestamp,
            'exchange': exchange, 'action': action, 'pair': pair,
            'price': f"{price:.6f}" if price else "0.0",
            'amount': f"{amount:.2f}" if amount else "0.0",
            'balance': f"{balance:.2f}" if balance else "0.0",
            'profit_pct': f"{profit_pct:.2f}" if profit_pct is not None else "N/A",
            'reason': reason or "N/A", 'direction': direction or "N/A",
            'stop_loss': f"{stop_loss_price:.6f}" if stop_loss_price else "N/A",
            'take_profit': f"{take_profit_price:.6f}" if take_profit_price else "N/A",
            'status': status
        }
        await self.write_queue.put(trade_data)

    async def _write_worker(self):
        while self.is_running:
            try:
                trade_data = await asyncio.wait_for(self.write_queue.get(), timeout=1.0)
                await self._write_trade_data(trade_data)
                self.write_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"Error in trade log write worker: {e}")

    async def _write_trade_data(self, trade_data):
        try:
            row_data = [
                trade_data['trade_id'],
                trade_data['timestamp'],
                trade_data['exchange'],
                trade_data['action'],
                trade_data['pair'],
                trade_data['price'],
                trade_data['amount'],
                trade_data['balance'],
                trade_data['profit_pct'],
                trade_data['reason'],
                trade_data['direction'],
                trade_data['stop_loss'],
                trade_data['take_profit'],
                trade_data['status']
            ]

            if AIOFILES_AVAILABLE:
                async with aiofiles.open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    await f.write(','.join(f'"{str(field)}"' for field in row_data) + '\n')
            else:
                await asyncio.get_event_loop().run_in_executor(None, self._write_sync, row_data)
        except Exception as e:
            logging.error(f"Failed to write trade data: {e}")

    def _write_sync(self, row_data):
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(row_data)
        except Exception as e:
            logging.error(f"Synchronous trade write failed: {e}")
