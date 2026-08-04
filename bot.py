# ==============================================
# ربات شرط‌بندی و کازینو تلگرام
# توسعه داده شده با aiogram 3.x و SQLite
# تمامی کامنت‌ها و توضیحات به زبان فارسی
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
# تنظیمات اولیه و کانفیگ ربات
# ==============================================

# توکن ربات تلگرام - این را با توکن واقعی خود جایگزین کنید
BOT_TOKEN = "8975472860:AAE-eW542h7VnDICPUQ9UhL7AjIY-YKSLUQ"

# آیدی عددی ادمین اصلی
ADMIN_USER_ID = 7548145568

# رمز عبور برای ورود به پنل مدیریت
ADMIN_PASSWORD = "mohamad1387"

# تنظیمات پیش‌فرض قیمت‌های بازی‌ها
DEFAULT_GAME_PRICES = {
    "rock_paper_scissors": 100,  # سنگ کاغذ قیچی
    "football": 200,              # فوتبال
    "basketball": 200,            # بسکتبال
    "dice": 500,                  # تاس
    "darts": 300,                 # دارت
    "bowling": 400,               # بولینگ
    "lottery": 1000              # قرعه‌کشی
}

# تنظیمات استارز
STAR_PACKAGES = {
    50: 1000,    # 50 استارز = 1000 سکه
    100: 2500,   # 100 استارز = 2500 سکه
    250: 7000,   # 250 استارز = 7000 سکه
    500: 15000,  # 500 استارز = 15000 سکه
    1000: 35000  # 1000 استارز = 35000 سکه
}

# شماره کارت ادمین برای پرداخت کارت به کارت
ADMIN_CARD_NUMBER = "6062-5610-0973-7464"
ADMIN_CARD_HOLDER = "مجاور"

# ==============================================
# راه‌اندازی سیستم لاگینگ
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
# مدیریت پایگاه داده SQLite
# ==============================================

