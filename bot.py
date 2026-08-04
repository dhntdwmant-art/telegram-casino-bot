# ==============================================
# ربات شرط‌بندی و کازینو تلگرام - نسخه کامل
# ویژگی‌ها: زیرمجموعه‌گیری، ماموریت روزانه، برداشت
# جوین اجباری، بازی بین کاربران، کانال گزارشات
# ==============================================

import asyncio
import logging
import sqlite3
import random
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    PreCheckoutQuery, Message, CallbackQuery,
    ChatMemberUpdated, ChatJoinRequest
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.enums import ParseMode, ChatMemberStatus

# ==============================================
# تنظیمات اولیه
# ==============================================

# اطلاعات از Railway
BOT_TOKEN = os.getenv("BOT_TOKEN", "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7548145568"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "09158029769")

# کانال‌های اجباری برای جوین
REQUIRED_CHANNELS = [
    {"id": "gozaresh_taj", "name": "کانال رسمی ربات", "link": "https://t.me/YOUR_CHANNEL_1"},
    {"id": "gozaresh_taj", "name": "گزارشات برداشت", "link": "https://t.me/YOUR_CHANNEL_2"}
]

# کانال گزارشات برداشت
WITHDRAW_LOG_CHANNEL = "@gozaresh_taj"  # یا آیدی عددی با -100

# تنظیمات سکه
COIN_TO_TOMAN = 1000  # هر ۱۰۰ سکه = ۱۰۰,۰۰۰ تومان
MIN_WITHDRAW_COINS = 100  # حداقل ۱۰۰ سکه برای برداشت
MIN_INVITES_FIRST_WITHDRAW = 4  # برای اولین برداشت باید ۴ نفر دعوت کرده باشه

# قیمت‌های بازی
GAME_PRICES = [50, 100, 200, 500, 1000]  # قیمت‌های قابل انتخاب

# ماموریت روزانه
DAILY_MISSION_GAMES = 3  # تعداد بازی برای ماموریت
DAILY_MISSION_REWARD = 50  # جایزه سکه

# اطلاعات کارت به کارت
ADMIN_CARD_NUMBER = "6062561009737464"
ADMIN_CARD_HOLDER = "مجاور"

# ==============================================
# سیستم لاگینگ
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(name)

# ==============================================
# مدیریت پایگاه داده
# ==============================================

