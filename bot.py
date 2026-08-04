# ==============================================
# ربات شرط‌بندی و کازینو تلگرام
# توسعه داده شده با aiogram 3.x و SQLite
# شانس برد کاربران: ~۲۰٪
# ==============================================

import asyncio
import logging
import sqlite3
import random
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    PreCheckoutQuery, Message, CallbackQuery,
    InputMediaPhoto, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.enums import ParseMode, ChatAction

# ==============================================
# تنظیمات اولیه
# ==============================================

# توکن و اطلاعات از متغیرهای محیطی Railway
BOT_TOKEN = os.getenv("BOT_TOKEN", "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7548145568"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "09158029769")

# قیمت‌های پیش‌فرض بازی‌ها
DEFAULT_GAME_PRICES = {
    "rps": 100,           # سنگ کاغذ قیچی
    "football": 200,      # فوتبال
    "basketball": 200,    # بسکتبال
    "dice": 500,          # تاس
    "darts": 300,         # دارت
    "bowling": 400,       # بولینگ
    "lottery": 1000       # قرعه‌کشی
}

# پکیج‌های استارز
STAR_PACKAGES = {
    50: 1000,
    100: 2500,
    250: 7000,
    500: 15000,
    1000: 35000
}

# اطلاعات کارت به کارت
ADMIN_CARD_NUMBER = "6062561009737464"
ADMIN_CARD_HOLDER = "فاطمه مجاور"

# ==============================================
# تنظیم شانس‌های برد (حدود ۲۰٪)
# ==============================================

# شانس برد در هر بازی
WIN_CHANCES = {
    "rps": 0.20,          # سنگ کاغذ قیچی: ۲۰٪ برد
    "football": 0.20,     # فوتبال: ۲۰٪ برد
    "basketball_2pts": 0.30,  # بسکتبال ۲ امتیازی: ۳۰٪
    "basketball_3pts": 0.15,  # بسکتبال ۳ امتیازی: ۱۵٪
    "basketball_dunk": 0.25,  # بسکتبال دانک: ۲۵٪
    "dice": 0.16,         # تاس: ۱۶٪ (۱ از ۶)
    "darts_bullseye": 0.05,   # دارت مرکز: ۵٪
    "darts_20": 0.15,     # دارت حلقه ۲۰: ۱۵٪
    "darts_15": 0.25,     # دارت حلقه ۱۵: ۲۵٪
    "darts_10": 0.35,     # دارت حلقه ۱۰: ۳۵٪
    "bowling_straight": 0.20,    # بولینگ مستقیم: ۲۰٪
    "bowling_curve": 0.22,       # بولینگ منحنی: ۲۲٪
    "bowling_power": 0.25,       # بولینگ قدرتی: ۲۵٪
    "lottery": 0.10       # قرعه‌کشی: ۱۰٪
}

# ضرایب جایزه
PRIZE_MULTIPLIERS = {
    "rps": 1.5,
    "football": 1.8,
    "basketball_2pts": 1.3,
    "basketball_3pts": 2.5,
    "basketball_dunk": 1.2,
    "dice": 4,
    "darts_bullseye": 8,
    "darts_20": 3,
    "darts_15": 2,
    "darts_10": 1.5,
    "bowling_straight": 1.8,
    "bowling_curve": 2,
    "bowling_power": 2.5,
    "lottery": 10
}

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
logger = logging.getLogger(__name__)

