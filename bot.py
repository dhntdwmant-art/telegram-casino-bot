# ==============================================
# 🎰 ربات کازینو - نسخه نهایی با پنل پیشرفته
# ==============================================

import asyncio
import logging
import sqlite3
import random
import json
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton, KeyboardButton, Message, CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.enums import ParseMode

# ==============================================
# 🔧 تنظیمات
# ==============================================

BOT_TOKEN = "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ"
ADMIN_USER_ID = 7548145568
ADMIN_PASSWORD = "09158029769"

# تنظیمات پیش‌فرض (قابل تغییر از پنل)
DEFAULT_SETTINGS = {
    "card_number": "6062561009737464",
    "card_holder": "مجاور",
    "support_username": "@ad_tas",
    "required_channel_id": "@gozaresh_taj",
    "required_channel_link": "https://t.me/gozaresh_taj",
    "withdraw_log_channel": "@gozaresh_taj",
    "coin_to_toman": 1000,
    "min_withdraw_coins": 100,
    "min_invites_first_withdraw": 4,
    "game_prices": [50, 100, 200, 500, 1000],
    "daily_mission_games": 3,
    "daily_mission_reward": 50,
    "dice_win_chance": 16,
    "lottery_win_chance": 2,
    "min_bet": 10,
    "max_bet": 10000
}

# ==============================================
# 📊 لاگینگ
# ==============================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==============================================
# 🗄️ دیتابیس پیشرفته
# ==============================================