class Database:
    """کلاس مدیریت پایگاه داده SQLite"""
    
    def init(self, db_path: str = "casino_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"خطا در دیتابیس: {e}")
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """ایجاد جداول پایگاه داده"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # جدول کاربران
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    balance INTEGER DEFAULT 0,
                    diamonds INTEGER DEFAULT 0,
                    invited_by INTEGER,
                    invite_code TEXT UNIQUE,

total_invites INTEGER DEFAULT 0,
                    total_games INTEGER DEFAULT 0,
                    today_games INTEGER DEFAULT 0,
                    last_game_date TEXT,
                    daily_mission_completed BOOLEAN DEFAULT FALSE,
                    daily_mission_claimed BOOLEAN DEFAULT FALSE,
                    first_withdraw_used BOOLEAN DEFAULT FALSE,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE,
                    is_admin BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # جدول تراکنش‌ها
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount INTEGER,
                    description TEXT,
                    status TEXT DEFAULT 'completed',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_id INTEGER,
                    reference_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول اتاق‌های بازی
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_rooms (
                    room_id TEXT PRIMARY KEY,
                    creator_id INTEGER,
                    player2_id INTEGER,
                    game_type TEXT,
                    bet_amount INTEGER,
                    status TEXT DEFAULT 'waiting',
                    winner_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول صف بازی سریع
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS match_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    game_type TEXT,
                    bet_amount INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول درخواست‌های برداشت
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS withdraw_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount_coins INTEGER,
                    amount_toman INTEGER,
                    card_number TEXT,
                    card_holder TEXT,
                    receipt_message_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_by INTEGER,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول ماموریت‌های روزانه
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_missions (
                    user_id INTEGER,
                    date TEXT,
                    games_played INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    claimed BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول گزارشات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

user_id INTEGER,
                    type TEXT,
                    description TEXT,
                    amount INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول پیام‌های یادآوری
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    last_reminder TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # اضافه کردن ادمین
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, is_admin, invite_code)
                VALUES (?, TRUE, ?)
            ''', (ADMIN_USER_ID, str(ADMIN_USER_ID)))
            
            logger.info("✅ پایگاه داده راه‌اندازی شد")
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None, 
                    last_name: str = None, invited_by: int = None) -> str:
        """ایجاد کاربر جدید و برگرداندن کد دعوت"""
        invite_code = str(user_id)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, 
                                            invited_by, invite_code)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, invited_by, invite_code))
            
            # اگر با لینک دعوت آمده، به دعوت‌کننده الماس بده
            if invited_by and invited_by != user_id:
                self.add_diamond(invited_by, 1, f'دعوت کاربر {user_id}')
                
                # به‌روزرسانی تعداد دعوت‌ها
                cursor.execute('''
                    UPDATE users SET total_invites = total_invites + 1 
                    WHERE user_id = ?
                ''', (invited_by,))
            
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('new_user', ?, 'ثبت نام کاربر جدید')
            ''', (user_id,))
        
        return invite_code
    
    def add_diamond(self, user_id: int, amount: int, description: str = ''):
        """اضافه کردن الماس به کاربر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?
            ''', (amount, user_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (?, 'diamond', ?, ?)
            ''', (user_id, amount, description))
    
    def update_balance(self, user_id: int, amount: int, transaction_type: str, description: str):
        """به‌روزرسانی موجودی سکه"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET balance = balance + ?, last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, user_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, transaction_type, amount, description))
            
            # ثبت گزارش
            cursor.execute('''
                INSERT INTO reports (user_id, type, description, amount)
                VALUES (?, ?, ?, ?)
            ''', (user_id, transaction_type, description, amount))
    
    def get_user(self, user_id: int) -> Optional[Dict]:

with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_balance(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user['balance'] if user else 0
    
    def get_user_diamonds(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user['diamonds'] if user else 0
    
    def get_invite_stats(self, user_id: int) -> Dict:
        """آمار زیرمجموعه‌گیری"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE invited_by = ?", (user_id,))
            total_invites = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM users 
                WHERE invited_by = ? AND total_games >= 1
            """, (user_id,))
            active_invites = cursor.fetchone()['count']
            
            cursor.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
            diamonds = cursor.fetchone()['diamonds'] if cursor.fetchone() else 0
        
        return {
            'total_invites': total_invites,
            'active_invites': active_invites,
            'diamonds_earned': diamonds
        }
    
    def can_withdraw(self, user_id: int) -> Tuple[bool, str]:
        """بررسی امکان برداشت"""
        user = self.get_user(user_id)
        if not user:
            return False, "کاربر یافت نشد"
        
        if user['balance'] < MIN_WITHDRAW_COINS:
            return False, f"حداقل موجودی برای برداشت: {MIN_WITHDRAW_COINS} سکه"
        
        # برای اولین برداشت، باید حداقل ۴ نفر دعوت کرده باشه
        if not user['first_withdraw_used']:
            active_invites = self.get_invite_stats(user_id)['active_invites']
            if active_invites < MIN_INVITES_FIRST_WITHDRAW:
                return False, f"برای اولین برداشت باید حداقل {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال داشته باشید"
        
        return True, "مجاز به برداشت"
    
    def create_game_room(self, creator_id: int, bet_amount: int, game_type: str) -> str:
        """ایجاد اتاق بازی"""
        room_id = str(random.randint(100000, 999999))
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO game_rooms (room_id, creator_id, bet_amount, game_type)
                VALUES (?, ?, ?, ?)
            ''', (room_id, creator_id, bet_amount, game_type))
        
        return room_id
    
    def join_game_room(self, room_id: str, player2_id: int) -> bool:
        """ورود به اتاق بازی"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM game_rooms WHERE room_id = ? AND status = 'waiting'", (room_id,))
            room = cursor.fetchone()
            
            if not room:
                return False
            
            if room['creator_id'] == player2_id:
                return False
            
            cursor.execute('''
                UPDATE game_rooms SET player2_id = ?, status = 'playing'
                WHERE room_id = ?
            ''', (player2_id, room_id))
            
            return True
    
    def add_to_queue(self, user_id: int, game_type: str, bet_amount: int):
        """اضافه کردن به صف بازی سریع"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO match_queue (user_id, game_type, bet_amount, joined_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)

''', (user_id, game_type, bet_amount))
    
    def find_match(self, user_id: int, bet_amount: int, game_type: str) -> Optional[int]:
        """پیدا کردن حریف از صف"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id FROM match_queue 
                WHERE bet_amount = ? AND game_type = ? AND user_id != ?
                ORDER BY joined_at ASC LIMIT 1
            ''', (bet_amount, game_type, user_id))
            match = cursor.fetchone()
            
            if match:
                # حذف از صف
                cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (match['user_id'],))
                cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (user_id,))
                return match['user_id']
            
            return None
    
    def remove_from_queue(self, user_id: int):
        """حذف از صف"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (user_id,))
    
    def update_daily_mission(self, user_id: int):
        """به‌روزرسانی ماموریت روزانه"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO daily_missions (user_id, date, games_played)
                VALUES (?, ?, 0)
            ''', (user_id, today))
            
            cursor.execute('''
                UPDATE daily_missions SET games_played = games_played + 1
                WHERE user_id = ? AND date = ?
            ''', (user_id, today))
            
            cursor.execute("SELECT games_played FROM daily_missions WHERE user_id = ? AND date = ?", (user_id, today))
            games_played = cursor.fetchone()['games_played']
            
            if games_played >= DAILY_MISSION_GAMES:
                cursor.execute('''
                    UPDATE daily_missions SET completed = TRUE
                    WHERE user_id = ? AND date = ?
                ''', (user_id, today))
    
    def get_daily_mission(self, user_id: int) -> Dict:
        """دریافت وضعیت ماموریت روزانه"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_missions WHERE user_id = ? AND date = ?", (user_id, today))
            mission = cursor.fetchone()
            
            if not mission:
                return {
                    'games_played': 0,
                    'completed': False,
                    'claimed': False,
                    'target': DAILY_MISSION_GAMES,
                    'reward': DAILY_MISSION_REWARD
                }
            
            return {
                'games_played': mission['games_played'],
                'completed': mission['completed'],
                'claimed': mission['claimed'],
                'target': DAILY_MISSION_GAMES,
                'reward': DAILY_MISSION_REWARD
            }
    
    def claim_daily_mission(self, user_id: int) -> bool:
        """دریافت جایزه ماموریت روزانه"""
        today = datetime.now().strftime('%Y-%m-%d')
        mission = self.get_daily_mission(user_id)
        
        if mission['completed'] and not mission['claimed']:
            self.update_balance(user_id, DAILY_MISSION_REWARD, 'daily_mission', 'جایزه ماموریت روزانه')
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE daily_missions SET claimed = TRUE
                    WHERE user_id = ? AND date = ?
                ''', (user_id, today))

return True
        
        return False
    
    def create_withdraw_request(self, user_id: int, amount_coins: int, 
                                 card_number: str, card_holder: str) -> int:
        """ایجاد درخواست برداشت"""
        amount_toman = amount_coins * COIN_TO_TOMAN
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # کم کردن موقت از موجودی
            cursor.execute('''
                UPDATE users SET balance = balance - ? WHERE user_id = ?
            ''', (amount_coins, user_id))
            
            cursor.execute('''
                INSERT INTO withdraw_requests (user_id, amount_coins, amount_toman, card_number, card_holder)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount_coins, amount_toman, card_number, card_holder))
            
            request_id = cursor.lastrowid
            
            # ثبت در گزارشات
            cursor.execute('''
                INSERT INTO reports (user_id, type, description, amount)
                VALUES (?, 'withdraw_request', ?, ?)
            ''', (user_id, f'درخواست برداشت {amount_coins} سکه', amount_toman))
        
        return request_id
    
    def process_withdraw(self, request_id: int, admin_id: int, approved: bool):
        """پردازش درخواست برداشت"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM withdraw_requests WHERE id = ?", (request_id,))
            request = cursor.fetchone()
            
            if not request:
                return None
            
            if approved:
                cursor.execute('''
                    UPDATE withdraw_requests 
                    SET status = 'approved', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, request_id))
                
                # علامت‌گذاری اولین برداشت
                cursor.execute('''
                    UPDATE users SET first_withdraw_used = TRUE WHERE user_id = ?
                ''', (request['user_id'],))
                
                # ثبت گزارش
                cursor.execute('''
                    INSERT INTO reports (user_id, type, description, amount)
                    VALUES (?, 'withdraw_approved', ?, ?)
                ''', (request['user_id'], f'برداشت تایید شد', request['amount_toman']))
            else:
                # برگشت سکه به کاربر
                cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (request['amount_coins'], request['user_id']))
                
                cursor.execute('''
                    UPDATE withdraw_requests 
                    SET status = 'rejected', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, request_id))
            
            return request
    
    def get_pending_withdrawals(self) -> List[Dict]:
        """دریافت درخواست‌های برداشت در انتظار"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT wr.*, u.username, u.first_name, u.last_name
                FROM withdraw_requests wr
                JOIN users u ON wr.user_id = u.user_id
                WHERE wr.status = 'pending'
                ORDER BY wr.timestamp DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_reports(self, limit: int = 20) -> List[Dict]:
        """دریافت گزارشات اخیر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reports ORDER BY timestamp DESC LIMIT ?", (limit,))