# ==============================================
# مدیریت پایگاه داده
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
            logger.error(f"خطا در عملیات دیتابیس: {e}")
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """ایجاد جداول پایگاه داده"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    balance INTEGER DEFAULT 0,
                    total_deposit INTEGER DEFAULT 0,
                    total_withdraw INTEGER DEFAULT 0,
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
                    status TEXT DEFAULT 'completed',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_id INTEGER,
                    reference_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS card_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER DEFAULT 0,
                    receipt_message_id INTEGER,
                    receipt_chat_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_by INTEGER,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_settings (
                    game_name TEXT PRIMARY KEY,
                    price INTEGER DEFAULT 100,
                    is_active BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_locks (
                    user_id INTEGER PRIMARY KEY,
                    game_name TEXT,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    user_id INTEGER,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # درج تنظیمات پیش‌فرض
            for game, price in DEFAULT_GAME_PRICES.items():
                cursor.execute('''
                    INSERT OR IGNORE INTO game_settings (game_name, price)
                    VALUES (?, ?)
                ''', (game, price))
            
            # اضافه کردن ادمین اصلی
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, is_admin)
                VALUES (?, TRUE)
            ''', (ADMIN_USER_ID,))
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('new_user', ?, 'کاربر جدید ثبت نام کرد')
            ''', (user_id,))
    
    def update_balance(self, user_id: int, amount: int, transaction_type: str, description: str, admin_id: int = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, user_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description, admin_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, transaction_type, amount, description, admin_id))
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('transaction', ?, ?)
            ''', (user_id, f"{transaction_type}: {amount} سکه - {description}"))
    
    def get_user_balance(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user['balance'] if user else 0
    
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
    
    def get_game_price(self, game_name: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT price FROM game_settings WHERE game_name = ?", (game_name,))
            result = cursor.fetchone()
            return result['price'] if result else DEFAULT_GAME_PRICES.get(game_name, 100)
    
    def set_game_price(self, game_name: str, price: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE game_settings 
                SET price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE game_name = ?
            ''', (price, game_name))
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('update_game_price', ?, ?)
            ''', (ADMIN_USER_ID, f"قیمت بازی {game_name} به {price} سکه تغییر یافت"))
    
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
    
    def create_card_request(self, user_id: int, amount: int, receipt_message_id: int, receipt_chat_id: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO card_requests (user_id, amount, receipt_message_id, receipt_chat_id)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount, receipt_message_id, receipt_chat_id))
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('card_request', ?, ?)
            ''', (user_id, f"درخواست واریز {amount} سکه"))
            return cursor.lastrowid
    
    def get_pending_requests(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT cr.*, u.username, u.first_name
                FROM card_requests cr
                JOIN users u ON cr.user_id = u.user_id
                WHERE cr.status = 'pending'
                ORDER BY cr.timestamp DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def process_card_request(self, request_id: int, admin_id: int, approved: bool):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if approved:
                cursor.execute("SELECT * FROM card_requests WHERE id = ?", (request_id,))
                request = cursor.fetchone()
                if request:
                    self.update_balance(
                        request['user_id'], 
                        request['amount'], 
                        'deposit', 
                        f'واریز کارت به کارت - درخواست #{request_id}',
                        admin_id
                    )
                    cursor.execute('''
                        UPDATE card_requests 
                        SET status = 'approved', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (admin_id, request_id))
            else:
                cursor.execute('''
                    UPDATE card_requests 
                    SET status = 'rejected', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, request_id))
            action = 'card_approved' if approved else 'card_rejected'
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES (?, ?, ?)
            ''', (action, admin_id, f"درخواست #{request_id} {'تایید' if approved else 'رد'} شد"))
    
    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM system_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

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

class AdminStates(StatesGroup):
    waiting_for_password = State()
    admin_menu = State()
    manage_users = State()
    edit_user_balance = State()
    broadcast_message = State()
    set_game_price = State()
    waiting_card_amount = State()

class UserStates(StatesGroup):
    waiting_for_receipt = State()
    waiting_for_card_amount = State()
    playing_game = State()

# ==============================================
# کیبوردهای اصلی
# ==============================================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🎮 بازی‌ها"),
        KeyboardButton(text="💰 خرید سکه")
    )
    builder.row(
        KeyboardButton(text="👤 حساب من"),
        KeyboardButton(text="📊 آمار")
    )
    builder.row(
        KeyboardButton(text="🎯 بازی‌های ویژه"),
        KeyboardButton(text="❓ راهنما")
    )
    return builder.as_markup(resize_keyboard=True)

def get_games_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    games = [
        ("✊ سنگ کاغذ قیچی", "game_rps"),
        ("⚽ فوتبال", "game_football"),
        ("🏀 بسکتبال", "game_basketball"),
        ("🎲 تاس", "game_dice"),
        ("🎯 دارت", "game_darts"),
        ("🎳 بولینگ", "game_bowling"),
        ("🎪 قرعه‌کشی", "game_lottery")
    ]
    
    for name, callback in games:
        price = db.get_game_price(callback.replace("game_", ""))
        builder.row(InlineKeyboardButton(
            text=f"{name} - {price:,} سکه",
            callback_data=callback
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main"))
    return builder.as_markup()

def get_shop_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for stars, coins in STAR_PACKAGES.items():
        builder.row(InlineKeyboardButton(
            text=f"⭐ {stars} استارز = {coins:,} سکه",
            callback_data=f"buy_stars_{stars}"
        ))
    
    builder.row(InlineKeyboardButton(text="💳 خرید با کارت به کارت", callback_data="buy_card"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_main"))
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    buttons = [
        ("📊 آمار کلی", "admin_stats"),
        ("👤 مدیریت کاربران", "admin_users"),
        ("💰 درخواست‌های کارت به کارت", "admin_card_requests"),
        ("📢 ارسال همگانی", "admin_broadcast"),
        ("🎲 تنظیمات بازی‌ها", "admin_game_settings"),
        ("⚙️ مشاهده لاگ‌ها", "admin_logs"),
        ("🚪 خروج از پنل", "admin_exit")
    ]
    
    for text, callback in buttons:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback))
    
    return builder.as_markup()

# ==============================================
# هندلرهای اصلی
# ==============================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    db.create_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    welcome_text = f"""
🎰 به ربات کازینو و شرط‌بندی خوش آمدید {message.from_user.first_name} عزیز!

