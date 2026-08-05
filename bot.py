import asyncio
import logging
import sqlite3
import random
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from decimal import Decimal

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, ParseMode
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ============================================================================
# Configuration
# ============================================================================

BOT_TOKEN = "8943333410:AAFaCwNKDQDk8bwxQcg1EUSHl7lkhHzuWWw"
OWNER_ID = 7548145568
CARD_NUMBER = "6062561009737464"
CARD_OWNER = "مجاور"
BOT_USERNAME = "shartbist_bot"
MIN_WITHDRAWAL = 100_000
MIN_DEPOSIT = 10_000
REFERRAL_REWARD = 10_000

# Game odds (with house edge)
DICE_ODDS = 5.0
RPS_ODDS = 1.8

BOWLING_ODDS = {
    "افتادن ۱ پین": 1.8,
    "افتادن ۲ پین": 2.2,
    "افتادن ۳ پین": 2.8,
    "نیمی از پین‌ها": 3.0,
    "اسپیر": 4.0,
    "استرایک": 6.0,
    "خارج از لاین": 2.0,
}

LOTTERY_ODDS = {
    "🍇🍇🍇": 2.0,
    "🍒🍒🍒": 3.0,
    "🍋🍋🍋": 4.0,
    "⭐⭐⭐": 5.0,
    "💎💎💎": 8.0,
    "7️⃣7️⃣7️⃣": 12.0,
    "🍀🍀🍀": 20.0,
}

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# Database
# ============================================================================

DB_PATH = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db()
    c = conn.cursor()
    
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            wallet INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            level TEXT DEFAULT '🥉 برنزی',
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            referral_earnings INTEGER DEFAULT 0,
            total_deposits INTEGER DEFAULT 0,
            total_withdrawals INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            is_muted BOOLEAN DEFAULT 0,
            last_activity TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            admin_note TEXT
        )
    """)
    
    # Games table
    c.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            bet_amount INTEGER,
            odds REAL,
            user_choice TEXT,
            result TEXT,
            outcome TEXT,
            profit INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Deposits table
    c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            receipt_photo_id TEXT,
            status TEXT DEFAULT 'pending',
            admin_comment TEXT,
            admin_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    
    # Withdrawals table
    c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            card_number TEXT,
            card_owner TEXT,
            status TEXT DEFAULT 'pending',
            admin_comment TEXT,
            admin_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    
    # Transactions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            status TEXT DEFAULT 'completed',
            description TEXT,
            admin_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Referrals table
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            reward INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Settings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert default settings
    default_settings = {
        'card_number': CARD_NUMBER,
        'card_owner': CARD_OWNER,
        'min_withdrawal': str(MIN_WITHDRAWAL),
        'min_deposit': str(MIN_DEPOSIT),
        'referral_reward': str(REFERRAL_REWARD),
        'bot_name': 'ربات شرط‌بندی',
        'maintenance_mode': '0',
        'dice_odds': str(DICE_ODDS),
        'rps_odds': str(RPS_ODDS),
        'bowling_odds': json.dumps(BOWLING_ODDS),
        'lottery_odds': json.dumps(LOTTERY_ODDS),
    }
    for key, value in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

# ============================================================================
# Database Functions
# ============================================================================

def get_user(telegram_id: int) -> Optional[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(telegram_id: int, username: str = None, first_name: str = None, 
                last_name: str = None, referred_by: int = None) -> Dict:
    conn = get_db()
    c = conn.cursor()
    referral_code = f"REF{telegram_id}{datetime.now().strftime('%Y%m%d')}"
    c.execute("""
        INSERT INTO users (telegram_id, username, first_name, last_name, 
                          referral_code, referred_by, last_activity)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (telegram_id, username, first_name, last_name, referral_code, referred_by))
    conn.commit()
    conn.close()
    return get_user(telegram_id)

def update_wallet(telegram_id: int, amount: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET wallet = wallet + ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
              (amount, telegram_id))
    conn.commit()
    conn.close()

