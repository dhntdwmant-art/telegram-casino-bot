# ==============================================
# 🎰 ربات کازینو و شرط‌بندی تلگرام - نسخه کامل
# تمام بازی‌های دو نفره + ربات + زیرمجموعه + برداشت
# ==============================================

import asyncio
import logging
import sqlite3
import random
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Message, CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.enums import ParseMode

# ==============================================
# تنظیمات اولیه
# ==============================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7548145568"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "09158029469")

# کانال‌ها
REQUIRED_CHANNELS = [
    {"id": "@gozaresh_taj", "name": "گزارشات برداشت", "link": "https://t.me/gozaresh_taj"}
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
# لاگینگ
# ==============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==============================================
# دیتابیس
# ==============================================

class Database:
    def __init__(self, db_path: str = "casino_bot.db"):
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
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    balance INTEGER DEFAULT 0,
                    diamonds INTEGER DEFAULT 0,
                    invited_by INTEGER,
                    invite_code TEXT,
                    total_invites INTEGER DEFAULT 0,
                    total_games INTEGER DEFAULT 0,
                    first_withdraw_used BOOLEAN DEFAULT FALSE,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE,
                    is_admin BOOLEAN DEFAULT FALSE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount INTEGER,
                    description TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    creator_choice TEXT,
                    player2_choice TEXT,
                    winner_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS match_queue (
                    user_id INTEGER UNIQUE,
                    game_type TEXT,
                    bet_amount INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS withdraw_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount_coins INTEGER,
                    amount_toman INTEGER,
                    card_number TEXT,
                    card_holder TEXT,
                    status TEXT DEFAULT 'pending',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_missions (
                    user_id INTEGER,
                    date TEXT,
                    games_played INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    claimed BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (user_id, date)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_locks (
                    user_id INTEGER PRIMARY KEY,
                    game_name TEXT,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    user_id INTEGER PRIMARY KEY,
                    last_reminder TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, is_admin, invite_code)
                VALUES (?, TRUE, ?)
            ''', (ADMIN_USER_ID, str(ADMIN_USER_ID)))
    
    def create_user(self, user_id, username=None, first_name=None, last_name=None, invited_by=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, invited_by, invite_code)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, invited_by, str(user_id)))
                
                if invited_by and invited_by != user_id:
                    cursor.execute('''
                        UPDATE users SET diamonds = diamonds + 1, total_invites = total_invites + 1
                        WHERE user_id = ?
                    ''', (invited_by,))
            else:
                cursor.execute('''
                    UPDATE users SET username = ?, first_name = ?, last_name = ? WHERE user_id = ?
                ''', (username, first_name, last_name, user_id))
    
    def get_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_balance(self, user_id):
        user = self.get_user(user_id)
        return user['balance'] if user else 0
    
    def update_balance(self, user_id, amount, ttype, desc):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET balance = balance + ?, last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, user_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, ttype, amount, desc))
    
    def lock_user(self, user_id, game_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO game_locks (user_id, game_name, locked_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, game_name))
    
    def unlock_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM game_locks WHERE user_id = ?", (user_id,))
    
    def is_locked(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as c FROM game_locks WHERE user_id = ?", (user_id,))
            return cursor.fetchone()['c'] > 0
    
    def create_room(self, creator_id, bet_amount, game_type='waiting'):
        room_id = str(random.randint(100000, 999999))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO game_rooms (room_id, creator_id, bet_amount, game_type)
                VALUES (?, ?, ?, ?)
            ''', (room_id, creator_id, bet_amount, game_type))
        return room_id
    
    def join_room(self, room_id, player2_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM game_rooms WHERE room_id = ? AND status = 'waiting'", (room_id,))
            room = cursor.fetchone()
            if not room or room['creator_id'] == player2_id:
                return None
            cursor.execute('''
                UPDATE game_rooms SET player2_id = ?, status = 'playing' WHERE room_id = ?
            ''', (player2_id, room_id))
            return dict(room)
    
    def set_room_game(self, room_id, game_type):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE game_rooms SET game_type = ? WHERE room_id = ?", (game_type, room_id))
    
    def set_player_choice(self, room_id, player_num, choice):
        col = 'creator_choice' if player_num == 1 else 'player2_choice'
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE game_rooms SET {col} = ? WHERE room_id = ?", (choice, room_id))
    
    def get_room(self, room_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM game_rooms WHERE room_id = ?", (room_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def finish_room(self, room_id, winner_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE game_rooms SET status = 'finished', winner_id = ? WHERE room_id = ?
            ''', (winner_id, room_id))
    
    def add_to_queue(self, user_id, game_type, bet_amount):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO match_queue (user_id, game_type, bet_amount, joined_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, game_type, bet_amount))
    
    def find_match(self, user_id, bet_amount, game_type):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id FROM match_queue 
                WHERE bet_amount = ? AND game_type = ? AND user_id != ?
                ORDER BY joined_at LIMIT 1
            ''', (bet_amount, game_type, user_id))
            match = cursor.fetchone()
            if match:
                cursor.execute("DELETE FROM match_queue WHERE user_id IN (?, ?)", (user_id, match['user_id']))
                return match['user_id']
            return None
    
    def remove_from_queue(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM match_queue WHERE user_id = ?", (user_id,))
    
    def get_invite_stats(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as c FROM users WHERE invited_by = ?", (user_id,))
            total = cursor.fetchone()['c']
            cursor.execute("SELECT COUNT(*) as c FROM users WHERE invited_by = ? AND total_games >= 1", (user_id,))
            active = cursor.fetchone()['c']
            cursor.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            diamonds = row['diamonds'] if row else 0
        return {'total': total, 'active': active, 'diamonds': diamonds}
    
    def can_withdraw(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return False, "کاربر یافت نشد"
        if user['balance'] < MIN_WITHDRAW_COINS:
            return False, f"حداقل {MIN_WITHDRAW_COINS} سکه نیاز است"
        if not user['first_withdraw_used']:
            stats = self.get_invite_stats(user_id)
            if stats['active'] < MIN_INVITES_FIRST_WITHDRAW:
                return False, f"برای اولین برداشت، {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال نیاز دارید"
        return True, "مجاز"
    
    def create_withdraw_request(self, user_id, coins, card, holder):
        toman = coins * COIN_TO_TOMAN
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET balance = balance - ? WHERE user_id = ?
            ''', (coins, user_id))
            cursor.execute('''
                INSERT INTO withdraw_requests (user_id, amount_coins, amount_toman, card_number, card_holder)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, coins, toman, card, holder))
            return cursor.lastrowid
    
    def process_withdraw(self, request_id, approved):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM withdraw_requests WHERE id = ?", (request_id,))
            req = cursor.fetchone()
            if not req:
                return None
            if approved:
                cursor.execute("UPDATE withdraw_requests SET status = 'approved' WHERE id = ?", (request_id,))
                cursor.execute("UPDATE users SET first_withdraw_used = TRUE WHERE user_id = ?", (req['user_id'],))
            else:
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (req['amount_coins'], req['user_id']))
                cursor.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (request_id,))
            return dict(req)
    
    def get_pending_withdrawals(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT wr.*, u.username, u.first_name, u.last_name
                FROM withdraw_requests wr JOIN users u ON wr.user_id = u.user_id
                WHERE wr.status = 'pending' ORDER BY wr.timestamp DESC
            ''')
            return [dict(r) for r in cursor.fetchall()]
    
    def update_daily_mission(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO daily_missions (user_id, date, games_played) VALUES (?, ?, 0)", (user_id, today))
            cursor.execute("UPDATE daily_missions SET games_played = games_played + 1 WHERE user_id = ? AND date = ?", (user_id, today))
            cursor.execute("SELECT games_played FROM daily_missions WHERE user_id = ? AND date = ?", (user_id, today))
            played = cursor.fetchone()['games_played']
            if played >= DAILY_MISSION_GAMES:
                cursor.execute("UPDATE daily_missions SET completed = TRUE WHERE user_id = ? AND date = ?", (user_id, today))
    
    def get_daily_mission(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_missions WHERE user_id = ? AND date = ?", (user_id, today))
            row = cursor.fetchone()
            if not row:
                return {'played': 0, 'completed': False, 'claimed': False}
            return {'played': row['games_played'], 'completed': bool(row['completed']), 'claimed': bool(row['claimed'])}
    
    def claim_daily_mission(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        mission = self.get_daily_mission(user_id)
        if mission['completed'] and not mission['claimed']:
            self.update_balance(user_id, DAILY_MISSION_REWARD, 'mission', 'جایزه ماموریت روزانه')
            with self.get_connection() as conn:
                conn.cursor().execute("UPDATE daily_missions SET claimed = TRUE WHERE user_id = ? AND date = ?", (user_id, today))
            return True
        return False
    
    def get_users_count(self):
        with self.get_connection() as conn:
            return conn.cursor().execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    
    def get_total_balance(self):
        with self.get_connection() as conn:
            r = conn.cursor().execute("SELECT SUM(balance) as t FROM users").fetchone()
            return r['t'] or 0
    
    def get_all_users(self):
        with self.get_connection() as conn:
            return [dict(r) for r in conn.cursor().execute("SELECT * FROM users ORDER BY join_date DESC").fetchall()]
    
    def get_users_for_reminder(self):
        cutoff = datetime.now() - timedelta(hours=24)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id FROM users u LEFT JOIN reminders r ON u.user_id = r.user_id
                WHERE u.last_activity < ? AND u.is_banned = 0 AND u.is_admin = 0
                AND (r.last_reminder IS NULL OR r.last_reminder < ?)
            ''', (cutoff, cutoff))
            return [r['user_id'] for r in cursor.fetchall()]
    
    def update_reminder(self, user_id):
        with self.get_connection() as conn:
            conn.cursor().execute("INSERT OR REPLACE INTO reminders (user_id, last_reminder) VALUES (?, CURRENT_TIMESTAMP)", (user_id,))

# ==============================================
# ربات و روتر
# ==============================================

db = Database()
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()

# ==============================================
# State‌ها
# ==============================================

class States(StatesGroup):
    waiting_card_amount = State()
    waiting_receipt = State()
    waiting_withdraw_amount = State()
    waiting_withdraw_card = State()
    waiting_withdraw_name = State()
    waiting_room_code = State()
    waiting_room_bet = State()
    waiting_quick_bet = State()
    admin_password = State()
    admin_broadcast = State()

# ==============================================
# کیبوردها
# ==============================================

def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎮 بازی‌ها"), KeyboardButton(text="💰 خرید سکه"))
    builder.row(KeyboardButton(text="👤 حساب من"), KeyboardButton(text="👥 زیرمجموعه‌گیری"))
    builder.row(KeyboardButton(text="🎯 ماموریت روزانه"), KeyboardButton(text="💎 برداشت"))
    builder.row(KeyboardButton(text="❓ راهنما"))
    return builder.as_markup(resize_keyboard=True)

def games_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎮 ساخت اتاق (بازی با دوست)", callback_data="create_room"))
    builder.row(InlineKeyboardButton(text="🔑 ورود با کد", callback_data="join_room"))
    builder.row(InlineKeyboardButton(text="🎯 بازی سریع", callback_data="quick_match"))
    builder.row(InlineKeyboardButton(text="🤖 بازی با ربات", callback_data="bot_games"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    return builder.as_markup()

def bot_games_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 تاس با ربات", callback_data="bot_dice"))
    builder.row(InlineKeyboardButton(text="🎪 قرعه‌کشی", callback_data="bot_lottery"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games"))
    return builder.as_markup()

def bet_keyboard(prefix):
    builder = InlineKeyboardBuilder()
    for p in GAME_PRICES:
        builder.row(InlineKeyboardButton(text=f"💰 {p:,} سکه", callback_data=f"{prefix}_{p}"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games"))
    return builder.as_markup()

def game_types_keyboard(room_id):
    builder = InlineKeyboardBuilder()
    games = [
        ("✊ سنگ کاغذ قیچی", f"setgame_rps_{room_id}"),
        ("⚽ فوتبال", f"setgame_football_{room_id}"),
        ("🏀 بسکتبال", f"setgame_basketball_{room_id}"),
        ("🎯 دارت", f"setgame_darts_{room_id}"),
        ("🎳 بولینگ", f"setgame_bowling_{room_id}"),
        ("🎲 تاس", f"setgame_dice_{room_id}")
    ]
    for name, cb in games:
        builder.row(InlineKeyboardButton(text=name, callback_data=cb))
    return builder.as_markup()

# ==============================================
# بازی‌های دو نفره
# ==============================================

GAME_HANDLERS = {}  # دیکشنری برای ذخیره بازی‌های در انتظار

async def determine_winner(game_type, p1_choice, p2_choice):
    """تعیین برنده بازی"""
    if game_type == 'rps':
        # سنگ کاغذ قیچی
        if p1_choice == p2_choice:
            return 0  # مساوی
        wins = {'rock': 'scissors', 'paper': 'rock', 'scissors': 'paper'}
        return 1 if wins.get(p1_choice) == p2_choice else 2
    
    elif game_type == 'dice':
        # تاس - عدد بزرگتر برنده
        p1 = int(p1_choice)
        p2 = int(p2_choice)
        return 1 if p1 > p2 else (2 if p2 > p1 else 0)
    
    elif game_type == 'football':
        # فوتبال - گل زدن
        p1_score = random.randint(0, 5)
        p2_score = random.randint(0, 5)
        return 1 if p1_score > p2_score else (2 if p2_score > p1_score else 0)
    
    elif game_type == 'basketball':
        # بسکتبال
        p1_score = random.randint(10, 30) * 2
        p2_score = random.randint(10, 30) * 2
        return 1 if p1_score > p2_score else (2 if p2_score > p1_score else 0)
    
    elif game_type == 'darts':
        # دارت
        p1_score = random.randint(0, 180)
        p2_score = random.randint(0, 180)
        return 1 if p1_score > p2_score else (2 if p2_score > p1_score else 0)
    
    elif game_type == 'bowling':
        # بولینگ
        p1_score = random.randint(0, 300)
        p2_score = random.randint(0, 300)
        return 1 if p1_score > p2_score else (2 if p2_score > p1_score else 0)
    
    return random.choice([1, 2])

# ==============================================
# هندلرهای اصلی
# ==============================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # بررسی جوین
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(ch['id'], user_id)
            if member.status in ['left', 'kicked']:
                await message.answer(
                    f"⛔ لطفاً ابتدا عضو کانال زیر شوید:\n\n📢 [{ch['name']}]({ch['link']})\n\nسپس /start را بزنید.",
                    parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
                )
                return
        except:
            pass
    
    # کد دعوت
    args = message.text.split()
    invited_by = None
    if len(args) > 1:
        try:
            invited_by = int(args[1])
            if invited_by == user_id:
                invited_by = None
        except:
            pass
    
    db.create_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name, invited_by)
    
    bot_username = (await bot.get_me()).username
    
    await message.answer(
        f"🎰 **به کازینو خوش آمدید!**\n\n"
        f"👤 {message.from_user.first_name} عزیز\n\n"
        f"🎮 بازی‌های دو نفره و تک نفره\n"
        f"💰 قیمت‌ها: {' | '.join([f'{p:,}' for p in GAME_PRICES])} سکه\n"
        f"💵 نرخ برداشت: هر سکه = {COIN_TO_TOMAN:,} تومان\n\n"
        f"👥 **لینک دعوت:**\n`https://t.me/{bot_username}?start={user_id}`\n\n"
        f"💎 با دعوت دوستان الماس بگیرید!",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text == "🎮 بازی‌ها")
async def show_games(message: Message):
    if db.is_locked(message.from_user.id):
        await message.answer("⚠️ شما در حال بازی هستید!")
        return
    await message.answer("🎮 **منوی بازی‌ها**\n\nیک گزینه را انتخاب کنید:", reply_markup=games_menu(), parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "👤 حساب من")
async def profile(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return await message.answer("❌ /start را بزنید")
    await message.answer(
        f"👤 **پروفایل**\n\n"
        f"🆔 `{user['user_id']}`\n"
        f"💰 سکه: {user['balance']:,}\n"
        f"💎 الماس: {user['diamonds']:,}\n"
        f"🎮 بازی‌ها: {user['total_games']:,}",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text == "👥 زیرمجموعه‌گیری")
async def referral(message: Message):
    user_id = message.from_user.id
    stats = db.get_invite_stats(user_id)
    bot_username = (await bot.get_me()).username
    
    await message.answer(
        f"👥 **زیرمجموعه‌گیری**\n\n"
        f"✏️ لینک دعوت:\n`https://t.me/{bot_username}?start={user_id}`\n\n"
        f"📊 **آمار:**\n"
        f"• کل: {stats['total']} نفر\n"
        f"• فعال: {stats['active']} نفر\n"
        f"• الماس: {stats['diamonds']} 💎\n\n"
        f"⚠️ اولین برداشت: {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(F.text == "🎯 ماموریت روزانه")
async def daily_mission(message: Message):
    mission = db.get_daily_mission(message.from_user.id)
    bar = "▓" * mission['played'] + "░" * (DAILY_MISSION_GAMES - mission['played'])
    
    builder = InlineKeyboardBuilder()
    if mission['completed'] and not mission['claimed']:
        builder.row(InlineKeyboardButton(text="🎁 دریافت جایزه", callback_data="claim_mission"))
    
    await message.answer(
        f"🎯 **ماموریت روزانه**\n\n"
        f"📋 {DAILY_MISSION_GAMES} بازی انجام دهید\n"
        f"🎁 جایزه: {DAILY_MISSION_REWARD} سکه\n\n"
        f"[{bar}] {mission['played']}/{DAILY_MISSION_GAMES}\n\n"
        f"{'✅ کلیک کنید 👇' if mission['completed'] and not mission['claimed'] else '🎉 دریافت شد' if mission['claimed'] else '🔴 ادامه دهید...'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup() if mission['completed'] and not mission['claimed'] else None
    )

@router.message(F.text == "💰 خرید سکه")
async def buy_coins(message: Message):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 مبلغ دلخواه", callback_data="buy_custom"))
    for p in [50, 100, 200, 500, 1000]:
        builder.row(InlineKeyboardButton(text=f"💰 {p:,} سکه = {p*COIN_TO_TOMAN:,} تومان", callback_data=f"buypkg_{p}"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    
    await message.answer(
        f"💰 **خرید سکه**\n\n💵 نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان\n\n📌 شماره کارت:\n`{ADMIN_CARD_NUMBER}`\n👤 {ADMIN_CARD_HOLDER}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.message(F.text == "💎 برداشت")
async def withdraw_menu(message: Message):
    can, reason = db.can_withdraw(message.from_user.id)
    if not can:
        return await message.answer(f"❌ {reason}")
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💎 درخواست برداشت", callback_data="req_withdraw"))
    
    await message.answer(
        f"💎 **برداشت**\n\n💰 موجودی: {db.get_balance(message.from_user.id):,} سکه\n💵 معادل: {db.get_balance(message.from_user.id)*COIN_TO_TOMAN:,} تومان\n\n⚠️ حداقل: {MIN_WITHDRAW_COINS} سکه",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

# ==============================================
# بازی‌ها - ساخت اتاق
# ==============================================

@router.callback_query(F.data == "create_room")
async def create_room(callback: CallbackQuery, state: FSMContext):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
    
    await state.set_state(States.waiting_room_bet)
    await callback.message.edit_text("🎮 **ساخت اتاق**\n\n💰 مبلغ شرط را انتخاب کنید:", reply_markup=bet_keyboard("room"), parse_mode=ParseMode.MARKDOWN)

@router.callback_query(F.data.startswith("room_"))
async def room_bet_selected(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_balance(user_id) < bet:
        return await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
    
    db.update_balance(user_id, -bet, 'bet', f'ساخت اتاق')
    db.lock_user(user_id, 'room_creator')
    
    room_id = db.create_room(user_id, bet)
    
    await state.clear()
    
    await callback.message.edit_text(
        f"🎮 **اتاق ساخته شد!**\n\n"
        f"🔑 **کد:** `{room_id}`\n"
        f"💰 **مبلغ:** {bet:,} سکه\n\n"
        f"📋 کد را برای دوستت بفرست\n"
        f"🎯 سپس نوع بازی را انتخاب کن:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=game_types_keyboard(room_id)
    )

@router.callback_query(F.data.startswith("setgame_"))
async def set_game_type(callback: CallbackQuery):
    parts = callback.data.split("_")
    game_type = parts[1]
    room_id = parts[2]
    
    db.set_room_game(room_id, game_type)
    
    game_names = {
        'rps': '✊ سنگ کاغذ قیچی',
        'football': '⚽ فوتبال',
        'basketball': '🏀 بسکتبال',
        'darts': '🎯 دارت',
        'bowling': '🎳 بولینگ',
        'dice': '🎲 تاس'
    }
    
    await callback.message.edit_text(
        f"✅ **بازی انتخاب شد:** {game_names.get(game_type, game_type)}\n\n"
        f"🔑 کد اتاق: `{room_id}`\n"
        f"⏰ منتظر بازیکن دوم...\n\n"
        f"📋 دوستت باید /start بزند و گزینه 'ورود با کد' را انتخاب کند.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="❌ لغو", callback_data=f"cancel_room_{room_id}")
        ).as_markup()
    )

@router.callback_query(F.data == "join_room")
async def join_room(callback: CallbackQuery, state: FSMContext):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
    
    await state.set_state(States.waiting_room_code)
    await callback.message.edit_text("🔑 کد ۶ رقمی اتاق را وارد کنید:")

@router.message(States.waiting_room_code)
async def process_room_code(message: Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    
    if not code.isdigit() or len(code) != 6:
        return await message.answer("❌ کد باید ۶ رقم باشد!")
    
    room = db.join_room(code, user_id)
    if not room:
        return await message.answer("❌ اتاق یافت نشد یا پر است!")
    
    bet = room['bet_amount']
    
    if db.get_balance(user_id) < bet:
        db.update_balance(room['creator_id'], bet, 'refund', 'بازگشت سکه - حریف پول نداشت')
        db.unlock_user(room['creator_id'])
        return await message.answer("❌ موجودی شما کافی نیست!")
    
    db.update_balance(user_id, -bet, 'bet', f'ورود به اتاق {code}')
    db.lock_user(user_id, f'room_{code}')
    
    await state.clear()
    
    # شروع بازی
    game_type = room['game_type']
    await start_two_player_game(message, room, game_type)

async def start_two_player_game(message: Message, room: Dict, game_type: str):
    """شروع بازی دو نفره"""
    creator_id = room['creator_id']
    player2_id = room['player2_id']
    bet = room['bet_amount']
    room_id = room['room_id']
    
    game_names = {
        'rps': '✊ سنگ کاغذ قیچی',
        'football': '⚽ فوتبال',
        'basketball': '🏀 بسکتبال',
        'darts': '🎯 دارت',
        'bowling': '🎳 بولینگ',
        'dice': '🎲 تاس'
    }
    
    # برای بازی‌های شانسی (فوتبال، بسکتبال، دارت، بولینگ) - نتیجه تصادفی
    if game_type in ['football', 'basketball', 'darts', 'bowling']:
        winner_num = await determine_winner(game_type, None, None)
        
        if winner_num == 0:
            # مساوی - برگشت پول
            db.update_balance(creator_id, bet, 'refund', 'بازی مساوی')
            db.update_balance(player2_id, bet, 'refund', 'بازی مساوی')
            result_text = "🤝 **بازی مساوی شد!**\n💰 سکه‌ها برگشت خورد."
            winner_id = None
        else:
            winner_id = creator_id if winner_num == 1 else player2_id
            loser_id = player2_id if winner_num == 1 else creator_id
            prize = bet * 2
            db.update_balance(winner_id, prize, 'win', f'برد در {game_names[game_type]}')
            result_text = f"🏆 **برنده:** `{winner_id}`\n💰 جایزه: {prize:,} سکه"
        
        db.unlock_user(creator_id)
        db.unlock_user(player2_id)
        db.finish_room(room_id, winner_id)
        
        db.update_daily_mission(creator_id)
        db.update_daily_mission(player2_id)
        
        await message.answer(result_text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard())
        
        # اطلاع به بازیکن دیگر
        try:
            other_id = player2_id if message.from_user.id == creator_id else creator_id
            await bot.send_message(other_id, result_text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass
        
        return
    
    # برای بازی‌های انتخابی (سنگ کاغذ قیچی و تاس)
    if game_type == 'rps':
        choice_text = "انتخاب کنید:\n✊ سنگ | 📄 کاغذ | ✂️ قیچی"
        choices = [
            ("✊ سنگ", f"pvp_rock_{room_id}"),
            ("📄 کاغذ", f"pvp_paper_{room_id}"),
            ("✂️ قیچی", f"pvp_scissors_{room_id}")
        ]
    elif game_type == 'dice':
        choice_text = "یک عدد انتخاب کنید (۱ تا ۶):"
        choices = [(f"🎲 {i}", f"pvp_{i}_{room_id}") for i in range(1, 7)]
    
    builder = InlineKeyboardBuilder()
    for text, cb in choices:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    msg = f"🎮 **{game_names[game_type]}**\n\n💰 مبلغ: {bet:,} سکه\n\n{choice_text}"
    
    await message.answer(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
    
    try:
        other_id = player2_id if message.from_user.id == creator_id else creator_id
        await bot.send_message(other_id, msg, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
    except:
        pass

@router.callback_query(F.data.startswith("pvp_"))
async def process_pvp_choice(callback: CallbackQuery):
    """پردازش انتخاب بازیکن در بازی دو نفره"""
    parts = callback.data.split("_")
    choice = parts[1]
    room_id = parts[2]
    user_id = callback.from_user.id
    
    room = db.get_room(room_id)
    if not room or room['status'] != 'playing':
        return await callback.answer("❌ بازی در دسترس نیست!", show_alert=True)
    
    # تشخیص شماره بازیکن
    if user_id == room['creator_id']:
        player_num = 1
    elif user_id == room['player2_id']:
        player_num = 2
    else:
        return await callback.answer("❌ شما در این بازی نیستید!", show_alert=True)
    
    db.set_player_choice(room_id, player_num, choice)
    
    await callback.answer("✅ انتخاب ثبت شد. منتظر بازیکن دیگر...", show_alert=True)
    
    # بررسی آیا هر دو انتخاب کردند
    room = db.get_room(room_id)
    if room['creator_choice'] and room['player2_choice']:
        # هر دو انتخاب کردند - تعیین برنده
        winner_num = await determine_winner(room['game_type'], room['creator_choice'], room['player2_choice'])
        bet = room['bet_amount']
        creator_id = room['creator_id']
        player2_id = room['player2_id']
        
        if winner_num == 0:
            db.update_balance(creator_id, bet, 'refund', 'مساوی')
            db.update_balance(player2_id, bet, 'refund', 'مساوی')
            result = "🤝 **مساوی!**\n💰 سکه‌ها برگشت خورد."
        else:
            winner_id = creator_id if winner_num == 1 else player2_id
            prize = bet * 2
            db.update_balance(winner_id, prize, 'win', 'برد در بازی')
            result = f"🏆 **برنده:** `{winner_id}`\n💰 جایزه: {prize:,} سکه"
        
        db.unlock_user(creator_id)
        db.unlock_user(player2_id)
        db.finish_room(room_id, winner_id if winner_num != 0 else None)
        db.update_daily_mission(creator_id)
        db.update_daily_mission(player2_id)
        
        result += f"\n\nانتخاب‌ها:\n👤 بازیکن ۱: {room['creator_choice']}\n👤 بازیکن ۲: {room['player2_choice']}"
        
        for uid in [creator_id, player2_id]:
            try:
                await bot.send_message(uid, result, parse_mode=ParseMode.MARKDOWN)
            except:
                pass

# ==============================================
# بازی سریع
# ==============================================

@router.callback_query(F.data == "quick_match")
async def quick_match(callback: CallbackQuery, state: FSMContext):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
    
    await state.set_state(States.waiting_quick_bet)
    await callback.message.edit_text("🎯 **بازی سریع**\n\n💰 مبلغ را انتخاب کنید:", reply_markup=bet_keyboard("quick"), parse_mode=ParseMode.MARKDOWN)

@router.callback_query(F.data.startswith("quick_"))
async def quick_bet_selected(callback: CallbackQuery, state: FSMContext):
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_balance(user_id) < bet:
        return await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
    
    db.update_balance(user_id, -bet, 'bet', 'بازی سریع')
    db.lock_user(user_id, 'quick_match')
    
    # انتخاب بازی تصادفی
    game_type = random.choice(['rps', 'dice', 'football', 'basketball'])
    
    opponent = db.find_match(user_id, bet, game_type)
    
    if opponent:
        await state.clear()
        # حریف پیدا شد
        room_id = db.create_room(opponent, bet, game_type)
        db.join_room(room_id, user_id)
        db.update_balance(opponent, -bet, 'bet', f'بازی سریع - اتاق {room_id}')
        db.lock_user(opponent, f'room_{room_id}')
        db.lock_user(user_id, f'room_{room_id}')
        
        room = db.get_room(room_id)
        
        game_names = {
            'rps': '✊ سنگ کاغذ قیچی',
            'dice': '🎲 تاس',
            'football': '⚽ فوتبال',
            'basketball': '🏀 بسکتبال'
        }
        
        # برای بازی‌های شانسی
        if game_type in ['football', 'basketball']:
            winner_num = await determine_winner(game_type, None, None)
            if winner_num == 0:
                db.update_balance(opponent, bet, 'refund', 'مساوی')
                db.update_balance(user_id, bet, 'refund', 'مساوی')
                result = "🤝 مساوی! سکه‌ها برگشت خورد."
            else:
                winner_id = opponent if winner_num == 1 else user_id
                db.update_balance(winner_id, bet*2, 'win', 'برد بازی سریع')
                result = f"🏆 برنده: `{winner_id}`\n💰 {bet*2:,} سکه"
            
            db.unlock_user(user_id)
            db.unlock_user(opponent)
            db.update_daily_mission(user_id)
            db.update_daily_mission(opponent)
            
            for uid in [user_id, opponent]:
                try:
                    await bot.send_message(uid, f"🎯 **بازی سریع - {game_names[game_type]}**\n\n{result}", parse_mode=ParseMode.MARKDOWN)
                except:
                    pass
        else:
            # بازی انتخابی - ارسال به هر دو
            msg = f"🎯 **حریف پیدا شد!**\n🎮 {game_names[game_type]}\n💰 {bet:,} سکه"
            for uid in [user_id, opponent]:
                try:
                    await bot.send_message(uid, msg, parse_mode=ParseMode.MARKDOWN)
                except:
                    pass
        
        await callback.message.delete()
    else:
        db.add_to_queue(user_id, game_type, bet)
        await state.clear()
        await callback.message.edit_text(
            f"🔍 **در جستجوی حریف...**\n🎮 {game_type}\n💰 {bet:,} سکه\n⏰ منتظر بمانید...",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="❌ لغو", callback_data="cancel_search")
            ).as_markup()
        )

# ==============================================
# بازی با ربات
# ==============================================

@router.callback_query(F.data == "bot_games")
async def bot_games(callback: CallbackQuery):
    await callback.message.edit_text("🤖 **بازی با ربات**\n\nانتخاب کنید:", reply_markup=bot_games_menu())

@router.callback_query(F.data == "bot_dice")
async def bot_dice(callback: CallbackQuery):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ در حال بازی!", show_alert=True)
    await callback.message.edit_text("🎲 **تاس با ربات**\n\n💰 مبلغ:", reply_markup=bet_keyboard("botdice"))

@router.callback_query(F.data.startswith("botdice_"))
async def play_bot_dice(callback: CallbackQuery):
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_balance(user_id) < bet:
        return await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
    
    db.update_balance(user_id, -bet, 'bet', 'تاس با ربات')
    db.lock_user(user_id, 'bot_dice')
    
    # ۱۶٪ شانس برد
    won = random.random() < 0.16
    prize = bet * 4 if won else 0
    if won:
        db.update_balance(user_id, prize, 'win', 'برد تاس با ربات')
    
    db.unlock_user(user_id)
    db.update_daily_mission(user_id)
    
    await callback.message.edit_text(
        f"🎲 **تاس با ربات**\n\n"
        f"{'🎉 بردید!' if won else '😢 باختید!'}\n"
        f"💰 جایزه: {prize:,} سکه\n"
        f"💳 موجودی: {db.get_balance(user_id):,}",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🔄 مجدد", callback_data="bot_dice"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="bot_games")
        ).as_markup()
    )

@router.callback_query(F.data == "bot_lottery")
async def bot_lottery(callback: CallbackQuery):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ در حال بازی!", show_alert=True)
    await callback.message.edit_text("🎪 **قرعه‌کشی**\n\n💰 مبلغ:", reply_markup=bet_keyboard("lottery"))

@router.callback_query(F.data.startswith("lottery_"))
async def play_lottery(callback: CallbackQuery):
    bet = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    if db.get_balance(user_id) < bet:
        return await callback.answer("❌ موجودی کافی نیست!", show_alert=True)
    
    db.update_balance(user_id, -bet, 'bet', 'قرعه‌کشی')
    db.lock_user(user_id, 'lottery')
    
    # ۲٪ شانس
    won = random.random() < 0.02
    prize = bet * 10 if won else 0
    if won:
        db.update_balance(user_id, prize, 'win', 'برنده قرعه‌کشی')
    
    db.unlock_user(user_id)
    db.update_daily_mission(user_id)
    
    await callback.message.edit_text(
        f"🎪 **قرعه‌کشی**\n\n"
        f"{'🎉 برنده شدید!' if won else '😢 برنده نشدید'}\n"
        f"🎫 شماره: {random.randint(1,100)}\n"
        f"💰 جایزه: {prize:,} سکه\n"
        f"💳 موجودی: {db.get_balance(user_id):,}",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🎪 مجدد", callback_data="bot_lottery"),
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="bot_games")
        ).as_markup()
    )

# ==============================================
# هندلرهای خرید، برداشت، ماموریت
# ==============================================

@router.callback_query(F.data == "buy_custom")
async def buy_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.waiting_card_amount)
    await callback.message.answer("💰 چند سکه می‌خواهید؟\n📝 تعداد را وارد کنید:")

@router.message(States.waiting_card_amount)
async def process_custom(message: Message, state: FSMContext):
    try:
        coins = int(message.text)
        if coins <= 0:
            raise ValueError
    except:
        return await message.answer("❌ عدد معتبر وارد کنید!")
    
    toman = coins * COIN_TO_TOMAN
    await state.update_data(buy_coins=coins, buy_toman=toman)
    await state.set_state(States.waiting_receipt)
    
    await message.answer(
        f"💳 **اطلاعات پرداخت**\n\n"
        f"💰 سکه: {coins:,}\n💵 مبلغ: {toman:,} تومان\n\n"
        f"📌 شماره کارت:\n`{ADMIN_CARD_NUMBER}`\n👤 {ADMIN_CARD_HOLDER}\n\n"
        f"📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("buypkg_"))
async def buy_package(callback: CallbackQuery, state: FSMContext):
    coins = int(callback.data.split("_")[1])
    toman = coins * COIN_TO_TOMAN
    await state.update_data(buy_coins=coins, buy_toman=toman)
    await state.set_state(States.waiting_receipt)
    
    await callback.message.answer(
        f"💳 **پرداخت**\n\n📦 {coins:,} سکه = {toman:,} تومان\n\n"
        f"📌 شماره کارت:\n`{ADMIN_CARD_NUMBER}`\n\n📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(States.waiting_receipt, F.photo)
async def receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    coins = data['buy_coins']
    toman = data['buy_toman']
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appbuy_{message.from_user.id}_{coins}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejbuy_{message.from_user.id}")
    )
    
    await bot.send_message(ADMIN_USER_ID,
        f"🔔 خرید جدید\n👤 {message.from_user.full_name}\n💰 {coins:,} سکه\n💵 {toman:,} تومان",
        reply_markup=builder.as_markup()
    )
    await bot.forward_message(ADMIN_USER_ID, message.chat.id, message.message_id)
    
    await message.answer("✅ رسید ارسال شد. منتظر تایید باشید.")
    await state.clear()

@router.callback_query(F.data.startswith("appbuy_"))
async def approve_buy(callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id, coins = int(parts[1]), int(parts[2])
    db.update_balance(user_id, coins, 'deposit', f'خرید {coins} سکه')
    await callback.message.edit_text(f"✅ {coins:,} سکه به کاربر {user_id} اضافه شد.")
    try:
        await bot.send_message(user_id, f"✅ خرید تایید شد!\n💰 {coins:,} سکه اضافه شد.")
    except:
        pass

@router.callback_query(F.data.startswith("rejbuy_"))
async def reject_buy(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.message.edit_text(f"❌ خرید کاربر {user_id} رد شد.")
    try:
        await bot.send_message(user_id, "❌ خرید تایید نشد.")
    except:
        pass

@router.callback_query(F.data == "req_withdraw")
async def req_withdraw(callback: CallbackQuery, state: FSMContext):
    can, reason = db.can_withdraw(callback.from_user.id)
    if not can:
        return await callback.answer(reason, show_alert=True)
    
    await state.set_state(States.waiting_withdraw_amount)
    await callback.message.answer(f"💰 چند سکه برداشت می‌کنید؟\n⚠️ حداقل: {MIN_WITHDRAW_COINS}")

@router.message(States.waiting_withdraw_amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        coins = int(message.text)
        if coins < MIN_WITHDRAW_COINS or coins > db.get_balance(message.from_user.id):
            return await message.answer(f"❌ مقدار نامعتبر! حداقل {MIN_WITHDRAW_COINS}")
    except:
        return await message.answer("❌ عدد وارد کنید!")
    
    await state.update_data(wd_coins=coins)
    await state.set_state(States.waiting_withdraw_card)
    await message.answer(f"💵 {coins*COIN_TO_TOMAN:,} تومان\n\n💳 شماره کارت ۱۶ رقمی:")

@router.message(States.waiting_withdraw_card)
async def wd_card(message: Message, state: FSMContext):
    card = message.text.replace(" ", "").replace("-", "")
    if not card.isdigit() or len(card) != 16:
        return await message.answer("❌ شماره کارت ۱۶ رقم باشد!")
    
    await state.update_data(wd_card=card)
    await state.set_state(States.waiting_withdraw_name)
    await message.answer("👤 نام صاحب کارت:")

@router.message(States.waiting_withdraw_name)
async def wd_name(message: Message, state: FSMContext):
    data = await state.get_data()
    coins = data['wd_coins']
    card = data['wd_card']
    holder = message.text.strip()
    
    req_id = db.create_withdraw_request(message.from_user.id, coins, card, holder)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appwd_{req_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejwd_{req_id}")
    )
    
    await bot.send_message(ADMIN_USER_ID,
        f"💎 برداشت #{req_id}\n👤 {message.from_user.full_name}\n💰 {coins:,} سکه = {coins*COIN_TO_TOMAN:,} تومان\n💳 `{card}`\n👤 {holder}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )
    
    # ارسال به کانال
    try:
        await bot.send_message(WITHDRAW_LOG_CHANNEL,
            f"⏳ **درخواست برداشت #{req_id}**\n👤 {message.from_user.first_name}\n💰 {coins:,} سکه\n💵 {coins*COIN_TO_TOMAN:,} تومان\n💳 `{card}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass
    
    await message.answer(f"✅ درخواست ثبت شد.\n💰 {coins:,} سکه = {coins*COIN_TO_TOMAN:,} تومان\n⏰ منتظر تایید باشید.")
    await state.clear()

@router.callback_query(F.data.startswith("appwd_"))
async def approve_wd(callback: CallbackQuery):
    req_id = int(callback.data.split("_")[1])
    req = db.process_withdraw(req_id, True)
    if req:
        try:
            await bot.send_message(WITHDRAW_LOG_CHANNEL,
                f"✅ **برداشت تایید شد #{req_id}**\n💰 {req['amount_coins']:,} سکه\n💵 {req['amount_toman']:,} تومان\n💳 `{req['card_number']}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        try:
            await bot.send_message(req['user_id'], f"✅ برداشت {req['amount_toman']:,} تومان تایید شد.")
        except:
            pass
    await callback.message.delete()

@router.callback_query(F.data.startswith("rejwd_"))
async def reject_wd(callback: CallbackQuery):
    req_id = int(callback.data.split("_")[1])
    req = db.process_withdraw(req_id, False)
    if req:
        try:
            await bot.send_message(req['user_id'], "❌ برداشت تایید نشد. سکه‌ها برگشت خورد.")
        except:
            pass
    await callback.message.delete()

@router.callback_query(F.data == "claim_mission")
async def claim_mission(callback: CallbackQuery):
    if db.claim_daily_mission(callback.from_user.id):
        await callback.answer(f"🎉 {DAILY_MISSION_REWARD} سکه دریافت شد!", show_alert=True)
    else:
        await callback.answer("❌ نمی‌توانید دریافت کنید!", show_alert=True)

# ==============================================
# دکمه‌های عمومی
# ==============================================

@router.callback_query(F.data == "back_games")
async def back_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 منوی بازی‌ها:", reply_markup=games_menu())

@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=main_keyboard())

@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery):
    db.remove_from_queue(callback.from_user.id)
    db.unlock_user(callback.from_user.id)
    await callback.message.edit_text("❌ جستجو لغو شد.", reply_markup=games_menu())

@router.callback_query(F.data.startswith("cancel_room_"))
async def cancel_room(callback: CallbackQuery):
    room_id = callback.data.split("_")[2]
    room = db.get_room(room_id)
    if room and room['creator_id'] == callback.from_user.id:
        db.update_balance(callback.from_user.id, room['bet_amount'], 'refund', 'لغو اتاق')
        db.unlock_user(callback.from_user.id)
        db.finish_room(room_id, None)
    await callback.message.edit_text("❌ اتاق لغو شد.", reply_markup=games_menu())

# ==============================================
# ادمین
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    if not db.get_user(message.from_user.id).get('is_admin'):
        return await message.answer("⛔ دسترسی غیرمجاز!")
    await state.set_state(States.admin_password)
    await message.answer("🔐 رمز عبور:")

@router.message(States.admin_password)
async def admin_check(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📊 آمار", callback_data="adm_stats"))
        builder.row(InlineKeyboardButton(text="💎 برداشت‌ها", callback_data="adm_wd"))
        builder.row(InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="adm_bc"))
        builder.row(InlineKeyboardButton(text="🚪 خروج", callback_data="adm_exit"))
        await state.clear()
        await message.answer("🔰 پنل مدیریت:", reply_markup=builder.as_markup())
    else:
        await message.answer("❌ رمز اشتباه!")
        await state.clear()

@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    await callback.message.edit_text(f"📊 کاربران: {db.get_users_count():,}\n💰 سکه: {db.get_total_balance():,}")

@router.callback_query(F.data == "adm_wd")
async def adm_wd(callback: CallbackQuery):
    reqs = db.get_pending_withdrawals()
    if not reqs:
        return await callback.message.edit_text("✅ هیچ درخواستی نیست.")
    r = reqs[0]
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appwd_{r['id']}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejwd_{r['id']}")
    )
    await callback.message.edit_text(
        f"💎 #{r['id']}\n👤 {r['first_name']}\n💰 {r['amount_coins']:,} سکه\n💳 `{r['card_number']}`",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "adm_bc")
async def adm_bc(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_broadcast)
    await callback.message.answer("📢 پیام را ارسال کنید:")

@router.message(States.admin_broadcast)
async def adm_send_bc(message: Message, state: FSMContext):
    users = db.get_all_users()
    s = 0
    for u in users:
        try:
            await bot.copy_message(u['user_id'], message.chat.id, message.message_id)
            s += 1
        except:
            pass
        await asyncio.sleep(0.05)
    await message.answer(f"✅ ارسال به {s} کاربر")
    await state.clear()

@router.callback_query(F.data == "adm_exit")
async def adm_exit(callback: CallbackQuery):
    await callback.message.edit_text("🚪 خارج شدید.")

# ==============================================
# یادآوری خودکار
# ==============================================

async def reminder_task():
    while True:
        await asyncio.sleep(3600)
        try:
            for uid in db.get_users_for_reminder():
                try:
                    await bot.send_message(uid, "👋 برگرد و بازی کن!\n🎁 ماموریت روزانه منتظرته!\n\n/start")
                    db.update_reminder(uid)
                except:
                    pass
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"یادآوری: {e}")

# ==============================================
# اجرا
# ==============================================

@router.errors()
async def errors(update, exception):
    logger.error(f"خطا: {exception}")
    return True

async def main():
    dp.include_router(router)
    asyncio.create_task(reminder_task())
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 ربات آماده!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
