# ==============================================
# ربات شرط‌بندی و کازینو تلگرام - نسخه کامل
# اصلاح شده برای اجرا روی Railway
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
# تنظیمات اولیه - از Railway متغیر محیطی میخونه
# ==============================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7548145568"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "mohamad1387")

# کانال‌های اجباری
REQUIRED_CHANNELS = [
    {"id": "@gozaresh_taj", "چنل گزارشات": "کانال رسمی", "link": "https://t.me/YOUR_CHANNEL_1"},
    {"id": "@YOUR_CHANNEL_2", "name": "گزارشات برداشت", "link": "https://t.me/YOUR_CHANNEL_2"}
]

WITHDRAW_LOG_CHANNEL = "@gozaresh_taj"

# تنظیمات مالی
COIN_TO_TOMAN = 1000
MIN_WITHDRAW_COINS = 100
MIN_INVITES_FIRST_WITHDRAW = 4

# قیمت‌های بازی
GAME_PRICES = [50, 100, 200, 500, 1000]

# ماموریت روزانه
DAILY_MISSION_GAMES = 3
DAILY_MISSION_REWARD = 50

# اطلاعات کارت
ADMIN_CARD_NUMBER = "6062561009737464"
ADMIN_CARD_HOLDER = "مجاور"

# ==============================================
# سیستم لاگینگ
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================
# مدیریت پایگاه داده SQLite
# ==============================================