def update_stats(telegram_id: int, win: bool):
    conn = get_db()
    c = conn.cursor()
    if win:
        c.execute("UPDATE users SET wins = wins + 1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                  (telegram_id,))
    else:
        c.execute("UPDATE users SET losses = losses + 1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                  (telegram_id,))
    conn.commit()
    conn.close()

def get_user_level(wallet: int) -> str:
    if wallet >= 5_000_000:
        return "👑 افسانه‌ای"
    elif wallet >= 1_000_000:
        return "💎 الماسی"
    elif wallet >= 500_000:
        return "🥇 طلایی"
    elif wallet >= 100_000:
        return "🥈 نقره‌ای"
    else:
        return "🥉 برنزی"

def get_top_users(limit: int = 10) -> List[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT telegram_id, username, first_name, wallet, wins, losses
        FROM users 
        WHERE is_banned = 0
        ORDER BY wallet DESC 
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_game(user_id: int, game_type: str, bet: int, odds: float,
              user_choice: str, result: str, outcome: str, profit: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO games (user_id, game_type, bet_amount, odds, 
                          user_choice, result, outcome, profit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, game_type, bet, odds, user_choice, result, outcome, profit))
    conn.commit()
    conn.close()

def get_user_games(user_id: int, limit: int = 5) -> List[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM games 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def create_deposit(user_id: int, amount: int, photo_id: str) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO deposits (user_id, amount, receipt_photo_id)
        VALUES (?, ?, ?)
    """, (user_id, amount, photo_id))
    deposit_id = c.lastrowid
    conn.commit()
    conn.close()
    return deposit_id

def get_pending_deposits() -> List[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM deposits WHERE status = 'pending' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def approve_deposit(deposit_id: int, admin_id: int = None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE deposits SET status = 'approved', admin_id = ?, 
        processed_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (admin_id, deposit_id))
    c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (deposit_id,))
    row = c.fetchone()
    if row:
        update_wallet(row['user_id'], row['amount'])
        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("""
            INSERT INTO transactions (user_id, amount, type, description, admin_id)
            VALUES (?, ?, 'deposit', ?, ?)
        """, (row['user_id'], row['amount'], f"واریز #{deposit_id}", admin_id))
        conn2.commit()
        conn2.close()
    conn.commit()
    conn.close()

def reject_deposit(deposit_id: int, comment: str = None, admin_id: int = None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE deposits SET status = 'rejected', admin_comment = ?, 
        admin_id = ?, processed_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (comment, admin_id, deposit_id))
    conn.commit()
    conn.close()

def create_withdrawal(user_id: int, amount: int, card_number: str, card_owner: str) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO withdrawals (user_id, amount, card_number, card_owner)
        VALUES (?, ?, ?, ?)
    """, (user_id, amount, card_number, card_owner))
    withdrawal_id = c.lastrowid
    conn.commit()
    conn.close()
    return withdrawal_id

def get_pending_withdrawals() -> List[Dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def approve_withdrawal(withdrawal_id: int, admin_id: int = None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE withdrawals SET status = 'approved', admin_id = ?, 
        processed_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (admin_id, withdrawal_id))
    c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (withdrawal_id,))
    row = c.fetchone()
    if row:
        update_wallet(row['user_id'], -row['amount'])
        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("""
            INSERT INTO transactions (user_id, amount, type, description, admin_id)
            VALUES (?, ?, 'withdrawal', ?, ?)
        """, (row['user_id'], -row['amount'], f"برداشت #{withdrawal_id}", admin_id))
        conn2.commit()
        conn2.close()
    conn.commit()
    conn.close()

def reject_withdrawal(withdrawal_id: int, comment: str = None, admin_id: int = None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE withdrawals SET status = 'rejected', admin_comment = ?, 
        admin_id = ?, processed_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (comment, admin_id, withdrawal_id))
    conn.commit()
    conn.close()

def check_referral_reward(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM games WHERE user_id = ?", (user_id,))
    count = c.fetchone()[0]
    if count > 1:
        conn.close()
        return
    
    c.execute("SELECT referred_by FROM users WHERE telegram_id = ?", (user_id,))
    row = c.fetchone()
    if not row or not row[0]:
        conn.close()
        return
    
    referrer_id = row[0]
    c.execute("SELECT COUNT(*) FROM referrals WHERE referred_id = ?", (user_id,))
    if c.fetchone()[0] > 0:
        conn.close()
        return
    
    reward = REFERRAL_REWARD
    update_wallet(referrer_id, reward)
    
    c.execute("""
        UPDATE users SET referral_count = referral_count + 1, 
        referral_earnings = referral_earnings + ? 
        WHERE telegram_id = ?
    """, (reward, referrer_id))
    
    c.execute("""
        INSERT INTO referrals (referrer_id, referred_id, reward, status)
        VALUES (?, ?, ?, 'completed')
    """, (referrer_id, user_id, reward))
    
    conn.commit()
    conn.close()

# ============================================================================
# Telegram Bot Setup
# ============================================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================================================
# States
# ============================================================================

class GameStates(StatesGroup):
    SELECT_GAME = State()
    SELECT_OUTCOME = State()
    SELECT_BET = State()
    CONFIRM_BET = State()

class DepositStates(StatesGroup):
    SELECT_AMOUNT = State()
    CUSTOM_AMOUNT = State()
    SEND_RECEIPT = State()

class WithdrawalStates(StatesGroup):
    SELECT_AMOUNT = State()
    ENTER_CARD = State()
    ENTER_CARD_OWNER = State()
    CONFIRM = State()

# ============================================================================
# Keyboards
# ============================================================================

def main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("🎮 شروع بازی", callback_data="games")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="profile")],
        [InlineKeyboardButton("🎯 مأموریت‌ها", callback_data="missions")],
        [InlineKeyboardButton("💳 افزایش موجودی", callback_data="deposit")],
        [InlineKeyboardButton("💸 برداشت موجودی", callback_data="withdraw")],
        [InlineKeyboardButton("🏆 لیدربورد", callback_data="leaderboard")],
        [InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="referral")],
        [InlineKeyboardButton("🎧 پشتیبانی", callback_data="support")],
        [InlineKeyboardButton("👑 مدیریت", callback_data="admin_panel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def games_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("🎲 تاس", callback_data="game_dice")],
        [InlineKeyboardButton("🎳 بولینگ", callback_data="game_bowling")],
        [InlineKeyboardButton("🎰 قرعه", callback_data="game_lottery")],
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game_rps")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def game_outcome_keyboard(game_type: str):
    buttons = []
    if game_type == "dice":
        for i in range(1, 7):
            buttons.append([InlineKeyboardButton(f"🎲 عدد {i}", callback_data=f"outcome_{i}")])
    elif game_type == "bowling":
        for outcome in BOWLING_ODDS.keys():
            odds = BOWLING_ODDS[outcome]
            buttons.append([InlineKeyboardButton(f"🎳 {outcome} ({odds}x)", callback_data=f"outcome_{outcome}")])
    elif game_type == "lottery":
        for outcome in LOTTERY_ODDS.keys():
            odds = LOTTERY_ODDS[outcome]
            buttons.append([InlineKeyboardButton(f"🎰 {outcome} ({odds}x)", callback_data=f"outcome_{outcome}")])
    elif game_type == "rps":
        buttons = [
            [InlineKeyboardButton("✊ سنگ", callback_data="outcome_سنگ")],
            [InlineKeyboardButton("✋ کاغذ", callback_data="outcome_کاغذ")],
            [InlineKeyboardButton("✌️ قیچی", callback_data="outcome_قیچی")],
        ]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def bet_amount_keyboard():
    amounts = [10_000, 50_000, 100_000, 150_000, 300_000, 500_000, 
               750_000, 1_000_000, 2_500_000, 5_000_000]
    buttons = []
    row = []
    for i, amt in enumerate(amounts):
        row.append(InlineKeyboardButton(f"{amt:,} تومان", callback_data=f"bet_{amt}"))
        if (i + 1) % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("💰 مبلغ دلخواه", callback_data="bet_custom")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_bet_keyboard():
    buttons = [
        [InlineKeyboardButton("✅ تایید و شروع", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ لغو", callback_data="confirm_no")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def deposit_amount_keyboard():
    amounts = [10_000, 20_000, 50_000, 100_000, 250_000, 
               500_000, 1_000_000, 2_000_000, 5_000_000]
    buttons = []
    row = []
    for i, amt in enumerate(amounts):
        row.append(InlineKeyboardButton(f"{amt:,} تومان", callback_data=f"deposit_{amt}"))
        if (i + 1) % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✍ مبلغ دلخواه", callback_data="deposit_custom")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("📊 داشبورد", callback_data="admin_dashboard")],
        [InlineKeyboardButton("💳 مدیریت واریز", callback_data="admin_deposits")],
        [InlineKeyboardButton("💸 مدیریت برداشت", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🎮 مدیریت بازی‌ها", callback_data="admin_games")],
        [InlineKeyboardButton("📈 گزارشات مالی", callback_data="admin_reports")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_action_keyboard(item_id: int, action_type: str):
    buttons = [
        [InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{action_type}_{item_id}")],
        [InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{action_type}_{item_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ============================================================================
# Game Engine
# ============================================================================

def play_dice(prediction: int) -> Dict:
    result = random.randint(1, 6)
    win = (result == prediction)
    return {
        'result': f"عدد {result}",
        'odds': DICE_ODDS if win else 0,
        'win': win,
    }

def play_bowling(prediction: str) -> Dict:
    outcomes = list(BOWLING_ODDS.keys())
    weights = [40, 20, 15, 10, 8, 5, 2]
    result = random.choices(outcomes, weights=weights)[0]
    win = (result == prediction)
    return {
        'result': result,
        'odds': BOWLING_ODDS.get(result, 2.0) if win else 0,
        'win': win,
    }

def play_lottery(prediction: str) -> Dict:
    outcomes = list(LOTTERY_ODDS.keys())
    weights = [30, 25, 20, 12, 8, 3, 2]
    result = random.choices(outcomes, weights=weights)[0]
    win = (result == prediction)
    return {
        'result': result,
        'odds': LOTTERY_ODDS.get(result, 3.0) if win else 0,
        'win': win,
    }

def play_rps(user_choice: str) -> Dict:
    choices = ["سنگ", "کاغذ", "قیچی"]
    if random.random() < 0.55:
        if user_choice == "سنگ":
            bot_choice = "کاغذ"
        elif user_choice == "کاغذ":
            bot_choice = "قیچی"
        else:
            bot_choice = "سنگ"
    else:
        bot_choice = random.choice(choices)
    
    if bot_choice == user_choice:
        return {'result': 'مساوی', 'win': False, 'odds': 0, 'bot_choice': bot_choice}
    elif (user_choice == "سنگ" and bot_choice == "قیچی") or \
         (user_choice == "کاغذ" and bot_choice == "سنگ") or \
         (user_choice == "قیچی" and bot_choice == "کاغذ"):
        return {'result': f"ربات: {bot_choice}", 'win': True, 'odds': RPS_ODDS, 'bot_choice': bot_choice}
    else:
        return {'result': f"ربات: {bot_choice}", 'win': False, 'odds': 0, 'bot_choice': bot_choice}

# ============================================================================
# Handlers
# ============================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    db_user = get_user(user.id)
    if not db_user:
        referred_by = None
        if message.text and 'ref_' in message.text:
            try:
                ref_code = message.text.split('ref_')[1]
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT telegram_id FROM users WHERE referral_code = ?", (ref_code,))
                row = c.fetchone()
                conn.close()
                if row:
                    referred_by = row[0]
            except:
                pass
        create_user(user.id, user.username, user.first_name, user.last_name, referred_by)
    
    await message.answer(
        "🎮 <b>به ربات بازی خوش آمدید!</b>\n\n"
        "در این ربات می‌توانید در بازی‌های مختلف شرکت کنید،\n"
        "موجودی خود را افزایش دهید، دوستانتان را دعوت کنید\n"
        "و در لیدربورد رقابت کنید.\n\n"
        "<b>لطفاً یکی از گزینه‌های زیر را انتخاب کنید:</b>",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data == "menu")
async def callback_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🎮 <b>منوی اصلی</b>\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data == "games")
async def callback_games(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🎮 <b>بازی‌های موجود</b>\n\nلطفاً یکی از بازی‌های زیر را انتخاب کنید:",
        reply_markup=games_menu_keyboard()
    )
    await state.set_state(GameStates.SELECT_GAME)

@dp.callback_query(F.data.startswith("game_"))
async def callback_game_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    game_type = callback.data.replace("game_", "")
    await state.update_data(game_type=game_type)
    
    game_names = {
        "dice": "تاس 🎲",
        "bowling": "بولینگ 🎳",
        "lottery": "قرعه 🎰",
        "rps": "سنگ کاغذ قیچی ✊"
    }
    
    await callback.message.edit_text(
        f"🎯 <b>مرحله اول: پیش‌بینی نتیجه</b>\n\n"
        f"بازی: {game_names.get(game_type, game_type)}\n\n"
        f"لطفاً نتیجه‌ای که فکر می‌کنید رخ خواهد داد را انتخاب کنید:\n\n"
        f"⚠️ شما فقط در صورتی برنده می‌شوید که دقیقاً همین نتیجه رخ دهد!",
        reply_markup=game_outcome_keyboard(game_type)
    )
    await state.set_state(GameStates.SELECT_OUTCOME)

@dp.callback_query(F.data.startswith("outcome_"), GameStates.SELECT_OUTCOME)
async def callback_outcome_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    outcome = callback.data.replace("outcome_", "")
    await state.update_data(outcome=outcome)
    
    user_data = await state.get_data()
    game_type = user_data.get('game_type')
    
    odds = 0
    if game_type == "dice":
        odds = DICE_ODDS
    elif game_type == "bowling":
        odds = BOWLING_ODDS.get(outcome, 2.0)
    elif game_type == "lottery":
        odds = LOTTERY_ODDS.get(outcome, 3.0)
    elif game_type == "rps":
        odds = RPS_ODDS
    
    await callback.message.edit_text(
        f"🎯 <b>مرحله دوم: تعیین مبلغ شرط</b>\n\n"
        f"🎮 بازی: {game_type}\n"
        f"🎯 انتخاب شما: {outcome}\n"
        f"📈 ضریب: {odds}x\n"
        f"💵 حداقل شرط: ۱۰,۰۰۰ تومان\n\n"
        f"لطفاً مبلغ شرط خود را انتخاب کنید:",
        reply_markup=bet_amount_keyboard()
    )
    await state.set_state(GameStates.SELECT_BET)

@dp.callback_query(F.data.startswith("bet_"), GameStates.SELECT_BET)
async def callback_bet_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bet_amount = int(callback.data.replace("bet_", ""))
    
    user = get_user(callback.from_user.id)
    if not user or user['wallet'] < bet_amount:
        await callback.message.edit_text(
            "❌ <b>موجودی شما کافی نیست!</b>\n\n"
            "لطفاً ابتدا حساب خود را شارژ نمایید.",
            reply_markup=deposit_amount_keyboard()
        )
        return
    
    await state.update_data(bet_amount=bet_amount)
    user_data = await state.get_data()
    
    await callback.message.edit_text(
        f"📋 <b>تایید نهایی شرط</b>\n\n"
        f"لطفاً اطلاعات زیر را بررسی کنید:\n\n"
        f"🎮 بازی: {user_data['game_type']}\n"
        f"🎯 پیش‌بینی: {user_data['outcome']}\n"
        f"💰 مبلغ شرط: {bet_amount:,} تومان\n\n"
        f"آیا از ثبت این شرط اطمینان دارید؟",
        reply_markup=confirm_bet_keyboard()
    )
    await state.set_state(GameStates.CONFIRM_BET)

@dp.callback_query(F.data == "bet_custom", GameStates.SELECT_BET)
async def callback_bet_custom(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "💰 <b>مبلغ دلخواه</b>\n\n"
        "لطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\n"
        "مثال: ۲۵۰,۰۰۰"
    )

@dp.message(StateFilter(GameStates.SELECT_BET))
async def message_bet_custom(message: Message, state: FSMContext):
    try:
        amount_str = message.text.replace(',', '').strip()
        bet_amount = int(amount_str)
        
        if bet_amount < 10_000:
            await message.answer("❌ حداقل مبلغ شرط ۱۰,۰۰۰ تومان است.")
            return
        
        user = get_user(message.from_user.id)
        if not user or user['wallet'] < bet_amount:
            await message.answer(
                "❌ <b>موجودی شما کافی نیست!</b>\n\n"
                "لطفاً ابتدا حساب خود را شارژ نمایید.",
                reply_markup=deposit_amount_keyboard()
            )
            return
        
        await state.update_data(bet_amount=bet_amount)
        user_data = await state.get_data()
        
        await message.answer(
            f"📋 <b>تایید نهایی شرط</b>\n\n"
            f"لطفاً اطلاعات زیر را بررسی کنید:\n\n"
            f"🎮 بازی: {user_data['game_type']}\n"
            f"🎯 پیش‌بینی: {user_data['outcome']}\n"
            f"💰 مبلغ شرط: {bet_amount:,} تومان\n\n"
            f"آیا از ثبت این شرط اطمینان دارید؟",
            reply_markup=confirm_bet_keyboard()
        )
        await state.set_state(GameStates.CONFIRM_BET)
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")

@dp.callback_query(F.data.startswith("confirm_"), GameStates.CONFIRM_BET)
async def callback_confirm_bet(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    action = callback.data.replace("confirm_", "")
    
    if action == "no":
        await callback.message.edit_text("❌ شرط لغو شد.", reply_markup=games_menu_keyboard())
        await state.clear()
        return
    
    user_data = await state.get_data()
    game_type = user_data['game_type']
    outcome = user_data['outcome']
    bet_amount = user_data['bet_amount']
    user_id = callback.from_user.id
    
    update_wallet(user_id, -bet_amount)
    
    if game_type == "dice":
        result = play_dice(int(outcome))
    elif game_type == "bowling":
        result = play_bowling(outcome)
    elif game_type == "lottery":
        result = play_lottery(outcome)
    elif game_type == "rps":
        result = play_rps(outcome)
    else:
        await callback.message.edit_text("❌ خطا در اجرای بازی!", reply_markup=main_menu_keyboard())
        await state.clear()
        return
    
    if result['win']:
        profit = int(bet_amount * result['odds']) - bet_amount
        update_wallet(user_id, bet_amount + profit)
        update_stats(user_id, True)
    else:
        profit = -bet_amount
        update_stats(user_id, False)
    
    save_game(user_id, game_type, bet_amount, result['odds'],
              outcome, str(result['result']), 'win' if result['win'] else 'loss', profit)
    
    check_referral_reward(user_id)
    
    user = get_user(user_id)
    if result['win']:
        await callback.message.edit_text(
            f"🎉 <b>تبریک!</b>\n\n"
            f"شما برنده شدید!\n\n"
            f"🎮 بازی: {game_type}\n"
            f"🎯 انتخاب شما: {outcome}\n"
            f"🎲 نتیجه نهایی: {result['result']}\n"
            f"📈 ضریب: {result['odds']}x\n"
            f"💵 مبلغ شرط: {bet_amount:,} تومان\n"
            f"🏆 جایزه: {profit:,} تومان\n"
            f"💰 موجودی جدید: {user['wallet']:,} تومان",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            f"😔 <b>این بار شانس با شما یار نبود.</b>\n\n"
            f"🎮 بازی: {game_type}\n"
            f"🎯 انتخاب شما: {outcome}\n"
            f"🎲 نتیجه نهایی: {result['result']}\n"
            f"💵 مبلغ شرط: {bet_amount:,} تومان\n"
            f"💰 موجودی فعلی: {user['wallet']:,} تومان\n\n"
            f"برای شما آرزوی موفقیت در بازی بعدی داریم.",
            reply_markup=main_menu_keyboard()
        )
    await state.clear()

@dp.callback_query(F.data == "profile")
async def callback_profile(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ کاربر یافت نشد!", reply_markup=main_menu_keyboard())
        return
    
    stats = get_user_games(callback.from_user.id, 5)
    games_text = "\n".join([
        f"🎮 {g['game_type']} | {g['bet_amount']:,} | {g['result']} | {g['profit']:,}"
        for g in stats
    ]) if stats else "هیچ بازی ثبت نشده"
    
    level = get_user_level(user['wallet'])
    total_games = user['wins'] + user['losses']
    win_rate = (user['wins'] / total_games * 100) if total_games > 0 else 0
    
    await callback.message.edit_text(
        f"<b>👤 حساب کاربری</b>\n\n"
        f"🆔 شناسه: {user['telegram_id']}\n"
        f"👤 نام: {user['first_name'] or 'نامشخص'}\n"
        f"🏅 سطح: {level}\n"
        f"💰 موجودی: {user['wallet']:,} تومان\n\n"
        f"✅ تعداد برد: {user['wins']}\n"
        f"❌ تعداد باخت: {user['losses']}\n"
        f"📊 درصد برد: {win_rate:.1f}%\n"
        f"🎮 تعداد بازی: {total_games}\n"
        f"👥 زیرمجموعه: {user['referral_count']}\n\n"
        f"📋 <b>آخرین بازی‌ها:</b>\n{games_text}",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query(F.data == "deposit")
async def callback_deposit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "💳 <b>افزایش موجودی</b>\n\n"
        "برای شارژ حساب، یکی از مبالغ زیر را انتخاب کنید:",
        reply_markup=deposit_amount_keyboard()
    )
    await state.set_state(DepositStates.SELECT_AMOUNT)

@dp.callback_query(F.data.startswith("deposit_"), DepositStates.SELECT_AMOUNT)
async def callback_deposit_amount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    amount = int(callback.data.replace("deposit_", ""))
    await state.update_data(deposit_amount=amount)
    
    await callback.message.edit_text(
        f"💳 <b>اطلاعات پرداخت</b>\n\n"
        f"💵 مبلغ قابل پرداخت: {amount:,} تومان\n"
        f"🏦 شماره کارت: <code>{CARD_NUMBER}</code>\n"
        f"👤 نام صاحب کارت: {CARD_OWNER}\n\n"
        f"📝 لطفاً پس از واریز، تصویر رسید پرداخت را ارسال نمایید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("📷 ارسال رسید", callback_data="deposit_send_receipt")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]
        ])
    )
    await state.set_state(DepositStates.SEND_RECEIPT)

@dp.callback_query(F.data == "deposit_custom", DepositStates.SELECT_AMOUNT)
async def callback_deposit_custom(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        f"✍ <b>مبلغ دلخواه</b>\n\n"
        f"لطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\n"
        f"حداقل مبلغ: {MIN_DEPOSIT:,} تومان"
    )
    await state.set_state(DepositStates.CUSTOM_AMOUNT)

@dp.message(DepositStates.CUSTOM_AMOUNT)
async def message_deposit_custom(message: Message, state: FSMContext):
    try:
        amount_str = message.text.replace(',', '').strip()
        amount = int(amount_str)
        if amount < MIN_DEPOSIT:
            await message.answer(f"❌ حداقل مبلغ واریز {MIN_DEPOSIT:,} تومان است.")
            return
        await state.update_data(deposit_amount=amount)
        await message.answer(
            f"💳 <b>اطلاعات پرداخت</b>\n\n"
            f"💵 مبلغ قابل پرداخت: {amount:,} تومان\n"
            f"🏦 شماره کارت: <code>{CARD_NUMBER}</code>\n"
            f"👤 نام صاحب کارت: {CARD_OWNER}\n\n"
            f"📝 لطفاً پس از واریز، تصویر رسید پرداخت را ارسال نمایید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("📷 ارسال رسید", callback_data="deposit_send_receipt")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]
            ])
        )
        await state.set_state(DepositStates.SEND_RECEIPT)
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")

@dp.callback_query(F.data == "deposit_send_receipt", DepositStates.SEND_RECEIPT)
async def callback_deposit_receipt(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📷 <b>ارسال رسید</b>\n\n"
        "لطفاً تصویر رسید پرداخت خود را ارسال کنید."
    )

@dp.message(F.photo, DepositStates.SEND_RECEIPT)
async def message_deposit_receipt(message: Message, state: FSMContext):
    user_data = await state.get_data()
    amount = user_data.get('deposit_amount')
    if not amount:
        await message.answer("❌ خطا! لطفاً دوباره از منو اقدام کنید.", reply_markup=main_menu_keyboard())
        await state.clear()
        return
    
    photo_id = message.photo[-1].file_id
    deposit_id = create_deposit(message.from_user.id, amount, photo_id)
    
    await message.answer(
        f"✅ <b>رسید شما دریافت شد.</b>\n\n"
        f"درخواست واریز شما با شماره #{deposit_id} ثبت گردید.\n"
        f"پس از تایید توسط ادمین، موجودی شما افزایش خواهد یافت.",
        reply_markup=main_menu_keyboard()
    )
    
    user = get_user(message.from_user.id)
    await bot.send_photo(
        chat_id=OWNER_ID,
        photo=photo_id,
        caption=f"📥 <b>درخواست واریز جدید</b>\n\n"
                f"🔢 شناسه: #{deposit_id}\n"
                f"👤 کاربر: {message.from_user.first_name}\n"
                f"🆔 آیدی: {message.from_user.id}\n"
                f"💰 مبلغ: {amount:,} تومان\n"
                f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        reply_markup=admin_action_keyboard(deposit_id, "deposit")
    )
    await state.clear()

@dp.callback_query(F.data == "withdraw")
async def callback_withdraw(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        f"💸 <b>برداشت موجودی</b>\n\n"
        f"لطفاً مبلغ مورد نظر برای برداشت را وارد کنید:\n"
        f"حداقل مبلغ: {MIN_WITHDRAWAL:,} تومان"
    )
    await state.set_state(WithdrawalStates.SELECT_AMOUNT)

@dp.message(WithdrawalStates.SELECT_AMOUNT)
async def message_withdraw_amount(message: Message, state: FSMContext):
    try:
        amount_str = message.text.replace(',', '').strip()
        amount = int(amount_str)
        if amount < MIN_WITHDRAWAL:
            await message.answer(f"❌ حداقل مبلغ برداشت {MIN_WITHDRAWAL:,} تومان است.")
            return
        
        user = get_user(message.from_user.id)
        if not user or user['wallet'] < amount:
            await message.answer("❌ موجودی شما کافی نیست!")
            return
        
        await state.update_data(withdraw_amount=amount)
        await message.answer(
            "💳 <b>اطلاعات کارت</b>\n\n"
            "لطفاً شماره کارت خود را وارد کنید:"
        )
        await state.set_state(WithdrawalStates.ENTER_CARD)
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")

@dp.message(WithdrawalStates.ENTER_CARD)
async def message_withdraw_card(message: Message, state: FSMContext):
    card_number = message.text.strip().replace('-', '').replace(' ', '')
    if not re.match(r'^\d{16}$', card_number):
        await message.answer("❌ شماره کارت نامعتبر است. لطفاً ۱۶ رقم وارد کنید.")
        return
    await state.update_data(card_number=card_number)
    await message.answer(
        "👤 <b>نام صاحب حساب</b>\n\n"
        "لطفاً نام صاحب حساب را وارد کنید:"
    )
    await state.set_state(WithdrawalStates.ENTER_CARD_OWNER)

@dp.message(WithdrawalStates.ENTER_CARD_OWNER)
async def message_withdraw_card_owner(message: Message, state: FSMContext):
    card_owner = message.text.strip()
    await state.update_data(card_owner=card_owner)
    user_data = await state.get_data()
    
    await message.answer(
        f"📋 <b>تایید درخواست برداشت</b>\n\n"
        f"لطفاً اطلاعات زیر را بررسی کنید:\n\n"
        f"💰 مبلغ: {user_data['withdraw_amount']:,} تومان\n"
        f"💳 شماره کارت: {user_data['card_number']}\n"
        f"👤 نام صاحب حساب: {card_owner}\n\n"
        f"آیا از ثبت این درخواست اطمینان دارید؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("✅ تایید", callback_data="withdraw_confirm")],
            [InlineKeyboardButton("❌ لغو", callback_data="withdraw_cancel")]
        ])
    )
    await state.set_state(WithdrawalStates.CONFIRM)

@dp.callback_query(F.data == "withdraw_confirm", WithdrawalStates.CONFIRM)
async def callback_withdraw_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()
    
    withdrawal_id = create_withdrawal(
        callback.from_user.id,
        user_data['withdraw_amount'],
        user_data['card_number'],
        user_data['card_owner']
    )
    
    update_wallet(callback.from_user.id, -user_data['withdraw_amount'])
    
    await callback.message.edit_text(
        f"✅ <b>درخواست برداشت شما ثبت شد.</b>\n\n"
        f"شماره درخواست: #{withdrawal_id}\n"
        f"مبلغ: {user_data['withdraw_amount']:,} تومان\n\n"
        f"پس از تایید ادمین، مبلغ به حساب شما واریز خواهد شد.",
        reply_markup=main_menu_keyboard()
    )
    
    user = get_user(callback.from_user.id)
    await bot.send_message(
        chat_id=OWNER_ID,
        text=f"📤 <b>درخواست برداشت جدید</b>\n\n"
             f"🔢 شناسه: #{withdrawal_id}\n"
             f"👤 کاربر: {callback.from_user.first_name}\n"
             f"🆔 آیدی: {callback.from_user.id}\n"
             f"💰 مبلغ: {user_data['withdraw_amount']:,} تومان\n"
             f"💳 شماره کارت: {user_data['card_number']}\n"
             f"👤 صاحب حساب: {user_data['card_owner']}\n"
             f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        reply_markup=admin_action_keyboard(withdrawal_id, "withdraw")
    )
    await state.clear()

@dp.callback_query(F.data == "withdraw_cancel", WithdrawalStates.CONFIRM)
async def callback_withdraw_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("❌ درخواست برداشت لغو شد.", reply_markup=main_menu_keyboard())
    await state.clear()

@dp.callback_query(F.data == "leaderboard")
async def callback_leaderboard(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    top_users = get_top_users(10)
    
    if user:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) + 1 FROM users WHERE wallet > ? AND is_banned = 0", (user['wallet'],))
        rank = c.fetchone()[0]
        conn.close()
    else:
        rank = "?"
    
    text = "🏆 <b>لیدربورد</b>\n\n"
    if user:
        text += f"👤 نام شما: {user['first_name'] or 'کاربر'}\n"
        text += f"🏅 سطح: {get_user_level(user['wallet'])}\n"
        text += f"💰 موجودی: {user['wallet']:,} تومان\n"
        text += f"📈 رتبه شما: #{rank}\n\n"
    
    text += "🥇 <b>۱۰ کاربر برتر</b>\n\n"
    for i, u in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
        name = u['username'] or u['first_name'] or f"کاربر {u['telegram_id']}"
        text += f"{medal} {name} — {u['wallet']:,} تومان\n"
    
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())

@dp.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery):
    await callback.answer()
    user = get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ کاربر یافت نشد!", reply_markup=main_menu_keyboard())
        return
    
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user['referral_code']}"
    await callback.message.edit_text(
        f"👥 <b>زیرمجموعه‌گیری</b>\n\n"
        f"دعوت از دوستان و دریافت پاداش!\n\n"
        f"🔗 لینک دعوت اختصاصی:\n<code>{link}</code>\n\n"
        f"🏆 زیرمجموعه‌های فعال: {user['referral_count']} نفر\n"
        f"💰 درآمد کسب شده: {user['referral_earnings']:,} تومان\n\n"
        f"📝 قوانین:\n"
        f"• به ازای هر دوست که از طریق لینک شما وارد شود\n"
        f"• و حداقل یک بازی انجام دهد\n"
        f"• شما {REFERRAL_REWARD:,} تومان پاداش دریافت می‌کنید",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🎧 <b>پشتیبانی</b>\n\n"
        "لطفاً پیام خود را ارسال کنید.\n"
        "پیام شما مستقیماً برای تیم پشتیبانی ارسال خواهد شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]
        ])
    )

@dp.callback_query(F.data == "missions")
async def callback_missions(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🎯 <b>مأموریت‌ها</b>\n\n"
        "🎯 انجام اولین بازی - پاداش: ۵,۰۰۰ تومان\n"
        "🎯 برنده شدن ۳ بازی - پاداش: ۱۵,۰۰۰ تومان\n"
        "🎯 دعوت از یک دوست - پاداش: ۱۰,۰۰۰ تومان\n"
        "🎯 واریز موجودی - پاداش: ۲۰,۰۰۰ تومان",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        await callback.message.edit_text("❌ شما دسترسی به این بخش ندارید.", reply_markup=main_menu_keyboard())
        return
    await callback.message.edit_text(
        "👑 <b>پنل مدیریت</b>\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=admin_menu_keyboard()
    )

@dp.callback_query(F.data == "admin_dashboard")
async def callback_admin_dashboard(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM games")
    total_games = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM deposits WHERE status = 'pending'")
    pending_deposits = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
    pending_withdrawals = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM transactions WHERE type = 'deposit'")
    total_deposits = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE type = 'withdrawal'")
    total_withdrawals = c.fetchone()[0] or 0
    c.execute("SELECT SUM(profit) FROM games")
    total_profit = c.fetchone()[0] or 0
    conn.close()
    
    await callback.message.edit_text(
        f"📊 <b>داشبورد مدیریت</b>\n\n"
        f"👥 تعداد کاربران: {total_users}\n"
        f"🎮 تعداد بازی‌ها: {total_games}\n\n"
        f"💰 کل واریز: {total_deposits:,} تومان\n"
        f"💸 کل برداشت: {total_withdrawals:,} تومان\n"
        f"📈 سود خالص: {total_profit:,} تومان\n\n"
        f"📥 واریز در انتظار: {pending_deposits}\n"
        f"📤 برداشت در انتظار: {pending_withdrawals}",
        reply_markup=admin_menu_keyboard()
    )

@dp.callback_query(F.data == "admin_deposits")
async def callback_admin_deposits(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        return
    
    pending = get_pending_deposits()
    if not pending:
        await callback.message.edit_text("✅ هیچ درخواست واریز در انتظار تایید وجود ندارد.", reply_markup=admin_menu_keyboard())
        return
    
    for dep in pending:
        user = get_user(dep['user_id'])
        await bot.send_photo(
            chat_id=OWNER_ID,
            photo=dep['receipt_photo_id'],
            caption=f"📥 <b>درخواست واریز #{dep['id']}</b>\n\n"
                    f"👤 کاربر: {user['first_name'] or 'کاربر'}\n"
                    f"🆔 آیدی: {dep['user_id']}\n"
                    f"💰 مبلغ: {dep['amount']:,} تومان\n"
                    f"📅 زمان: {dep['created_at']}",
            reply_markup=admin_action_keyboard(dep['id'], "deposit")
        )
    await callback.message.edit_text("📤 لیست درخواست‌های واریز ارسال شد.", reply_markup=admin_menu_keyboard())

@dp.callback_query(F.data == "admin_withdrawals")
async def callback_admin_withdrawals(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        return
    
    pending = get_pending_withdrawals()
    if not pending:
        await callback.message.edit_text("✅ هیچ درخواست برداشت در انتظار تایید وجود ندارد.", reply_markup=admin_menu_keyboard())
        return
    
    for wd in pending:
        user = get_user(wd['user_id'])
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"📤 <b>درخواست برداشت #{wd['id']}</b>\n\n"
                 f"👤 کاربر: {user['first_name'] or 'کاربر'}\n"
                 f"🆔 آیدی: {wd['user_id']}\n"
                 f"💰 مبلغ: {wd['amount']:,} تومان\n"
                 f"💳 شماره کارت: {wd['card_number']}\n"
                 f"👤 صاحب حساب: {wd['card_owner']}\n"
                 f"📅 زمان: {wd['created_at']}",
            reply_markup=admin_action_keyboard(wd['id'], "withdraw")
        )
    await callback.message.edit_text("📤 لیست درخواست‌های برداشت ارسال شد.", reply_markup=admin_menu_keyboard())

@dp.callback_query(F.data == "admin_games")
async def callback_admin_games(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT game_type, COUNT(*) as total, SUM(profit) as profit FROM games GROUP BY game_type")
    stats = c.fetchall()
    conn.close()
    
    text = "🎮 <b>مدیریت بازی‌ها</b>\n\n"
    for stat in stats:
        text += f"{stat['game_type']}\n🎮 تعداد: {stat['total']}\n💰 سود: {stat['profit'] or 0:,} تومان\n---\n"
    
    await callback.message.edit_text(text, reply_markup=admin_menu_keyboard())

@dp.callback_query(F.data == "admin_reports")
async def callback_admin_reports(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'deposit' AND DATE(created_at) = DATE('now')")
    today_deposit = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'withdrawal' AND DATE(created_at) = DATE('now')")
    today_withdrawal = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(profit), 0) FROM games WHERE DATE(created_at) = DATE('now')")
    today_profit = c.fetchone()[0]
    conn.close()
    
    await callback.message.edit_text(
        f"📈 <b>گزارشات مالی</b>\n\n"
        f"📅 <b>امروز</b>\n"
        f"💰 واریز: {today_deposit:,} تومان\n"
        f"💸 برداشت: {today_withdrawal:,} تومان\n"
        f"📊 سود: {today_profit:,} تومان",
        reply_markup=admin_menu_keyboard()
    )

@dp.callback_query(F.data.startswith("admin_"))
async def callback_admin_action(callback: CallbackQuery):
    await callback.answer()
    if callback.from_user.id != OWNER_ID:
        await callback.message.edit_text("❌ دسترسی غیرمجاز!", reply_markup=main_menu_keyboard())
        return
    
    parts = callback.data.split("_")
    action = parts[1]
    action_type = parts[2]
    item_id = int(parts[3])
    
    if action_type == "deposit":
        if action == "approve":
            approve_deposit(item_id, OWNER_ID)
            dep = None
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (item_id,))
            dep = c.fetchone()
            conn.close()
            if dep:
                await bot.send_message(
                    chat_id=dep['user_id'],
                    text=f"✅ <b>واریز شما تایید شد!</b>\n\n"
                         f"💰 مبلغ: {dep['amount']:,} تومان\n"
                         f"💵 موجودی جدید: {get_user(dep['user_id'])['wallet']:,} تومان\n\n"
                         f"با تشکر از شما."
                )
            await callback.message.edit_text(f"✅ واریز #{item_id} تایید شد.", reply_markup=admin_menu_keyboard())
        else:
            reject_deposit(item_id, "رد شده توسط ادمین", OWNER_ID)
            dep = None
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (item_id,))
            dep = c.fetchone()
            conn.close()
            if dep:
                await bot.send_message(
                    chat_id=dep['user_id'],
                    text=f"❌ <b>واریز شما رد شد.</b>\n\n"
                         f"در صورت نیاز با پشتیبانی تماس بگیرید."
                )
            await callback.message.edit_text(f"❌ واریز #{item_id} رد شد.", reply_markup=admin_menu_keyboard())
    
    elif action_type == "withdraw":
        if action == "approve":
            approve_withdrawal(item_id, OWNER_ID)
            wd = None
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (item_id,))
            wd = c.fetchone()
            conn.close()
            if wd:
                await bot.send_message(
                    chat_id=wd['user_id'],
                    text=f"✅ <b>درخواست برداشت شما تایید شد!</b>\n\n"
                         f"💰 مبلغ: {wd['amount']:,} تومان\n\n"
                         f"به زودی به حساب شما واریز خواهد شد."
                )
            await callback.message.edit_text(f"✅ برداشت #{item_id} تایید شد.", reply_markup=admin_menu_keyboard())
        else:
            reject_withdrawal(item_id, "رد شده توسط ادمین", OWNER_ID)
            wd = None
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (item_id,))
            wd = c.fetchone()
            conn.close()
            if wd:
                await bot.send_message(
                    chat_id=wd['user_id'],
                    text=f"❌ <b>درخواست برداشت شما رد شد.</b>\n\n"
                         f"در صورت نیاز با پشتیبانی تماس بگیرید."
                )
            await callback.message.edit_text(f"❌ برداشت #{item_id} رد شد.", reply_markup=admin_menu_keyboard())

# ============================================================================
# Error Handler
# ============================================================================

@dp.error()
async def error_handler(event: Any, context: Dict):
    logger.error(f"Error: {context.get('exception')}")
    if hasattr(event, 'message') and event.message:
        await event.message.answer(
            "❌ <b>خطا!</b>\n\n"
            "مشکلی در پردازش درخواست شما به وجود آمد.\n"
            "لطفاً مجدداً تلاش کنید."
        )
    await bot.send_message(
        chat_id=OWNER_ID,
        text=f"❌ <b>خطا در ربات</b>\n\n{str(context.get('exception'))}"
    )

# ============================================================================
# Main
# ============================================================================

async def main():
    init_database()
    logger.info("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