return [dict(row) for row in cursor.fetchall()]
    
    def get_inactive_users(self, hours: int = 24) -> List[int]:
        """دریافت کاربران غیرفعال در ۲۴ ساعت گذشته"""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id FROM users 
                WHERE last_activity < ? AND is_banned = FALSE AND is_admin = FALSE
            ''', (cutoff,))
            return [row['user_id'] for row in cursor.fetchall()]
    
    def update_reminder(self, user_id: int):
        """به‌روزرسانی زمان یادآوری"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO reminders (user_id, last_reminder)
                VALUES (?, CURRENT_TIMESTAMP)
            ''', (user_id,))
    
    def get_users_for_reminder(self) -> List[int]:
        """دریافت کاربرانی که باید یادآوری دریافت کنند"""
        cutoff = datetime.now() - timedelta(hours=24)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id FROM users u
                LEFT JOIN reminders r ON u.user_id = r.user_id
                WHERE u.last_activity < ? 
                AND u.is_banned = FALSE 
                AND u.is_admin = FALSE
                AND (r.last_reminder IS NULL OR r.last_reminder < ?)
            ''', (cutoff, cutoff))
            return [row['user_id'] for row in cursor.fetchall()]
    
    def get_all_users(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY join_date DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_users_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            return cursor.fetchone()['count']
    
    def get_total_balance(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(balance) as total FROM users")
            result = cursor.fetchone()['total']
            return result if result else 0
    
    def lock_user_game(self, user_id: int, game_name: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO game_locks (user_id, game_name, locked_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, game_name))
    
    def unlock_user(self, user_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM game_locks WHERE user_id = ?", (user_id,))
    
    def is_user_locked(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM game_locks WHERE user_id = ?", (user_id,))
            return cursor.fetchone()['count'] > 0

# ==============================================
# ایجاد نمونه‌های اصلی
# ==============================================

db = Database()
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()

# ==============================================
# State‌های ربات
# ==============================================

class UserStates(StatesGroup):
    waiting_for_receipt = State()
    waiting_card_amount = State()
    waiting_withdraw_card = State()
    waiting_withdraw_amount = State()
    waiting_room_code = State()
    waiting_room_bet = State()
    waiting_quick_bet = State()
    playing_game = State()

class AdminStates(StatesGroup):
    waiting_for_password = State()
    admin_menu = State()
    broadcast_message = State()
    waiting_card_amount = State()

# ==============================================
# توابع کمکی
# ==============================================

async def check_channel_membership(user_id: int) -> Tuple[bool, str]:
    """بررسی عضویت در کانال‌های اجباری"""
    not_joined = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status in ['left', 'kicked', 'banned']:
                not_joined.append(channel)
        except:
            # اگر ربات ادمین کانال نبود، از این کانال رد میشه
            continue
    
    if not_joined:
        channels_text = "\n".join([f"• [{ch['name']}]({ch['link']})" for ch in not_joined])
        return False, f"⛔ برای استفاده از ربات، لطفاً در کانال‌های زیر عضو شوید:\n\n{channels_text}\n\n✅ پس از عضویت، /start را بزنید."
    
    return True, ""

async def send_withdraw_log(request: Dict, status: str):
    """ارسال گزارش برداشت به کانال"""
    try:
        emoji = "✅" if status == "approved" else "❌" if status == "rejected" else "⏳"
        status_fa = "تایید شده" if status == "approved" else "رد شده" if status == "rejected" else "در انتظار"
        
        log_text = f"""
{emoji} گزارش برداشت #{request['id']}

👤 کاربر: {request.get('first_name', 'نامشخص')}
🆔 شناسه: {request['user_id']}
💰 سکه: {request['amount_coins']:,}
💵 تومان: {request['amount_toman']:,}
💳 کارت: {request['card_number']}
👤 صاحب کارت: {request['card_holder']}
📊 وضعیت: {status_fa}
⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        await bot.send_message(WITHDRAW_LOG_CHANNEL, log_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"خطا در ارسال گزارش به کانال: {e}")

async def calculate_card_amount(coins: int) -> int:
    """محاسبه مبلغ تومان بر اساس سکه"""
    return coins * COIN_TO_TOMAN

# ==============================================
# کیبوردها
# ==============================================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🎮 بازی‌ها"),
        KeyboardButton(text="💰 خرید سکه")
    )
    builder.row(
        KeyboardButton(text="👤 حساب من"),
        KeyboardButton(text="👥 زیرمجموعه‌گیری")
    )
    builder.row(
        KeyboardButton(text="🎯 ماموریت روزانه"),
        KeyboardButton(text="💎 برداشت")
    )
    builder.row(
        KeyboardButton(text="❓ راهنما"),
        KeyboardButton(text="📊 آمار")
    )
    return builder.as_markup(resize_keyboard=True)

def get_games_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="🎮 ساخت اتاق (بازی با دوست)", callback_data="game_create_room"))
    builder.row(InlineKeyboardButton(text="🎯 بازی سریع (حریف تصادفی)", callback_data="game_quick_match"))
    builder.row(InlineKeyboardButton(text="🎲 بازی تاس (با ربات)", callback_data="game_dice_bot"))
    builder.row(InlineKeyboardButton(text="🎪 قرعه‌کشی (با ربات)", callback_data="game_lottery_bot"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main"))
    
    return builder.as_markup()

def get_bet_amount_keyboard(prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for price in GAME_PRICES:
        builder.row(InlineKeyboardButton(
            text=f"💰 {price:,} سکه",
            callback_data=f"{prefix}_{price}"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    return builder.as_markup()

def get_game_choice_keyboard(room_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    games = [
        ("✊ سنگ کاغذ قیچی", f"room_game_rps_{room_id}"),
        ("⚽ فوتبال", f"room_game_football_{room_id}"),
        ("🎲 تاس", f"room_game_dice_{room_id}")
    ]
    
    for name, callback in games:
        builder.row(InlineKeyboardButton(text=name, callback_data=callback))
    
    return builder.as_markup()

# ==============================================
# هندلرهای اصلی
# ==============================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """شروع ربات"""
    user_id = message.from_user.id
    
    # بررسی جوین اجباری
    is_member, error_msg = await check_channel_membership(user_id)
    if not is_member:
        await message.answer(error_msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        return
    
    # بررسی کد دعوت
    args = message.text.split()
    invited_by = None
    
    if len(args) > 1:
        try:
            invited_by = int(args[1])
            if invited_by == user_id:
                invited_by = None
        except:
            pass
    
    # ایجاد کاربر
    invite_code = db.create_user(
        user_id, 
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
        invited_by
    )
    
    welcome_text = f"""
🎰 به ربات کازینو خوش آمدید {message.from_user.first_name} عزیز!

🎮 بازی‌ها:
• بازی با دوستان (اتاق خصوصی)
• بازی سریع (حریف تصادفی)
• تاس با ربات
• قرعه‌کشی

💰 سکه: هر ۱۰۰ سکه = ۱۰۰,۰۰۰ تومان
💎 الماس: با دعوت دوستان دریافت کنید

👥 لینک دعوت شما:
https://t.me/{(await bot.get_me()).username}?start={invite_code}

🎯 برای شروع، یک گزینه را انتخاب کنید:
    """
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "🎮 بازی‌ها")
async def show_games_menu(message: Message):
    """نمایش منوی بازی‌ها"""
    is_member, error_msg = await check_channel_membership(message.from_user.id)
    if not is_member:
        await message.answer(error_msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        return
    
    if db.is_user_locked(message.from_user.id):
        await message.answer("⚠️ شما در حال انجام یک بازی هستید!")
        return
    
    await message.answer(
        "🎮 منوی بازی‌ها\n\n"
        "🎮 ساخت اتاق: با دوست خود بازی کنید\n"
        "🎯 بازی سریع: با حریف تصادفی\n"
        "🤖 بازی با ربات: تاس و قرعه‌کشی\n\n"
        "💰 قیمت‌های قابل انتخاب: " + " | ".join([f"{p:,} سکه" for p in GAME_PRICES]),
        reply_markup=get_games_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text == "👥 زیرمجموعه‌گیری")
async def show_referral(message: Message):
    """نمایش بخش زیرمجموعه‌گیری"""
    user_id = message.from_user.id
    user = db.get_user(user_id)
    stats = db.get_invite_stats(user_id)
    
    bot_username = (await bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start={user_id}"
    
    referral_text = f"""
👥 بخش زیرمجموعه‌گیری

💎 با دعوت دوستان خود الماس رایگان دریافت کنید!

✏️ لینک دعوت اختصاصی شما:
{invite_link}

📊 آمار شما:
• 👥 زیرمجموعه‌های کل: {stats['total_invites']} نفر
• ✅ زیرمجموعه‌های فعال: {stats['active_invites']} نفر
• 💎 الماس‌های کسب شده: {stats['diamonds_earned']} 💎

⚠️ قوانین:
• به ازای هر دوست که عضو شود: ۱ 💎
• زیرمجموعه فعال = حداقل ۱ بازی انجام داده
• برای اولین برداشت، حداقل {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال نیاز دارید
    """
    
    await message.answer(referral_text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "🎯 ماموریت روزانه")
async def show_daily_mission(message: Message):
    """نمایش ماموریت روزانه"""
    user_id = message.from_user.id
    mission = db.get_daily_mission(user_id)
    
    progress_bar = "▓" * mission['games_played'] + "░" * (mission['target'] - mission['games_played'])
    
    mission_text = f"""
🎯 ماموریت روزانه

📋 وظیفه: {mission['target']} بازی انجام دهید
🎁 جایزه: {mission['reward']:,} سکه رایگان

📊 پیشرفت: [{progress_bar}] {mission['games_played']}/{mission['target']}

{'✅ ماموریت کامل شده! روی دکمه زیر کلیک کنید' if mission['completed'] and not mission['claimed'] else 
 '🎉 جایزه دریافت شده!' if mission['claimed'] else 
 '🔴 هنوز کامل نشده. به بازی ادامه دهید!'}
    """
    
    builder = InlineKeyboardBuilder()
    
    if mission['completed'] and not mission['claimed']:
        builder.row(InlineKeyboardButton(text="🎁 دریافت جایزه", callback_data="claim_daily_mission"))
    
    await message.answer(mission_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup() if mission['completed'] and not mission['claimed'] else None)

@router.message(F.text == "💰 خرید سکه")
async def show_buy_coins(message: Message):
    """نمایش منوی خرید سکه"""
    buy_text = f"""
💰 خرید سکه

💳 فقط کارت به کارت

💵 نرخ تبدیل:
هر ۱۰۰ سکه = {COIN_TO_TOMAN:,} تومان

📌 اطلاعات حساب:
• شماره کارت: {ADMIN_CARD_NUMBER}
• به نام: {ADMIN_CARD_HOLDER}

📝 گزینه‌ها:
• خرید با مبلغ دلخواه
• انتخاب از بسته‌های پیشنهادی
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 مبلغ دلخواه", callback_data="buy_custom_amount"))
    
    packages = [50, 100, 200, 500, 1000]
    for pkg in packages:
        toman = pkg * COIN_TO_TOMAN
        builder.row(InlineKeyboardButton(
            text=f"💰 {pkg:,} سکه = {toman:,} تومان",
            callback_data=f"buy_package_{pkg}"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main"))
    
    await message.answer(buy_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "buy_custom_amount")
async def buy_custom_amount(callback: CallbackQuery, state: FSMContext):
    """خرید با مبلغ دلخواه"""
    await state.set_state(UserStates.waiting_card_amount)
    await callback.message.answer(
        "💰 چند سکه می‌خواهید خریداری کنید؟\n"
        f"💵 نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان\n\n"
        "📝 لطفاً تعداد سکه را وارد کنید (فقط عدد):"
    )

@router.message(UserStates.waiting_card_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    """پردازش مبلغ دلخواه"""
    try:
        coins = int(message.text)
        if coins <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")
        return
    
    toman = await calculate_card_amount(coins)
    
    await state.update_data(buy_coins=coins, buy_toman=toman)
    await state.set_state(UserStates.waiting_for_receipt)
    
    payment_text = f"""
💳 اطلاعات پرداخت

💰 سکه درخواستی: {coins:,} سکه
💵 مبلغ قابل پرداخت: {toman:,} تومان

📌 شماره کارت:
{ADMIN_CARD_NUMBER}
👤 به نام: {ADMIN_CARD_HOLDER}

⚠️ لطفاً دقیقاً {toman:,} تومان واریز کنید.
📸 سپس عکس رسید را ارسال کنید.
    """
    
    await message.answer(payment_text, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(F.data.startswith("buy_package_"))
async def buy_package(callback: CallbackQuery, state: FSMContext):
    """خرید بسته مشخص"""
    coins = int(callback.data.split("_")[2])
    toman = await calculate_card_amount(coins)
    
    await state.update_data(buy_coins=coins, buy_toman=toman)
    await state.set_state(UserStates.waiting_for_receipt)
    
    payment_text = f"""
💳 اطلاعات پرداخت

📦 بسته: {coins:,} سکه
💵 مبلغ: {toman:,} تومان

📌 شماره کارت:
{ADMIN_CARD_NUMBER}
👤 به نام: {ADMIN_CARD_HOLDER}

📸 عکس رسید را ارسال کنید.
    """
    
    await callback.message.answer(payment_text, parse_mode=ParseMode.MARKDOWN)

@router.message(UserStates.waiting_for_receipt, F.photo)
async def process_payment_receipt(message: Message, state: FSMContext):
    """پردازش رسید پرداخت"""
    data = await state.get_data()
    coins = data.get('buy_coins', 0)
    toman = data.get('buy_toman', 0)
    
    user_id = message.from_user.id
    
    # اطلاع به ادمین
    admin_text = f"""
🔔 درخواست خرید سکه جدید

👤 کاربر: {message.from_user.full_name}
🆔 شناسه: {user_id}
💰 سکه: {coins:,}
💵 تومان: {toman:,}
⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📸 رسید: 👇
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_buy_{user_id}_{coins}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_buy_{user_id}")
    )
    
    await bot.send_message(ADMIN_USER_ID, admin_text, parse_mode=ParseMode.MARKDOWN)
    await bot.forward_message(ADMIN_USER_ID, message.chat.id, message.message_id)
    await bot.send_message(ADMIN_USER_ID, "⚡ اقدام:", reply_markup=builder.as_markup())
    
    await message.answer("✅ رسید شما دریافت شد. پس از تایید ادمین، سکه‌ها به حسابتان اضافه می‌شود.")
    await state.clear()

@router.callback_query(F.data.startswith("approve_buy_"))
async def approve_buy(callback: CallbackQuery):
    """تایید خرید سکه"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    coins = int(parts[3])
    
    db.update_balance(user_id, coins, 'deposit', f'خرید {coins} سکه - تایید شده')
    
    await callback.message.edit_text(f"✅ خرید {coins:,} سکه برای کاربر {user_id} تایید شد.")
    
    try:
        await bot.send_message(user_id, f"✅ خرید شما تایید شد!\n💰 {coins:,} سکه به حساب شما اضافه شد.\n💳 موجودی: {db.get_user_balance(user_id):,} سکه")
    except:
        pass

@router.callback_query(F.data.startswith("reject_buy_"))
async def reject_buy(callback: CallbackQuery):
    """رد خرید سکه"""
    user_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_text(f"❌ خرید کاربر {user_id} رد شد.")
    
    try:
        await bot.send_message(user_id, "❌ متاسفانه درخواست خرید شما تایید نشد. لطفاً با پشتیبانی تماس بگیرید.")
    except:
        pass

@router.message(F.text == "💎 برداشت")
async def show_withdraw_menu(message: Message):
    """نمایش منوی برداشت"""
    user_id = message.from_user.id
    can_withdraw, reason = db.can_withdraw(user_id)
    
    if not can_withdraw:
        await message.answer(f"❌ {reason}")
        return
    
    user = db.get_user(user_id)
    
    withdraw_text = f"""
💎 برداشت سکه

💰 موجودی شما: {user['balance']:,} سکه
💵 معادل: {user['balance'] * COIN_TO_TOMAN:,} تومان

⚠️ قوانین برداشت:
• حداقل برداشت: {MIN_WITHDRAW_COINS} سکه
• نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان
• اولین برداشت: نیاز به {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال

📝 برای برداشت، روی دکمه زیر کلیک کنید:
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💎 درخواست برداشت", callback_data="request_withdraw"))
    
    await message.answer(withdraw_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "request_withdraw")
async def request_withdraw_start(callback: CallbackQuery, state: FSMContext):
    """شروع فرآیند برداشت"""
    user_id = callback.from_user.id
    can_withdraw, reason = db.can_withdraw(user_id)
    
    if not can_withdraw:
        await callback.answer(f"❌ {reason}", show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_withdraw_amount)
    await callback.message.answer(
        f"💰 چند سکه می‌خواهید برداشت کنید؟\n"
        f"💵 نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان\n"
        f"⚠️ حداقل: {MIN_WITHDRAW_COINS} سکه\n\n"
        "📝 لطفاً تعداد سکه را وارد کنید:"
    )

@router.message(UserStates.waiting_withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    """پردازش مبلغ برداشت"""
    try:
        coins = int(message.text)
        if coins < MIN_WITHDRAW_COINS:
            await message.answer(f"❌ حداقل برداشت {MIN_WITHDRAW_COINS} سکه است!")
            return
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")
        return
    
    user_id = message.from_user.id
    balance = db.get_user_balance(user_id)
    
    if coins > balance:

await message.answer(f"❌ موجودی شما کافی نیست! موجودی: {balance:,} سکه")
        return
    
    toman = coins * COIN_TO_TOMAN
    
    await state.update_data(withdraw_coins=coins, withdraw_toman=toman)
    await state.set_state(UserStates.waiting_withdraw_card)
    
    await message.answer(
        f"💵 مبلغ برداشت: {toman:,} تومان\n\n"
        "💳 لطفاً شماره کارت ۱۶ رقمی خود را وارد کنید:\n"
        "⚠️ شماره کارت باید به نام خودتان باشد."
    )

@router.message(UserStates.waiting_withdraw_card)
async def process_withdraw_card(message: Message, state: FSMContext):
    """پردازش شماره کارت برداشت"""
    card_number = message.text.replace(" ", "").replace("-", "")
    
    if not card_number.isdigit() or len(card_number) != 16:
        await message.answer("❌ شماره کارت نامعتبر! لطفاً ۱۶ رقم را وارد کنید.")
        return
    
    await state.update_data(withdraw_card=card_number)
    
    await message.answer(
        "👤 لطفاً نام صاحب کارت را وارد کنید:\n"
        "⚠️ حتماً نام دقیق صاحب کارت را بنویسید."
    )
    await state.set_state(UserStates.waiting_withdraw_amount)  # استفاده مجدد برای نام
    
    # ذخیره موقت برای مرحله بعد
    await state.update_data(withdraw_card_holder_pending=True, withdraw_card_temp=card_number)

@router.message(lambda msg: msg.from_user.id in [s.user for s in dp.storage.states if s.state == UserStates.waiting_withdraw_amount])
async def process_withdraw_name(message: Message, state: FSMContext):
    """پردازش نام صاحب کارت و نهایی کردن برداشت"""
    data = await state.get_data()
    
    if not data.get('withdraw_card_holder_pending'):
        return
    
    card_holder = message.text.strip()
    coins = data.get('withdraw_coins')
    card_number = data.get('withdraw_card_temp')
    toman = data.get('withdraw_toman')
    
    user_id = message.from_user.id
    
    # ایجاد درخواست برداشت
    request_id = db.create_withdraw_request(user_id, coins, card_number, card_holder)
    
    # ارسال به کانال گزارشات
    request_data = {
        'id': request_id,
        'user_id': user_id,
        'first_name': message.from_user.first_name,
        'amount_coins': coins,
        'amount_toman': toman,
        'card_number': card_number,
        'card_holder': card_holder
    }
    await send_withdraw_log(request_data, 'pending')
    
    # اطلاع به ادمین
    admin_text = f"""
💎 درخواست برداشت جدید #{request_id}

👤 کاربر: {message.from_user.full_name}
🆔 شناسه: {user_id}
💰 سکه: {coins:,}
💵 تومان: {toman:,}
💳 کارت: {card_number}
👤 صاحب: {card_holder}
⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید برداشت", callback_data=f"approve_withdraw_{request_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_withdraw_{request_id}")
    )
    
    await bot.send_message(ADMIN_USER_ID, admin_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
    
    await message.answer(
        f"✅ درخواست برداشت شما ثبت شد!\n\n"
        f"💰 مبلغ: {coins:,} سکه = {toman:,} تومان\n"
        f"💳 کارت: {card_number}\n"
        f"⏰ پس از تایید ادمین، مبلغ واریز می‌شود.\n\n"
        f"📢 گزارش در کانال @YOUR_CHANNEL_2 ثبت شد."
    )
    
    await state.clear()

# ==============================================
# بازی‌ها - ساخت اتاق و بازی بین کاربران
# ==============================================

@router.callback_query(F.data == "game_create_room")
async def create_game_room(callback: CallbackQuery, state: FSMContext):
    """ساخت اتاق بازی"""
    user_id = callback.from_user.id
    
    if db.is_user_locked(user_id):
        await callback.answer("⚠️ شما در حال بازی هستید!", show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_room_bet)
    await callback.message.edit_text(
        "🎮 ساخت اتاق بازی\n\n"
        "💰 مبلغ شرط را انتخاب کنید:",
        reply_markup=get_bet_amount_keyboard("create_room"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("create_room_"))
async def process_room_bet(callback: CallbackQuery, state: FSMContext):
    """پردازش مبلغ اتاق"""
    bet_amount = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    balance = db.get_user_balance(user_id)
    if balance < bet_amount:
        await callback.answer(f"❌ موجودی کافی نیست! نیاز: {bet_amount:,}", show_alert=True)
        return
    
    # ایجاد اتاق
    room_id = db.create_game_room(user_id, bet_amount, 'custom')
    
    # کم کردن سکه از سازنده
    db.update_balance(user_id, -bet_amount, 'game_bet', f'ساخت اتاق #{room_id}')
    db.lock_user_game(user_id, f'room_{room_id}')
    
    await state.clear()
    
    room_text = f"""
🎮 اتاق بازی ایجاد شد!

🔑 کد اتاق: {room_id}
💰 مبلغ شرط: {bet_amount:,} سکه

📋 نحوه دعوت:
1. این کد را برای دوستت بفرست
2. دوستت روی "ورود با کد" بزند
3. کد را وارد کند
4. بازی شروع می‌شود!

⏰ منتظر بازیکن دوم...
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎯 انتخاب بازی", callback_data=f"select_room_game_{room_id}"))
    builder.row(InlineKeyboardButton(text="❌ لغو اتاق", callback_data=f"cancel_room_{room_id}"))
    
    await callback.message.edit_text(room_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)

@router.callback_query(F.data == "game_quick_match")
async def quick_match(callback: CallbackQuery, state: FSMContext):
    """بازی سریع - جستجوی حریف"""
    user_id = callback.from_user.id
    
    if db.is_user_locked(user_id):
        await callback.answer("⚠️ شما در حال بازی هستید!", show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_quick_bet)
    await callback.message.edit_text(
        "🎯 بازی سریع\n\n"
        "💰 مبلغ شرط را انتخاب کنید:",
        reply_markup=get_bet_amount_keyboard("quick_match"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("quick_match_"))
async def process_quick_match(callback: CallbackQuery, state: FSMContext):
    """پردازش بازی سریع"""
    bet_amount = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    balance = db.get_user_balance(user_id)
    if balance < bet_amount:
        await callback.answer(f"❌ موجودی کافی نیست! نیاز: {bet_amount:,}", show_alert=True)
        return
    
    # کم کردن سکه
    db.update_balance(user_id, -bet_amount, 'game_bet', f'بازی سریع - {bet_amount} سکه')
    db.lock_user_game(user_id, 'quick_match')
    
    # جستجوی حریف
    opponent_id = db.find_match(user_id, bet_amount, 'quick')
    
    if opponent_id:
        # حریف پیدا شد - بازی رو شروع کن
        await start_game_between_players(user_id, opponent_id, bet_amount, callback.message)
    else:
        # اضافه به صف انتظار
        db.add_to_queue(user_id, 'quick', bet_amount)
        
        await callback.message.edit_text(
            f"🔍 در حال جستجوی حریف...\n\n"
            f"💰 مبلغ: {bet_amount:,} سکه\n"
            f"⏰ لطفاً منتظر بمانید...\n\n"
            f"❌ برای لغو، /cancel را بزنید",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="❌ لغو جستجو", callback_data="cancel_search")
            ).as_markup()
        )

async def start_game_between_players(player1_id: int, player2_id: int, bet_amount: int, message: Message):
    """شروع بازی بین دو بازیکن"""
    # انتخاب بازی تصادفی
    game_type = random.choice(['rps', 'dice', 'football'])
    
    # ایجاد اتاق
    room_id = db.create_game_room(player1_id, bet_amount, game_type)
    db.join_game_room(room_id, player2_id)
    
    # کم کردن سکه از بازیکن دوم
    db.update_balance(player2_id, -bet_amount, 'game_bet', f'بازی سریع - اتاق #{room_id}')
    db.lock_user_game(player2_id, f'room_{room_id}')

# شروع بازی
    if game_type == 'rps':
        await play_rps_game(room_id, player1_id, player2_id, bet_amount, message)
    elif game_type == 'dice':
        await play_dice_game(room_id, player1_id, player2_id, bet_amount, message)
    else:
        await play_football_game(room_id, player1_id, player2_id, bet_amount, message)

async def play_rps_game(room_id: str, player1_id: int, player2_id: int, bet_amount: int, message: Message):
    """بازی سنگ کاغذ قیچی بین دو بازیکن"""
    # اینجا منطق بازی بین دو نفر پیاده‌سازی میشه
    # برای سادگی، برد تصادفی
    winner_id = random.choice([player1_id, player2_id])
    loser_id = player2_id if winner_id == player1_id else player1_id
    
    prize = bet_amount * 2  # مجموع شرط دو نفر
    
    db.update_balance(winner_id, prize, 'game_win', f'برد در بازی - اتاق #{room_id}')
    db.unlock_user(player1_id)
    db.unlock_user(player2_id)
    
    # به‌روزرسانی ماموریت
    db.update_daily_mission(player1_id)
    db.update_daily_mission(player2_id)
    
    result_text = f"""
🎮 نتیجه بازی سنگ کاغذ قیچی

👤 بازیکن ۱: {player1_id}
👤 بازیکن ۲: {player2_id}

🏆 برنده: {winner_id}
💰 جایزه: {prize:,} سکه
    """
    
    await message.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)
    
    # اطلاع به بازنده
    try:
        await bot.send_message(loser_id, f"😢 شما در بازی مقابل {winner_id} باختید.\n💰 مبلغ: {bet_amount:,} سکه", parse_mode=ParseMode.MARKDOWN)
    except:
        pass

async def play_dice_game(room_id: str, player1_id: int, player2_id: int, bet_amount: int, message: Message):
    """بازی تاس بین دو بازیکن"""
    # منطق ساده شده
    winner_id = random.choice([player1_id, player2_id])
    loser_id = player2_id if winner_id == player1_id else player1_id
    
    prize = bet_amount * 2
    
    db.update_balance(winner_id, prize, 'game_win', f'برد تاس - اتاق #{room_id}')
    db.unlock_user(player1_id)
    db.unlock_user(player2_id)
    
    db.update_daily_mission(player1_id)
    db.update_daily_mission(player2_id)
    
    result_text = f"""
🎲 نتیجه بازی تاس

🏆 برنده: {winner_id}
💰 جایزه: {prize:,} سکه
    """
    
    await message.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)

async def play_football_game(room_id: str, player1_id: int, player2_id: int, bet_amount: int, message: Message):
    """بازی فوتبال بین دو بازیکن"""
    winner_id = random.choice([player1_id, player2_id])
    loser_id = player2_id if winner_id == player1_id else player1_id
    
    prize = bet_amount * 2
    
    db.update_balance(winner_id, prize, 'game_win', f'برد فوتبال - اتاق #{room_id}')
    db.unlock_user(player1_id)
    db.unlock_user(player2_id)
    
    db.update_daily_mission(player1_id)
    db.update_daily_mission(player2_id)
    
    result_text = f"""
⚽ نتیجه بازی فوتبال

🏆 برنده: {winner_id}
💰 جایزه: {prize:,} سکه
    """
    
    await message.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)

# ==============================================
# بازی با ربات - تاس و قرعه‌کشی
# ==============================================

@router.callback_query(F.data == "game_dice_bot")
async def dice_vs_bot(callback: CallbackQuery):
    """بازی تاس با ربات"""
    user_id = callback.from_user.id
    
    if db.is_user_locked(user_id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for price in GAME_PRICES:
        builder.row(InlineKeyboardButton(
            text=f"💰 {price:,} سکه",
            callback_data=f"dice_bot_{price}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(
        "🎲 تاس با ربات\n\n"
        "🤖 با ربات تاس بازی کنید\n"
        "⚠️ شانس برد: ۱۶٪\n"
        "💰 مبلغ شرط را انتخاب کنید:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "game_lottery_bot")
async def lottery_vs_bot(callback: CallbackQuery):
    """قرعه‌کشی با ربات"""
    user_id = callback.from_user.id
    
    if db.is_user_locked(user_id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for price in GAME_PRICES:
        builder.row(InlineKeyboardButton(
            text=f"💰 {price:,} سکه",
            callback_data=f"lottery_bot_{price}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(
        "🎪 قرعه‌کشی\n\n"
        "🎯 شانس خود را امتحان کنید!\n"
        "⚠️ شانس برد: فقط ۲٪\n"
        "🎁 جایزه: ۱۰ برابر مبلغ شرط\n"
        "💰 مبلغ شرط را انتخاب کنید:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("dice_bot_"))
async def process_dice_bot(callback: CallbackQuery):
    """پردازش بازی تاس با ربات"""
    user_id = callback.from_user.id
    bet_amount = int(callback.data.split("_")[2])
    
    balance = db.get_user_balance(user_id)
    if balance < bet_amount:
        await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    
    db.update_balance(user_id, -bet_amount, 'game_bet', f'تاس با ربات')
    
    # ۱۶٪ شانس برد
    rand = random.random()
    if rand < 0.16:
        prize = bet_amount * 4
        db.update_balance(user_id, prize, 'game_win', 'برد تاس')
        result = f"🎉 بردید!\n💰 جایزه: {prize:,} سکه"
    else:
        prize = 0
        result = "😢 باختید!"
    
    db.update_daily_mission(user_id)
    db.unlock_user(user_id)
    
    await callback.message.edit_text(
        f"🎲 نتیجه تاس\n\n{result}\n💳 موجودی: {db.get_user_balance(user_id):,} سکه",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🔄 بازی مجدد", callback_data="game_dice_bot"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games")
        ).as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("lottery_bot_"))
async def process_lottery_bot(callback: CallbackQuery):
    """پردازش قرعه‌کشی"""
    user_id = callback.from_user.id
    bet_amount = int(callback.data.split("_")[2])
    
    balance = db.get_user_balance(user_id)
    if balance < bet_amount:
        await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    
    db.update_balance(user_id, -bet_amount, 'game_bet', f'قرعه‌کشی')
    
    # فقط ۲٪ شانس برد
    lucky_number = random.randint(1, 100)
    is_winner = random.random() < 0.02  # ۲٪ شانس
    
    if is_winner:
        prize = bet_amount * 10
        db.update_balance(user_id, prize, 'lottery_win', f'برنده قرعه‌کشی شماره {lucky_number}')
        result = f"🎉 برنده شدید!\n🎫 شماره شانس: {lucky_number}\n💰 جایزه: {prize:,} سکه"
    else:
        result = f"😢 برنده نشدید\n🎫 شماره: {lucky_number}\n💡 شانس خود را دوباره امتحان کنید!"
    
    db.update_daily_mission(user_id)
    db.unlock_user(user_id)
    
    await callback.message.edit_text(
        f"🎪 نتیجه قرعه‌کشی\n\n{result}\n💳 موجودی: {db.get_user_balance(user_id):,} سکه",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🎪 شرکت مجدد", callback_data="game_lottery_bot"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games")
        ).as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

# ==============================================
# هندلرهای اضافی
# ==============================================

@router.callback_query(F.data == "claim_daily_mission")
async def claim_daily_mission_handler(callback: CallbackQuery):
    """دریافت جایزه ماموریت روزانه"""

user_id = callback.from_user.id
    
    if db.claim_daily_mission(user_id):
        await callback.answer(f"🎉 {DAILY_MISSION_REWARD} سکه دریافت کردید!", show_alert=True)
        await callback.message.edit_text(
            f"✅ جایزه دریافت شد!\n💰 {DAILY_MISSION_REWARD:,} سکه به حساب شما اضافه شد.\n💳 موجودی: {db.get_user_balance(user_id):,} سکه",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await callback.answer("❌ نمی‌توانید جایزه را دریافت کنید!", show_alert=True)

@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery):
    """لغو جستجوی حریف"""
    user_id = callback.from_user.id
    db.remove_from_queue(user_id)
    db.unlock_user(user_id)
    
    # برگشت سکه
    # اینجا باید سکه برگرده - بستگی به منطق شما داره
    
    await callback.message.edit_text("❌ جستجو لغو شد.", reply_markup=get_games_menu_keyboard())

@router.callback_query(F.data == "back_to_games")
async def back_to_games_menu(callback: CallbackQuery):
    await callback.message.edit_text("🎮 منوی بازی‌ها:", reply_markup=get_games_menu_keyboard())

@router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=get_main_keyboard())

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """لغو عملیات جاری"""
    user_id = message.from_user.id
    db.unlock_user(user_id)
    db.remove_from_queue(user_id)
    await state.clear()
    await message.answer("✅ عملیات جاری لغو شد.", reply_markup=get_main_keyboard())

# ==============================================
# پنل مدیریت
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user or not user['is_admin']:
        await message.answer("⛔ دسترسی غیرمجاز!")
        return
    
    await state.set_state(AdminStates.waiting_for_password)
    await message.answer("🔐 رمز عبور:")

@router.message(AdminStates.waiting_for_password)
async def admin_check_password(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        await state.set_state(AdminStates.admin_menu)
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📊 آمار", callback_data="admin_stats"))
        builder.row(InlineKeyboardButton(text="💎 برداشت‌های معلق", callback_data="admin_withdrawals"))
        builder.row(InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="admin_broadcast"))
        builder.row(InlineKeyboardButton(text="🚪 خروج", callback_data="admin_exit"))
        
        await message.answer("🔰 پنل مدیریت:", reply_markup=builder.as_markup())
    else:
        await message.answer("❌ رمز اشتباه!")
        await state.clear()

@router.callback_query(F.data == "admin_withdrawals")
async def admin_view_withdrawals(callback: CallbackQuery):
    """مشاهده درخواست‌های برداشت"""
    requests = db.get_pending_withdrawals()
    
    if not requests:
        await callback.message.edit_text("✅ هیچ درخواست برداشتی نیست.")
        return
    
    request = requests[0]
    
    text = f"""
💎 درخواست برداشت #{request['id']}

👤 کاربر: {request['first_name']} {request['last_name'] or ''}
🆔 شناسه: {request['user_id']}
💰 سکه: {request['amount_coins']:,}
💵 تومان: {request['amount_toman']:,}
💳 کارت: {request['card_number']}
👤 صاحب: {request['card_holder']}
⏰ زمان: {request['timestamp'][:19]}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_withdraw_{request['id']}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_withdraw_{request['id']}")
    )
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("approve_withdraw_"))
async def approve_withdraw_admin(callback: CallbackQuery):
    """تایید برداشت توسط ادمین"""
    request_id = int(callback.data.split("_")[2])
    
    request = db.process_withdraw(request_id, callback.from_user.id, approved=True)
    
    if request:
        await send_withdraw_log(request, 'approved')
        
        try:
            await bot.send_message(
                request['user_id'],
                f"✅ درخواست برداشت شما تایید شد!\n💰 مبلغ {request['amount_toman']:,} تومان به حساب شما واریز می‌شود."
            )
        except:
            pass
        
        await callback.answer("✅ تایید شد", show_alert=True)
    
    await admin_view_withdrawals(callback)

@router.callback_query(F.data.startswith("reject_withdraw_"))
async def reject_withdraw_admin(callback: CallbackQuery):
    """رد برداشت توسط ادمین"""
    request_id = int(callback.data.split("_")[2])
    
    request = db.process_withdraw(request_id, callback.from_user.id, approved=False)
    
    if request:
        await send_withdraw_log(request, 'rejected')
        
        try:
            await bot.send_message(
                request['user_id'],
                f"❌ درخواست برداشت شما تایید نشد.\n💰 سکه‌ها به حساب شما برگشت داده شد."
            )
        except:
            pass
        
        await callback.answer("❌ رد شد", show_alert=True)
    
    await admin_view_withdrawals(callback)

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """آمار کلی"""
    users_count = db.get_users_count()
    total_balance = db.get_total_balance()
    
    text = f"""
📊 آمار ربات

👥 کاربران: {users_count:,}
💰 مجموع سکه: {total_balance:,}
🕐 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.answer("📢 پیام همگانی را ارسال کنید:")

@router.message(AdminStates.broadcast_message)
async def admin_send_broadcast(message: Message, state: FSMContext):
    users = db.get_all_users()
    success = 0
    
    for user in users:
        try:
            await bot.copy_message(user['user_id'], message.chat.id, message.message_id)
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await message.answer(f"✅ ارسال شد به {success} کاربر")
    await state.clear()

@router.callback_query(F.data == "admin_exit")
async def admin_exit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚪 خارج شدید.")

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 آمار", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="💎 برداشت‌های معلق", callback_data="admin_withdrawals"))
    builder.row(InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="🚪 خروج", callback_data="admin_exit"))
    
    await callback.message.edit_text("🔰 پنل مدیریت:", reply_markup=builder.as_markup())

# ==============================================
# وظایف زمان‌بندی شده
# ==============================================

async def reminder_scheduler():
    """ارسال یادآوری به کاربران غیرفعال"""
    while True:
        try:
            await asyncio.sleep(3600)  # هر ساعت
            
            users = db.get_users_for_reminder()
            for user_id in users:
                try:
                    await bot.send_message(

user_id,
                        "👋 سلام! مدت زیادی از آخرین بازدید شما می‌گذرد.\n"
                        "🎮 به ربات برگردید و بازی کنید!\n"
                        "🎁 ماموریت روزانه منتظر شماست!\n\n"
                        "/start"
                    )
                    db.update_reminder(user_id)
                except:
                    pass
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"خطا در زمان‌بند یادآوری: {e}")

# ==============================================
# راه‌اندازی ربات
# ==============================================

@router.errors()
async def error_handler(update: types.Update, exception: Exception):
    logger.error(f"خطا: {exception}", exc_info=True)
    return True

async def main():
    """تابع اصلی"""
    dp.include_router(router)
    
    # راه‌اندازی زمان‌بند یادآوری
    asyncio.create_task(reminder_scheduler())
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 ربات آماده!")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if name == "main":
    asyncio.run(main())