class Database:
    """کلاس مدیریت پایگاه داده SQLite"""
    
    def __init__(self, db_path: str = "casino_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """مدیریت اتصال به پایگاه داده"""
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
            
            # جدول قفل‌های بازی
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_locks (
                    user_id INTEGER PRIMARY KEY,
                    game_name TEXT,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول یادآوری‌ها
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    user_id INTEGER PRIMARY KEY,
                    last_reminder TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # اضافه کردن ادمین اصلی
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, is_admin, invite_code)
                VALUES (?, TRUE, ?)
            ''', (ADMIN_USER_ID, str(ADMIN_USER_ID)))
            
            logger.info("✅ پایگاه داده با موفقیت راه‌اندازی شد")
    
    # ==============================================
    # توابع کاربران
    # ==============================================
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None, 
                    last_name: str = None, invited_by: int = None) -> str:
        """ایجاد کاربر جدید و برگرداندن کد دعوت"""
        invite_code = str(user_id)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وجود کاربر
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            existing = cursor.fetchone()
            
            if not existing:
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, 
                                      invited_by, invite_code)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, invited_by, invite_code))
                
                # اگر با لینک دعوت آمده
                if invited_by and invited_by != user_id and invited_by != ADMIN_USER_ID:
                    self.add_diamond(invited_by, 1, f'زیرمجموعه جدید: {user_id}')
                    cursor.execute('''
                        UPDATE users SET total_invites = total_invites + 1 
                        WHERE user_id = ?
                    ''', (invited_by,))
            else:
                # به‌روزرسانی اطلاعات
                cursor.execute('''
                    UPDATE users SET username = ?, first_name = ?, last_name = ?
                    WHERE user_id = ?
                ''', (username, first_name, last_name, user_id))
        
        return invite_code
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """دریافت اطلاعات کاربر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_balance(self, user_id: int) -> int:
        """دریافت موجودی کاربر"""
        user = self.get_user(user_id)
        return user['balance'] if user else 0
    
    def get_user_diamonds(self, user_id: int) -> int:
        """دریافت الماس کاربر"""
        user = self.get_user(user_id)
        return user['diamonds'] if user else 0
    
    def update_balance(self, user_id: int, amount: int, transaction_type: str, description: str):
        """به‌روزرسانی موجودی"""
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
    
    def add_diamond(self, user_id: int, amount: int, description: str = ''):
        """اضافه کردن الماس"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET diamonds = diamonds + ? WHERE user_id = ?
            ''', (amount, user_id))
            
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (?, 'diamond', ?, ?)
            ''', (user_id, amount, description))
    
    # ==============================================
    # توابع زیرمجموعه‌گیری
    # ==============================================
    
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
            row = cursor.fetchone()
            diamonds = row['diamonds'] if row else 0
        
        return {
            'total_invites': total_invites,
            'active_invites': active_invites,
            'diamonds_earned': diamonds
        }
    
    # ==============================================
    # توابع برداشت
    # ==============================================
    
    def can_withdraw(self, user_id: int) -> Tuple[bool, str]:
        """بررسی امکان برداشت"""
        user = self.get_user(user_id)
        if not user:
            return False, "کاربر یافت نشد"
        
        if user['balance'] < MIN_WITHDRAW_COINS:
            return False, f"حداقل موجودی: {MIN_WITHDRAW_COINS} سکه"
        
        if not user['first_withdraw_used']:
            stats = self.get_invite_stats(user_id)
            if stats['active_invites'] < MIN_INVITES_FIRST_WITHDRAW:
                return False, f"برای اولین برداشت، {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال نیاز دارید"
        
        return True, "مجاز"
    
    def create_withdraw_request(self, user_id: int, amount_coins: int, 
                                 card_number: str, card_holder: str) -> int:
        """ایجاد درخواست برداشت"""
        amount_toman = amount_coins * COIN_TO_TOMAN
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users SET balance = balance - ? WHERE user_id = ?
            ''', (amount_coins, user_id))
            
            cursor.execute('''
                INSERT INTO withdraw_requests (user_id, amount_coins, amount_toman, card_number, card_holder)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount_coins, amount_toman, card_number, card_holder))
            
            request_id = cursor.lastrowid
            
            cursor.execute('''
                INSERT INTO reports (user_id, type, description, amount)
                VALUES (?, 'withdraw_request', ?, ?)
            ''', (user_id, f'درخواست برداشت {amount_coins} سکه', amount_toman))
            
            return request_id
    
    def process_withdraw(self, request_id: int, approved: bool, admin_id: int = None) -> Optional[Dict]:
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
                
                cursor.execute('''
                    UPDATE users SET first_withdraw_used = TRUE WHERE user_id = ?
                ''', (request['user_id'],))
                
                cursor.execute('''
                    INSERT INTO reports (user_id, type, description, amount)
                    VALUES (?, 'withdraw_approved', ?, ?)
                ''', (request['user_id'], f'برداشت تایید شد', request['amount_toman']))
            else:
                cursor.execute('''
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                ''', (request['amount_coins'], request['user_id']))
                
                cursor.execute('''
                    UPDATE withdraw_requests 
                    SET status = 'rejected', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, request_id))
                
                cursor.execute('''
                    INSERT INTO reports (user_id, type, description, amount)
                    VALUES (?, 'withdraw_rejected', ?, ?)
                ''', (request['user_id'], f'برداشت رد شد', request['amount_toman']))
            
            return dict(request)
    
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
    
    # ==============================================
    # توابع بازی‌ها
    # ==============================================
    
    def create_game_room(self, creator_id: int, bet_amount: int, game_type: str = 'custom') -> str:
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
            
            if not room or room['creator_id'] == player2_id:
                return False
            
            cursor.execute('''
                UPDATE game_rooms SET player2_id = ?, status = 'playing'
                WHERE room_id = ?
            ''', (player2_id, room_id))
            
            return True
    
    def add_to_queue(self, user_id: int, game_type: str, bet_amount: int):
        """اضافه به صف بازی سریع"""
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
                cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (match['user_id'],))
                cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (user_id,))
                return match['user_id']
            
            return None
    
    def remove_from_queue(self, user_id: int):
        """حذف از صف"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (user_id,))
    
    # ==============================================
    # توابع ماموریت روزانه
    # ==============================================
    
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
            row = cursor.fetchone()
            games_played = row['games_played'] if row else 0
            
            if games_played >= DAILY_MISSION_GAMES:
                cursor.execute('''
                    UPDATE daily_missions SET completed = TRUE
                    WHERE user_id = ? AND date = ?
                ''', (user_id, today))
    
    def get_daily_mission(self, user_id: int) -> Dict:
        """دریافت وضعیت ماموریت"""
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
                'games_played': mission['games_played'] if mission['games_played'] else 0,
                'completed': bool(mission['completed']),
                'claimed': bool(mission['claimed']),
                'target': DAILY_MISSION_GAMES,
                'reward': DAILY_MISSION_REWARD
            }
    
    def claim_daily_mission(self, user_id: int) -> bool:
        """دریافت جایزه ماموریت"""
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
    
    # ==============================================
    # توابع قفل بازی
    # ==============================================
    
    def lock_user_game(self, user_id: int, game_name: str):
        """قفل کردن کاربر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO game_locks (user_id, game_name, locked_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, game_name))
    
    def unlock_user(self, user_id: int):
        """آزاد کردن قفل"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM game_locks WHERE user_id = ?", (user_id,))
    
    def is_user_locked(self, user_id: int) -> bool:
        """بررسی قفل بودن"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM game_locks WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row['count'] > 0 if row else False
    
    # ==============================================
    # توابع یادآوری
    # ==============================================
    
    def get_users_for_reminder(self) -> List[int]:
        """دریافت کاربران برای یادآوری"""
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
    
    def update_reminder(self, user_id: int):
        """به‌روزرسانی یادآوری"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO reminders (user_id, last_reminder)
                VALUES (?, CURRENT_TIMESTAMP)
            ''', (user_id,))
    
    # ==============================================
    # توابع آماری
    # ==============================================
    
    def get_all_users(self) -> List[Dict]:
        """لیست همه کاربران"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY join_date DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_users_count(self) -> int:
        """تعداد کاربران"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def get_total_balance(self) -> int:
        """موجودی کل"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(balance) as total FROM users")
            row = cursor.fetchone()
            return row['total'] if row and row['total'] else 0

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
    waiting_withdraw_name = State()
    waiting_room_code = State()
    waiting_room_bet = State()
    waiting_quick_bet = State()
    playing_game = State()

class AdminStates(StatesGroup):
    waiting_for_password = State()
    admin_menu = State()
    broadcast_message = State()

# ==============================================
# توابع کمکی
# ==============================================

async def check_channel_membership(user_id: int) -> Tuple[bool, str]:
    """بررسی عضویت در کانال‌های اجباری"""
    not_joined = []
    
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except Exception as e:
            logger.warning(f"خطا در بررسی عضویت کانال {channel['id']}: {e}")
            continue
    
    if not_joined:
        channels_text = "\n".join([f"• [{ch['name']}]({ch['link']})" for ch in not_joined])
        return False, f"⛔ لطفاً ابتدا در کانال‌های زیر عضو شوید:\n\n{channels_text}\n\n✅ سپس /start را بزنید."
    
    return True, ""

async def send_withdraw_log(request: Dict, status: str):
    """ارسال گزارش برداشت به کانال"""
    try:
        emoji = "✅" if status == "approved" else "❌" if status == "rejected" else "⏳"
        status_fa = "تایید شده" if status == "approved" else "رد شده" if status == "rejected" else "در انتظار"
        
        log_text = f"""
{emoji} **گزارش برداشت #{request['id']}**

👤 کاربر: {request.get('first_name', 'نامشخص')}
🆔 شناسه: `{request['user_id']}`
💰 سکه: {request['amount_coins']:,}
💵 تومان: {request['amount_toman']:,}
💳 کارت: `{request['card_number']}`
👤 صاحب: {request['card_holder']}
📊 وضعیت: {status_fa}
⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        await bot.send_message(WITHDRAW_LOG_CHANNEL, log_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"خطا در ارسال به کانال: {e}")

# ==============================================
# کیبوردها
# ==============================================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد اصلی"""
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
    """منوی بازی‌ها"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="🎮 ساخت اتاق (بازی با دوست)", callback_data="game_create_room"))
    builder.row(InlineKeyboardButton(text="🔑 ورود با کد", callback_data="game_join_room"))
    builder.row(InlineKeyboardButton(text="🎯 بازی سریع (حریف تصادفی)", callback_data="game_quick_match"))
    builder.row(InlineKeyboardButton(text="🎲 بازی تاس (با ربات)", callback_data="game_dice_bot"))
    builder.row(InlineKeyboardButton(text="🎪 قرعه‌کشی (با ربات)", callback_data="game_lottery_bot"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main"))
    
    return builder.as_markup()

def get_bet_amount_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """کیبورد انتخاب مبلغ"""
    builder = InlineKeyboardBuilder()
    
    for price in GAME_PRICES:
        builder.row(InlineKeyboardButton(
            text=f"💰 {price:,} سکه",
            callback_data=f"{prefix}_{price}"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
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
    db.create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
        invited_by
    )
    
    bot_username = (await bot.get_me()).username
    
    welcome_text = f"""
🎰 **به ربات کازینو خوش آمدید!**

👤 {message.from_user.first_name} عزیز

🎮 **بازی‌ها:**
• بازی با دوستان (اتاق خصوصی)
• بازی سریع (حریف تصادفی)
• تاس و قرعه‌کشی با ربات

💰 **قیمت‌ها:** {' | '.join([f'{p:,} سکه' for p in GAME_PRICES])}
💵 **نرخ:** هر {COIN_TO_TOMAN//1000}۰۰ سکه = {COIN_TO_TOMAN*100:,} تومان

👥 **لینک دعوت شما:**
`https://t.me/{bot_username}?start={user_id}`

🎯 یک گزینه را انتخاب کنید:
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
        "🎮 **منوی بازی‌ها**\n\n"
        "🎮 **ساخت اتاق:** با دوست خود بازی کنید\n"
        "🔑 **ورود با کد:** وارد اتاق دوست شوید\n"
        "🎯 **بازی سریع:** با حریف تصادفی\n"
        "🤖 **بازی با ربات:** تاس و قرعه‌کشی",
        reply_markup=get_games_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text == "👤 حساب من")
async def show_profile(message: Message):
    """نمایش پروفایل"""
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await message.answer("❌ ابتدا /start را بزنید.")
        return
    
    profile_text = f"""
👤 **پروفایل کاربری**

🆔 شناسه: `{user['user_id']}`
👤 نام: {user['first_name'] or 'نامشخص'}
📅 عضویت: {user['join_date'][:10] if user['join_date'] else 'نامشخص'}

💰 **سکه:** {user['balance']:,}
💎 **الماس:** {user['diamonds']:,}
🎮 **بازی‌ها:** {user['total_games']:,}
    """
    
    await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "👥 زیرمجموعه‌گیری")
async def show_referral(message: Message):
    """نمایش زیرمجموعه‌گیری"""
    user_id = message.from_user.id
    stats = db.get_invite_stats(user_id)
    
    bot_username = (await bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?start={user_id}"
    
    referral_text = f"""
👥 **زیرمجموعه‌گیری**

💎 با دعوت دوستان خود الماس رایگان دریافت کنید!

✏️ **لینک دعوت شما:**
`{invite_link}`

📊 **آمار:**
• 👥 کل زیرمجموعه‌ها: {stats['total_invites']} نفر
• ✅ زیرمجموعه‌های فعال: {stats['active_invites']} نفر
• 💎 الماس‌های کسب شده: {stats['diamonds_earned']}

⚠️ **قوانین:**
• هر زیرمجموعه فعال = ۱ الماس
• زیرمجموعه فعال = حداقل ۱ بازی
• اولین برداشت: نیاز به {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال
    """
    
    await message.answer(referral_text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "🎯 ماموریت روزانه")
async def show_daily_mission(message: Message):
    """نمایش ماموریت روزانه"""
    user_id = message.from_user.id
    mission = db.get_daily_mission(user_id)
    
    progress_bar = "▓" * mission['games_played'] + "░" * (mission['target'] - mission['games_played'])
    
    mission_text = f"""
🎯 **ماموریت روزانه**

📋 وظیفه: {mission['target']} بازی انجام دهید
🎁 جایزه: {mission['reward']:,} سکه رایگان

📊 پیشرفت: [{progress_bar}] {mission['games_played']}/{mission['target']}

{
    '✅ کامل شده! روی دکمه زیر کلیک کنید 👇' if mission['completed'] and not mission['claimed'] 
    else '🎉 جایزه دریافت شد!' if mission['claimed'] 
    else '🔴 ادامه دهید...'
}
    """
    
    builder = InlineKeyboardBuilder()
    if mission['completed'] and not mission['claimed']:
        builder.row(InlineKeyboardButton(text="🎁 دریافت جایزه", callback_data="claim_daily_mission"))
    
    await message.answer(
        mission_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup() if mission['completed'] and not mission['claimed'] else None
    )

@router.message(F.text == "💰 خرید سکه")
async def show_buy_coins(message: Message):
    """نمایش خرید سکه"""
    buy_text = f"""
💰 **خرید سکه (فقط کارت به کارت)**

💵 **نرخ:** هر {COIN_TO_TOMAN//1000}۰۰ سکه = {COIN_TO_TOMAN*100:,} تومان

📌 **شماره کارت:**
`{ADMIN_CARD_NUMBER}`
👤 به نام: {ADMIN_CARD_HOLDER}

📝 گزینه مورد نظر را انتخاب کنید:
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 مبلغ دلخواه", callback_data="buy_custom_amount"))
    
    for pkg in [50, 100, 200, 500, 1000]:
        toman = pkg * COIN_TO_TOMAN
        builder.row(InlineKeyboardButton(
            text=f"💰 {pkg:,} سکه = {toman:,} تومان",
            callback_data=f"buy_package_{pkg}"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main"))
    
    await message.answer(buy_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "💎 برداشت")
async def show_withdraw(message: Message):
    """نمایش منوی برداشت"""
    user_id = message.from_user.id
    user = db.get_user(user_id)
    can_withdraw, reason = db.can_withdraw(user_id)
    
    if not can_withdraw:
        await message.answer(f"❌ {reason}")
        return
    
    withdraw_text = f"""
💎 **برداشت سکه**

💰 موجودی: {user['balance']:,} سکه
💵 معادل: {user['balance'] * COIN_TO_TOMAN:,} تومان

⚠️ **قوانین:**
• حداقل: {MIN_WITHDRAW_COINS} سکه
• نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان

برای درخواست برداشت کلیک کنید 👇
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💎 درخواست برداشت", callback_data="request_withdraw"))
    
    await message.answer(withdraw_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "❓ راهنما")
async def show_help(message: Message):
    """راهنما"""
    help_text = """
📚 **راهنمای ربات**

🎮 **بازی‌ها:**
• ساخت اتاق → کد رو به دوستت بده
• ورود با کد → کد رو از دوستت بگیر
• بازی سریع → منتظر حریف تصادفی بمون
• تاس و قرعه‌کشی → با ربات بازی کن

💰 **مالی:**
• خرید با کارت به کارت
• برداشت با شرط زیرمجموعه

🎁 **ماموریت روزانه:** ۳ بازی = ۵۰ سکه
👥 **زیرمجموعه:** هر نفر = ۱ الماس
    """
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

# ==============================================
# هندلرهای خرید سکه
# ==============================================

@router.callback_query(F.data == "buy_custom_amount")
async def buy_custom(callback: CallbackQuery, state: FSMContext):
    """خرید با مبلغ دلخواه"""
    await state.set_state(UserStates.waiting_card_amount)
    await callback.message.answer(
        "💰 چند سکه می‌خواهید؟\n"
        f"💵 نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان\n\n"
        "📝 تعداد سکه را وارد کنید:"
    )

@router.message(UserStates.waiting_card_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    """پردازش مبلغ دلخواه"""
    try:
        coins = int(message.text)
        if coins <= 0:
            raise ValueError
    except:
        await message.answer("❌ عدد معتبر وارد کنید!")
        return
    
    toman = coins * COIN_TO_TOMAN
    
    await state.update_data(buy_coins=coins, buy_toman=toman)
    await state.set_state(UserStates.waiting_for_receipt)
    
    await message.answer(
        f"💳 **اطلاعات پرداخت**\n\n"
        f"💰 سکه: {coins:,}\n"
        f"💵 مبلغ: {toman:,} تومان\n\n"
        f"📌 **شماره کارت:**\n`{ADMIN_CARD_NUMBER}`\n"
        f"👤 به نام: {ADMIN_CARD_HOLDER}\n\n"
        f"📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("buy_package_"))
async def buy_package(callback: CallbackQuery, state: FSMContext):
    """خرید بسته"""
    coins = int(callback.data.split("_")[2])
    toman = coins * COIN_TO_TOMAN
    
    await state.update_data(buy_coins=coins, buy_toman=toman)
    await state.set_state(UserStates.waiting_for_receipt)
    
    await callback.message.answer(
        f"💳 **پرداخت**\n\n"
        f"📦 بسته: {coins:,} سکه\n"
        f"💵 مبلغ: {toman:,} تومان\n\n"
        f"📌 **شماره کارت:**\n`{ADMIN_CARD_NUMBER}`\n\n"
        f"📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(UserStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    """پردازش رسید"""
    data = await state.get_data()
    coins = data.get('buy_coins', 0)
    toman = data.get('buy_toman', 0)
    
    # اطلاع به ادمین
    admin_text = f"""
🔔 **درخواست خرید سکه**

👤 {message.from_user.full_name}
🆔 `{message.from_user.id}`
💰 {coins:,} سکه
💵 {toman:,} تومان
⏰ {datetime.now().strftime('%H:%M:%S')}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_buy_{message.from_user.id}_{coins}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_buy_{message.from_user.id}")
    )
    
    await bot.send_message(ADMIN_USER_ID, admin_text, parse_mode=ParseMode.MARKDOWN)
    await bot.forward_message(ADMIN_USER_ID, message.chat.id, message.message_id)
    await bot.send_message(ADMIN_USER_ID, "⚡ اقدام:", reply_markup=builder.as_markup())
    
    await message.answer("✅ رسید دریافت شد. منتظر تایید باشید.")
    await state.clear()

@router.callback_query(F.data.startswith("approve_buy_"))
async def approve_buy(callback: CallbackQuery):
    """تایید خرید"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    coins = int(parts[3])
    
    db.update_balance(user_id, coins, 'deposit', f'خرید {coins} سکه')
    
    await callback.message.edit_text(f"✅ {coins:,} سکه به کاربر {user_id} اضافه شد.")
    
    try:
        await bot.send_message(user_id, f"✅ خرید تایید شد!\n💰 {coins:,} سکه اضافه شد.")
    except:
        pass

@router.callback_query(F.data.startswith("reject_buy_"))
async def reject_buy(callback: CallbackQuery):
    """رد خرید"""
    user_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(f"❌ خرید کاربر {user_id} رد شد.")
    
    try:
        await bot.send_message(user_id, "❌ خرید تایید نشد.")
    except:
        pass

# ==============================================
# هندلرهای برداشت
# ==============================================

@router.callback_query(F.data == "request_withdraw")
async def request_withdraw(callback: CallbackQuery, state: FSMContext):
    """درخواست برداشت"""
    user_id = callback.from_user.id
    can, reason = db.can_withdraw(user_id)
    
    if not can:
        await callback.answer(reason, show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_withdraw_amount)
    await callback.message.answer(
        f"💰 چند سکه برداشت می‌کنید؟\n"
        f"💵 نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان\n"
        f"⚠️ حداقل: {MIN_WITHDRAW_COINS} سکه\n\n"
        "📝 تعداد را وارد کنید:"
    )

@router.message(UserStates.waiting_withdraw_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    """پردازش مبلغ برداشت"""
    try:
        coins = int(message.text)
        if coins < MIN_WITHDRAW_COINS:
            await message.answer(f"❌ حداقل {MIN_WITHDRAW_COINS} سکه!")
            return
    except:
        await message.answer("❌ عدد معتبر وارد کنید!")
        return
    
    if coins > db.get_user_balance(message.from_user.id):
        await message.answer("❌ موجودی کافی نیست!")
        return
    
    toman = coins * COIN_TO_TOMAN
    
    await state.update_data(wd_coins=coins, wd_toman=toman)
    await state.set_state(UserStates.waiting_withdraw_card)
    
    await message.answer(
        f"💵 مبلغ: {toman:,} تومان\n\n"
        "💳 شماره کارت ۱۶ رقمی را وارد کنید:"
    )

@router.message(UserStates.waiting_withdraw_card)
async def process_withdraw_card(message: Message, state: FSMContext):
    """پردازش شماره کارت"""
    card = message.text.replace(" ", "").replace("-", "")
    
    if not card.isdigit() or len(card) != 16:
        await message.answer("❌ شماره کارت باید ۱۶ رقم باشد!")
        return
    
    await state.update_data(wd_card=card)
    await state.set_state(UserStates.waiting_withdraw_name)
    
    await message.answer("👤 نام صاحب کارت را وارد کنید:")

@router.message(UserStates.waiting_withdraw_name)
async def process_withdraw_name(message: Message, state: FSMContext):
    """نهایی کردن برداشت"""
    data = await state.get_data()
    coins = data['wd_coins']
    toman = data['wd_toman']
    card = data['wd_card']
    holder = message.text.strip()
    
    request_id = db.create_withdraw_request(message.from_user.id, coins, card, holder)
    
    # ارسال به کانال
    await send_withdraw_log({
        'id': request_id,
        'user_id': message.from_user.id,
        'first_name': message.from_user.first_name,
        'amount_coins': coins,
        'amount_toman': toman,
        'card_number': card,
        'card_holder': holder
    }, 'pending')
    
    # اطلاع به ادمین
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_wd_{request_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_wd_{request_id}")
    )
    
    await bot.send_message(
        ADMIN_USER_ID,
        f"💎 **درخواست برداشت #{request_id}**\n"
        f"👤 {message.from_user.full_name}\n"
        f"💰 {coins:,} سکه = {toman:,} تومان\n"
        f"💳 `{card}`\n👤 {holder}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )
    
    await message.answer(f"✅ درخواست ثبت شد.\n💰 {coins:,} سکه = {toman:,} تومان\n⏰ منتظر تایید باشید.")
    await state.clear()

@router.callback_query(F.data.startswith("approve_wd_"))
async def approve_withdraw(callback: CallbackQuery):
    """تایید برداشت"""
    request_id = int(callback.data.split("_")[2])
    request = db.process_withdraw(request_id, True, callback.from_user.id)
    
    if request:
        await send_withdraw_log(request, 'approved')
        try:
            await bot.send_message(request['user_id'], f"✅ برداشت {request['amount_toman']:,} تومان تایید شد.")
        except:
            pass
    
    await callback.answer("✅ تایید شد")
    await callback.message.delete()

@router.callback_query(F.data.startswith("reject_wd_"))
async def reject_withdraw(callback: CallbackQuery):
    """رد برداشت"""
    request_id = int(callback.data.split("_")[2])
    request = db.process_withdraw(request_id, False, callback.from_user.id)
    
    if request:
        await send_withdraw_log(request, 'rejected')
        try:
            await bot.send_message(request['user_id'], "❌ برداشت تایید نشد. سکه‌ها برگشت خورد.")
        except:
            pass
    
    await callback.answer("❌ رد شد")
    await callback.message.delete()

# ==============================================
# هندلرهای بازی‌ها
# ==============================================

@router.callback_query(F.data == "game_create_room")
async def create_room(callback: CallbackQuery, state: FSMContext):
    """ساخت اتاق"""
    if db.is_user_locked(callback.from_user.id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_room_bet)
    await callback.message.edit_text(
        "🎮 **ساخت اتاق**\n\n💰 مبلغ را انتخاب کنید:",
        reply_markup=get_bet_amount_keyboard("room"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("room_"))
async def process_room_bet(callback: CallbackQuery, state: FSMContext):
    """پردازش مبلغ اتاق"""
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_user_balance(user_id) < bet:
        await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    
    room_id = db.create_game_room(user_id, bet)
    db.update_balance(user_id, -bet, 'game_bet', f'ساخت اتاق #{room_id}')
    db.lock_user_game(user_id, f'room_{room_id}')
    
    await state.clear()
    
    await callback.message.edit_text(
        f"🎮 **اتاق ساخته شد!**\n\n"
        f"🔑 **کد:** `{room_id}`\n"
        f"💰 **مبلغ:** {bet:,} سکه\n\n"
        f"📋 کد رو به دوستت بده\n"
        f"⏰ منتظر بازیکن دوم...",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="❌ لغو", callback_data=f"cancel_room_{room_id}")
        ).as_markup()
    )

@router.callback_query(F.data == "game_join_room")
async def join_room(callback: CallbackQuery, state: FSMContext):
    """ورود به اتاق"""
    if db.is_user_locked(callback.from_user.id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_room_code)
    await callback.message.edit_text("🔑 کد ۶ رقمی اتاق را وارد کنید:")

@router.message(UserStates.waiting_room_code)
async def process_room_code(message: Message, state: FSMContext):
    """پردازش کد اتاق"""
    code = message.text.strip()
    user_id = message.from_user.id
    
    if not code.isdigit() or len(code) != 6:
        await message.answer("❌ کد باید ۶ رقم باشد!")
        return
    
    if db.join_game_room(code, user_id):
        await state.clear()
        
        # بازی شروع میشه
        winner = random.choice([user_id, ADMIN_USER_ID])  # موقتاً تصادفی
        prize = 1000  # مبلغ نمونه
        
        db.update_balance(winner, prize, 'game_win', f'برد در اتاق #{code}')
        db.unlock_user(user_id)
        db.update_daily_mission(user_id)
        
        await message.answer(
            f"🎮 **وارد اتاق شدید!**\n🏆 برنده: `{winner}`\n💰 جایزه: {prize:,} سکه",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("❌ اتاق یافت نشد یا پر است!")

@router.callback_query(F.data == "game_quick_match")
async def quick_match(callback: CallbackQuery, state: FSMContext):
    """بازی سریع"""
    if db.is_user_locked(callback.from_user.id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    await state.set_state(UserStates.waiting_quick_bet)
    await callback.message.edit_text(
        "🎯 **بازی سریع**\n\n💰 مبلغ را انتخاب کنید:",
        reply_markup=get_bet_amount_keyboard("quick"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("quick_"))
async def process_quick_match(callback: CallbackQuery, state: FSMContext):
    """پردازش بازی سریع"""
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_user_balance(user_id) < bet:
        await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    
    db.update_balance(user_id, -bet, 'game_bet', 'بازی سریع')
    db.lock_user_game(user_id, 'quick_match')
    
    opponent = db.find_match(user_id, bet, 'quick')
    
    if opponent:
        # حریف پیدا شد
        db.update_balance(user_id, bet * 2, 'game_win', 'برد بازی سریع')
        db.unlock_user(user_id)
        db.unlock_user(opponent)
        db.update_daily_mission(user_id)
        db.update_daily_mission(opponent)
        
        await state.clear()
        await callback.message.edit_text(
            f"🎯 **حریف پیدا شد!**\n💰 بردید: {bet*2:,} سکه",
            reply_markup=get_games_menu_keyboard()
        )
    else:
        db.add_to_queue(user_id, 'quick', bet)
        await state.clear()
        await callback.message.edit_text(
            f"🔍 **در جستجوی حریف...**\n💰 مبلغ: {bet:,} سکه\n⏰ منتظر بمانید...",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="❌ لغو", callback_data="cancel_search")
            ).as_markup()
        )

@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery):
    """لغو جستجو"""
    user_id = callback.from_user.id
    db.remove_from_queue(user_id)
    db.unlock_user(user_id)
    
    await callback.message.edit_text("❌ جستجو لغو شد.", reply_markup=get_games_menu_keyboard())

# ==============================================
# بازی با ربات
# ==============================================

@router.callback_query(F.data == "game_dice_bot")
async def dice_bot_menu(callback: CallbackQuery):
    """منوی تاس با ربات"""
    if db.is_user_locked(callback.from_user.id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎲 **تاس با ربات**\n\n💰 مبلغ را انتخاب کنید:",
        reply_markup=get_bet_amount_keyboard("dicebot"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("dicebot_"))
async def play_dice_bot(callback: CallbackQuery):
    """بازی تاس با ربات"""
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_user_balance(user_id) < bet:
        await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    
    db.update_balance(user_id, -bet, 'game_bet', 'تاس با ربات')
    db.lock_user_game(user_id, 'dice_bot')
    
    # ۱۶٪ شانس برد
    if random.random() < 0.16:
        prize = bet * 4
        db.update_balance(user_id, prize, 'game_win', 'برد تاس')
        result = f"🎉 **بردید!**\n💰 جایزه: {prize:,} سکه"
    else:
        result = "😢 **باختید!**"
    
    db.unlock_user(user_id)
    db.update_daily_mission(user_id)
    
    await callback.message.edit_text(
        f"🎲 **نتیجه تاس**\n\n{result}\n💳 موجودی: {db.get_user_balance(user_id):,}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🔄 مجدد", callback_data="game_dice_bot"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games")
        ).as_markup()
    )

@router.callback_query(F.data == "game_lottery_bot")
async def lottery_bot_menu(callback: CallbackQuery):
    """منوی قرعه‌کشی"""
    if db.is_user_locked(callback.from_user.id):
        await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎪 **قرعه‌کشی**\n\n💰 مبلغ را انتخاب کنید:",
        reply_markup=get_bet_amount_keyboard("lottery"),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("lottery_"))
async def play_lottery(callback: CallbackQuery):
    """قرعه‌کشی"""
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_user_balance(user_id) < bet:
        await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
        return
    
    db.update_balance(user_id, -bet, 'game_bet', 'قرعه‌کشی')
    db.lock_user_game(user_id, 'lottery')
    
    # فقط ۲٪ شانس برد
    if random.random() < 0.02:
        prize = bet * 10
        db.update_balance(user_id, prize, 'lottery_win', 'برنده قرعه‌کشی')
        result = f"🎉 **برنده شدید!**\n🎫 شماره شانس: {random.randint(1,100)}\n💰 جایزه: {prize:,} سکه"
    else:
        result = f"😢 **برنده نشدید**\n🎫 شماره: {random.randint(1,100)}"
    
    db.unlock_user(user_id)
    db.update_daily_mission(user_id)
    
    await callback.message.edit_text(
        f"🎪 **نتیجه قرعه‌کشی**\n\n{result}\n💳 موجودی: {db.get_user_balance(user_id):,}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🎪 مجدد", callback_data="game_lottery_bot"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games")
        ).as_markup()
    )

# ==============================================
# هندلرهای عمومی
# ==============================================

@router.callback_query(F.data == "claim_daily_mission")
async def claim_mission(callback: CallbackQuery):
    """دریافت جایزه ماموریت"""
    if db.claim_daily_mission(callback.from_user.id):
        await callback.answer(f"🎉 {DAILY_MISSION_REWARD} سکه دریافت شد!", show_alert=True)
    else:
        await callback.answer("❌ نمی‌توانید دریافت کنید!", show_alert=True)
    
    await show_daily_mission(callback.message)

@router.callback_query(F.data == "back_to_games")
async def back_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 منوی بازی‌ها:", reply_markup=get_games_menu_keyboard())

@router.callback_query(F.data == "back_to_main")
async def back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=get_main_keyboard())

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """لغو عملیات"""
    db.unlock_user(message.from_user.id)
    db.remove_from_queue(message.from_user.id)
    await state.clear()
    await message.answer("✅ لغو شد.", reply_markup=get_main_keyboard())

# ==============================================
# پنل مدیریت
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    """ورود ادمین"""
    user = db.get_user(message.from_user.id)
    if not user or not user.get('is_admin'):
        await message.answer("⛔ دسترسی غیرمجاز!")
        return
    
    await state.set_state(AdminStates.waiting_for_password)
    await message.answer("🔐 رمز عبور:")

@router.message(AdminStates.waiting_for_password)
async def admin_password(message: Message, state: FSMContext):
    """بررسی رمز"""
    if message.text == ADMIN_PASSWORD:
        await state.set_state(AdminStates.admin_menu)
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📊 آمار", callback_data="admin_stats"))
        builder.row(InlineKeyboardButton(text="💎 برداشت‌ها", callback_data="admin_withdrawals"))
        builder.row(InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="admin_broadcast"))
        builder.row(InlineKeyboardButton(text="🚪 خروج", callback_data="admin_exit"))
        
        await message.answer("🔰 پنل مدیریت:", reply_markup=builder.as_markup())
    else:
        await message.answer("❌ رمز اشتباه!")
        await state.clear()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """آمار"""
    users = db.get_users_count()
    balance = db.get_total_balance()
    
    await callback.message.edit_text(
        f"📊 **آمار**\n\n👥 کاربران: {users:,}\n💰 سکه: {balance:,}\n🕐 {datetime.now().strftime('%H:%M:%S')}",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "admin_withdrawals")
async def admin_withdrawals(callback: CallbackQuery):
    """درخواست‌های برداشت"""
    requests = db.get_pending_withdrawals()
    
    if not requests:
        await callback.message.edit_text("✅ هیچ درخواستی نیست.")
        return
    
    req = requests[0]
    text = f"""
💎 **درخواست #{req['id']}**

👤 {req['first_name']} {req['last_name'] or ''}
🆔 `{req['user_id']}`
💰 {req['amount_coins']:,} سکه = {req['amount_toman']:,} تومان
💳 `{req['card_number']}`
👤 {req['card_holder']}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_wd_{req['id']}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_wd_{req['id']}")
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """ارسال همگانی"""
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.answer("📢 پیام را ارسال کنید:")

@router.message(AdminStates.broadcast_message)
async def admin_send_broadcast(message: Message, state: FSMContext):
    """ارسال به همه"""
    users = db.get_all_users()
    success = 0
    
    for user in users:
        try:
            await bot.copy_message(user['user_id'], message.chat.id, message.message_id)
            success += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await message.answer(f"✅ ارسال به {success} کاربر")
    await state.clear()

@router.callback_query(F.data == "admin_exit")
async def admin_exit(callback: CallbackQuery, state: FSMContext):
    """خروج"""
    await state.clear()
    await callback.message.edit_text("🚪 خارج شدید.")

# ==============================================
# یادآوری خودکار
# ==============================================

async def reminder_scheduler():
    """زمان‌بند یادآوری"""
    while True:
        try:
            await asyncio.sleep(3600)  # هر ساعت
            
            users = db.get_users_for_reminder()
            for user_id in users:
                try:
                    await bot.send_message(
                        user_id,
                        "👋 سلام! مدت زیادی از آخرین بازدید شما می‌گذرد.\n"
                        "🎮 برگرد و بازی کن!\n"
                        "🎁 ماموریت روزانه منتظر توست!\n\n"
                        "/start"
                    )
                    db.update_reminder(user_id)
                except:
                    pass
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"خطا در یادآوری: {e}")

# ==============================================
# راه‌اندازی
# ==============================================

@router.errors()
async def error_handler(update: types.Update, exception: Exception):
    """مدیریت خطا"""
    logger.error(f"خطا: {exception}", exc_info=True)
    return True

async def main():
    """تابع اصلی"""
    dp.include_router(router)
    
    # راه‌اندازی یادآوری
    asyncio.create_task(reminder_scheduler())
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 ربات آماده!")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
