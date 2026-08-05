# ==============================================
# 🎰 ربات کازینو - نسخه نهایی و کامل
# تمام بازی‌های دو نفره + ربات + زیرمجموعه + برداشت
# ==============================================

import asyncio
import logging
import sqlite3
import random
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
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
# 🔧 تنظیمات
# ==============================================

BOT_TOKEN = "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ"
ADMIN_USER_ID = 7548145568
ADMIN_PASSWORD = "mohamad1387"

# 💳 اطلاعات مالی
ADMIN_CARD_NUMBER = "6062561009737464"
ADMIN_CARD_HOLDER = "مجاور"
SUPPORT_USERNAME = "@ad_tas"

# 📢 کانال اجباری
REQUIRED_CHANNEL = {
    "id": "@gozaresh_taj",
    "name": "📢 کانال رسمی",
    "link": "https://t.me/gozaresh_taj"
}
WITHDRAW_LOG_CHANNEL = "@gozaresh_taj"

# 💰 تنظیمات مالی
COIN_TO_TOMAN = 1000
MIN_WITHDRAW_COINS = 100
MIN_INVITES_FIRST_WITHDRAW = 4

# 🎮 قیمت‌های بازی
GAME_PRICES = [50, 100, 200, 500, 1000]

# 🎯 ماموریت روزانه
DAILY_MISSION_GAMES = 3
DAILY_MISSION_REWARD = 50