class Database:
    """کلاس مدیریت پایگاه داده SQLite"""
    
    def __init__(self, db_path: str = "casino_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """مدیریت اتصال به پایگاه داده با context manager"""
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
        """ایجاد جداول پایگاه داده در صورت عدم وجود"""
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
                    total_deposit INTEGER DEFAULT 0,
                    total_withdraw INTEGER DEFAULT 0,
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
            
            # جدول درخواست‌های کارت به کارت
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS card_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    receipt_message_id INTEGER,
                    receipt_chat_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_by INTEGER,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول تنظیمات بازی‌ها
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_settings (
                    game_name TEXT PRIMARY KEY,
                    price INTEGER DEFAULT 100,
                    min_bet INTEGER DEFAULT 10,
                    max_bet INTEGER DEFAULT 10000,
                    is_active BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # جدول قفل‌های بازی (جلوگیری از اجرای همزمان)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_locks (
                    user_id INTEGER PRIMARY KEY,
                    game_name TEXT,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # جدول لاگ‌های سیستم
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT,
                    user_id INTEGER,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # درج تنظیمات پیش‌فرض بازی‌ها
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
            
            logger.info("✅ پایگاه داده با موفقیت راه‌اندازی شد")
    
    # ==============================================
    # توابع مدیریت کاربران
    # ==============================================
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """دریافت اطلاعات یک کاربر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """ایجاد کاربر جدید"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            
            # لاگ سیستم
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('new_user', ?, 'کاربر جدید ثبت نام کرد')
            ''', (user_id,))
    
    def update_balance(self, user_id: int, amount: int, transaction_type: str, description: str, admin_id: int = None):
        """به‌روزرسانی موجودی کاربر و ثبت تراکنش"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # به‌روزرسانی موجودی
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (amount, user_id))
            
            # ثبت تراکنش
            cursor.execute('''
                INSERT INTO transactions (user_id, type, amount, description, admin_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, transaction_type, amount, description, admin_id))
            
            # لاگ سیستم
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('transaction', ?, ?)
            ''', (user_id, f"{transaction_type}: {amount} سکه - {description}"))
    
    def get_user_balance(self, user_id: int) -> int:
        """دریافت موجودی کاربر"""
        user = self.get_user(user_id)
        return user['balance'] if user else 0
    
    def get_all_users(self) -> List[Dict]:
        """دریافت لیست تمام کاربران"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY join_date DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_users_count(self) -> int:
        """تعداد کل کاربران"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            return cursor.fetchone()['count']
    
    def get_total_balance(self) -> int:
        """مجموع موجودی تمام کاربران"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(balance) as total FROM users")
            result = cursor.fetchone()['total']
            return result if result else 0
    
    # ==============================================
    # توابع مدیریت درخواست‌های کارت به کارت
    # ==============================================
    
    def create_card_request(self, user_id: int, amount: int, receipt_message_id: int, receipt_chat_id: int) -> int:
        """ایجاد درخواست کارت به کارت جدید"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO card_requests (user_id, amount, receipt_message_id, receipt_chat_id)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount, receipt_message_id, receipt_chat_id))
            
            # لاگ سیستم
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('card_request', ?, ?)
            ''', (user_id, f"درخواست واریز {amount} سکه"))
            
            return cursor.lastrowid
    
    def get_pending_requests(self) -> List[Dict]:
        """دریافت درخواست‌های در انتظار تایید"""
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
        """پردازش درخواست کارت به کارت"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if approved:
                # دریافت اطلاعات درخواست
                cursor.execute("SELECT * FROM card_requests WHERE id = ?", (request_id,))
                request = cursor.fetchone()
                
                if request:
                    # افزایش موجودی کاربر
                    self.update_balance(
                        request['user_id'], 
                        request['amount'], 
                        'deposit', 
                        f'واریز از طریق کارت به کارت - درخواست #{request_id}',
                        admin_id
                    )
                    
                    # به‌روزرسانی وضعیت درخواست
                    cursor.execute('''
                        UPDATE card_requests 
                        SET status = 'approved', 
                            processed_by = ?, 
                            processed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (admin_id, request_id))
            else:
                # رد درخواست
                cursor.execute('''
                    UPDATE card_requests 
                    SET status = 'rejected', 
                        processed_by = ?, 
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (admin_id, request_id))
            
            # لاگ سیستم
            action = 'card_approved' if approved else 'card_rejected'
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES (?, ?, ?)
            ''', (action, admin_id, f"درخواست #{request_id} {'تایید' if approved else 'رد'} شد"))
    
    # ==============================================
    # توابع مدیریت بازی‌ها
    # ==============================================
    
    def get_game_price(self, game_name: str) -> int:
        """دریافت قیمت یک بازی"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT price FROM game_settings WHERE game_name = ?", (game_name,))
            result = cursor.fetchone()
            return result['price'] if result else DEFAULT_GAME_PRICES.get(game_name, 100)
    
    def set_game_price(self, game_name: str, price: int):
        """تنظیم قیمت یک بازی"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE game_settings 
                SET price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE game_name = ?
            ''', (price, game_name))
            
            # لاگ سیستم
            cursor.execute('''
                INSERT INTO system_logs (action, user_id, details)
                VALUES ('update_game_price', ?, ?)
            ''', (ADMIN_USER_ID, f"قیمت بازی {game_name} به {price} سکه تغییر یافت"))
    
    def lock_user_game(self, user_id: int, game_name: str):
        """قفل کردن کاربر برای یک بازی"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO game_locks (user_id, game_name, locked_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, game_name))
    
    def unlock_user(self, user_id: int):
        """آزاد کردن قفل کاربر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM game_locks WHERE user_id = ?", (user_id,))
    
    def is_user_locked(self, user_id: int) -> bool:
        """بررسی قفل بودن کاربر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM game_locks WHERE user_id = ?", (user_id,))
            return cursor.fetchone()['count'] > 0
    
    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        """دریافت لاگ‌های اخیر سیستم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM system_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

# ==============================================
# ایجاد نمونه‌های پایگاه داده و ربات
# ==============================================

db = Database()
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
router = Router()

# ==============================================
# تعریف State‌های ربات
# ==============================================

class AdminStates(StatesGroup):
    """State‌های مربوط به پنل مدیریت"""
    waiting_for_password = State()
    admin_menu = State()
    manage_users = State()
    edit_user_balance = State()
    broadcast_message = State()
    set_game_price = State()
    waiting_card_amount = State()

class UserStates(StatesGroup):
    """State‌های مربوط به کاربران"""
    waiting_for_receipt = State()
    waiting_for_card_amount = State()
    playing_game = State()

# ==============================================
# کیبوردهای اصلی ربات
# ==============================================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد اصلی کاربر"""
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
    """کیبورد بازی‌ها"""
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
    
    builder.row(InlineKeyboardButton(
        text="🔙 بازگشت",
        callback_data="back_to_main"
    ))
    
    return builder.as_markup()

def get_shop_keyboard() -> InlineKeyboardMarkup:
    """کیبورد فروشگاه"""
    builder = InlineKeyboardBuilder()
    
    # دکمه‌های خرید با استارز
    for stars, coins in STAR_PACKAGES.items():
        builder.row(InlineKeyboardButton(
            text=f"⭐ {stars} استارز = {coins:,} سکه",
            callback_data=f"buy_stars_{stars}"
        ))
    
    builder.row(InlineKeyboardButton(
        text="💳 خرید با کارت به کارت",
        callback_data="buy_card"
    ))
    
    builder.row(InlineKeyboardButton(
        text="🔙 بازگشت",
        callback_data="back_to_main"
    ))
    
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """کیبورد پنل مدیریت"""
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
# هندلرهای اصلی ربات
# ==============================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """دستور شروع ربات"""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # ثبت کاربر در پایگاه داده
    db.create_user(user_id, username, first_name, last_name)
    
    # پیام خوش‌آمدگویی
    welcome_text = f"""
🎰 به ربات کازینو و شرط‌بندی خوش آمدید {first_name} عزیز!

🎮 با این ربات می‌توانید:
• در بازی‌های مختلف شرط‌بندی کنید
• سکه‌های خود را افزایش دهید
• در قرعه‌کشی‌ها شرکت کنید

💰 برای شروع، می‌توانید سکه خریداری کنید یا از بازی‌های رایگان استفاده کنید.

🎯 برای مشاهده منوی بازی‌ها، روی دکمه "🎮 بازی‌ها" کلیک کنید.
    """
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(F.text == "🎮 بازی‌ها")
async def show_games(message: Message):
    """نمایش منوی بازی‌ها"""
    user_id = message.from_user.id
    
    # بررسی قفل بودن کاربر
    if db.is_user_locked(user_id):
        await message.answer("⚠️ شما در حال انجام یک بازی هستید. لطفاً ابتدا آن را به پایان برسانید.")
        return
    
    await message.answer(
        "🎮 یک بازی را انتخاب کنید:\n"
        "💰 قیمت هر بازی کنار آن نوشته شده است.",
        reply_markup=get_games_keyboard()
    )

@router.message(F.text == "💰 خرید سکه")
async def show_shop(message: Message):
    """نمایش منوی خرید سکه"""
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
    """نمایش پروفایل کاربر"""
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
📤 کل برداشت: {user['total_withdraw']:,}

🎮 تعداد بازی‌های امروز: --
🏆 رتبه: --
    """
    
    await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN)

@router.message(F.text == "❓ راهنما")
async def show_help(message: Message):
    """نمایش راهنما"""
    help_text = """
📚 **راهنمای ربات کازینو**

🎮 **بازی‌ها:**
• ✊ سنگ کاغذ قیچی - پیش‌بینی نتیجه
• ⚽ فوتبال - شرط‌بندی روی نتایج
• 🏀 بسکتبال - پیش‌بینی امتیاز
• 🎲 تاس - شرط‌بندی روی عدد تاس
• 🎯 دارت - پیش‌بینی امتیاز دارت
• 🎳 بولینگ - شرط‌بندی روی نتیجه
• 🎪 قرعه‌کشی - شانس برنده شدن

💰 **خرید سکه:**
• ⭐ استارز تلگرام (آنی)
• 💳 کارت به کارت (با تایید ادمین)

⚠️ **قوانین:**
• حداقل سن: 18 سال
• مسئولیت شرط‌بندی با خودتان است
• تقلب = مسدودیت دائمی

📞 **پشتیبانی:** @admin
    """
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

# ==============================================
# هندلرهای خرید سکه
# ==============================================

@router.callback_query(F.data.startswith("buy_stars_"))
async def process_star_purchase(callback: CallbackQuery):
    """پردازش خرید با استارز"""
    stars = int(callback.data.split("_")[2])
    coins = STAR_PACKAGES[stars]
    
    # ایجاد فاکتور پرداخت
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"خرید {coins:,} سکه",
        description=f"پرداخت {stars} استارز برای دریافت {coins:,} سکه",
        payload=f"stars_{stars}_coins_{coins}",
        provider_token="",  # برای استارز خالی بگذارید
        currency="XTR",
        prices=[types.LabeledPrice(label=f"{coins:,} سکه", amount=stars)]
    )
    
    await callback.answer("🧾 فاکتور پرداخت ایجاد شد")

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """تایید پیش‌پرداخت"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """پردازش پرداخت موفق"""
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    # استخراج اطلاعات از payload
    if payload.startswith("stars_"):
        parts = payload.split("_")
        coins = int(parts[3])
        
        # افزایش موجودی کاربر
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
async def card_payment_info(callback: CallbackQuery, state: FSMContext):
    """نمایش اطلاعات کارت به کارت"""
    card_info = f"""
💳 **پرداخت کارت به کارت**

📌 **اطلاعات حساب:**
• شماره کارت: `{ADMIN_CARD_NUMBER}`
• به نام: {ADMIN_CARD_HOLDER}

📝 **راهنما:**
1. مبلغ مورد نظر را به شماره کارت بالا واریز کنید
2. از رسید پرداخت عکس بگیرید
3. روی دکمه "📤 ارسال رسید" کلیک کنید
4. منتظر تایید ادمین باشید (حداکثر 30 دقیقه)

⚠️ **توجه:** حداقل مبلغ واریز 50,000 تومان معادل 1,000 سکه است.
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📤 ارسال رسید پرداخت",
        callback_data="send_receipt"
    ))
    builder.row(InlineKeyboardButton(
        text="🔙 بازگشت",
        callback_data="back_to_shop"
    ))
    
    await callback.message.edit_text(
        card_info,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "send_receipt")
async def request_receipt(callback: CallbackQuery, state: FSMContext):
    """درخواست ارسال رسید"""
    await state.set_state(UserStates.waiting_for_receipt)
    await callback.message.answer(
        "📸 لطفاً عکس رسید پرداخت خود را ارسال کنید.\n"
        "💡 نکته: رسید باید شامل مبلغ، تاریخ و ساعت واریز باشد."
    )

@router.message(UserStates.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    """پردازش عکس رسید"""
    user_id = message.from_user.id
    
    # ذخیره درخواست در دیتابیس
    request_id = db.create_card_request(
        user_id=user_id,
        amount=0,  # مبلغ بعداً توسط ادمین تعیین می‌شود
        receipt_message_id=message.message_id,
        receipt_chat_id=message.chat.id
    )
    
    # ارسال به ادمین
    admin_notification = f"""
🔔 **درخواست واریز کارت به کارت جدید**

🆔 شناسه درخواست: #{request_id}
👤 کاربر: {message.from_user.full_name}
🆔 شناسه کاربر: `{user_id}`
⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📸 رسید پرداخت: 👇
    """
    
    # ساخت کیبورد تایید برای ادمین
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ تایید و واریز",
            callback_data=f"approve_card_{request_id}"
        ),
        InlineKeyboardButton(
            text="❌ رد درخواست",
            callback_data=f"reject_card_{request_id}"
        )
    )
    builder.row(InlineKeyboardButton(
        text="💰 تعیین مبلغ",
        callback_data=f"set_amount_{request_id}"
    ))
    
    # فوروارد رسید به ادمین
    await bot.send_message(
        ADMIN_USER_ID,
        admin_notification,
        parse_mode=ParseMode.MARKDOWN
    )
    await bot.forward_message(
        ADMIN_USER_ID,
        message.chat.id,
        message.message_id
    )
    await bot.send_message(
        ADMIN_USER_ID,
        "⚡ برای تایید یا رد درخواست از دکمه‌های زیر استفاده کنید:",
        reply_markup=builder.as_markup()
    )
    
    await message.answer(
        "✅ رسید شما با موفقیت ارسال شد.\n"
        "⏰ لطفاً منتظر تایید ادمین باشید.\n"
        "📞 در صورت تاخیر با پشتیبانی تماس بگیرید."
    )
    
    await state.clear()

# ==============================================
# هندلرهای بازی‌ها
# ==============================================

@router.callback_query(F.data.startswith("game_"))
async def start_game(callback: CallbackQuery):
    """شروع یک بازی"""
    user_id = callback.from_user.id
    game_key = callback.data
    game_name = game_key.replace("game_", "")
    
    # بررسی قفل بودن کاربر
    if db.is_user_locked(user_id):
        await callback.answer("⚠️ شما یک بازی در حال انجام دارید!", show_alert=True)
        return
    
    # دریافت قیمت بازی
    game_price = db.get_game_price(game_name)
    user_balance = db.get_user_balance(user_id)
    
    # بررسی موجودی کافی
    if user_balance < game_price:
        await callback.answer(
            f"❌ موجودی شما کافی نیست!\n"
            f"💰 نیاز: {game_price:,} سکه\n"
            f"💳 موجودی: {user_balance:,} سکه",
            show_alert=True
        )
        return
    
    # کسر هزینه بازی
    db.update_balance(user_id, -game_price, 'game_fee', f'شروع بازی {game_name}')
    
    # قفل کردن کاربر
    db.lock_user_game(user_id, game_name)
    
    # اجرای بازی مربوطه
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
    else:
        await callback.answer("🚫 این بازی در دست توسعه است")

async def play_rock_paper_scissors(callback: CallbackQuery):
    """بازی سنگ کاغذ قیچی"""
    builder = InlineKeyboardBuilder()
    
    choices = [
        ("✊ سنگ", "rps_choice_rock"),
        ("📄 کاغذ", "rps_choice_paper"),
        ("✂️ قیچی", "rps_choice_scissors")
    ]
    
    for text, callback_data in choices:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    await callback.message.edit_text(
        "✊ سنگ کاغذ قیچی\n\n"
        "🤖 ربات یکی را انتخاب می‌کند.\n"
        "👆 شما هم یکی را انتخاب کنید:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("rps_choice_"))
async def process_rps_choice(callback: CallbackQuery):
    """پردازش انتخاب سنگ کاغذ قیچی"""
    user_id = callback.from_user.id
    user_choice = callback.data.split("_")[2]
    
    choices = ["rock", "paper", "scissors"]
    bot_choice = random.choice(choices)
    
    # تعیین برنده
    if user_choice == bot_choice:
        result = "draw"
        prize_multiplier = 1
    elif (user_choice == "rock" and bot_choice == "scissors") or \
         (user_choice == "paper" and bot_choice == "rock") or \
         (user_choice == "scissors" and bot_choice == "paper"):
        result = "win"
        prize_multiplier = 2
    else:
        result = "lose"
        prize_multiplier = 0
    
    # محاسبه جایزه
    game_price = db.get_game_price("rps")
    prize = int(game_price * prize_multiplier)
    
    # واریز جایزه
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'برد در سنگ کاغذ قیچی')
    
    # آزاد کردن قفل
    db.unlock_user(user_id)
    
    # نمایش نتیجه
    emoji_map = {"rock": "✊", "paper": "📄", "scissors": "✂️"}
    result_text = {
        "win": "🎉 شما برنده شدید!",
        "lose": "😢 شما باختید!",
        "draw": "🤝 مساوی!"
    }
    
    result_message = f"""
{emoji_map[user_choice]} شما: {user_choice}
{emoji_map[bot_choice]} ربات: {bot_choice}

{result_text[result]}

💰 {'جایزه' if result == 'win' else 'بازگشت هزینه'}: {prize:,} سکه
💳 موجودی فعلی: {db.get_user_balance(user_id):,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🔄 بازی مجدد",
        callback_data="game_rps"
    ))
    builder.row(InlineKeyboardButton(
        text="🔙 بازگشت به بازی‌ها",
        callback_data="back_to_games"
    ))
    
    await callback.message.edit_text(
        result_message,
        reply_markup=builder.as_markup()
    )

async def play_football(callback: CallbackQuery):
    """بازی فوتبال"""
    user_id = callback.from_user.id
    builder = InlineKeyboardBuilder()
    
    teams = [
        ("بارسلونا", "football_team_barcelona"),
        ("رئال مادرید", "football_team_realmadrid"),
        ("منچستر سیتی", "football_team_mancity"),
        ("بایرن مونیخ", "football_team_bayern")
    ]
    
    for team, callback_data in teams:
        builder.row(InlineKeyboardButton(text=f"⚽ {team}", callback_data=callback_data))
    
    await callback.message.edit_text(
        "⚽ شرط‌بندی فوتبال\n\n"
        "🏆 یک تیم را برای برد انتخاب کنید:\n"
        "📊 شانس برد هر تیم متفاوت است!",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("football_team_"))
async def process_football_bet(callback: CallbackQuery):
    """پردازش شرط‌بندی فوتبال"""
    user_id = callback.from_user.id
    team = callback.data.split("_")[2]
    
    # نتایج تصادفی
    results = ["برد", "مساوی", "باخت"]
    weights = [0.4, 0.3, 0.3]  # شانس‌ها
    
    result = random.choices(results, weights=weights)[0]
    
    if result == "برد":
        prize_multiplier = 2.5
    elif result == "مساوی":
        prize_multiplier = 1
    else:
        prize_multiplier = 0
    
    game_price = db.get_game_price("football")
    prize = int(game_price * prize_multiplier)
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'شرط‌بندی فوتبال - {team}')
    
    db.unlock_user(user_id)
    
    result_text = f"""
⚽ **نتیجه بازی فوتبال**

🏆 تیم شما: {team}
📊 نتیجه: {result}

{'🎉 بردید!' if result == 'برد' else '🤝 مساوی' if result == 'مساوی' else '😢 باختید!'}

💰 جایزه: {prize:,} سکه
💳 موجودی: {db.get_user_balance(user_id):,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 شرط‌بندی مجدد", callback_data="game_football"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())

async def play_dice(callback: CallbackQuery):
    """بازی تاس"""
    builder = InlineKeyboardBuilder()
    
    for i in range(1, 7):
        builder.row(InlineKeyboardButton(
            text=f"🎲 عدد {i}",
            callback_data=f"dice_number_{i}"
        ))
    
    await callback.message.edit_text(
        "🎲 شرط‌بندی تاس\n\n"
        "🎯 یک عدد از 1 تا 6 را انتخاب کنید:\n"
        "💰 شانس برد: 1 به 6\n"
        "🎁 جایزه: 6 برابر مبلغ شرط",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("dice_number_"))
async def process_dice_bet(callback: CallbackQuery):
    """پردازش شرط‌بندی تاس"""
    user_id = callback.from_user.id
    user_number = int(callback.data.split("_")[2])
    
    # پرتاب تاس
    dice_result = random.randint(1, 6)
    
    if user_number == dice_result:
        prize_multiplier = 6
        result = "win"
    else:
        prize_multiplier = 0
        result = "lose"
    
    game_price = db.get_game_price("dice")
    prize = int(game_price * prize_multiplier)
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'برد در تاس - عدد {dice_result}')
    
    db.unlock_user(user_id)
    
    result_text = f"""
🎲 **نتیجه پرتاب تاس**

🎯 انتخاب شما: {user_number}
🎲 عدد تاس: {dice_result}

{'🎉 برنده شدید!' if result == 'win' else '😢 باختید!'}

💰 جایزه: {prize:,} سکه
💳 موجودی: {db.get_user_balance(user_id):,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 بازی مجدد", callback_data="game_dice"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())

async def play_lottery(callback: CallbackQuery):
    """قرعه‌کشی"""
    user_id = callback.from_user.id
    
    # تولید شماره شانس تصادفی
    lucky_number = random.randint(1, 100)
    
    # تعیین برنده (10% شانس)
    is_winner = random.random() < 0.1
    
    if is_winner:
        prize_multiplier = random.randint(5, 20)
        prize = db.get_game_price("lottery") * prize_multiplier
        db.update_balance(user_id, prize, 'lottery_win', f'برنده قرعه‌کشی شماره {lucky_number}')
        
        result_text = f"""
🎪 **نتیجه قرعه‌کشی**

🎫 شماره شما: {lucky_number}
🎉 **تبریک! شما برنده شدید!**

💰 جایزه: {prize:,} سکه
💳 موجودی: {db.get_user_balance(user_id):,} سکه
        """
    else:
        result_text = f"""
🎪 **نتیجه قرعه‌کشی**

🎫 شماره شما: {lucky_number}
😢 متاسفانه برنده نشدید.

💡 شانس خود را دوباره امتحان کنید!
        """
    
    db.unlock_user(user_id)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎪 شرکت مجدد", callback_data="game_lottery"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())

async def play_basketball(callback: CallbackQuery):
    """بازی بسکتبال"""
    user_id = callback.from_user.id
    builder = InlineKeyboardBuilder()
    
    options = [
        ("🏀 پرتاب 2 امتیازی", "basketball_2pts"),
        ("🏀 پرتاب 3 امتیازی", "basketball_3pts"),
        ("🏀 دانک", "basketball_dunk")
    ]
    
    for text, callback_data in options:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    await callback.message.edit_text(
        "🏀 شرط‌بندی بسکتبال\n\n"
        "🎯 نوع پرتاب را انتخاب کنید:\n"
        "💰 پرتاب‌های سخت‌تر جایزه بیشتری دارند!",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("basketball_"))
async def process_basketball_bet(callback: CallbackQuery):
    """پردازش شرط‌بندی بسکتبال"""
    user_id = callback.from_user.id
    shot_type = callback.data.split("_")[1]
    
    # شانس موفقیت بر اساس نوع پرتاب
    success_rates = {
        "2pts": 0.7,
        "3pts": 0.5,
        "dunk": 0.9
    }
    
    is_successful = random.random() < success_rates.get(shot_type, 0.5)
    
    # ضرایب جایزه
    multipliers = {
        "2pts": 1.5,
        "3pts": 3,
        "dunk": 1.2
    }
    
    multiplier = multipliers.get(shot_type, 1)
    game_price = db.get_game_price("basketball")
    prize = int(game_price * multiplier) if is_successful else 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'پرتاب بسکتبال - {shot_type}')
    
    db.unlock_user(user_id)
    
    shot_names = {"2pts": "2 امتیازی", "3pts": "3 امتیازی", "dunk": "دانک"}
    
    result_text = f"""
🏀 **نتیجه پرتاب بسکتبال**

🎯 نوع پرتاب: {shot_names.get(shot_type, shot_type)}
📊 نتیجه: {'✅ موفق' if is_successful else '❌ ناموفق'}

{'🎉 امتیاز گرفتید!' if is_successful else '😢 از دست رفت!'}

💰 جایزه: {prize:,} سکه
💳 موجودی: {db.get_user_balance(user_id):,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 پرتاب مجدد", callback_data="game_basketball"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())

async def play_darts(callback: CallbackQuery):
    """بازی دارت"""
    builder = InlineKeyboardBuilder()
    
    targets = [
        ("🎯 مرکز (Bullseye)", "darts_bullseye"),
        ("🎯 حلقه 20", "darts_20"),
        ("🎯 حلقه 15", "darts_15"),
        ("🎯 حلقه 10", "darts_10")
    ]
    
    for text, callback_data in targets:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    await callback.message.edit_text(
        "🎯 شرط‌بندی دارت\n\n"
        "📍 هدف را انتخاب کنید:\n"
        "🎯 اهداف دقیق‌تر = جایزه بیشتر\n"
        "⚠️ شانس موفقیت کمتر!",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("darts_"))
async def process_darts_bet(callback: CallbackQuery):
    """پردازش شرط‌بندی دارت"""
    user_id = callback.from_user.id
    target = callback.data.split("_")[1]
    
    # شانس موفقیت و ضرایب
    target_stats = {
        "bullseye": {"chance": 0.1, "multiplier": 10},
        "20": {"chance": 0.3, "multiplier": 3},
        "15": {"chance": 0.5, "multiplier": 2},
        "10": {"chance": 0.7, "multiplier": 1.5}
    }
    
    stats = target_stats.get(target, {"chance": 0.5, "multiplier": 1})
    is_successful = random.random() < stats["chance"]
    
    game_price = db.get_game_price("darts")
    prize = int(game_price * stats["multiplier"]) if is_successful else 0
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'دارت - هدف {target}')
    
    db.unlock_user(user_id)
    
    target_names = {
        "bullseye": "مرکز (Bullseye)",
        "20": "حلقه 20",
        "15": "حلقه 15",
        "10": "حلقه 10"
    }
    
    result_text = f"""
🎯 **نتیجه پرتاب دارت**

📍 هدف: {target_names.get(target, target)}
📊 نتیجه: {'✅ به هدف خورد!' if is_successful else '❌ خطا رفت!'}

{'🎉 عالی!' if is_successful else '😢 دفعه بعد بهتر میشه!'}

💰 جایزه: {prize:,} سکه
💳 موجودی: {db.get_user_balance(user_id):,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 پرتاب مجدد", callback_data="game_darts"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())

async def play_bowling(callback: CallbackQuery):
    """بازی بولینگ"""
    builder = InlineKeyboardBuilder()
    
    styles = [
        ("🎳 مستقیم", "bowling_straight"),
        ("🎳 منحنی راست", "bowling_curve_right"),
        ("🎳 منحنی چپ", "bowling_curve_left"),
        ("🎳 قدرتی", "bowling_power")
    ]
    
    for text, callback_data in styles:
        builder.row(InlineKeyboardButton(text=text, callback_data=callback_data))
    
    await callback.message.edit_text(
        "🎳 شرط‌بندی بولینگ\n\n"
        "🎯 سبک پرتاب را انتخاب کنید:\n"
        "🎳 هر سبک شانس و جایزه متفاوتی دارد!",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("bowling_"))
async def process_bowling_bet(callback: CallbackQuery):
    """پردازش شرط‌بندی بولینگ"""
    user_id = callback.from_user.id
    style = callback.data.split("_")[1]
    
    # تنظیمات سبک‌های بولینگ
    style_stats = {
        "straight": {"strike_chance": 0.4, "spare_chance": 0.3, "multiplier": 2},
        "curve_right": {"strike_chance": 0.5, "spare_chance": 0.3, "multiplier": 2.5},
        "curve_left": {"strike_chance": 0.5, "spare_chance": 0.3, "multiplier": 2.5},
        "power": {"strike_chance": 0.6, "spare_chance": 0.2, "multiplier": 3}
    }
    
    stats = style_stats.get(style, style_stats["straight"])
    
    # تعیین نتیجه
    random_num = random.random()
    if random_num < stats["strike_chance"]:
        result = "strike"
        multiplier = stats["multiplier"]
    elif random_num < stats["strike_chance"] + stats["spare_chance"]:
        result = "spare"
        multiplier = stats["multiplier"] * 0.7
    else:
        result = "miss"
        multiplier = 0
    
    game_price = db.get_game_price("bowling")
    prize = int(game_price * multiplier)
    
    if prize > 0:
        db.update_balance(user_id, prize, 'game_win', f'بولینگ - {result}')
    
    db.unlock_user(user_id)
    
    result_names = {
        "strike": "🎉 استرایک! عالی!",
        "spare": "👍 اسپیر! خوب بود!",
        "miss": "😢 از دست رفت!"
    }
    
    style_names = {
        "straight": "مستقیم",
        "curve_right": "منحنی راست",
        "curve_left": "منحنی چپ",
        "power": "قدرتی"
    }
    
    result_text = f"""
🎳 **نتیجه بولینگ**

🎯 سبک: {style_names.get(style, style)}
📊 نتیجه: {result_names.get(result, result)}

💰 جایزه: {prize:,} سکه
💳 موجودی: {db.get_user_balance(user_id):,} سکه
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 پرتاب مجدد", callback_data="game_bowling"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_to_games"))
    
    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())

# ==============================================
# هندلرهای پنل مدیریت
# ==============================================

@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    """ورود به پنل مدیریت"""
    user_id = message.from_user.id
    
    # بررسی ادمین بودن
    user = db.get_user(user_id)
    if not user or not user['is_admin']:
        await message.answer("⛔ شما دسترسی ادمین ندارید!")
        return
    
    await state.set_state(AdminStates.waiting_for_password)
    await message.answer("🔐 لطفاً رمز عبور مدیریت را وارد کنید:")

@router.message(AdminStates.waiting_for_password)
async def check_admin_password(message: Message, state: FSMContext):
    """بررسی رمز عبور مدیریت"""
    if message.text == ADMIN_PASSWORD:
        await state.set_state(AdminStates.admin_menu)
        await message.answer(
            "✅ ورود موفق!\n🔰 به پنل مدیریت خوش آمدید.",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer("❌ رمز عبور اشتباه است!")
        await state.clear()

@router.callback_query(F.data == "admin_stats")
async def admin_statistics(callback: CallbackQuery):
    """نمایش آمار کلی"""
    users_count = db.get_users_count()
    total_balance = db.get_total_balance()
    
    # محاسبه آمار تراکنش‌ها
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE type = 'deposit'")
        total_deposits = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE type = 'withdraw'")
        total_withdraws = cursor.fetchone()['count']
    
    stats_text = f"""
📊 **آمار کلی ربات**

👥 تعداد کاربران: {users_count:,}
💰 مجموع سکه‌های در گردش: {total_balance:,}
📥 تعداد واریزها: {total_deposits:,}
📤 تعداد برداشت‌ها: {total_withdraws:,}

🕐 زمان سرور: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(
        stats_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery):
    """نمایش لیست کاربران"""
    users = db.get_all_users()
    
    if not users:
        await callback.answer("هیچ کاربری یافت نشد!")
        return
    
    # نمایش 10 کاربر اول
    page = 1
    per_page = 10
    total_pages = (len(users) - 1) // per_page + 1
    
    start = (page - 1) * per_page
    end = start + per_page
    page_users = users[start:end]
    
    users_text = f"👥 **لیست کاربران (صفحه {page}/{total_pages})**\n\n"
    
    for i, user in enumerate(page_users, 1):
        users_text += f"{i}. {user['first_name'] or 'ناشناس'} - 💰 {user['balance']:,} سکه\n"
        users_text += f"   🆔 `{user['user_id']}` | @{user['username'] or '---'}\n\n"
    
    builder = InlineKeyboardBuilder()
    
    # دکمه‌های صفحه‌بندی
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ قبلی",
            callback_data=f"users_page_{page-1}"
        ))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="➡️ بعدی",
            callback_data=f"users_page_{page+1}"
        ))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔍 جستجوی کاربر", callback_data="admin_search_user"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(
        users_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_card_requests")
async def admin_pending_requests(callback: CallbackQuery):
    """نمایش درخواست‌های کارت به کارت"""
    requests = db.get_pending_requests()
    
    if not requests:
        await callback.message.edit_text(
            "✅ هیچ درخواست در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back")
            ).as_markup()
        )
        return
    
    # نمایش اولین درخواست
    request = requests[0]
    
    request_text = f"""
💰 **درخواست کارت به کارت #{request['id']}**

👤 کاربر: {request['first_name'] or 'ناشناس'}
🆔 شناسه: `{request['user_id']}`
📅 تاریخ: {request['timestamp'][:19]}
💰 مبلغ: {request['amount']:,} سکه (در انتظار تعیین)

📸 رسید پرداخت: (به پیام فوروارد شده مراجعه کنید)
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ تایید و واریز",
            callback_data=f"approve_card_{request['id']}"
        ),
        InlineKeyboardButton(
            text="❌ رد",
            callback_data=f"reject_card_{request['id']}"
        )
    )
    builder.row(InlineKeyboardButton(
        text="💰 تعیین مبلغ",
        callback_data=f"set_amount_{request['id']}"
    ))
    
    if len(requests) > 1:
        builder.row(InlineKeyboardButton(
            text=f"➡️ درخواست بعدی ({len(requests)-1} مورد دیگر)",
            callback_data="next_card_request_1"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(
        request_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("approve_card_"))
async def approve_card_request(callback: CallbackQuery):
    """تایید درخواست کارت به کارت"""
    request_id = int(callback.data.split("_")[2])
    
    # دریافت اطلاعات درخواست
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
    
    # پردازش درخواست
    db.process_card_request(request_id, callback.from_user.id, approved=True)
    
    # اطلاع به کاربر
    try:
        await bot.send_message(
            request['user_id'],
            f"✅ درخواست واریز شما تایید شد!\n"
            f"💰 مبلغ {request['amount']:,} سکه به حساب شما اضافه شد.\n"
            f"🎉 موجودی فعلی: {db.get_user_balance(request['user_id']):,} سکه"
        )
    except:
        logger.error(f"خطا در ارسال پیام به کاربر {request['user_id']}")
    
    await callback.answer("✅ درخواست با موفقیت تایید شد")
    
    # بازگشت به لیست درخواست‌ها
    await admin_pending_requests(callback)

@router.callback_query(F.data.startswith("reject_card_"))
async def reject_card_request(callback: CallbackQuery):
    """رد درخواست کارت به کارت"""
    request_id = int(callback.data.split("_")[2])
    
    db.process_card_request(request_id, callback.from_user.id, approved=False)
    
    # اطلاع به کاربر
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM card_requests WHERE id = ?", (request_id,))
        request = cursor.fetchone()
        
        if request:
            try:
                await bot.send_message(
                    request['user_id'],
                    "❌ متاسفانه درخواست واریز شما تایید نشد.\n"
                    "📞 برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
                )
            except:
                pass
    
    await callback.answer("❌ درخواست رد شد")
    await admin_pending_requests(callback)

@router.callback_query(F.data.startswith("set_amount_"))
async def set_card_amount_start(callback: CallbackQuery, state: FSMContext):
    """شروع فرآیند تعیین مبلغ"""
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id)
    await state.set_state(AdminStates.waiting_card_amount)
    
    await callback.message.answer(
        "💰 لطفاً مبلغ سکه را وارد کنید:\n"
        "💡 فقط عدد وارد کنید (مثال: 5000)"
    )

@router.message(AdminStates.waiting_card_amount)
async def set_card_amount_process(message: Message, state: FSMContext):
    """پردازش مبلغ وارد شده"""
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید!")
        return
    
    data = await state.get_data()
    request_id = data.get('request_id')
    
    # به‌روزرسانی مبلغ درخواست
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE card_requests SET amount = ? WHERE id = ?",
            (amount, request_id)
        )
    
    await message.answer(f"✅ مبلغ {amount:,} سکه برای درخواست #{request_id} ثبت شد.")
    await state.clear()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """شروع ارسال همگانی"""
    await state.set_state(AdminStates.broadcast_message)
    await callback.message.answer(
        "📢 لطفاً پیام همگانی خود را ارسال کنید:\n\n"
        "💡 نکات:\n"
        "• پیام می‌تواند شامل متن، عکس، فیلم و ... باشد\n"
        "• برای لغو، /cancel را بفرستید\n"
        "• پس از ارسال، به همه کاربران فوروارد می‌شود"
    )

@router.message(AdminStates.broadcast_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    """ارسال پیام همگانی"""
    users = db.get_all_users()
    success_count = 0
    fail_count = 0
    
    # ارسال پیام وضعیت
    status_msg = await message.answer("📤 در حال ارسال پیام همگانی...")
    
    for user in users:
        try:
            await bot.copy_message(
                chat_id=user['user_id'],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success_count += 1
            await asyncio.sleep(0.05)  # جلوگیری از محدودیت تلگرام
        except Exception as e:
            fail_count += 1
            logger.error(f"خطا در ارسال به {user['user_id']}: {e}")
        
        # به‌روزرسانی وضعیت هر 10 کاربر
        if (success_count + fail_count) % 10 == 0:
            await status_msg.edit_text(
                f"📤 در حال ارسال...\n"
                f"✅ موفق: {success_count}\n"
                f"❌ ناموفق: {fail_count}"
            )
    
    await status_msg.edit_text(
        f"✅ ارسال همگانی به پایان رسید!\n\n"
        f"📊 آمار ارسال:\n"
        f"👥 کل کاربران: {len(users):,}\n"
        f"✅ موفق: {success_count:,}\n"
        f"❌ ناموفق: {fail_count:,}"
    )
    
    await state.clear()

@router.callback_query(F.data == "admin_game_settings")
async def admin_game_settings_menu(callback: CallbackQuery):
    """منوی تنظیمات بازی‌ها"""
    builder = InlineKeyboardBuilder()
    
    games = [
        ("rock_paper_scissors", "✊ سنگ کاغذ قیچی"),
        ("football", "⚽ فوتبال"),
        ("basketball", "🏀 بسکتبال"),
        ("dice", "🎲 تاس"),
        ("darts", "🎯 دارت"),
        ("bowling", "🎳 بولینگ"),
        ("lottery", "🎪 قرعه‌کشی")
    ]
    
    for game_id, game_name in games:
        price = db.get_game_price(game_id)
        builder.row(InlineKeyboardButton(
            text=f"{game_name} - {price:,} سکه",
            callback_data=f"edit_game_price_{game_id}"
        ))
    
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(
        "🎲 **تنظیمات قیمت بازی‌ها**\n\n"
        "💰 روی هر بازی کلیک کنید تا قیمت آن را تغییر دهید.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("edit_game_price_"))
async def edit_game_price_start(callback: CallbackQuery, state: FSMContext):
    """شروع ویرایش قیمت بازی"""
    game_id = callback.data.split("_")[3]
    current_price = db.get_game_price(game_id)
    
    game_names = {
        "rock_paper_scissors": "سنگ کاغذ قیچی",
        "football": "فوتبال",
        "basketball": "بسکتبال",
        "dice": "تاس",
        "darts": "دارت",
        "bowling": "بولینگ",
        "lottery": "قرعه‌کشی"
    }
    
    await state.update_data(game_id=game_id)
    await state.set_state(AdminStates.set_game_price)
    
    await callback.message.answer(
        f"🎲 بازی: {game_names.get(game_id, game_id)}\n"
        f"💰 قیمت فعلی: {current_price:,} سکه\n\n"
        "📝 لطفاً قیمت جدید را وارد کنید (فقط عدد):"
    )

@router.message(AdminStates.set_game_price)
async def set_game_price_process(message: Message, state: FSMContext):
    """پردازش قیمت جدید بازی"""
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
    
    await message.answer(
        f"✅ قیمت بازی با موفقیت به {new_price:,} سکه تغییر یافت."
    )
    await state.clear()

@router.callback_query(F.data == "admin_logs")
async def admin_view_logs(callback: CallbackQuery):
    """نمایش لاگ‌های سیستم"""
    logs = db.get_recent_logs(20)
    
    if not logs:
        await callback.answer("هیچ لاگی یافت نشد!")
        return
    
    logs_text = "📋 **آخرین لاگ‌های سیستم**\n\n"
    
    for log in logs:
        timestamp = log['timestamp'][:19] if log['timestamp'] else 'نامشخص'
        logs_text += f"🕐 {timestamp}\n"
        logs_text += f"📌 {log['action']}\n"
        logs_text += f"👤 کاربر: {log['user_id'] or 'سیستم'}\n"
        logs_text += f"📝 {log['details']}\n"
        logs_text += "─" * 30 + "\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="admin_logs"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back"))
    
    await callback.message.edit_text(
        logs_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_exit")
async def admin_exit(callback: CallbackQuery, state: FSMContext):
    """خروج از پنل مدیریت"""
    await state.clear()
    await callback.message.edit_text(
        "🚪 از پنل مدیریت خارج شدید.\n"
        "برای ورود مجدد: /admin"
    )

@router.callback_query(F.data == "admin_back")
async def admin_back_to_menu(callback: CallbackQuery):
    """بازگشت به منوی اصلی مدیریت"""
    await callback.message.edit_text(
        "🔰 منوی پنل مدیریت:",
        reply_markup=get_admin_keyboard()
    )

# ==============================================
# هندلرهای عمومی و بازگشت
# ==============================================

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """بازگشت به منوی اصلی"""
    await callback.message.delete()
    await callback.message.answer(
        "🏠 منوی اصلی:",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "back_to_games")
async def back_to_games(callback: CallbackQuery):
    """بازگشت به لیست بازی‌ها"""
    await callback.message.edit_text(
        "🎮 یک بازی را انتخاب کنید:",
        reply_markup=get_games_keyboard()
    )

@router.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: CallbackQuery):
    """بازگشت به فروشگاه"""
    await callback.message.edit_text(
        "🛒 فروشگاه سکه:",
        reply_markup=get_shop_keyboard()
    )

# ==============================================
# مدیریت خطاها
# ==============================================

@router.errors()
async def error_handler(update: types.Update, exception: Exception):
    """مدیریت خطاهای ربات"""
    logger.error(f"خطا در پردازش آپدیت: {exception}", exc_info=True)
    
    # تلاش برای ارسال پیام خطا به کاربر
    try:
        if update.callback_query:
            await update.callback_query.answer(
                "❌ خطایی رخ داد! لطفاً دوباره تلاش کنید.",
                show_alert=True
            )
        elif update.message:
            await update.message.answer(
                "❌ متاسفانه خطایی رخ داد. لطفاً دوباره تلاش کنید."
            )
    except:
        pass
    
    return True

# ==============================================
# راه‌اندازی ربات
# ==============================================

async def main():
    """تابع اصلی راه‌اندازی ربات"""
    
    # ثبت روتر
    dp.include_router(router)
    
    # حذف وب‌هوک و شروع polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("🚀 ربات در حال راه‌اندازی...")
    logger.info(f"👤 ادمین اصلی: {ADMIN_USER_ID}")
    logger.info(f"💾 پایگاه داده: {db.db_path}")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("👋 ربات خاموش شد")

if __name__ == "__main__":
    # اجرای ربات
    asyncio.run(main())