🎮 بازی‌های موجود:
• ✊ سنگ کاغذ قیچی
• ⚽ فوتبال
• 🏀 بسکتبال
• 🎲 تاس
• 🎯 دارت
• 🎳 بولینگ
• 🎪 قرعه‌کشی

💰 برای شروع، سکه خریداری کنید یا شانس خود را امتحان کنید!
⚠️ شانس برد در بازی‌ها حدود ۲۰٪ است.

🎯 برای مشاهده منوی بازی‌ها، روی دکمه "🎮 بازی‌ها" کلیک کنید.
    """
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "🎮 بازی‌ها")
async def show_games(message: Message):
    user_id = message.from_user.id
    if db.is_user_locked(user_id):
        await message.answer("⚠️ شما در حال انجام یک بازی هستید. لطفاً ابتدا آن را به پایان برسانید.")
        return
    
    await message.answer(
        "🎮 یک بازی را انتخاب کنید:\n"
        "💰 قیمت هر بازی کنار آن نوشته شده.\n"
        "⚠️ شانس برد: حدود ۲۰٪",
        reply_markup=get_games_keyboard()
    )

@router.message(F.text == "💰 خرید سکه")
async def show_shop(message: Message):
    await message.answer(
        "🛒 به فروشگاه سکه خوش آمدید!\n\n"
        "💰 روش‌های خرید:\n"
        "• ⭐ خرید با استارز تلگرام (آنی)\n"
        "• 💳 کارت به کارت (پس از تایید ادمین)\n\n"
        "یک روش را انتخاب کنید:",
        reply_markup=get_shop_keyboard()
    )

@router.message(F.text == "👤 حساب من")
async def show_profile(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        await message.answer("❌ شما هنوز ثبت نام نکرده‌اید. /start را بزنید.")
        return
    
    profile_text = f"""
👤 **پروفایل کاربری**

🆔 شناسه: `{user['user_id']}`
👤 نام: {user['first_name'] or 'نامشخص'}
📅 تاریخ عضویت: {user['join_date'][:10]}

💰 **موجودی سکه:** {user['balance']:,}
📥 کل واریز: {user['total_deposit']:,}
    """
    
    await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "❓ راهنما")
async def show_help(message: Message):
    help_text = """
📚 **راهنمای ربات کازینو**

🎮 **بازی‌ها:**
• ✊ سنگ کاغذ قیچی - شانس برد ۲۰٪
• ⚽ فوتبال - شانس برد ۲۰٪
• 🏀 بسکتبال - شانس برد ۱۵-۳۰٪
• 🎲 تاس - شانس برد ۱۶٪
• 🎯 دارت - شانس برد ۵-۳۵٪
• 🎳 بولینگ - شانس برد ۲۰-۲۵٪
• 🎪 قرعه‌کشی - شانس برد ۱۰٪

💰 **خرید سکه:**
• ⭐ استارز تلگرام (آنی)
• 💳 کارت به کارت (با تایید ادمین)