# ==============================================
# 📊 لاگینگ
# ==============================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==============================================
# 🗄️ دیتابیس
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
        except:
            c.rollback()
            raise
        finally:
            c.close()
    
    def init_db(self):
        with self.conn() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT, first_name TEXT, last_name TEXT,
                    balance INTEGER DEFAULT 0, diamonds INTEGER DEFAULT 0,
                    invited_by INTEGER, invite_code TEXT,
                    total_invites INTEGER DEFAULT 0, total_games INTEGER DEFAULT 0,
                    first_withdraw_used BOOLEAN DEFAULT FALSE,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE,
                    is_admin BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, type TEXT, amount INTEGER,
                    description TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS game_rooms (
                    room_id TEXT PRIMARY KEY,
                    creator_id INTEGER, player2_id INTEGER,
                    game_type TEXT, bet_amount INTEGER,
                    status TEXT DEFAULT 'waiting',
                    creator_choice TEXT, player2_choice TEXT,
                    winner_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS match_queue (
                    user_id INTEGER UNIQUE, game_type TEXT,
                    bet_amount INTEGER, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS withdraw_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, amount_coins INTEGER,
                    amount_toman INTEGER, card_number TEXT,
                    card_holder TEXT, status TEXT DEFAULT 'pending',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS daily_missions (
                    user_id INTEGER, date TEXT,
                    games_played INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT FALSE,
                    claimed BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (user_id, date)
                );
                CREATE TABLE IF NOT EXISTS game_locks (
                    user_id INTEGER PRIMARY KEY,
                    game_name TEXT, locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT OR IGNORE INTO users (user_id, is_admin, invite_code) 
                VALUES (7548145568, TRUE, '7548145568');
            ''')
    
    def get_user(self, uid):
        with self.conn() as c:
            r = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            return dict(r) if r else None
    
    def create_user(self, uid, username, first_name, last_name, invited_by=None):
        with self.conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone():
                c.execute('''INSERT INTO users (user_id,username,first_name,last_name,invited_by,invite_code)
                            VALUES (?,?,?,?,?,?)''', (uid,username,first_name,last_name,invited_by,str(uid)))
                if invited_by and invited_by != uid:
                    c.execute("UPDATE users SET diamonds=diamonds+1, total_invites=total_invites+1 WHERE user_id=?", (invited_by,))
            else:
                c.execute("UPDATE users SET username=?,first_name=?,last_name=? WHERE user_id=?", (username,first_name,last_name,uid))
    
    def get_balance(self, uid):
        u = self.get_user(uid)
        return u['balance'] if u else 0
    
    def update_balance(self, uid, amount, ttype, desc):
        with self.conn() as c:
            c.execute("UPDATE users SET balance=balance+?, last_activity=CURRENT_TIMESTAMP WHERE user_id=?", (amount, uid))
            c.execute("INSERT INTO transactions (user_id,type,amount,description) VALUES (?,?,?,?)", (uid,ttype,amount,desc))
    
    def lock_user(self, uid, game):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO game_locks VALUES (?,?,CURRENT_TIMESTAMP)", (uid,game))
    
    def unlock_user(self, uid):
        with self.conn() as c:
            c.execute("DELETE FROM game_locks WHERE user_id=?", (uid,))
    
    def is_locked(self, uid):
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) as c FROM game_locks WHERE user_id=?", (uid,)).fetchone()['c'] > 0
    
    def create_room(self, creator_id, bet):
        rid = str(random.randint(100000, 999999))
        with self.conn() as c:
            c.execute("INSERT INTO game_rooms (room_id,creator_id,bet_amount) VALUES (?,?,?)", (rid,creator_id,bet))
        return rid
    
    def join_room(self, rid, p2id):
        with self.conn() as c:
            r = c.execute("SELECT * FROM game_rooms WHERE room_id=? AND status='waiting'", (rid,)).fetchone()
            if not r or r['creator_id'] == p2id:
                return None
            c.execute("UPDATE game_rooms SET player2_id=?, status='playing' WHERE room_id=?", (p2id,rid))
            return dict(r)
    
    def set_room_game(self, rid, gtype):
        with self.conn() as c:
            c.execute("UPDATE game_rooms SET game_type=? WHERE room_id=?", (gtype,rid))
    
    def set_choice(self, rid, pnum, choice):
        col = 'creator_choice' if pnum == 1 else 'player2_choice'
        with self.conn() as c:
            c.execute(f"UPDATE game_rooms SET {col}=? WHERE room_id=?", (choice,rid))
    
    def get_room(self, rid):
        with self.conn() as c:
            r = c.execute("SELECT * FROM game_rooms WHERE room_id=?", (rid,)).fetchone()
            return dict(r) if r else None
    
    def finish_room(self, rid, winner):
        with self.conn() as c:
            c.execute("UPDATE game_rooms SET status='finished', winner_id=? WHERE room_id=?", (winner,rid))
    
    def add_queue(self, uid, gtype, bet):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO match_queue VALUES (?,?,?,CURRENT_TIMESTAMP)", (uid,gtype,bet))
    
    def find_match(self, uid, bet, gtype):
        with self.conn() as c:
            r = c.execute("SELECT user_id FROM match_queue WHERE bet_amount=? AND game_type=? AND user_id!=? ORDER BY joined_at LIMIT 1", (bet,gtype,uid)).fetchone()
            if r:
                c.execute("DELETE FROM match_queue WHERE user_id IN (?,?)", (uid,r['user_id']))
                return r['user_id']
            return None
    
    def remove_queue(self, uid):
        with self.conn() as c:
            c.execute("DELETE FROM match_queue WHERE user_id=?", (uid,))
    
    def get_last_bet(self, uid):
        with self.conn() as c:
            r = c.execute("SELECT amount FROM transactions WHERE user_id=? AND type='bet' ORDER BY timestamp DESC LIMIT 1", (uid,)).fetchone()
            return abs(r['amount']) if r else 0
    
    def get_invite_stats(self, uid):
        with self.conn() as c:
            total = c.execute("SELECT COUNT(*) as c FROM users WHERE invited_by=?", (uid,)).fetchone()['c']
            active = c.execute("SELECT COUNT(*) as c FROM users WHERE invited_by=? AND total_games>=1", (uid,)).fetchone()['c']
            d = c.execute("SELECT diamonds FROM users WHERE user_id=?", (uid,)).fetchone()
            return {'total': total, 'active': active, 'diamonds': d['diamonds'] if d else 0}
    
    def can_withdraw(self, uid):
        u = self.get_user(uid)
        if not u: return False, "کاربر یافت نشد"
        if u['balance'] < MIN_WITHDRAW_COINS: return False, f"❌ حداقل موجودی: {MIN_WITHDRAW_COINS} سکه"
        if not u['first_withdraw_used']:
            s = self.get_invite_stats(uid)
            if s['active'] < MIN_INVITES_FIRST_WITHDRAW:
                return False, f"❌ برای اولین برداشت، {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه فعال نیاز دارید\n📊 زیرمجموعه‌های فعال شما: {s['active']}"
        return True, "✅"
    
    def create_withdraw(self, uid, coins, card, holder):
        toman = coins * COIN_TO_TOMAN
        with self.conn() as c:
            c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (coins,uid))
            c.execute("INSERT INTO withdraw_requests (user_id,amount_coins,amount_toman,card_number,card_holder) VALUES (?,?,?,?,?)", (uid,coins,toman,card,holder))
            return c.lastrowid
    
    def process_withdraw(self, rid, approved):
        with self.conn() as c:
            r = c.execute("SELECT * FROM withdraw_requests WHERE id=?", (rid,)).fetchone()
            if not r: return None
            if approved:
                c.execute("UPDATE withdraw_requests SET status='approved' WHERE id=?", (rid,))
                c.execute("UPDATE users SET first_withdraw_used=TRUE WHERE user_id=?", (r['user_id'],))
            else:
                c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r['amount_coins'], r['user_id']))
                c.execute("UPDATE withdraw_requests SET status='rejected' WHERE id=?", (rid,))
            return dict(r)
    
    def pending_withdrawals(self):
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT wr.*,u.first_name,u.last_name FROM withdraw_requests wr JOIN users u ON wr.user_id=u.user_id WHERE wr.status='pending' ORDER BY wr.timestamp DESC").fetchall()]
    
    def update_mission(self, uid):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO daily_missions VALUES (?,?,0,0,0)", (uid,today))
            c.execute("UPDATE daily_missions SET games_played=games_played+1 WHERE user_id=? AND date=?", (uid,today))
            p = c.execute("SELECT games_played FROM daily_missions WHERE user_id=? AND date=?", (uid,today)).fetchone()['games_played']
            if p >= DAILY_MISSION_GAMES:
                c.execute("UPDATE daily_missions SET completed=TRUE WHERE user_id=? AND date=?", (uid,today))
    
    def get_mission(self, uid):
        today = datetime.now().strftime('%Y-%m-%d')
        with self.conn() as c:
            r = c.execute("SELECT * FROM daily_missions WHERE user_id=? AND date=?", (uid,today)).fetchone()
            return {'played': r['games_played'], 'completed': bool(r['completed']), 'claimed': bool(r['claimed'])} if r else {'played':0,'completed':False,'claimed':False}
    
    def claim_mission(self, uid):
        today = datetime.now().strftime('%Y-%m-%d')
        m = self.get_mission(uid)
        if m['completed'] and not m['claimed']:
            self.update_balance(uid, DAILY_MISSION_REWARD, 'mission', '🎁 جایزه ماموریت روزانه')
            with self.conn() as c:
                c.execute("UPDATE daily_missions SET claimed=TRUE WHERE user_id=? AND date=?", (uid,today))
            return True
        return False
    
    def get_users(self):
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM users ORDER BY join_date DESC").fetchall()]
    
    def count_users(self):
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    
    def total_balance(self):
        with self.conn() as c:
            r = c.execute("SELECT SUM(balance) as t FROM users").fetchone()
            return r['t'] or 0

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
    wait_card_amount = State()
    wait_receipt = State()
    wait_wd_amount = State()
    wait_wd_card = State()
    wait_wd_name = State()
    wait_room_code = State()
    admin_pass = State()
    admin_bc = State()

# ==============================================
# 🎨 کیبوردهای گرافیکی
# ==============================================

def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🎮 بازی‌ها"), KeyboardButton(text="💰 خرید سکه"))
    builder.row(KeyboardButton(text="👤 پروفایل"), KeyboardButton(text="👥 زیرمجموعه‌گیری"))
    builder.row(KeyboardButton(text="🎯 ماموریت روزانه"), KeyboardButton(text="💎 برداشت"))
    builder.row(KeyboardButton(text="📞 پشتیبانی"), KeyboardButton(text="❓ راهنما"))
    return builder.as_markup(resize_keyboard=True)

def game_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👥 بازی با دوست (ساخت اتاق)", callback_data="mode_friend"))
    builder.row(InlineKeyboardButton(text="🤖 بازی با ربات", callback_data="mode_bot"))
    builder.row(InlineKeyboardButton(text="🎯 حریف تصادفی", callback_data="mode_random"))
    builder.row(InlineKeyboardButton(text="🔑 ورود با کد اتاق", callback_data="join_room"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    return builder.as_markup()

def game_selection_menu(mode: str):
    builder = InlineKeyboardBuilder()
    
    if mode == "bot":
        games = [
            ("🎲 تاس", f"game_dice_{mode}"),
            ("🎪 قرعه‌کشی", f"game_lottery_{mode}")
        ]
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
    return builder.as_markup()

def bet_selection_menu(game_key: str):
    builder = InlineKeyboardBuilder()
    
    for price in GAME_PRICES:
        builder.row(InlineKeyboardButton(
            text=f"💎 {price:,} سکه",
            callback_data=f"bet_{game_key}_{price}"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games"))
    return builder.as_markup()

# ==============================================
# 🚀 هندلر شروع
# ==============================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL['id'], user_id)
        if member.status in ['left', 'kicked']:
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text=f"📢 عضویت در {REQUIRED_CHANNEL['name']}", url=REQUIRED_CHANNEL['link']))
            builder.row(InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join"))
            
            await message.answer(
                f"⛔ **برای استفاده از ربات، ابتدا باید عضو کانال ما شوید!**\n\n"
                f"📢 **{REQUIRED_CHANNEL['name']}**\n"
                f"🔗 {REQUIRED_CHANNEL['link']}\n\n"
                f"پس از عضویت، روی دکمه زیر کلیک کنید 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=builder.as_markup(),
                disable_web_page_preview=True
            )
            return
    except:
        pass
    
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
💎 **الماس:** {db.get_user(user_id)['diamonds']:,}

👥 **لینک دعوت شما:**
`https://t.me/{bot_username}?start={user_id}`

📞 **پشتیبانی:** {SUPPORT_USERNAME}

🎮 از منوی زیر استفاده کنید 👇
    """
    
    await message.answer(welcome, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())

@router.callback_query(F.data == "check_join")
async def check_join(callback: CallbackQuery):
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL['id'], callback.from_user.id)
        if member.status not in ['left', 'kicked']:
            await callback.message.delete()
            await continue_start(callback.message)
        else:
            await callback.answer("❌ هنوز عضو نشده‌اید!", show_alert=True)
    except:
        await callback.answer("❌ خطا در بررسی!", show_alert=True)

# ==============================================
# 🎮 منوهای اصلی
# ==============================================

@router.message(F.text == "🎮 بازی‌ها")
async def menu_games(message: Message):
    if db.is_locked(message.from_user.id):
        return await message.answer("⚠️ شما در حال انجام یک بازی هستید!")
    
    await message.answer(
        "🎮 **منوی بازی‌ها**\n\n"
        "👥 **بازی با دوست:** ساخت اتاق خصوصی\n"
        "🤖 **بازی با ربات:** تک نفره\n"
        "🎯 **حریف تصادفی:** بازی با بازیکن آنلاین\n"
        "🔑 **ورود با کد:** وارد اتاق دوست شوید\n\n"
        "👇 یک گزینه را انتخاب کنید:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=game_main_menu()
    )

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
📅 **تاریخ عضویت:** {u['join_date'][:10] if u['join_date'] else '---'}

💰 **موجودی سکه:** {u['balance']:,}
💎 **الماس:** {u['diamonds']:,}
🎮 **تعداد بازی‌ها:** {u['total_games']:,}

👥 **زیرمجموعه‌ها:**
• کل: {stats['total']} نفر
• فعال: {stats['active']} نفر
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

💎 با دعوت دوستان، الماس رایگان دریافت کنید!

✏️ **لینک دعوت شما:**
`https://t.me/{bot_username}?start={uid}`

📊 **آمار شما:**
• 👥 کل: **{stats['total']}** نفر
• ✅ فعال: **{stats['active']}** نفر
• 💎 الماس: **{stats['diamonds']}**

⚠️ اولین برداشت: **{MIN_INVITES_FIRST_WITHDRAW}** زیرمجموعه فعال
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "🎯 ماموریت روزانه")
async def menu_mission(message: Message):
    m = db.get_mission(message.from_user.id)
    bar_filled = m['played']
    bar_empty = DAILY_MISSION_GAMES - m['played']
    bar = "🟢" * bar_filled + "⚪" * bar_empty
    
    builder = InlineKeyboardBuilder()
    if m['completed'] and not m['claimed']:
        builder.row(InlineKeyboardButton(text="🎁 دریافت جایزه", callback_data="claim_mission"))
    
    text = f"""
╔══════════════════════╗
║  🎯 ماموریت روزانه    ║
╚══════════════════════╝

📋 **وظیفه:** {DAILY_MISSION_GAMES} بازی
🎁 **جایزه:** {DAILY_MISSION_REWARD:,} سکه

📊 **پیشرفت:**
{bar}
{m['played']} از {DAILY_MISSION_GAMES} بازی

{
    '✅ **کامل شد!** 👇' if m['completed'] and not m['claimed']
    else '🎉 **دریافت شد**' if m['claimed']
    else '🔴 ادامه دهید...'
}
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup() if builder else None)

@router.message(F.text == "💰 خرید سکه")
async def menu_buy(message: Message):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 مبلغ دلخواه", callback_data="buy_custom"))
    
    for p in [50, 100, 200, 500, 1000]:
        toman = p * COIN_TO_TOMAN
        builder.row(InlineKeyboardButton(text=f"📦 {p:,} سکه = {toman:,} تومان", callback_data=f"buypkg_{p}"))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    
    text = f"""
╔══════════════════════╗
║   💰 خرید سکه        ║
╚══════════════════════╝

💵 **نرخ:** هر سکه = {COIN_TO_TOMAN:,} تومان

💳 **شماره کارت:**
`{ADMIN_CARD_NUMBER}`
👤 **صاحب حساب:** {ADMIN_CARD_HOLDER}

📝 **نحوه خرید:**
۱. مبلغ را واریز کنید
۲. عکس رسید را ارسال کنید
۳. منتظر تایید باشید
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "💎 برداشت")
async def menu_withdraw(message: Message):
    uid = message.from_user.id
    can, reason = db.can_withdraw(uid)
    
    if not can:
        return await message.answer(f"❌ {reason}")
    
    balance = db.get_balance(uid)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💎 درخواست برداشت", callback_data="req_withdraw"))
    
    text = f"""
╔══════════════════════╗
║   💎 برداشت سکه      ║
╚══════════════════════╝

💰 **موجودی:** {balance:,} سکه
💵 **معادل:** {balance * COIN_TO_TOMAN:,} تومان

⚠️ حداقل: {MIN_WITHDRAW_COINS} سکه
⚠️ نرخ: هر سکه = {COIN_TO_TOMAN:,} تومان
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.message(F.text == "📞 پشتیبانی")
async def menu_support(message: Message):
    await message.answer(f"📞 **پشتیبانی:** {SUPPORT_USERNAME}\n\n💡 برای سوالات و مشکلات در ارتباط باشید.", parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "❓ راهنما")
async def menu_help(message: Message):
    text = f"""
╔══════════════════════╗
║    ❓ راهنما          ║
╚══════════════════════╝

🎮 **بازی با دوست:**
۱. ساخت اتاق → دریافت کد
۲. ارسال کد به دوست
۳. دوست با کد وارد می‌شود

🤖 **بازی با ربات:**
• تاس و قرعه‌کشی

🎯 **حریف تصادفی:**
• منتظر بازیکن دیگر

💰 **برداشت:**
• اولین برداشت: {MIN_INVITES_FIRST_WITHDRAW} زیرمجموعه
• حداقل: {MIN_WITHDRAW_COINS} سکه

📞 **پشتیبانی:** {SUPPORT_USERNAME}
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

# ==============================================
# 🎮 انتخاب حالت بازی
# ==============================================

@router.callback_query(F.data.startswith("mode_"))
async def select_mode(callback: CallbackQuery):
    mode = callback.data.split("_")[1]
    
    mode_names = {"friend": "👥 بازی با دوست", "bot": "🤖 بازی با ربات", "random": "🎯 حریف تصادفی"}
    
    await callback.message.edit_text(
        f"{mode_names.get(mode, mode)}\n\n🎮 **نوع بازی را انتخاب کنید:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=game_selection_menu(mode)
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
    
    await callback.message.edit_text(
        f"🎮 **{game_names.get(game_type, game_type)}**\n\n💰 **مبلغ شرط را انتخاب کنید:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=bet_selection_menu(game_key)
    )

# ==============================================
# 🎲 شروع بازی
# ==============================================

@router.callback_query(F.data.startswith("bet_"))
async def start_game(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    game_type = parts[1]
    mode = parts[2]
    bet = int(parts[3])
    user_id = callback.from_user.id
    
    if db.is_locked(user_id):
        return await callback.answer("⚠️ شما در حال بازی هستید!", show_alert=True)
    
    if db.get_balance(user_id) < bet:
        return await callback.answer(f"❌ موجودی کافی نیست! نیاز: {bet:,} سکه", show_alert=True)
    
    db.update_balance(user_id, -bet, 'bet', f'شرط {game_type}')
    db.lock_user(user_id, f'game_{game_type}')
    
    if mode == "bot":
        await play_vs_bot(callback, game_type, bet)
    elif mode == "friend":
        await create_game_room(callback, game_type, bet)
    elif mode == "random":
        await find_random_opponent(callback, game_type, bet)

# ==============================================
# 🤖 بازی با ربات
# ==============================================

async def play_vs_bot(callback: CallbackQuery, game_type: str, bet: int):
    user_id = callback.from_user.id
    
    if game_type == "dice":
        won = random.random() < 0.16
        prize = bet * 4 if won else 0
        emoji = "🎲"
    else:
        won = random.random() < 0.02
        prize = bet * 10 if won else 0
        emoji = "🎪"
    
    if prize > 0:
        db.update_balance(user_id, prize, 'win', f'برد {game_type}')
    
    db.unlock_user(user_id)
    db.update_mission(user_id)
    
    balance = db.get_balance(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 بازی مجدد", callback_data=f"bet_{game_type}_bot_{bet}"))
    builder.row(InlineKeyboardButton(text="🔙 منوی بازی‌ها", callback_data="back_games"))
    
    text = f"""
{emoji} **نتیجه بازی**

{'🎉 **برنده شدید!**' if won else '😢 **باختید!**'}

💰 شرط: {bet:,} سکه
🎁 جایزه: {prize:,} سکه
💳 موجودی: {balance:,} سکه
    """
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

# ==============================================
# 👥 ساخت اتاق
# ==============================================

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
╔══════════════════════╗
║  🎮 اتاق بازی ساخته شد║
╚══════════════════════╝

🎯 **بازی:** {game_names.get(game_type, game_type)}
💰 **مبلغ:** {bet:,} سکه
🔑 **کد اتاق:** `{room_id}`

📋 دوستت باید:
۱. /start بزند
۲. 🎮 بازی‌ها را انتخاب کند
۳. 🔑 ورود با کد را بزند
۴. کد `{room_id}` را وارد کند

⏰ منتظر بازیکن دوم...
    """
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

# ==============================================
# 🔑 ورود با کد
# ==============================================

@router.callback_query(F.data == "join_room")
async def join_room_start(callback: CallbackQuery, state: FSMContext):
    if db.is_locked(callback.from_user.id):
        return await callback.answer("⚠️ شما در حال بازی هستید!", show_alert=True)
    
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
    game_type = room['game_type']
    creator_id = room['creator_id']
    
    if db.get_balance(user_id) < bet:
        db.update_balance(creator_id, bet, 'refund', 'حریف موجودی کافی نداشت')
        db.unlock_user(creator_id)
        db.finish_room(code, None)
        return await message.answer("❌ موجودی شما کافی نیست! اتاق لغو شد.")
    
    db.update_balance(user_id, -bet, 'bet', f'ورود به اتاق {code}')
    db.lock_user(user_id, f'room_{code}')
    
    await start_pvp_game(message, room, user_id)

# ==============================================
# 🎮 شروع بازی دو نفره
# ==============================================

async def start_pvp_game(message: Message, room: Dict, player2_id: int):
    game_type = room['game_type']
    bet = room['bet_amount']
    room_id = room['room_id']
    creator_id = room['creator_id']
    
    game_names = {
        'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
        'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ'
    }
    
    # بازی‌های شانسی
    if game_type in ['football', 'basketball', 'darts', 'bowling']:
        winner_num = random.choice([1, 2])
        winner_id = creator_id if winner_num == 1 else player2_id
        
        prize = bet * 2
        db.update_balance(winner_id, prize, 'win', f'برد {game_type}')
        db.unlock_user(creator_id)
        db.unlock_user(player2_id)
        db.finish_room(room_id, winner_id)
        db.update_mission(creator_id)
        db.update_mission(player2_id)
        
        scores = {
            'football': f"{random.randint(0,5)} - {random.randint(0,5)}",
            'basketball': f"{random.randint(60,120)} - {random.randint(60,120)}",
            'darts': f"{random.randint(0,180)} - {random.randint(0,180)}",
            'bowling': f"{random.randint(100,300)} - {random.randint(100,300)}"
        }
        
        result = f"""
🏆 **نتیجه بازی**

🎮 {game_names.get(game_type, game_type)}
📊 نتیجه: {scores.get(game_type, '---')}

🎉 **برنده:** `{winner_id}`
💰 جایزه: {prize:,} سکه
        """
        
        for uid in [creator_id, player2_id]:
            try:
                await bot.send_message(uid, result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
            except:
                pass
        
        if message:
            await message.answer("✅ وارد اتاق شدید!", reply_markup=main_menu())
        
        return
    
    # بازی‌های انتخابی
    if game_type == 'rps':
        choices = [
            ("✊ سنگ", f"pvp_rock_{room_id}"),
            ("📄 کاغذ", f"pvp_paper_{room_id}"),
            ("✂️ قیچی", f"pvp_scissors_{room_id}")
        ]
        choice_text = "انتخاب کنید:"
    elif game_type == 'dice':
        choices = [(f"🎲 {i}", f"pvp_{i}_{room_id}") for i in range(1, 7)]
        choice_text = "یک عدد انتخاب کنید:"
    else:
        choices = []
        choice_text = ""
    
    builder = InlineKeyboardBuilder()
    for text, cb in choices:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    msg = f"""
🎮 **{game_names.get(game_type, game_type)}**
💰 مبلغ: {bet:,} سکه

{choice_text}
    """
    
    for uid in [creator_id, player2_id]:
        try:
            await bot.send_message(uid, msg, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())
        except Exception as e:
            logger.error(f"خطا در ارسال به {uid}: {e}")

# ==============================================
# ✊ پردازش انتخاب بازیکن
# ==============================================

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
    
    # بررسی آمادگی هر دو
    room = db.get_room(room_id)
    if room['creator_choice'] and room['player2_choice']:
        await determine_pvp_winner(room)
    else:
        await callback.message.edit_text(
            f"✅ انتخاب شما: {choice}\n⏰ منتظر بازیکن دیگر...",
            parse_mode=ParseMode.MARKDOWN
        )

async def determine_pvp_winner(room: Dict):
    game_type = room['game_type']
    p1_choice = room['creator_choice']
    p2_choice = room['player2_choice']
    bet = room['bet_amount']
    creator_id = room['creator_id']
    player2_id = room['player2_id']
    room_id = room['room_id']
    
    if game_type == 'rps':
        wins = {'rock': 'scissors', 'paper': 'rock', 'scissors': 'paper'}
        if p1_choice == p2_choice:
            winner_num = 0
        elif wins.get(p1_choice) == p2_choice:
            winner_num = 1
        else:
            winner_num = 2
    elif game_type == 'dice':
        p1 = int(p1_choice)
        p2 = int(p2_choice)
        if p1 > p2:
            winner_num = 1
        elif p2 > p1:
            winner_num = 2
        else:
            winner_num = 0
    else:
        winner_num = 0
    
    if winner_num == 0:
        db.update_balance(creator_id, bet, 'refund', 'مساوی - برگشت سکه')
        db.update_balance(player2_id, bet, 'refund', 'مساوی - برگشت سکه')
        result = f"""
🤝 **بازی مساوی شد!**

👤 بازیکن ۱: {p1_choice}
👤 بازیکن ۲: {p2_choice}

💰 سکه‌ها برگشت خورد.
        """
    else:
        winner_id = creator_id if winner_num == 1 else player2_id
        prize = bet * 2
        db.update_balance(winner_id, prize, 'win', 'برد بازی دو نفره')
        
        result = f"""
🏆 **نتیجه بازی**

👤 بازیکن ۱: {p1_choice}
👤 بازیکن ۲: {p2_choice}

🎉 **برنده:** `{winner_id}`
💰 جایزه: {prize:,} سکه
        """
        db.finish_room(room_id, winner_id)
    
    db.unlock_user(creator_id)
    db.unlock_user(player2_id)
    if winner_num != 0:
        db.finish_room(room_id, creator_id if winner_num == 1 else player2_id)
    else:
        db.finish_room(room_id, None)
    
    db.update_mission(creator_id)
    db.update_mission(player2_id)
    
    for uid in [creator_id, player2_id]:
        try:
            await bot.send_message(uid, result, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
        except:
            pass

# ==============================================
# 🎯 حریف تصادفی
# ==============================================

async def find_random_opponent(callback: CallbackQuery, game_type: str, bet: int):
    user_id = callback.from_user.id
    
    opponent = db.find_match(user_id, bet, game_type)
    
    if opponent:
        room_id = db.create_room(opponent, bet)
        db.set_room_game(room_id, game_type)
        db.join_room(room_id, user_id)
        
        db.update_balance(opponent, -bet, 'bet', f'بازی تصادفی')
        db.lock_user(opponent, f'room_{room_id}')
        db.lock_user(user_id, f'room_{room_id}')
        
        room = db.get_room(room_id)
        
        game_names = {
            'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
            'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ'
        }
        
        await callback.message.edit_text(
            f"🎯 **حریف پیدا شد!**\n\n🎮 {game_names.get(game_type, game_type)}\n💰 {bet:,} سکه\n\n⏳ شروع بازی...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await start_pvp_game(None, room, user_id)
    else:
        db.add_queue(user_id, game_type, bet)
        
        game_names = {
            'rps': '✊ سنگ کاغذ قیچی', 'dice': '🎲 تاس', 'football': '⚽ فوتبال',
            'basketball': '🏀 بسکتبال', 'darts': '🎯 دارت', 'bowling': '🎳 بولینگ'
        }
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="❌ لغو جستجو", callback_data="cancel_search"))
        
        await callback.message.edit_text(
            f"🔍 **در جستجوی حریف...**\n\n🎮 {game_names.get(game_type, game_type)}\n💰 {bet:,} سکه\n⏰ منتظر بمانید...",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=builder.as_markup()
        )

# ==============================================
# ❌ لغو
# ==============================================

@router.callback_query(F.data.startswith("cancel_room_"))
async def cancel_room(callback: CallbackQuery):
    room_id = callback.data.split("_")[2]
    room = db.get_room(room_id)
    user_id = callback.from_user.id
    
    if not room:
        return await callback.answer("❌ اتاق یافت نشد!", show_alert=True)
    
    if room['creator_id'] != user_id:
        return await callback.answer("❌ فقط سازنده می‌تواند لغو کند!", show_alert=True)
    
    if room['player2_id']:
        return await callback.answer("❌ بازیکن دوم وارد شده! نمی‌توانید لغو کنید.", show_alert=True)
    
    db.update_balance(user_id, room['bet_amount'], 'refund', f'لغو اتاق {room_id}')
    db.unlock_user(user_id)
    db.finish_room(room_id, None)
    
    await callback.message.edit_text(
        f"❌ **اتاق لغو شد**\n\n💰 مبلغ {room['bet_amount']:,} سکه به حساب شما برگشت خورد.\n💳 موجودی: {db.get_balance(user_id):,} سکه",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games")).as_markup()
    )

@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery):
    user_id = callback.from_user.id
    db.remove_queue(user_id)
    
    refund = db.get_last_bet(user_id)
    if refund > 0:
        db.update_balance(user_id, refund, 'refund', 'لغو جستجو')
    
    db.unlock_user(user_id)
    
    await callback.message.edit_text(
        f"❌ **جستجو لغو شد**\n\n💰 سکه به حساب شما برگشت خورد.\n💳 موجودی: {db.get_balance(user_id):,} سکه",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_games")).as_markup()
    )

# ==============================================
# 💰 خرید سکه
# ==============================================

@router.callback_query(F.data == "buy_custom")
async def buy_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(States.wait_card_amount)
    await callback.message.answer("💰 چند سکه می‌خواهید؟\n📝 تعداد را وارد کنید:")

@router.message(States.wait_card_amount)
async def process_custom(message: Message, state: FSMContext):
    try:
        coins = int(message.text)
        if coins <= 0:
            raise ValueError
    except:
        return await message.answer("❌ عدد معتبر وارد کنید!")
    
    await state.update_data(buy_coins=coins)
    await state.set_state(States.wait_receipt)
    
    await message.answer(
        f"💳 **پرداخت**\n\n📦 سکه: {coins:,}\n💵 مبلغ: {coins*COIN_TO_TOMAN:,} تومان\n\n"
        f"📌 شماره کارت:\n`{ADMIN_CARD_NUMBER}`\n👤 {ADMIN_CARD_HOLDER}\n\n📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("buypkg_"))
async def buy_package(callback: CallbackQuery, state: FSMContext):
    coins = int(callback.data.split("_")[1])
    await state.update_data(buy_coins=coins)
    await state.set_state(States.wait_receipt)
    
    await callback.message.answer(
        f"💳 **پرداخت**\n\n📦 {coins:,} سکه\n💵 {coins*COIN_TO_TOMAN:,} تومان\n\n"
        f"📌 شماره کارت:\n`{ADMIN_CARD_NUMBER}`\n\n📸 عکس رسید را ارسال کنید.",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(States.wait_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    data = await state.get_data()
    coins = data['buy_coins']
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"appbuy_{message.from_user.id}_{coins}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"rejbuy_{message.from_user.id}")
    )
    
    await bot.send_message(ADMIN_USER_ID,
        f"🔔 خرید جدید\n👤 {message.from_user.full_name}\n💰 {coins:,} سکه\n💵 {coins*COIN_TO_TOMAN:,} تومان",
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
    await callback.message.edit_text(f"✅ {coins:,} سکه به کاربر `{user_id}` اضافه شد.", parse_mode=ParseMode.MARKDOWN)
    try:
        await bot.send_message(user_id, f"✅ خرید تایید شد!\n💰 {coins:,} سکه اضافه شد.")
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

# ==============================================
# 💎 برداشت
# ==============================================

@router.callback_query(F.data == "req_withdraw")
async def req_withdraw(callback: CallbackQuery, state: FSMContext):
    can, reason = db.can_withdraw(callback.from_user.id)
    if not can:
        return await callback.answer(reason, show_alert=True)
    
    await state.set_state(States.wait_wd_amount)
    await callback.message.answer(f"💰 چند سکه برداشت می‌کنید؟\n⚠️ حداقل: {MIN_WITHDRAW_COINS}")

@router.message(States.wait_wd_amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        coins = int(message.text)
        if coins < MIN_WITHDRAW_COINS or coins > db.get_balance(message.from_user.id):
            return await message.answer(f"❌ مقدار نامعتبر!")
    except:
        return await message.answer("❌ عدد وارد کنید!")
    
    await state.update_data(wd_coins=coins)
    await state.set_state(States.wait_wd_card)
    await message.answer(f"💵 {coins*COIN_TO_TOMAN:,} تومان\n\n💳 شماره کارت ۱۶ رقمی:")

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
    toman = coins * COIN_TO_TOMAN
    
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
    
    try:
        await bot.send_message(WITHDRAW_LOG_CHANNEL,
            f"⏳ درخواست برداشت #{req_id}\n💰 {coins:,} سکه\n💵 {toman:,} تومان",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass
    
    await message.answer(f"✅ درخواست ثبت شد.\n💰 {coins:,} سکه = {toman:,} تومان\n⏰ منتظر تایید باشید.", reply_markup=main_menu())
    await state.clear()

@router.callback_query(F.data.startswith("appwd_"))
async def approve_wd(callback: CallbackQuery):
    req_id = int(callback.data.split("_")[1])
    req = db.process_withdraw(req_id, True)
    if req:
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

# ==============================================
# 🎯 ماموریت
# ==============================================

@router.callback_query(F.data == "claim_mission")
async def claim_mission(callback: CallbackQuery):
    if db.claim_mission(callback.from_user.id):
        await callback.answer(f"🎉 {DAILY_MISSION_REWARD} سکه دریافت شد!", show_alert=True)
    else:
        await callback.answer("❌ نمی‌توانید دریافت کنید!", show_alert=True)

# ==============================================
# 🔙 بازگشت
# ==============================================

@router.callback_query(F.data == "back_games")
async def back_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 **منوی بازی‌ها**", parse_mode=ParseMode.MARKDOWN, reply_markup=game_main_menu())

@router.callback_query(F.data == "back_main")
async def back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=main_menu())

# ==============================================
# 👑 پنل مدیریت
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    u = db.get_user(message.from_user.id)
    if not u or not u.get('is_admin'):
        return await message.answer("⛔ دسترسی غیرمجاز!")
    
    await state.set_state(States.admin_pass)
    await message.answer("🔐 رمز عبور:")

@router.message(States.admin_pass)
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
    await callback.message.edit_text(f"📊 کاربران: {db.count_users():,}\n💰 سکه: {db.total_balance():,}")

@router.callback_query(F.data == "adm_wd")
async def adm_wd(callback: CallbackQuery):
    reqs = db.pending_withdrawals()
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
    await state.set_state(States.admin_bc)
    await callback.message.answer("📢 پیام را ارسال کنید:")

@router.message(States.admin_bc)
async def adm_send_bc(message: Message, state: FSMContext):
    users = db.get_users()
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
# 🚀 اجرا
# ==============================================

@router.errors()
async def error_handler(update, exception):
    logger.error(f"خطا: {exception}")
    return True

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 ربات آماده!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