class Database:
    def __init__(self, db_path="casino.db"):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception as e:
            c.rollback()
            logger.error(f"DB Error: {e}")
            raise
        finally:
            c.close()
    
    def init_db(self):
        with self.conn() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                
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
                    total_wins INTEGER DEFAULT 0,
                    total_losses INTEGER DEFAULT 0,
                    first_withdraw_used INTEGER DEFAULT 0,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned INTEGER DEFAULT 0,
                    is_admin INTEGER DEFAULT 0,
                    ban_reason TEXT
                );
                
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount INTEGER,
                    description TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
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
                );
                
                CREATE TABLE IF NOT EXISTS match_queue (
                    user_id INTEGER UNIQUE,
                    game_type TEXT,
                    bet_amount INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
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
                    processed_at TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS daily_missions (
                    user_id INTEGER,
                    date TEXT,
                    games_played INTEGER DEFAULT 0,
                    completed INTEGER DEFAULT 0,
                    claimed INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                );
                
                CREATE TABLE IF NOT EXISTS game_locks (
                    user_id INTEGER PRIMARY KEY,
                    game_name TEXT,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                INSERT OR IGNORE INTO users (user_id, is_admin, invite_code) 
                VALUES (7548145568, 1, '7548145568');
            ''')
            
            # درج تنظیمات پیش‌فرض
            for key, value in DEFAULT_SETTINGS.items():
                c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", 
                         (key, json.dumps(value) if isinstance(value, (list, dict)) else str(value)))
    
    # ========== تنظیمات ==========
    
    def get_setting(self, key, default=None):
        with self.conn() as c:
            r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if not r:
                return default
            val = r['value']
            try:
                return json.loads(val)
            except:
                return val
    
    def set_setting(self, key, value):
        with self.conn() as c:
            val = json.dumps(value) if isinstance(value, (list, dict)) else str(value)
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    
    def get_all_settings(self):
        with self.conn() as c:
            rows = c.execute("SELECT * FROM settings").fetchall()
            settings = {}
            for r in rows:
                try:
                    settings[r['key']] = json.loads(r['value'])
                except:
                    settings[r['key']] = r['value']
            return settings
    
    # ========== کاربران ==========
    
    def get_user(self, user_id):
        with self.conn() as c:
            r = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            return dict(r) if r else None
    
    def create_user(self, user_id, username=None, first_name=None, last_name=None, invited_by=None):
        with self.conn() as c:
            exist = c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not exist:
                c.execute(
                    "INSERT INTO users (user_id, username, first_name, last_name, invited_by, invite_code) VALUES (?,?,?,?,?,?)",
                    (user_id, username, first_name, last_name, invited_by, str(user_id))
                )
                if invited_by and invited_by != user_id:
                    c.execute("UPDATE users SET diamonds=diamonds+1, total_invites=total_invites+1 WHERE user_id=?", (invited_by,))
            else:
                c.execute("UPDATE users SET username=?, first_name=?, last_name=? WHERE user_id=?", 
                         (username, first_name, last_name, user_id))
    
    def get_balance(self, user_id):
        with self.conn() as c:
            r = c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
            return r['balance'] if r else 0
    
    def set_balance(self, user_id, amount, admin_id=None):
        with self.conn() as c:
            old = c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
            old_balance = old['balance'] if old else 0
            diff = amount - old_balance
            c.execute("UPDATE users SET balance=?, last_activity=CURRENT_TIMESTAMP WHERE user_id=?", (amount, user_id))
            c.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?,?,?,?)",
                     (user_id, 'admin_set', diff, f'تنظیم موجودی توسط ادمین {admin_id}'))
    
    def add_balance(self, user_id, amount, ttype='deposit', desc=''):
        with self.conn() as c:
            c.execute("UPDATE users SET balance=balance+?, last_activity=CURRENT_TIMESTAMP WHERE user_id=?", (amount, user_id))
            c.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?,?,?,?)",
                     (user_id, ttype, amount, desc))
            if ttype == 'win':
                c.execute("UPDATE users SET total_wins=total_wins+1 WHERE user_id=?", (user_id,))
            elif ttype == 'loss':
                c.execute("UPDATE users SET total_losses=total_losses+1 WHERE user_id=?", (user_id,))
    
    def get_all_users(self, page=1, per_page=10, search=None):
        with self.conn() as c:
            if search:
                query = "SELECT * FROM users WHERE user_id LIKE ? OR first_name LIKE ? OR username LIKE ? ORDER BY join_date DESC"
                param = f"%{search}%"
                rows = c.execute(query, (param, param, param)).fetchall()
            else:
                rows = c.execute("SELECT * FROM users ORDER BY join_date DESC LIMIT ? OFFSET ?", 
                               (per_page, (page-1)*per_page)).fetchall()
            total = c.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
            return [dict(r) for r in rows], total
    
    def ban_user(self, user_id, reason=''):
        with self.conn() as c:
            c.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?", (reason, user_id))
    
    def unban_user(self, user_id):
        with self.conn() as c:
            c.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE user_id=?", (user_id,))
    
    def set_admin(self, user_id, is_admin=True):
        with self.conn() as c:
            c.execute("UPDATE users SET is_admin=? WHERE user_id=?", (1 if is_admin else 0, user_id))
    
    # ========== بازی‌ها ==========
    
    def lock_user(self, user_id, game_name):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO game_locks VALUES (?,?,CURRENT_TIMESTAMP)", (user_id, game_name))
    
    def unlock_user(self, user_id):
        with self.conn() as c:
            c.execute("DELETE FROM game_locks WHERE user_id=?", (user_id,))
    
    def is_locked(self, user_id):
        with self.conn() as c:
            r = c.execute("SELECT COUNT(*) as c FROM game_locks WHERE user_id=?", (user_id,)).fetchone()
            return r['c'] > 0
    
    def create_room(self, creator_id, bet):
        rid = str(random.randint(100000, 999999))
        with self.conn() as c:
            c.execute("INSERT INTO game_rooms (room_id, creator_id, bet_amount) VALUES (?,?,?)", (rid, creator_id, bet))
        return rid
    
    def join_room(self, rid, p2id):
        with self.conn() as c:
            r = c.execute("SELECT * FROM game_rooms WHERE room_id=? AND status='waiting'", (rid,)).fetchone()
            if not r or r['creator_id'] == p2id:
                return None
            c.execute("UPDATE game_rooms SET player2_id=?, status='playing' WHERE room_id=?", (p2id, rid))
            return dict(r)
    
    def set_room_game(self, rid, gtype):
        with self.conn() as c:
            c.execute("UPDATE game_rooms SET game_type=? WHERE room_id=?", (gtype, rid))
    
    def set_choice(self, rid, pnum, choice):
        col = 'creator_choice' if pnum == 1 else 'player2_choice'
        with self.conn() as c:
            c.execute(f"UPDATE game_rooms SET {col}=? WHERE room_id=?", (choice, rid))
    
    def get_room(self, rid):
        with self.conn() as c:
            r = c.execute("SELECT * FROM game_rooms WHERE room_id=?", (rid,)).fetchone()
            return dict(r) if r else None
    
    def finish_room(self, rid, winner):
        with self.conn() as c:
            c.execute("UPDATE game_rooms SET status='finished', winner_id=? WHERE room_id=?", (winner, rid))
    
    def add_queue(self, uid, gtype, bet):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO match_queue VALUES (?,?,?,CURRENT_TIMESTAMP)", (uid, gtype, bet))
    
    def find_match(self, uid, bet, gtype):
        with self.conn() as c:
            r = c.execute(
                "SELECT user_id FROM match_queue WHERE bet_amount=? AND game_type=? AND user_id!=? ORDER BY joined_at LIMIT 1",
                (bet, gtype, uid)
            ).fetchone()
            if r:
                c.execute("DELETE FROM match_queue WHERE user_id IN (?,?)", (uid, r['user_id']))
                return r['user_id']
            return None
    
    def remove_queue(self, uid):
        with self.conn() as c:
            c.execute("DELETE FROM match_queue WHERE user_id=?", (uid,))
    
    def get_queue_count(self):
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) as c FROM match_queue").fetchone()['c']
    
    # ========== تراکنش‌ها ==========
    
    def get_transactions(self, user_id=None, limit=50):
        with self.conn() as c:
            if user_id:
                rows = c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY timestamp DESC LIMIT ?", 
                               (user_id, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", 
                               (limit,)).fetchall()
            return [dict(r) for r in rows]
    
    def get_transactions_count(self):
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) as c FROM transactions").fetchone()['c']
    
    def get_total_deposits(self):
        with self.conn() as c:
            r = c.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='deposit'").fetchone()
            return r['t']
    
    def get_total_withdraws(self):
        with self.conn() as c:
            r = c.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='withdraw'").fetchone()
            return r['t']
    
    # ========== برداشت ==========
    
    def can_withdraw(self, uid):
        settings = self.get_all_settings()
        min_coins = int(settings.get('min_withdraw_coins', 100))
        min_invites = int(settings.get('min_invites_first_withdraw', 4))
        
        u = self.get_user(uid)
        if not u:
            return False, "❌ کاربر یافت نشد"
        if u['balance'] < min_coins:
            return False, f"❌ حداقل موجودی: {min_coins} سکه\n💰 موجودی شما: {u['balance']:,} سکه"
        if not u['first_withdraw_used']:
            s = self.get_invite_stats(uid)
            if s['active'] < min_invites:
                return False, f"❌ برای اولین برداشت، {min_invites} زیرمجموعه فعال نیاز دارید\n📊 زیرمجموعه‌های فعال: {s['active']}"
        return True, "✅"
    
    def create_withdraw(self, uid, coins, card, holder):
        settings = self.get_all_settings()
        rate = int(settings.get('coin_to_toman', 1000))
        toman = coins * rate
        
        with self.conn() as c:
            c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (coins, uid))
            c.execute(
                "INSERT INTO withdraw_requests (user_id, amount_coins, amount_toman, card_number, card_holder) VALUES (?,?,?,?,?)",
                (uid, coins, toman, card, holder)
            )
            return c.lastrowid
    
    def process_withdraw(self, rid, approved, admin_id=None):
        with self.conn() as c:
            r = c.execute("SELECT * FROM withdraw_requests WHERE id=?", (rid,)).fetchone()
            if not r:
                return None
            if approved:
                c.execute("UPDATE withdraw_requests SET status='approved', processed_by=?, processed_at=CURRENT_TIMESTAMP WHERE id=?", (admin_id, rid))
                c.execute("UPDATE users SET first_withdraw_used=1 WHERE user_id=?", (r['user_id'],))
            else:
                c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r['amount_coins'], r['user_id']))
                c.execute("UPDATE withdraw_requests SET status='rejected', processed_by=?, processed_at=CURRENT_TIMESTAMP WHERE id=?", (admin_id, rid))
            return dict(r)
    
    def get_pending_withdrawals(self):
        with self.conn() as c:
            rows = c.execute(
                "SELECT wr.*, u.first_name, u.last_name, u.username FROM withdraw_requests wr JOIN users u ON wr.user_id=u.user_id WHERE wr.status='pending' ORDER BY wr.timestamp DESC"
            ).fetchall()
            return [dict(r) for r in rows]
    
    def get_all_withdrawals(self, limit=50):
        with self.conn() as c:
            rows = c.execute(
                "SELECT wr.*, u.first_name, u.last_name FROM withdraw_requests wr JOIN users u ON wr.user_id=u.user_id ORDER BY wr.timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    
    # ========== آمار ==========
    
    def get_invite_stats(self, uid):
        with self.conn() as c:
            total = c.execute("SELECT COUNT(*) as c FROM users WHERE invited_by=?", (uid,)).fetchone()['c']
            active = c.execute("SELECT COUNT(*) as c FROM users WHERE invited_by=? AND total_games>=1", (uid,)).fetchone()['c']
            d = c.execute("SELECT diamonds FROM users WHERE user_id=?", (uid,)).fetchone()
            return {'total': total, 'active': active, 'diamonds': d['diamonds'] if d else 0}
    
    def get_stats(self):
        with self.conn() as c:
            users = c.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
            banned = c.execute("SELECT COUNT(*) as c FROM users WHERE is_banned=1").fetchone()['c']
            total_balance = c.execute("SELECT COALESCE(SUM(balance),0) as t FROM users").fetchone()['t']
            total_games = c.execute("SELECT COALESCE(SUM(total_games),0) as t FROM users").fetchone()['t']
            today = datetime.now().strftime('%Y-%m-%d')
            today_users = c.execute("SELECT COUNT(*) as c FROM users WHERE date(join_date)=?", (today,)).fetchone()['c']
            active_today = c.execute("SELECT COUNT(*) as c FROM users WHERE date(last_activity)=?", (today,)).fetchone()['c']
            
            return {
                'total_users': users,
                'banned_users': banned,
                'total_balance': total_balance,
                'total_games': total_games,
                'today_users': today_users,
                'active_today': active_today
            }
    
    def get_top_users(self, limit=10):
        with self.conn() as c:
            rows = c.execute("SELECT user_id, first_name, username, balance, total_games FROM users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
    
    # ========== ماموریت ==========
    
    def update_mission(self, uid):
        today = datetime.now().strftime('%Y-%m-%d')
        settings = self.get_all_settings()
        target = int(settings.get('daily_mission_games', 3))
        
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO daily_missions VALUES (?,?,0,0,0)", (uid, today))
            c.execute("UPDATE daily_missions SET games_played=games_played+1 WHERE user_id=? AND date=?", (uid, today))
            p = c.execute("SELECT games_played FROM daily_missions WHERE user_id=? AND date=?", (uid, today)).fetchone()['games_played']
            if p >= target:
                c.execute("UPDATE daily_missions SET completed=1 WHERE user_id=? AND date=?", (uid, today))
    
    def get_mission(self, uid):
        today = datetime.now().strftime('%Y-%m-%d')
        settings = self.get_all_settings()
        target = int(settings.get('daily_mission_games', 3))
        reward = int(settings.get('daily_mission_reward', 50))
        
        with self.conn() as c:
            r = c.execute("SELECT * FROM daily_missions WHERE user_id=? AND date=?", (uid, today)).fetchone()
            if r:
                return {'played': r['games_played'], 'completed': bool(r['completed']), 'claimed': bool(r['claimed']), 'target': target, 'reward': reward}
            return {'played': 0, 'completed': False, 'claimed': False, 'target': target, 'reward': reward}
    
    def claim_mission(self, uid):
        today = datetime.now().strftime('%Y-%m-%d')
        settings = self.get_all_settings()
        reward = int(settings.get('daily_mission_reward', 50))
        
        m = self.get_mission(uid)
        if m['completed'] and not m['claimed']:
            self.add_balance(uid, reward, 'mission', '🎁 جایزه ماموریت روزانه')
            with self.conn() as c:
                c.execute("UPDATE daily_missions SET claimed=1 WHERE user_id=? AND date=?", (uid, today))
            return True
        return False

# ==============================================
# 🤖 ربات
# ==============================================

db = Database()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# ==============================================
# 📌 State‌ها
# ==============================================

class States(StatesGroup):
    # کاربر
    wait_card_amount = State()
    wait_receipt = State()
    wait_wd_amount = State()
    wait_wd_card = State()
    wait_wd_name = State()
    wait_room_code = State()
    
    # ادمین
    admin_pass = State()
    admin_bc = State()
    admin_search = State()
    admin_edit_balance = State()
    admin_edit_setting = State()
    admin_add_admin = State()
    admin_ban_reason = State()

# ==============================================
# 🎨 کیبوردها
# ==============================================

def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎮 بازی‌ها"), KeyboardButton(text="💰 خرید سکه"))
    builder.row(KeyboardButton(text="👤 پروفایل"), KeyboardButton(text="👥 زیرمجموعه‌گیری"))
    builder.row(KeyboardButton(text="🎯 ماموریت روزانه"), KeyboardButton(text="💎 برداشت"))
    builder.row(KeyboardButton(text="📞 پشتیبانی"), KeyboardButton(text="❓ راهنما"))
    return builder.as_markup(resize_keyboard=True)

def admin_panel():
    """پنل مدیریت پیشرفته"""
    builder = InlineKeyboardBuilder()
    
    # ردیف ۱ - آمار
    builder.row(
        InlineKeyboardButton(text="📊 آمار کلی", callback_data="adm_stats"),
        InlineKeyboardButton(text="📋 آمار دقیق", callback_data="adm_detailed_stats")
    )
    
    # ردیف ۲ - کاربران
    builder.row(
        InlineKeyboardButton(text="👥 لیست کاربران", callback_data="adm_users_list"),
        InlineKeyboardButton(text="🔍 جستجوی کاربر", callback_data="adm_search_user")
    )
    
    # ردیف ۳ - مدیریت کاربر
    builder.row(
        InlineKeyboardButton(text="💰 تغییر موجودی", callback_data="adm_edit_balance_menu"),
        InlineKeyboardButton(text="🚫 بن/آزاد سازی", callback_data="adm_ban_menu")
    )
    
    # ردیف ۴ - ادمین‌ها
    builder.row(
        InlineKeyboardButton(text="👑 مدیریت ادمین‌ها", callback_data="adm_manage_admins"),
    )
    
    # ردیف ۵ - تراکنش‌ها
    builder.row(
        InlineKeyboardButton(text="💳 تراکنش‌ها", callback_data="adm_transactions"),
        InlineKeyboardButton(text="💎 برداشت‌ها", callback_data="adm_withdrawals")
    )
    
    # ردیف ۶ - تنظیمات
    builder.row(
        InlineKeyboardButton(text="⚙️ تنظیمات ربات", callback_data="adm_settings"),
        InlineKeyboardButton(text="🎮 تنظیمات بازی", callback_data="adm_game_settings")
    )
    
    # ردیف ۷ - تنظیمات مالی
    builder.row(
        InlineKeyboardButton(text="💳 تنظیمات کارت", callback_data="adm_card_settings"),
        InlineKeyboardButton(text="📢 تنظیمات کانال", callback_data="adm_channel_settings")
    )
    
    # ردیف ۸ - عملیات
    builder.row(
        InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="adm_broadcast"),
        InlineKeyboardButton(text="🔒 رفع قفل کاربران", callback_data="adm_unlock_all")
    )
    
    # ردیف ۹ - خروج
    builder.row(
        InlineKeyboardButton(text="🚪 خروج از پنل", callback_data="adm_exit")
    )
    
    return builder.as_markup()

# ==============================================
# 🚀 هندلر شروع
# ==============================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # بررسی بن
    user = db.get_user(user_id)
    if user and user['is_banned']:
        reason = user.get('ban_reason', 'تخلف از قوانین')
        return await message.answer(f"🚫 **حساب شما مسدود شده است**\n\n❌ دلیل: {reason}\n📞 پشتیبانی: {db.get_setting('support_username', '@ad_tas')}", parse_mode=ParseMode.MARKDOWN)
    
    # بررسی جوین
    channel_id = db.get_setting('required_channel_id', '@gozaresh_taj')
    channel_link = db.get_setting('required_channel_link', 'https://t.me/gozaresh_taj')
    
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        if member.status in ['left', 'kicked']:
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="📢 عضویت در کانال", url=channel_link))
            builder.row(InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join"))
            
            await message.answer(
                f"⛔ **برای استفاده از ربات، ابتدا باید عضو کانال ما شوید!**\n\n"
                f"📢 **کانال رسمی**\n🔗 {channel_link}\n\n"
                f"پس از عضویت، روی دکمه زیر کلیک کنید 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=builder.as_markup(),
                disable_web_page_preview=True
            )
            return
    except Exception as e:
        logger.error(f"Channel check error: {e}")
    
    await continue_start(message)

async def continue_start(message: Message):
    user_id = message.from_user.id
    
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
    
    welcome = f"""
╔══════════════════════╗
║   🎰 کازینو آنلاین   ║
╚══════════════════════╝

👤 **{message.from_user.first_name}** عزیز، خوش آمدید!

💰 **موجودی:** {db.get_balance(user_id):,} سکه

👥 **لینک دعوت شما:**
`https://t.me/{bot_username}?start={user_id}`

📞 **پشتیبانی:** {db.get_setting('support_username', '@ad_tas')}

🎮 از منوی زیر استفاده کنید 👇
    """
    
    await message.answer(welcome, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())

@router.callback_query(F.data == "check_join")
async def check_join(callback: CallbackQuery):
    channel_id = db.get_setting('required_channel_id', '@gozaresh_taj')
    try:
        member = await bot.get_chat_member(channel_id, callback.from_user.id)
        if member.status not in ['left', 'kicked']:
            await callback.message.delete()
            await continue_start(callback.message)
        else:
            await callback.answer("❌ هنوز عضو نشده‌اید!", show_alert=True)
    except:
        await callback.answer("❌ خطا! لطفاً دوباره تلاش کنید.", show_alert=True)

# ==============================================
# 📋 منوهای کاربر
# ==============================================

@router.message(F.text == "🎮 بازی‌ها")
async def menu_games(message: Message):
    if db.is_locked(message.from_user.id):
        return await message.answer("⚠️ شما در حال انجام یک بازی هستید!")
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👥 بازی با دوست (ساخت اتاق)", callback_data="mode_friend"))
    builder.row(InlineKeyboardButton(text="🤖 بازی با ربات", callback_data="mode_bot"))
    builder.row(InlineKeyboardButton(text="🎯 حریف تصادفی", callback_data="mode_random"))
    builder.row(InlineKeyboardButton(text="🔑 ورود با کد اتاق", callback_data="join_room"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    
    await message.answer("🎮 **منوی بازی‌ها**\n\n👇 یک گزینه را انتخاب کنید:", parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "👤 پروفایل")
async def menu_profile(message: Message):
    u = db.get_user(message.from_user.id)
    if not u: return await message.answer("❌ /start را بزنید")
    
    stats = db.get_invite_stats(message.from_user.id)
    
    text = f"""
╔══════════════════════╗
║     👤 پروفایل شما    ║
╚══════════════════════╝

🆔 **شناسه:** `{u['user_id']}`
👤 **نام:** {u['first_name'] or 'نامشخص'}
📅 **عضویت:** {u['join_date'][:10] if u['join_date'] else '---'}

💰 **موجودی:** {u['balance']:,} سکه
💎 **الماس:** {u['diamonds']:,}
🎮 **بازی‌ها:** {u['total_games']:,}
🏆 **برد:** {u['total_wins']:,} | 😢 **باخت:** {u['total_losses']:,}

👥 **زیرمجموعه‌ها:**
• کل: {stats['total']} | فعال: {stats['active']}
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "👥 زیرمجموعه‌گیری")
async def menu_referral(message: Message):
    uid = message.from_user.id
    stats = db.get_invite_stats(uid)
    bot_username = (await bot.get_me()).username
    
    text = f"""
╔══════════════════════╗
║  👥 زیرمجموعه‌گیری    ║
╚══════════════════════╝

💎 با دعوت دوستان، الماس دریافت کنید!

✏️ **لینک دعوت:**
`https://t.me/{bot_username}?start={uid}`

📊 **آمار:**
• کل: {stats['total']} | فعال: {stats['active']}
• 💎 الماس: {stats['diamonds']}
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "🎯 ماموریت روزانه")
async def menu_mission(message: Message):
    m = db.get_mission(message.from_user.id)
    bar = "🟢" * m['played'] + "⚪" * (m['target'] - m['played'])
    
    builder = InlineKeyboardBuilder()
    if m['completed'] and not m['claimed']:
        builder.row(InlineKeyboardButton(text="🎁 دریافت جایزه", callback_data="claim_mission"))
    
    text = f"""
🎯 **ماموریت روزانه**

📋 {m['target']} بازی انجام دهید
🎁 جایزه: {m['reward']:,} سکه

📊 [{bar}] {m['played']}/{m['target']}

{'✅ کامل شد! 👇' if m['completed'] and not m['claimed'] else '🎉 دریافت شد' if m['claimed'] else '🔴 ادامه دهید...'}
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup() if builder else None)

@router.message(F.text == "💰 خرید سکه")
async def menu_buy(message: Message):
    card = db.get_setting('card_number', '6062561009737464')
    holder = db.get_setting('card_holder', 'مجاور')
    rate = int(db.get_setting('coin_to_toman', 1000))
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 مبلغ دلخواه", callback_data="buy_custom"))
    
    for p in [50, 100, 200, 500, 1000]:
        builder.row(InlineKeyboardButton(text=f"📦 {p:,} سکه = {p*rate:,} تومان", callback_data=f"buypkg_{p}"))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    
    text = f"""
💰 **خرید سکه**

💵 نرخ: هر سکه = {rate:,} تومان
💳 شماره کارت: `{card}`
👤 صاحب حساب: {holder}

📝 مبلغ را واریز و عکس رسید را ارسال کنید
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "💎 برداشت")
async def menu_withdraw(message: Message):
    uid = message.from_user.id
    can, reason = db.can_withdraw(uid)
    
    if not can:
        return await message.answer(f"❌ {reason}")
    
    rate = int(db.get_setting('coin_to_toman', 1000))
    balance = db.get_balance(uid)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💎 درخواست برداشت", callback_data="req_withdraw"))
    
    text = f"""
💎 **برداشت سکه**

💰 موجودی: {balance:,} سکه
💵 معادل: {balance*rate:,} تومان

⚠️ حداقل: {db.get_setting('min_withdraw_coins', 100)} سکه
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "📞 پشتیبانی")
async def menu_support(message: Message):
    support = db.get_setting('support_username', '@ad_tas')
    await message.answer(f"📞 **پشتیبانی:** {support}\n\n💡 برای سوالات و مشکلات در ارتباط باشید.", parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "❓ راهنما")
async def menu_help(message: Message):
    text = f"""
❓ **راهنما**

🎮 **بازی با دوست:**
۱. ساخت اتاق → دریافت کد
۲. ارسال کد به دوست
۳. دوست با کد وارد می‌شود

🤖 **بازی با ربات:**
• تاس (شانس {db.get_setting('dice_win_chance', 16)}٪)
• قرعه‌کشی (شانس {db.get_setting('lottery_win_chance', 2)}٪)

🎯 **حریف تصادفی:**
• منتظر بازیکن آنلاین

💰 **برداشت:**
• اولین برداشت: {db.get_setting('min_invites_first_withdraw', 4)} زیرمجموعه

📞 پشتیبانی: {db.get_setting('support_username', '@ad_tas')}
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

# ==============================================
# 🎮 بازی‌ها
# ==============================================

@router.callback_query(F.data.startswith("mode_"))
async def select_mode(callback: CallbackQuery):
    mode = callback.data.split("_")[1]
    mode_names = {"friend": "👥 بازی با دوست", "bot": "🤖 بازی با ربات", "random": "🎯 حریف تصادفی"}
    
    builder = InlineKeyboardBuilder()
    
    if mode == "bot":
        games = [("🎲 تاس", f"game_dice_{mode}"), ("🎪 قرعه‌کشی", f"game_lottery_{mode}")]
    else:
        games = [
            ("✊ سنگ کاغذ قیچی", f"game_rps_{mode}"),
            ("🎲 تاس", f"game_dice_{mode}"),
            ("⚽ فوتبال", f"game_football_{mode}"),
            ("🏀 بسکتبال", f"game_basketball_{mode}"),
            ("🎯 دارت", f"game_darts_{mode}"),
            ("🎳 بولینگ", f"game_bowling_{mode}")
        ]
    
    for name, cb in games:
        builder.row(InlineKeyboardButton(text=name, callback_data=cb))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games"))
    
    await callback.message.edit_text(
        f"{mode_names.get(mode, mode)}\n\n🎮 **نوع بازی را انتخاب کنید:**",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("game_"))
async def select_game(callback: CallbackQuery):
    parts = callback.data.split("_")
    game_type = parts[1]
    mode = parts[2]
    game_key = f"{game_type}_{mode}"
    
    game_names = {
        'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
        'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ',
        'lottery': '🎪 قرعه‌کشی'
    }
    
    prices = db.get_setting('game_prices', [50, 100, 200, 500, 1000])
    
    builder = InlineKeyboardBuilder()
    for price in prices:
        builder.row(InlineKeyboardButton(text=f"💎 {price:,} سکه", callback_data=f"bet_{game_key}_{price}"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games"))
    
    await callback.message.edit_text(
        f"🎮 **{game_names.get(game_type, game_type)}**\n\n💰 **مبلغ شرط را انتخاب کنید:**",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("bet_"))
async def start_game(callback: CallbackQuery):
    parts = callback.data.split("_")
    game_type = parts[1]
    mode = parts[2]
    bet = int(parts[3])
    user_id = callback.from_user.id
    
    if db.is_locked(user_id):
        return await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
    
    if db.get_balance(user_id) < bet:
        return await callback.answer(f"❌ موجودی کافی نیست!", show_alert=True)
    
    db.add_balance(user_id, -bet, 'bet', f'شرط {game_type}')
    db.lock_user(user_id, f'game_{game_type}')
    
    if mode == "bot":
        await play_vs_bot(callback, game_type, bet)
    elif mode == "friend":
        await create_game_room(callback, game_type, bet)
    elif mode == "random":
        await find_random_opponent(callback, game_type, bet)

async def play_vs_bot(callback: CallbackQuery, game_type: str, bet: int):
    user_id = callback.from_user.id
    
    if game_type == "dice":
        chance = int(db.get_setting('dice_win_chance', 16)) / 100
        won = random.random() < chance
        prize = bet * 4 if won else 0
        emoji = "🎲"
    else:
        chance = int(db.get_setting('lottery_win_chance', 2)) / 100
        won = random.random() < chance
        prize = bet * 10 if won else 0
        emoji = "🎪"
    
    if prize > 0:
        db.add_balance(user_id, prize, 'win', f'برد {game_type}')
    else:
        db.add_balance(user_id, 0, 'loss', f'باخت {game_type}')
    
    db.unlock_user(user_id)
    db.update_mission(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 بازی مجدد", callback_data=f"bet_{game_type}_bot_{bet}"))
    builder.row(InlineKeyboardButton(text="🔙 منوی بازی‌ها", callback_data="back_games"))
    
    text = f"""
{emoji} **نتیجه بازی**

{'🎉 **برنده شدید!**' if won else '😢 **باختید!**'}

💰 شرط: {bet:,} سکه
🎁 جایزه: {prize:,} سکه
💳 موجودی: {db.get_balance(user_id):,} سکه
    """
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

async def create_game_room(callback: CallbackQuery, game_type: str, bet: int):
    user_id = callback.from_user.id
    room_id = db.create_room(user_id, bet)
    db.set_room_game(room_id, game_type)
    
    game_names = {
        'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
        'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ'
    }
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ لغو اتاق", callback_data=f"cancel_room_{room_id}"))
    
    text = f"""
🎮 **اتاق بازی ساخته شد!**

🎯 بازی: {game_names.get(game_type, game_type)}
💰 مبلغ: {bet:,} سکه
🔑 کد: `{room_id}`

📋 دوستت با /start وارد شود و گزینه "🔑 ورود با کد" را بزند
    """
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "join_room")
async def join_room_start(callback: CallbackQuery, state: FSMContext):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ در حال بازی هستید!", show_alert=True)
    
    await state.set_state(States.wait_room_code)
    await callback.message.edit_text("🔑 **کد ۶ رقمی اتاق را وارد کنید:**", parse_mode=ParseMode.MARKDOWN)

@router.message(States.wait_room_code)
async def process_room_code(message: Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    
    if not code.isdigit() or len(code) != 6:
        return await message.answer("❌ کد باید ۶ رقم باشد!")
    
    room = db.join_room(code, user_id)
    if not room:
        return await message.answer("❌ اتاق یافت نشد یا پر است!")
    
    await state.clear()
    
    bet = room['bet_amount']
    creator_id = room['creator_id']
    
    if db.get_balance(user_id) < bet:
        db.add_balance(creator_id, bet, 'refund', 'حریف موجودی کافی نداشت')
        db.unlock_user(creator_id)
        db.finish_room(code, None)
        return await message.answer("❌ موجودی شما کافی نیست!")
    
    db.add_balance(user_id, -bet, 'bet', f'ورود به اتاق {code}')
    db.lock_user(user_id, f'room_{code}')
    
    await start_pvp_game(message, room, user_id)

async def start_pvp_game(message: Message, room: dict, player2_id: int):
    game_type = room['game_type']
    bet = room['bet_amount']
    room_id = room['room_id']
    creator_id = room['creator_id']
    
    game_names = {
        'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
        'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ'
    }
    
    if game_type in ['football', 'basketball', 'darts', 'bowling']:
        winner_id = random.choice([creator_id, player2_id])
        prize = bet * 2
        db.add_balance(winner_id, prize, 'win', f'برد {game_type}')
        loser_id = player2_id if winner_id == creator_id else creator_id
        db.add_balance(loser_id, 0, 'loss', f'باخت {game_type}')
        db.unlock_user(creator_id)
        db.unlock_user(player2_id)
        db.finish_room(room_id, winner_id)
        db.update_mission(creator_id)
        db.update_mission(player2_id)
        
        result = f"🏆 **نتیجه بازی**\n🎮 {game_names.get(game_type)}\n🎉 برنده: `{winner_id}`\n💰 جایزه: {prize:,} سکه"
        
        for uid in [creator_id, player2_id]:
            try:
                await bot.send_message(uid, result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
            except:
                pass
        
        if message:
            await message.answer("✅ وارد اتاق شدید!", reply_markup=main_menu())
        return
    
    if game_type == 'rps':
        choices = [("✊ سنگ", f"pvp_rock_{room_id}"), ("📄 کاغذ", f"pvp_paper_{room_id}"), ("✂️ قیچی", f"pvp_scissors_{room_id}")]
    elif game_type == 'dice':
        choices = [(f"🎲 {i}", f"pvp_{i}_{room_id}") for i in range(1, 7)]
    else:
        choices = []
    
    builder = InlineKeyboardBuilder()
    for text, cb in choices:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    msg = f"🎮 **{game_names.get(game_type)}**\n💰 مبلغ: {bet:,} سکه\n\nانتخاب کنید:"
    
    for uid in [creator_id, player2_id]:
        try:
            await bot.send_message(uid, msg, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
        except:
            pass

@router.callback_query(F.data.startswith("pvp_"))
async def process_pvp_choice(callback: CallbackQuery):
    parts = callback.data.split("_")
    choice = parts[1]
    room_id = parts[2]
    user_id = callback.from_user.id
    
    room = db.get_room(room_id)
    if not room or room['status'] != 'playing':
        return await callback.answer("❌ بازی در دسترس نیست!", show_alert=True)
    
    if user_id == room['creator_id']:
        player_num = 1
    elif user_id == room['player2_id']:
        player_num = 2
    else:
        return await callback.answer("❌ شما در این بازی نیستید!", show_alert=True)
    
    db.set_choice(room_id, player_num, choice)
    await callback.answer("✅ انتخاب ثبت شد. منتظر بازیکن دیگر...")
    
    room = db.get_room(room_id)
    if room['creator_choice'] and room['player2_choice']:
        await determine_pvp_winner(room)
    else:
        await callback.message.edit_text(f"✅ انتخاب شما: {choice}\n⏰ منتظر بازیکن دیگر...", parse_mode=ParseMode.MARKDOWN)

async def determine_pvp_winner(room: dict):
    game_type = room['game_type']
    p1 = room['creator_choice']
    p2 = room['player2_choice']
    bet = room['bet_amount']
    cid = room['creator_id']
    pid = room['player2_id']
    rid = room['room_id']
    
    if game_type == 'rps':
        wins = {'rock': 'scissors', 'paper': 'rock', 'scissors': 'paper'}
        if p1 == p2: winner = 0
        elif wins.get(p1) == p2: winner = 1
        else: winner = 2
    elif game_type == 'dice':
        if int(p1) > int(p2): winner = 1
        elif int(p2) > int(p1): winner = 2
        else: winner = 0
    else:
        winner = 0
    
    if winner == 0:
        db.add_balance(cid, bet, 'refund', 'مساوی')
        db.add_balance(pid, bet, 'refund', 'مساوی')
        result = f"🤝 **مساوی!**\n👤 ۱: {p1}\n👤 ۲: {p2}\n💰 سکه‌ها برگشت خورد."
    else:
        winner_id = cid if winner == 1 else pid
        prize = bet * 2
        db.add_balance(winner_id, prize, 'win', 'برد')
        loser_id = pid if winner == 1 else cid
        db.add_balance(loser_id, 0, 'loss', 'باخت')
        result = f"🏆 **نتیجه**\n👤 ۱: {p1}\n👤 ۲: {p2}\n🎉 برنده: `{winner_id}`\n💰 {prize:,} سکه"
    
    db.unlock_user(cid)
    db.unlock_user(pid)
    db.finish_room(rid, cid if winner == 1 else (pid if winner == 2 else None))
    db.update_mission(cid)
    db.update_mission(pid)
    
    for uid in [cid, pid]:
        try:
            await bot.send_message(uid, result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
        except:
            pass

async def find_random_opponent(callback: CallbackQuery, game_type: str, bet: int):
    user_id = callback.from_user.id
    opponent = db.find_match(user_id, bet, game_type)
    
    if opponent:
        room_id = db.create_room(opponent, bet)
        db.set_room_game(room_id, game_type)
        db.join_room(room_id, user_id)
        db.add_balance(opponent, -bet, 'bet', 'بازی تصادفی')
        db.lock_user(opponent, f'room_{room_id}')
        db.lock_user(user_id, f'room_{room_id}')
        
        room = db.get_room(room_id)
        await callback.message.edit_text("🎯 **حریف پیدا شد!**\n⏳ شروع بازی...", parse_mode=ParseMode.MARKDOWN)
        await start_pvp_game(None, room, user_id)
    else:
        db.add_queue(user_id, game_type, bet)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="❌ لغو جستجو", callback_data="cancel_search"))
        
        game_names = {'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
                      'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ'}
        
        await callback.message.edit_text(
            f"🔍 **در جستجوی حریف...**\n🎮 {game_names.get(game_type)}\n💰 {bet:,} سکه",
            parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
        )

@router.callback_query(F.data.startswith("cancel_room_"))
async def cancel_room(callback: CallbackQuery):
    room_id = callback.data.split("_")[2]
    room = db.get_room(room_id)
    user_id = callback.from_user.id
    
    if not room: return await callback.answer("❌ اتاق یافت نشد!", show_alert=True)
    if room['creator_id'] != user_id: return await callback.answer("❌ فقط سازنده می‌تواند لغو کند!", show_alert=True)
    if room['player2_id']: return await callback.answer("❌ بازیکن دوم وارد شده!", show_alert=True)
    
    db.add_balance(user_id, room['bet_amount'], 'refund', f'لغو اتاق')
    db.unlock_user(user_id)
    db.finish_room(room_id, None)
    
    await callback.message.edit_text(
        f"❌ **اتاق لغو شد**\n💰 {room['bet_amount']:,} سکه برگشت خورد.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games")).as_markup()
    )

@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery):
    user_id = callback.from_user.id
    refund = db.get_last_bet(user_id)
    db.remove_queue(user_id)
    if refund > 0:
        db.add_balance(user_id, refund, 'refund', 'لغو جستجو')
    db.unlock_user(user_id)
    
    await callback.message.edit_text(
        f"❌ **جستجو لغو شد**\n💰 سکه برگشت خورد.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games")).as_markup()
    )

# ==============================================
# 💰 خرید و برداشت
# ==============================================

@router.callback_query(F.data == "buy_custom")
async def buy_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.wait_card_amount)
    await callback.message.answer("💰 چند سکه می‌خواهید؟\n📝 تعداد را وارد کنید:")

@router.message(States.wait_card_amount)
async def process_custom(message: Message, state: FSMContext):
    try:
        coins = int(message.text)
        if coins <= 0: raise ValueError
    except:
        return await message.answer("❌ عدد معتبر وارد کنید!")
    
    await state.update_data(buy_coins=coins)
    await state.set_state(States.wait_receipt)
    
    rate = int(db.get_setting('coin_to_toman', 1000))
    card = db.get_setting('card_number', '6062561009737464')
    holder = db.get_setting('card_holder', 'مجاور')
    
    await message.answer(
        f"💳 **پرداخت**\n\n📦 {coins:,} سکه\n💵 {coins*rate:,} تومان\n\n"
        f"📌 شماره کارت:\n`{card}`\n👤 {holder}\n\n📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("buypkg_"))
async def buy_package(callback: CallbackQuery, state: FSMContext):
    coins = int(callback.data.split("_")[1])
    await state.update_data(buy_coins=coins)
    await state.set_state(States.wait_receipt)
    
    rate = int(db.get_setting('coin_to_toman', 1000))
    card = db.get_setting('card_number', '6062561009737464')
    
    await callback.message.answer(
        f"💳 **پرداخت**\n\n📦 {coins:,} سکه\n💵 {coins*rate:,} تومان\n\n"
        f"📌 شماره کارت:\n`{card}`\n\n📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(States.wait_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    coins = data['buy_coins']
    rate = int(db.get_setting('coin_to_toman', 1000))
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appbuy_{message.from_user.id}_{coins}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejbuy_{message.from_user.id}")
    )
    
    await bot.send_message(ADMIN_USER_ID,
        f"🔔 خرید جدید\n👤 {message.from_user.full_name}\n🆔 `{message.from_user.id}`\n💰 {coins:,} سکه\n💵 {coins*rate:,} تومان",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )
    await bot.forward_message(ADMIN_USER_ID, message.chat.id, message.message_id)
    
    await message.answer("✅ رسید ارسال شد. منتظر تایید باشید.")
    await state.clear()

@router.callback_query(F.data.startswith("appbuy_"))
async def approve_buy(callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id, coins = int(parts[1]), int(parts[2])
    db.add_balance(user_id, coins, 'deposit', f'خرید {coins} سکه')
    await callback.message.edit_text(f"✅ {coins:,} سکه به کاربر `{user_id}` اضافه شد.", parse_mode=ParseMode.MARKDOWN)
    try:
        await bot.send_message(user_id, f"✅ خرید تایید شد!\n💰 {coins:,} سکه اضافه شد.\n💳 موجودی: {db.get_balance(user_id):,} سکه", parse_mode=ParseMode.MARKDOWN)
    except:
        pass

@router.callback_query(F.data.startswith("rejbuy_"))
async def reject_buy(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.message.edit_text(f"❌ خرید کاربر `{user_id}` رد شد.", parse_mode=ParseMode.MARKDOWN)
    try:
        await bot.send_message(user_id, "❌ خرید تایید نشد.")
    except:
        pass

@router.callback_query(F.data == "req_withdraw")
async def req_withdraw(callback: CallbackQuery, state: FSMContext):
    can, reason = db.can_withdraw(callback.from_user.id)
    if not can:
        return await callback.answer(reason, show_alert=True)
    
    await state.set_state(States.wait_wd_amount)
    min_wd = int(db.get_setting('min_withdraw_coins', 100))
    await callback.message.answer(f"💰 چند سکه برداشت می‌کنید؟\n⚠️ حداقل: {min_wd}")

@router.message(States.wait_wd_amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        coins = int(message.text)
        min_wd = int(db.get_setting('min_withdraw_coins', 100))
        if coins < min_wd or coins > db.get_balance(message.from_user.id):
            return await message.answer(f"❌ مقدار نامعتبر! حداقل {min_wd}")
    except:
        return await message.answer("❌ عدد وارد کنید!")
    
    await state.update_data(wd_coins=coins)
    await state.set_state(States.wait_wd_card)
    await message.answer("💳 شماره کارت ۱۶ رقمی:")

@router.message(States.wait_wd_card)
async def wd_card(message: Message, state: FSMContext):
    card = message.text.replace(" ", "").replace("-", "")
    if not card.isdigit() or len(card) != 16:
        return await message.answer("❌ شماره کارت باید ۱۶ رقم باشد!")
    
    await state.update_data(wd_card=card)
    await state.set_state(States.wait_wd_name)
    await message.answer("👤 نام صاحب کارت:")

@router.message(States.wait_wd_name)
async def wd_name(message: Message, state: FSMContext):
    data = await state.get_data()
    coins = data['wd_coins']
    card = data['wd_card']
    holder = message.text.strip()
    rate = int(db.get_setting('coin_to_toman', 1000))
    toman = coins * rate
    
    req_id = db.create_withdraw(message.from_user.id, coins, card, holder)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appwd_{req_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejwd_{req_id}")
    )
    
    await bot.send_message(ADMIN_USER_ID,
        f"💎 برداشت #{req_id}\n👤 {message.from_user.full_name}\n💰 {coins:,} سکه = {toman:,} تومان\n💳 `{card}`\n👤 {holder}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )
    
    log_channel = db.get_setting('withdraw_log_channel', '@gozaresh_taj')
    try:
        await bot.send_message(log_channel, f"⏳ برداشت #{req_id}\n💰 {coins:,} سکه\n💵 {toman:,} تومان", parse_mode=ParseMode.MARKDOWN)
    except:
        pass
    
    await message.answer(f"✅ درخواست ثبت شد.\n💰 {coins:,} سکه = {toman:,} تومان\n⏰ منتظر تایید باشید.", reply_markup=main_menu())
    await state.clear()

@router.callback_query(F.data.startswith("appwd_"))
async def approve_wd(callback: CallbackQuery):
    req_id = int(callback.data.split("_")[1])
    req = db.process_withdraw(req_id, True, callback.from_user.id)
    if req:
        try:
            await bot.send_message(req['user_id'], f"✅ برداشت {req['amount_toman']:,} تومان تایید شد.")
        except:
            pass
    await callback.message.delete()

@router.callback_query(F.data.startswith("rejwd_"))
async def reject_wd(callback: CallbackQuery):
    req_id = int(callback.data.split("_")[1])
    req = db.process_withdraw(req_id, False, callback.from_user.id)
    if req:
        try:
            await bot.send_message(req['user_id'], "❌ برداشت تایید نشد. سکه‌ها برگشت خورد.")
        except:
            pass
    await callback.message.delete()

@router.callback_query(F.data == "claim_mission")
async def claim_mission(callback: CallbackQuery):
    if db.claim_mission(callback.from_user.id):
        await callback.answer("🎉 جایزه دریافت شد!", show_alert=True)
    else:
        await callback.answer("❌ نمی‌توانید دریافت کنید!", show_alert=True)

# ==============================================
# 👑 پنل مدیریت پیشرفته
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    u = db.get_user(message.from_user.id)
    if not u or not u.get('is_admin'):
        return await message.answer("⛔ دسترسی غیرمجاز!")
    
    await state.set_state(States.admin_pass)
    await message.answer("🔐 رمز عبور مدیریت:")

@router.message(States.admin_pass)
async def admin_check(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        await state.clear()
        await message.answer("🔰 **پنل مدیریت پیشرفته**\n\nیک گزینه را انتخاب کنید:", parse_mode=ParseMode.MARKDOWN, reply_markup=admin_panel())
    else:
        await message.answer("❌ رمز اشتباه!")
        await state.clear()

# ==== آمار ====

@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    stats = db.get_stats()
    text = f"""
📊 **آمار کلی ربات**

👥 کل کاربران: {stats['total_users']:,}
🚫 کاربران مسدود: {stats['banned_users']:,}
👤 کاربران امروز: {stats['today_users']:,}
🟢 فعال امروز: {stats['active_today']:,}

💰 مجموع موجودی: {stats['total_balance']:,} سکه
🎮 کل بازی‌ها: {stats['total_games']:,}

⏳ صف انتظار: {db.get_queue_count()} نفر
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="adm_stats"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "adm_detailed_stats")
async def adm_detailed_stats(callback: CallbackQuery):
    stats = db.get_stats()
    top = db.get_top_users(5)
    
    text = f"""
📋 **آمار دقیق**

📊 **کاربران:**
• کل: {stats['total_users']:,}
• امروز: {stats['today_users']:,}
• فعال: {stats['active_today']:,}
• مسدود: {stats['banned_users']:,}

💰 **مالی:**
• موجودی کل: {stats['total_balance']:,} سکه
• بازی‌ها: {stats['total_games']:,}

🏆 **برترین کاربران:**
"""
    for i, u in enumerate(top, 1):
        text += f"{i}. `{u['user_id']}` - {u['first_name'] or '---'} - 💰 {u['balance']:,}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

# ==== کاربران ====

@router.callback_query(F.data == "adm_users_list")
async def adm_users_list(callback: CallbackQuery):
    users, total = db.get_all_users(page=1, per_page=5)
    
    text = f"👥 **لیست کاربران** (کل: {total})\n\n"
    for u in users:
        ban = "🚫" if u['is_banned'] else "✅"
        admin = "👑" if u['is_admin'] else "👤"
        text += f"{admin}{ban} `{u['user_id']}` - {u['first_name'] or '---'} - 💰 {u['balance']:,}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 جستجو", callback_data="adm_search_user"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "adm_search_user")
async def adm_search_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_search)
    await callback.message.edit_text("🔍 **شناسه یا نام کاربر را وارد کنید:**", parse_mode=ParseMode.MARKDOWN)

@router.message(States.admin_search)
async def adm_search_result(message: Message, state: FSMContext):
    search = message.text.strip()
    users, _ = db.get_all_users(search=search)
    
    if not users:
        await message.answer("❌ کاربری یافت نشد!")
    else:
        text = "🔍 **نتایج جستجو:**\n\n"
        for u in users[:10]:
            text += f"🆔 `{u['user_id']}` - {u['first_name'] or '---'} - 💰 {u['balance']:,}\n"
        
        builder = InlineKeyboardBuilder()
        for u in users[:5]:
            builder.row(InlineKeyboardButton(
                text=f"👤 {u['first_name'] or u['user_id']}",
                callback_data=f"adm_user_detail_{u['user_id']}"
            ))
        builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
        
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
    
    await state.clear()

@router.callback_query(F.data.startswith("adm_user_detail_"))
async def adm_user_detail(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    u = db.get_user(user_id)
    
    if not u:
        return await callback.answer("❌ کاربر یافت نشد!", show_alert=True)
    
    text = f"""
👤 **جزئیات کاربر**

🆔 شناسه: `{u['user_id']}`
👤 نام: {u['first_name'] or '---'} {u['last_name'] or ''}
📅 عضویت: {u['join_date'][:10] if u['join_date'] else '---'}

💰 موجودی: {u['balance']:,} سکه
💎 الماس: {u['diamonds']:,}
🎮 بازی‌ها: {u['total_games']:,}
🏆 برد: {u['total_wins']:,} | 😢 باخت: {u['total_losses']:,}

🚫 وضعیت: {'مسدود' if u['is_banned'] else 'فعال'}
👑 ادمین: {'بله' if u['is_admin'] else 'خیر'}
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 تغییر موجودی", callback_data=f"adm_set_balance_{user_id}"),
        InlineKeyboardButton(text="📋 تراکنش‌ها", callback_data=f"adm_user_tx_{user_id}")
    )
    
    if u['is_banned']:
        builder.row(InlineKeyboardButton(text="✅ رفع مسدودیت", callback_data=f"adm_unban_{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🚫 مسدود کردن", callback_data=f"adm_ban_{user_id}"))
    
    if not u['is_admin']:
        builder.row(InlineKeyboardButton(text="👑 تبدیل به ادمین", callback_data=f"adm_make_admin_{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="⬇️ حذف از ادمین", callback_data=f"adm_remove_admin_{user_id}"))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users_list"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

# ==== تغییر موجودی ====

@router.callback_query(F.data == "adm_edit_balance_menu")
async def adm_edit_balance_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_edit_balance)
    await callback.message.edit_text(
        "💰 **تغییر موجودی کاربر**\n\n"
        "📝 ابتدا شناسه کاربر را وارد کنید:",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(States.admin_edit_balance)
async def adm_edit_balance_user(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        u = db.get_user(user_id)
        if not u:
            return await message.answer("❌ کاربر یافت نشد!")
        
        await state.update_data(edit_uid=user_id)
        await message.answer(
            f"👤 کاربر: {u['first_name'] or user_id}\n💰 موجودی فعلی: {u['balance']:,} سکه\n\n"
            f"📝 موجودی جدید را وارد کنید (یا +amount / -amount):"
        )
    except:
        await message.answer("❌ شناسه معتبر وارد کنید!")

# ==== تنظیم موجودی ====

@router.callback_query(F.data.startswith("adm_set_balance_"))
async def adm_set_balance(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[3])
    await state.update_data(edit_uid=user_id)
    u = db.get_user(user_id)
    
    await callback.message.edit_text(
        f"👤 کاربر: {u['first_name'] or user_id}\n💰 موجودی فعلی: {u['balance']:,} سکه\n\n"
        f"📝 موجودی جدید را وارد کنید:",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(States.admin_edit_balance)

# ==== بن کردن ====

@router.callback_query(F.data == "adm_ban_menu")
async def adm_ban_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_ban_reason)
    await callback.message.edit_text(
        "🚫 **مسدود کردن کاربر**\n\n📝 شناسه کاربر را وارد کنید:",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("adm_ban_"))
async def adm_ban_user(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    await state.update_data(ban_uid=user_id)
    await state.set_state(States.admin_ban_reason)
    await callback.message.edit_text("📝 دلیل مسدودیت را وارد کنید:", parse_mode=ParseMode.MARKDOWN)

@router.message(States.admin_ban_reason)
async def adm_ban_process(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('ban_uid') or data.get('edit_uid')
    reason = message.text.strip()
    
    if data.get('ban_uid'):
        db.ban_user(user_id, reason)
        await message.answer(f"🚫 کاربر `{user_id}` مسدود شد.\n❌ دلیل: {reason}", parse_mode=ParseMode.MARKDOWN)
    else:
        try:
            amount = int(message.text)
            db.set_balance(user_id, amount, message.from_user.id)
            await message.answer(f"✅ موجودی کاربر `{user_id}` به {amount:,} سکه تغییر یافت.", parse_mode=ParseMode.MARKDOWN)
        except:
            await message.answer("❌ عدد معتبر وارد کنید!")
    
    await state.clear()

@router.callback_query(F.data.startswith("adm_unban_"))
async def adm_unban_user(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    db.unban_user(user_id)
    await callback.answer("✅ کاربر آزاد شد!", show_alert=True)

# ==== ادمین‌ها ====

@router.callback_query(F.data == "adm_manage_admins")
async def adm_manage_admins(callback: CallbackQuery):
    with db.conn() as c:
        admins = c.execute("SELECT * FROM users WHERE is_admin=1").fetchall()
    
    text = "👑 **لیست ادمین‌ها:**\n\n"
    for a in admins:
        text += f"• `{a['user_id']}` - {a['first_name'] or '---'}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ اضافه کردن ادمین", callback_data="adm_add_admin"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_add_admin)
    await callback.message.edit_text("📝 شناسه کاربر جدید را وارد کنید:", parse_mode=ParseMode.MARKDOWN)

@router.message(States.admin_add_admin)
async def adm_add_admin_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        db.set_admin(user_id, True)
        await message.answer(f"✅ کاربر `{user_id}` به ادمین اضافه شد.", parse_mode=ParseMode.MARKDOWN)
    except:
        await message.answer("❌ شناسه معتبر وارد کنید!")
    await state.clear()

@router.callback_query(F.data.startswith("adm_make_admin_"))
async def adm_make_admin(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    db.set_admin(user_id, True)
    await callback.answer("✅ کاربر ادمین شد!", show_alert=True)

@router.callback_query(F.data.startswith("adm_remove_admin_"))
async def adm_remove_admin(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    if user_id == ADMIN_USER_ID:
        return await callback.answer("❌ نمی‌توانید ادمین اصلی را حذف کنید!", show_alert=True)
    db.set_admin(user_id, False)
    await callback.answer("✅ کاربر از ادمین حذف شد!", show_alert=True)

# ==== تراکنش‌ها و برداشت‌ها ====

@router.callback_query(F.data == "adm_transactions")
async def adm_transactions(callback: CallbackQuery):
    txs = db.get_transactions(limit=10)
    text = "💳 **آخرین تراکنش‌ها:**\n\n"
    for tx in txs:
        text += f"#{tx['id']} | 👤 `{tx['user_id']}` | {tx['type']}: {tx['amount']:,}\n📝 {tx['description'][:30]}\n🕐 {tx['timestamp'][:19]}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(callback: CallbackQuery):
    reqs = db.get_pending_withdrawals()
    
    if not reqs:
        return await callback.message.edit_text("✅ هیچ درخواست برداشتی نیست.", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back")).as_markup())
    
    r = reqs[0]
    text = f"💎 **درخواست #{r['id']}**\n👤 {r['first_name']} ({r['user_id']})\n💰 {r['amount_coins']:,} سکه = {r['amount_toman']:,} تومان\n💳 `{r['card_number']}`\n👤 {r['card_holder']}"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appwd_{r['id']}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejwd_{r['id']}")
    )
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("adm_user_tx_"))
async def adm_user_tx(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    txs = db.get_transactions(user_id, 10)
    
    text = f"📋 **تراکنش‌های کاربر {user_id}:**\n\n"
    for tx in txs:
        text += f"#{tx['id']} | {tx['type']}: {tx['amount']:,} | {tx['description'][:30]}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_user_detail_{user_id}"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

# ==== تنظیمات ====

@router.callback_query(F.data == "adm_settings")
async def adm_settings(callback: CallbackQuery):
    settings = db.get_all_settings()
    
    text = "⚙️ **تنظیمات فعلی ربات:**\n\n"
    text += f"💳 شماره کارت: `{settings.get('card_number', '---')}`\n"
    text += f"👤 صاحب کارت: {settings.get('card_holder', '---')}\n"
    text += f"📞 پشتیبانی: {settings.get('support_username', '---')}\n"
    text += f"📢 کانال: {settings.get('required_channel_id', '---')}\n"
    text += f"💰 نرخ سکه: {settings.get('coin_to_toman', '---')} تومان\n"
    text += f"⚠️ حداقل برداشت: {settings.get('min_withdraw_coins', '---')} سکه\n"
    text += f"👥 حداقل دعوت: {settings.get('min_invites_first_withdraw', '---')}\n"
    text += f"🎲 شانس تاس: {settings.get('dice_win_chance', '---')}٪\n"
    text += f"🎪 شانس قرعه‌کشی: {settings.get('lottery_win_chance', '---')}٪\n"
    text += f"🎮 قیمت‌ها: {settings.get('game_prices', '---')}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ ویرایش تنظیمات", callback_data="adm_edit_setting"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_back"))
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "adm_edit_setting")
async def adm_edit_setting(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    
    settings_list = [
        ("💳 شماره کارت", "card_number"),
        ("👤 صاحب کارت", "card_holder"),
        ("📞 پشتیبانی", "support_username"),
        ("📢 آیدی کانال", "required_channel_id"),
        ("🔗 لینک کانال", "required_channel_link"),
        ("📊 کانال گزارشات", "withdraw_log_channel"),
        ("💰 نرخ سکه (تومان)", "coin_to_toman"),
        ("⚠️ حداقل برداشت", "min_withdraw_coins"),
        ("👥 حداقل دعوت", "min_invites_first_withdraw"),
        ("🎲 شانس تاس (٪)", "dice_win_chance"),
        ("🎪 شانس قرعه‌کشی (٪)", "lottery_win_chance"),
        ("🎯 ماموریت (تعداد)", "daily_mission_games"),
        ("🎁 جایزه ماموریت", "daily_mission_reward"),
    ]
    
    for name, key in settings_list:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"adm_set_{key}"))
    
    builder.row(InlineKeyboardButton(text="🎮 قیمت‌های بازی", callback_data="adm_set_game_prices"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_settings"))
    
    await callback.message.edit_text("⚙️ **یک تنظیم را برای ویرایش انتخاب کنید:**", parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("adm_set_"))
async def adm_set_setting(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split("_", 2)[2]
    current = db.get_setting(key, '')
    
    await state.update_data(setting_key=key)
    await state.set_state(States.admin_edit_setting)
    
    await callback.message.edit_text(
        f"⚙️ **ویرایش: {key}**\n\n📝 مقدار فعلی: `{current}`\n\n✏️ مقدار جدید را وارد کنید:",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "adm_set_game_prices")
async def adm_set_game_prices(callback: CallbackQuery, state: FSMContext):
    current = db.get_setting('game_prices', [50, 100, 200, 500, 1000])
    
    await state.update_data(setting_key='game_prices')
    await state.set_state(States.admin_edit_setting)
    
    await callback.message.edit_text(
        f"🎮 **قیمت‌های بازی**\n\n📝 فعلی: {current}\n\n✏️ قیمت‌های جدید را با کاما وارد کنید:\nمثال: 50,100,200,500,1000",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(States.admin_edit_setting)
async def adm_save_setting(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data['setting_key']
    value = message.text.strip()
    
    if key == 'game_prices':
        try:
            value = [int(x.strip()) for x in value.split(',')]
        except:
            return await message.answer("❌ فرمت نامعتبر! مثال: 50,100,200")
    elif key in ['coin_to_toman', 'min_withdraw_coins', 'min_invites_first_withdraw', 
                 'dice_win_chance', 'lottery_win_chance', 'daily_mission_games', 'daily_mission_reward']:
        try:
            value = int(value)
        except:
            return await message.answer("❌ عدد وارد کنید!")
    
    db.set_setting(key, value)
    await message.answer(f"✅ تنظیم `{key}` با موفقیت به `{value}` تغییر یافت.", reply_markup=await admin_back_keyboard())
    await state.clear()

async def admin_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="adm_back"))
    return builder.as_markup()

@router.callback_query(F.data == "adm_card_settings")
async def adm_card_settings(callback: CallbackQuery, state: FSMContext):
    card = db.get_setting('card_number', '6062561009737464')
    holder = db.get_setting('card_holder', 'مجاور')
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ ویرایش شماره کارت", callback_data="adm_set_card_number"))
    builder.row(InlineKeyboardButton(text="✏️ ویرایش نام صاحب", callback_data="adm_set_card_holder"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_settings"))
    
    await callback.message.edit_text(
        f"💳 **تنظیمات کارت**\n\n📌 شماره: `{card}`\n👤 صاحب: {holder}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "adm_channel_settings")
async def adm_channel_settings(callback: CallbackQuery):
    ch_id = db.get_setting('required_channel_id', '@gozaresh_taj')
    ch_link = db.get_setting('required_channel_link', 'https://t.me/gozaresh_taj')
    log_ch = db.get_setting('withdraw_log_channel', '@gozaresh_taj')
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ آیدی کانال", callback_data="adm_set_required_channel_id"))
    builder.row(InlineKeyboardButton(text="✏️ لینک کانال", callback_data="adm_set_required_channel_link"))
    builder.row(InlineKeyboardButton(text="✏️ کانال گزارشات", callback_data="adm_set_withdraw_log_channel"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_settings"))
    
    await callback.message.edit_text(
        f"📢 **تنظیمات کانال**\n\n📌 کانال: {ch_id}\n🔗 لینک: {ch_link}\n📊 گزارشات: {log_ch}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "adm_game_settings")
async def adm_game_settings(callback: CallbackQuery):
    dice = db.get_setting('dice_win_chance', 16)
    lottery = db.get_setting('lottery_win_chance', 2)
    prices = db.get_setting('game_prices', [50, 100, 200, 500, 1000])
    mission_games = db.get_setting('daily_mission_games', 3)
    mission_reward = db.get_setting('daily_mission_reward', 50)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 شانس تاس", callback_data="adm_set_dice_win_chance"))
    builder.row(InlineKeyboardButton(text="🎪 شانس قرعه‌کشی", callback_data="adm_set_lottery_win_chance"))
    builder.row(InlineKeyboardButton(text="🎮 قیمت‌های بازی", callback_data="adm_set_game_prices"))
    builder.row(InlineKeyboardButton(text="🎯 تعداد ماموریت", callback_data="adm_set_daily_mission_games"))
    builder.row(InlineKeyboardButton(text="🎁 جایزه ماموریت", callback_data="adm_set_daily_mission_reward"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_settings"))
    
    await callback.message.edit_text(
        f"🎮 **تنظیمات بازی**\n\n"
        f"🎲 شانس تاس: {dice}٪\n"
        f"🎪 شانس قرعه‌کشی: {lottery}٪\n"
        f"💰 قیمت‌ها: {prices}\n"
        f"🎯 ماموریت: {mission_games} بازی\n"
        f"🎁 جایزه: {mission_reward} سکه",
        parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup()
    )

# ==== عملیات ====

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.admin_bc)
    await callback.message.edit_text("📢 پیام همگانی را ارسال کنید:")

@router.message(States.admin_bc)
async def adm_send_broadcast(message: Message, state: FSMContext):
    users, _ = db.get_all_users(per_page=100000)
    s = 0
    for u in users:
        try:
            await bot.copy_message(u['user_id'], message.chat.id, message.message_id)
            s += 1
        except:
            pass
        await asyncio.sleep(0.05)
    
    await message.answer(f"✅ پیام به {s} کاربر ارسال شد.", reply_markup=await admin_back_keyboard())
    await state.clear()

@router.callback_query(F.data == "adm_unlock_all")
async def adm_unlock_all(callback: CallbackQuery):
    with db.conn() as c:
        c.execute("DELETE FROM game_locks")
    await callback.answer("✅ قفل همه کاربران باز شد!", show_alert=True)

@router.callback_query(F.data == "adm_exit")
async def adm_exit(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🚪 از پنل خارج شدید.", reply_markup=main_menu())

@router.callback_query(F.data == "adm_back")
async def adm_back(callback: CallbackQuery):
    await callback.message.edit_text("🔰 **پنل مدیریت**", parse_mode=ParseMode.MARKDOWN, reply_markup=admin_panel())

# ==============================================
# 🔙 دکمه‌های عمومی
# ==============================================

@router.callback_query(F.data == "back_games")
async def back_games(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👥 بازی با دوست", callback_data="mode_friend"))
    builder.row(InlineKeyboardButton(text="🤖 بازی با ربات", callback_data="mode_bot"))
    builder.row(InlineKeyboardButton(text="🎯 حریف تصادفی", callback_data="mode_random"))
    builder.row(InlineKeyboardButton(text="🔑 ورود با کد", callback_data="join_room"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    
    await callback.message.edit_text("🎮 **منوی بازی‌ها**", parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=main_menu())

# ==============================================
# 🚀 اجرا
# ==============================================

@router.errors()
async def error_handler(update, exception):
    logger.error(f"Error: {exception}")
    return True

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