⚠️ **توجه:**
• شانس برد در تمام بازی‌ها حدود ۲۰٪ است
• مسئولیت شرط‌بندی با خودتان است
• تقلب = مسدودیت دائمی
    """
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

# ==============================================
# هندلرهای خرید سکه
# ==============================================

@router.callback_query(F.data.startswith("buy_stars_"))
async def process_star_purchase(callback: CallbackQuery):
    stars = int(callback.data.split("_")[2])
    coins = STAR_PACKAGES[stars]
    
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"خرید {coins:,} سکه",
        description=f"پرداخت {stars} استارز برای دریافت {coins:,} سکه",
        payload=f"stars_{stars}_coins_{coins}",
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice(label=f"{coins:,} سکه", amount=stars)]
    )
    
    await callback.answer("🧾 فاکتور پرداخت ایجاد شد")

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    if payload.startswith("stars_"):
        parts = payload.split("_")
        coins = int(parts[3])
        
        db.update_balance(
            message.from_user.id,
            coins,
            'deposit',
            f'خرید با {parts[1]} استارز'
        )
        
        await message.answer(
            f"✅ پرداخت موفق!\n"
            f"💰 {coins:,} سکه به حساب شما اضافه شد.\n"
            f"🎉 موجودی فعلی: {db.get_user_balance(message.from_user.id):,} سکه"
        )

@router.callback_query(F.data == "buy_card")
async def card_payment_info(callback: CallbackQuery):
    card_info = f"""
💳 **پرداخت کارت به کارت**

📌 **اطلاعات حساب:**
• شماره کارت: `{ADMIN_CARD_NUMBER}`
• به نام: {ADMIN_CARD_HOLDER}

📝 **راهنما:**
1. مبلغ مورد نظر را واریز کنید
2. از رسید پرداخت عکس بگیرید
3. روی دکمه "📤 ارسال رسید" کلیک کنید
4. منتظر تایید ادمین باشید

⚠️ حداقل واریز: 50,000 تومان = 1,000 سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📤 ارسال رسید پرداخت", callback_data="send_receipt"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_shop"))
    
    await callback.message.edit_text(card_info, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "send_receipt")
async def request_receipt(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_receipt)
    await callback.message.answer("📸 لطفاً عکس رسید پرداخت خود را ارسال کنید.")

