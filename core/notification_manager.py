import asyncio
import logging
import threading
import winsound
import pyttsx3
from telegram import Bot
from telegram.error import TelegramError
from config.config import Config

class NotificationManager:
    def __init__(self):
        self.engine = None
        self.voice_id = None
        self.engine_lock = threading.Lock()
        try:
            logging.info("Initializing text-to-speech engine...")
            self._find_best_voice()
            logging.info("Voice notification system ready")
        except Exception as e:
            logging.error(f"Failed to set up voice notification system: {e}")

    def _find_best_voice(self):
        try:
            temp_engine = pyttsx3.init()
            voices = temp_engine.getProperty('voices')
            for voice in voices:
                if 'zira' in voice.name.lower():
                    self.voice_id = voice.id
                    break
            if not self.voice_id:
                for voice in voices:
                    if 'female' in voice.name.lower():
                        self.voice_id = voice.id
                        break
            if not self.voice_id and voices:
                self.voice_id = voices[0].id
            del temp_engine
        except Exception as e:
            logging.error(f"Error finding voices: {e}")

    def _create_engine(self):
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 145)
            engine.setProperty('volume', 1.0)
            if self.voice_id:
                engine.setProperty('voice', self.voice_id)
            return engine
        except Exception as e:
            logging.error(f"Failed to create speech engine: {e}")
            return None

    def play_notification_sound(self, sound_type="default"):
        try:
            if sound_type == "long":
                winsound.Beep(1200, 500)
            elif sound_type == "short":
                winsound.Beep(800, 500)
            else:
                winsound.Beep(1000, 500)
        except Exception as e:
            logging.error(f"Failed to play notification sound: {e}")
            print("\a", flush=True)

    def speak_notification(self, text):
        def speak_thread():
            with self.engine_lock:
                try:
                    engine = self._create_engine()
                    if not engine: return
                    engine.say(text)
                    engine.runAndWait()
                    del engine
                except Exception as e:
                    logging.error(f"Error during speech: {e}")
        thread = threading.Thread(target=speak_thread)
        thread.daemon = True
        thread.start()

    def notify_trade(self, direction, pair):
        if not Config.ENABLE_SOUND_NOTIFICATIONS:
            return
        self.play_notification_sound(sound_type=direction)
        formatted_pair = pair.replace('/', ' ')
        if direction.lower() == "test":
            text = "Hello, I will notify you when trades are taken."
        elif direction.lower() == "long":
            text = f"Yay! Long trade taken in {formatted_pair}. Let's go to the moon!"
        elif direction.lower() == "short":
            text = f"Oh my! Short trade taken in {formatted_pair}. Time to ride the wave down!"
        else:
            text = f"Trade {direction} taken in {formatted_pair}"
        self.speak_notification(text)

class TelegramNotifier:
    def __init__(self, display_manager):
        self.display = display_manager
        self.bot = Bot(token=Config.TELEGRAM_TOKEN) if Config.TELEGRAM_TOKEN else None
        self.last_signal_time = {}
        self.notification_manager = NotificationManager()

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        if not self.bot: return
        for attempt in range(3):
            try:
                await self.bot.send_message(chat_id=Config.TELEGRAM_CHAT_ID, text=text, parse_mode=parse_mode)
                return
            except Exception as e:
                logging.error(f"Telegram send error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(5)

    async def send_signal(self, pair: str, signal_type: str, price: float, amount: float, balance: float, reason: str, direction: str, stop_loss_price: float, take_profit_price: float, profit_pct: float = None):
        from datetime import datetime
        current_time = datetime.now()
        pair_key = f"{pair}_{signal_type}"
        if pair_key in self.last_signal_time and (current_time - self.last_signal_time[pair_key]).seconds < 900:
            return
        self.last_signal_time[pair_key] = current_time
        emoji = "🚀" if signal_type == "BUY" else "🛑" if signal_type == "SELL" else "ℹ️"
        message = (
            f"{emoji} *Sniper Bot V1 Signal (Paper Trade)* {emoji}\n"
            f"*Pair:* {pair}\n"
            f"*Action:* {signal_type} ({direction.upper()})\n"
            f"*Price:* {price:.4f}\n"
            f"*Amount:* {amount:.2f} USDT\n"
            f"*Stop Loss:* {stop_loss_price:.4f}\n"
            f"*Take Profit:* {take_profit_price:.4f}\n"
            f"*Balance:* {balance:.2f} USDT\n"
            f"*Reason:* {reason}\n"
            f"*Time:* {current_time.strftime('%Y-%m-%d %H:%M:%S')} IST"
        )
        if profit_pct is not None:
            message += f"\n*P/L:* {profit_pct:.2f}%"
        await self.send_message(message)
        if signal_type in ["BUY", "SELL"] and "P/L" not in reason:
            trade_direction = "long" if signal_type == "BUY" else "short"
            self.notification_manager.notify_trade(trade_direction, pair)