@router.message(UserStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    request_id = db.create_card_request(
        user_id=user_id,
        amount=0,
        receipt_message_id=message.message_id,
        receipt_chat_id=message.chat.id
    )
    
    admin_notification = f"""
🔔 **درخواست واریز جدید**

🆔 درخواست: #{request_id}
👤 کاربر: {message.from_user.full_name}
🆔 شناسه: `{user_id}`
⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_card_{request_id}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_card_{request_id}")
    )
    builder.row(InlineKeyboardButton(text="💰 تعیین مبلغ", callback_data=f"set_amount_{request_id}"))
    
    await bot.send_message(ADMIN_USER_ID, admin_notification, parse_mode=ParseMode.MARKDOWN)
    await bot.forward_message(ADMIN_USER_ID, message.chat.id, message.message_id)
    await bot.send_message(ADMIN_USER_ID, "⚡ اقدام لازم:", reply_markup=builder.as_markup())
    
    await message.answer("✅ رسید شما ارسال شد. منتظر تایید ادمین باشید.")
    await state.clear()

# ==============================================
# هندلرهای بازی‌ها (شانس برد ~۲۰٪)
# ==============================================

@router.callback_query(F.data.startswith("game_"))
async def start_game(callback: CallbackQuery):
    user_id = callback.from_user.id
    game_name = callback.data.replace("game_", "")
    
    if db.is_user_locked(user_id):
        await callback.answer("⚠️ شما یک بازی در حال انجام دارید!", show_alert=True)
        return
    
    game_price = db.get_game_price(game_name)
    user_balance = db.get_user_balance(user_id)
    
    if user_balance < game_price:
        await callback.answer(
            f"❌ موجودی کافی نیست!\n💰 نیاز: {game_price:,} | 💳 موجودی: {user_balance:,}",
            show_alert=True
        )
        return
    
    db.update_balance(user_id, -game_price, 'game_fee', f'شروع بازی {game_name}')
    db.lock_user_game(user_id, game_name)
    
    game_handlers = {
        "rps": play_rock_paper_scissors,
        "football": play_football,
        "basketball": play_basketball,
        "dice": play_dice,
        "darts": play_darts,
        "bowling": play_bowling,
        "lottery": play_lottery
    }
    
    handler = game_handlers.get(game_name)
    if handler:
        await handler(callback)

async def play_rock_paper_scissors(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    choices = [
        ("✊ سنگ", "rps_choice_rock"),
        ("📄 کاغذ", "rps_choice_paper"),
        ("✂️ قیچی", "rps_choice_scissors")
    ]
    for text, cb in choices:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    await callback.message.edit_text(
        "✊ **سنگ کاغذ قیچی**\n\n🤖 ربات یکی را انتخاب می‌کند.\n👆 شما هم انتخاب کنید:\n⚠️ شانس برد: ۲۰٪",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("rps_choice_"))
async def process_rps_choice(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_choice = callback.data.split("_")[2]
    
    # الگوریتم با شانس ۲۰٪ برد
    rand = random.random()
    
    if rand < WIN_CHANCES["rps"]:  # ۲۰٪ شانس برد
        if user_choice == "rock": bot_choice = "scissors"
        elif user_choice == "paper": bot_choice = "rock"
        else: bot_choice = "paper"
        result = "win"
    elif rand < 0.50:  # ۳۰٪ مساوی
        bot_choice = user_choice
        result = "draw"
    else:  # ۵۰٪ باخت
        if user_choice == "rock": bot_choice = "paper"
        elif user_choice == "paper": bot_choice = "scissors"
        else: bot_choice = "rock"
        result = "lose"
    
    prize = int(db.get_game_price("rps") * PRIZE_MULTIPLIERS["rps"]) if result == "win" else (int(db.get_game_price("rps") * 0.5) if result == "draw" else 0)
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win' if result == "win" else 'game_draw', f'سنگ کاغذ قیچی - {result}')
    
    db.unlock_user(user_id)
    
    emoji = {"rock": "✊", "paper": "📄", "scissors": "✂️"}
    result_fa = {"win": "🎉 بردید!", "lose": "😢 باختید!", "draw": "🤝 مساوی!"}
    
    msg = f"{emoji[user_choice]} شما\n{emoji[bot_choice]} ربات\n\n{result_fa[result]}\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 بازی مجدد", callback_data="game_rps"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

async def play_football(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    teams = [("بارسلونا", "football_team_barcelona"), ("رئال مادرید", "football_team_realmadrid"), ("منچستر سیتی", "football_team_mancity"), ("بایرن مونیخ", "football_team_bayern")]
    for team, cb in teams:
        builder.row(InlineKeyboardButton(text=f"⚽ {team}", callback_data=cb))
    
    await callback.message.edit_text("⚽ **فوتبال**\n\n🏆 یک تیم انتخاب کنید:\n⚠️ شانس برد: ۲۰٪", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("football_team_"))
async def process_football(callback: CallbackQuery):
    user_id = callback.from_user.id
    team = callback.data.split("_")[2]
    
    rand = random.random()
    if rand < WIN_CHANCES["football"]:
        result = "برد"
        prize = int(db.get_game_price("football") * PRIZE_MULTIPLIERS["football"])
    elif rand < 0.40:
        result = "مساوی"
        prize = int(db.get_game_price("football") * 0.5)
    else:
        result = "باخت"
        prize = 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'فوتبال - {team} - {result}')
    
    db.unlock_user(user_id)
    
    msg = f"⚽ **نتیجه فوتبال**\n🏆 تیم: {team}\n📊 نتیجه: {result}\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 مجدد", callback_data="game_football"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

async def play_dice(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    for i in range(1, 7):
        builder.row(InlineKeyboardButton(text=f"🎲 عدد {i}", callback_data=f"dice_number_{i}"))
    
    await callback.message.edit_text("🎲 **تاس**\n\n🎯 یک عدد انتخاب کنید:\n⚠️ شانس برد: ۱۶٪", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("dice_number_"))
async def process_dice(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_num = int(callback.data.split("_")[2])
    
    rand = random.random()
    if rand < WIN_CHANCES["dice"]:
        dice_result = user_num
        prize = int(db.get_game_price("dice") * PRIZE_MULTIPLIERS["dice"])
    else:
        possible = [n for n in range(1, 7) if n != user_num]
        dice_result = random.choice(possible)
        prize = 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'تاس - عدد {dice_result}')
    
    db.unlock_user(user_id)
    
    msg = f"🎲 **نتیجه تاس**\n🎯 انتخاب: {user_num}\n🎲 تاس: {dice_result}\n{'🎉 بردید!' if prize > 0 else '😢 باختید!'}\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 مجدد", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

async def play_darts(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    targets = [("🎯 مرکز (۵٪)", "darts_bullseye"), ("🎯 حلقه ۲۰ (۱۵٪)", "darts_20"), ("🎯 حلقه ۱۵ (۲۵٪)", "darts_15"), ("🎯 حلقه ۱۰ (۳۵٪)", "darts_10")]
    for text, cb in targets:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    await callback.message.edit_text("🎯 **دارت**\n\n📍 هدف را انتخاب کنید:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("darts_"))
async def process_darts(callback: CallbackQuery):
    user_id = callback.from_user.id
    target = callback.data.split("_")[1]
    
    chance_key = f"darts_{target}"
    multiplier_key = f"darts_{target}"
    
    is_success = random.random() < WIN_CHANCES.get(chance_key, 0.2)
    prize = int(db.get_game_price("darts") * PRIZE_MULTIPLIERS.get(multiplier_key, 2)) if is_success else 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'دارت - {target}')
    
    db.unlock_user(user_id)
    
    names = {"bullseye": "مرکز", "20": "حلقه ۲۰", "15": "حلقه ۱۵", "10": "حلقه ۱۰"}
    msg = f"🎯 **دارت**\n📍 هدف: {names.get(target, target)}\n{'✅ موفق!' if is_success else '❌ خطا!'}\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 مجدد", callback_data="game_darts"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

async def play_bowling(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    styles = [("🎳 مستقیم (۲۰٪)", "bowling_straight"), ("🎳 منحنی (۲۲٪)", "bowling_curve"), ("🎳 قدرتی (۲۵٪)", "bowling_power")]
    for text, cb in styles:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    await callback.message.edit_text("🎳 **بولینگ**\n\n🎯 سبک پرتاب را انتخاب کنید:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("bowling_"))
async def process_bowling(callback: CallbackQuery):
    user_id = callback.from_user.id
    style = callback.data.split("_")[1]
    
    chance_key = f"bowling_{style}"
    multiplier_key = f"bowling_{style}"
    
    rand = random.random()
    chance = WIN_CHANCES.get(chance_key, 0.2)
    
    if rand < chance:
        result = "strike"
        prize = int(db.get_game_price("bowling") * PRIZE_MULTIPLIERS.get(multiplier_key, 2))
    elif rand < chance + 0.25:
        result = "spare"
        prize = int(db.get_game_price("bowling") * PRIZE_MULTIPLIERS.get(multiplier_key, 2) * 0.5)
    else:
        result = "miss"
        prize = 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'بولینگ - {result}')
    
    db.unlock_user(user_id)
    
    result_fa = {"strike": "🎉 استرایک!", "spare": "👍 اسپیر!", "miss": "😢 از دست رفت!"}
    names = {"straight": "مستقیم", "curve": "منحنی", "power": "قدرتی"}
    
    msg = f"🎳 **بولینگ**\n🎯 سبک: {names.get(style, style)}\n📊 نتیجه: {result_fa[result]}\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 مجدد", callback_data="game_bowling"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

async def play_basketball(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    options = [("🏀 ۲ امتیازی (۳۰٪)", "basketball_2pts"), ("🏀 ۳ امتیازی (۱۵٪)", "basketball_3pts"), ("🏀 دانک (۲۵٪)", "basketball_dunk")]
    for text, cb in options:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    
    await callback.message.edit_text("🏀 **بسکتبال**\n\n🎯 نوع پرتاب را انتخاب کنید:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("basketball_"))
async def process_basketball(callback: CallbackQuery):
    user_id = callback.from_user.id
    shot = callback.data.split("_")[1]
    
    chance_key = f"basketball_{shot}"
    multiplier_key = f"basketball_{shot}"
    
    is_success = random.random() < WIN_CHANCES.get(chance_key, 0.25)
    prize = int(db.get_game_price("basketball") * PRIZE_MULTIPLIERS.get(multiplier_key, 1.5)) if is_success else 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'بسکتبال - {shot}')
    
    db.unlock_user(user_id)
    
    names = {"2pts": "۲ امتیازی", "3pts": "۳ امتیازی", "dunk": "دانک"}
    msg = f"🏀 **بسکتبال**\n🎯 پرتاب: {names.get(shot, shot)}\n{'✅ موفق!' if is_success else '❌ ناموفق!'}\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 مجدد", callback_data="game_basketball"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

async def play_lottery(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    lucky_number = random.randint(1, 100)
    is_winner = random.random() < WIN_CHANCES["lottery"]
    
    if is_winner:
        prize = db.get_game_price("lottery") * PRIZE_MULTIPLIERS["lottery"]
        db.update_balance(user_id, prize, 'lottery_win', f'برنده قرعه‌کشی شماره {lucky_number}')
        msg = f"🎪 **قرعه‌کشی**\n🎫 شماره: {lucky_number}\n🎉 **برنده شدید!**\n💰 جایزه: {prize:,} سکه\n💳 موجودی: {db.get_user_balance(user_id):,}"
    else:
        msg = f"🎪 **قرعه‌کشی**\n🎫 شماره: {lucky_number}\n😢 برنده نشدید.\n💡 شانس خود را دوباره امتحان کنید!"
    
    db.unlock_user(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎪 شرکت مجدد", callback_data="game_lottery"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(msg, reply_markup=builder.as_markup())

# ==============================================
# هندلرهای پنل مدیریت
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    if not user or not user['is_admin']:
        await message.answer("⛔ شما دسترسی ادمین ندارید!")
        return
    
    await state.set_state(AdminStates.waiting_for_password)
    await message.answer("🔐 لطفاً رمز عبور مدیریت را وارد کنید:")

@router.message(AdminStates.waiting_for_password)
async def check_admin_password(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        await state.set_state(AdminStates.admin_menu)
        await message.answer("✅ ورود موفق!\n🔰 به پنل مدیریت خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        await message.answer("❌ رمز عبور اشتباه است!")
        await state.clear()

@router.callback_query(F.data == "admin_stats")
async def admin_statistics(callback: CallbackQuery):
    users_count = db.get_users_count()
    total_balance = db.get_total_balance()
    
    stats_text = f"""
📊 **آمار کلی ربات**

👥 کاربران: {users_count:,}
💰 مجموع سکه: {total_balance:,}
🕐 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery):
    users = db.get_all_users()
    
    if not users:
        await callback.answer("هیچ کاربری یافت نشد!")
        return
    
    users_text = "👥 **لیست کاربران**\n\n"
    for i, user in enumerate(users[:10], 1):
        users_text += f"{i}. {user['first_name'] or 'ناشناس'} - 💰 {user['balance']:,} سکه\n   🆔 `{user['user_id']}`\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(users_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_card_requests")
async def admin_pending_requests(callback: CallbackQuery):
    requests = db.get_pending_requests()
    
    if not requests:
        await callback.message.edit_text("✅ هیچ درخواست در انتظاری وجود ندارد.", reply_markup=InlineKeyboardBuilder().row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back")).as_markup())
        return
    
    request = requests[0]
    
    request_text = f"""
💰 **درخواست #{request['id']}**

👤 کاربر: {request['first_name'] or 'ناشناس'}
🆔 شناسه: `{request['user_id']}`
📅 تاریخ: {request['timestamp'][:19]}
💰 مبلغ: {request['amount']:,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_card_{request['id']}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_card_{request['id']}")
    )
    builder.row(InlineKeyboardButton(text="💰 تعیین مبلغ", callback_data=f"set_amount_{request['id']}"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(request_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("approve_card_"))
async def approve_card_request(callback: CallbackQuery):
    request_id = int(callback.data.split("_")[2])
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM card_requests WHERE id = ?", (request_id,))
        request = cursor.fetchone()
    
    if not request:
        await callback.answer("❌ درخواست یافت نشد!")
        return
    
    if request['amount'] <= 0:
        await callback.answer("⚠️ لطفاً ابتدا مبلغ را تعیین کنید!")
        return
    
    db.process_card_request(request_id, callback.from_user.id, approved=True)
    
    try:
        await bot.send_message(
            request['user_id'],
            f"✅ درخواست واریز شما تایید شد!\n💰 مبلغ {request['amount']:,} سکه اضافه شد."
        )
    except:
        pass
    
    await callback.answer("✅ تایید شد")
    await admin_pending_requests(callback)

@router.callback_query(F.data.startswith("reject_card_"))
async def reject_card_request(callback: CallbackQuery):
    request_id = int(callback.data.split("_")[2])
    db.process_card_request(request_id, callback.from_user.id, approved=False)
    await callback.answer("❌ رد شد")
    await admin_pending_requests(callback)

@router.callback_query(F.data.startswith("set_amount_"))
async def set_card_amount_start(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    await state.set_state(AdminStates.waiting_card_amount)
    await callback.message.answer("💰 لطفاً مبلغ سکه را وارد کنید:")

@router.message(AdminStates.waiting_card_amount)
async def set_card_amount_process(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")
        return
    
    data = await state.get_data()
    request_id = data.get('request_id')
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE card_requests SET amount = ? WHERE id = ?", (amount, request_id))
    
    await message.answer(f"✅ مبلغ {amount:,} سکه ثبت شد.")
    await state.clear()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.answer("📢 لطفاً پیام همگانی خود را ارسال کنید:\nبرای لغو: /cancel")

@router.message(AdminStates.broadcast_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    users = db.get_all_users()
    success = 0
    fail = 0
    
    status_msg = await message.answer("📤 در حال ارسال...")
    
    for user in users:
        try:
            await bot.copy_message(chat_id=user['user_id'], from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(f"✅ ارسال پایان یافت!\n✅ موفق: {success}\n❌ ناموفق: {fail}")
    await state.clear()

@router.callback_query(F.data == "admin_game_settings")
async def admin_game_settings_menu(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    
    games = [
        ("rps", "✊ سنگ کاغذ قیچی"),
        ("football", "⚽ فوتبال"),
        ("basketball", "🏀 بسکتبال"),
        ("dice", "🎲 تاس"),
        ("darts", "🎯 دارت"),
        ("bowling", "🎳 بولینگ"),
        ("lottery", "🎪 قرعه‌کشی")
    ]
    
    for game_id, game_name in games:
        price = db.get_game_price(game_id)
        builder.row(InlineKeyboardButton(text=f"{game_name} - {price:,} سکه", callback_data=f"edit_game_price_{game_id}"))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text("🎲 **تنظیمات قیمت بازی‌ها**", parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("edit_game_price_"))
async def edit_game_price_start(callback: CallbackQuery, state: FSMContext):
    game_id = callback.data.split("_")[3]
    current_price = db.get_game_price(game_id)
    
    await state.update_data(game_id=game_id)
    await state.set_state(AdminStates.set_game_price)
    
    await callback.message.answer(f"🎲 قیمت فعلی: {current_price:,} سکه\n📝 قیمت جدید را وارد کنید:")

@router.message(AdminStates.set_game_price)
async def set_game_price_process(message: Message, state: FSMContext):
    try:
        new_price = int(message.text)
        if new_price < 10:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر (حداقل 10) وارد کنید!")
        return
    
    data = await state.get_data()
    game_id = data.get('game_id')
    
    db.set_game_price(game_id, new_price)
    
    await message.answer(f"✅ قیمت به {new_price:,} سکه تغییر یافت.")
    await state.clear()

@router.callback_query(F.data == "admin_logs")
async def admin_view_logs(callback: CallbackQuery):
    logs = db.get_recent_logs(20)
    
    if not logs:
        await callback.answer("هیچ لاگی یافت نشد!")
        return
    
    logs_text = "📋 **آخرین لاگ‌ها**\n\n"
    for log in logs:
        logs_text += f"🕐 {log['timestamp'][:19]}\n📌 {log['action']}\n👤 کاربر: {log['user_id'] or 'سیستم'}\n📝 {log['details']}\n{'─'*30}\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="admin_logs"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(logs_text, parse_mode=ParseMode.MARKDOWN, reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_exit")
async def admin_exit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚪 از پنل مدیریت خارج شدید.\nبرای ورود مجدد: /admin")

@router.callback_query(F.data == "admin_back")
async def admin_back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text("🔰 منوی پنل مدیریت:", reply_markup=get_admin_keyboard())

# ==============================================
# دکمه‌های بازگشت
# ==============================================

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 منوی اصلی:", reply_markup=get_main_keyboard())

@router.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 یک بازی را انتخاب کنید:", reply_markup=get_games_keyboard())

@router.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: CallbackQuery):
    await callback.message.edit_text("🛒 فروشگاه سکه:", reply_markup=get_shop_keyboard())

# ==============================================
# مدیریت خطاها
# ==============================================

@router.errors()
async def error_handler(update: types.Update, exception: Exception):
    logger.error(f"خطا: {exception}", exc_info=True)
    try:
        if update.callback_query:
            await update.callback_query.answer("❌ خطایی رخ داد!", show_alert=True)
        elif update.message:
            await update.message.answer("❌ متاسفانه خطایی رخ داد.")
    except:
        pass
    return True

# ==============================================
# راه‌اندازی ربات
# ==============================================

async def main():
    """تابع اصلی راه‌اندازی ربات"""
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 ربات با polling شروع به کار کرد")
    logger.info(f"👤 ادمین: {ADMIN_USER_ID}")
    logger.info("⚠️ شانس برد کاربران: حدود ۲۰٪")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("👋 ربات خاموش شد")

if __name__ == "__main__":
    asyncio.run(main())
