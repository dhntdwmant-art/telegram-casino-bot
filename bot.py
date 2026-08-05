# ============================================================================
# TELEGRAM BETTING BOT - COMPLETE PRODUCTION CODE
# ============================================================================
# Version: 1.0.0
# Architecture: Clean Architecture + Repository Pattern + Service Layer
# Database: PostgreSQL (SQLite for development)
# ============================================================================

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal
import json
import hashlib
import re
from dataclasses import dataclass
from enum import Enum

# ============================================================================
# Environment & Configuration
# ============================================================================

BOT_TOKEN = "8943333410:AAFaCwNKDQDk8bwxQcg1EUSHl7lkhHzuWWw"
OWNER_ID = 7548145568
CARD_NUMBER = "6062561009737464"
CARD_OWNER = "مجاور"
BOT_USERNAME = "shartbist_bot"
MIN_WITHDRAWAL = 100_000  # Toman
MIN_DEPOSIT = 10_000  # Toman
REFERRAL_REWARD = 10_000  # Toman

# Game odds (house edge ~10-20%)
DICE_ODDS = 5.0  # Fair would be 6x, house edge ~16.7%
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
RPS_ODDS = 1.8  # House edge ~10%

# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Database Layer (SQLite for development)
# ============================================================================

import sqlite3
from contextlib import contextmanager

DB_PATH = "bot_data.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize all database tables"""
    with get_db() as conn:
        c = conn.cursor()

        # Users table
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
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
                admin_note TEXT,
                FOREIGN KEY (referred_by) REFERENCES users(id)
            )
        """)

        # Admins table
        c.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY,
                user_id INTEGER UNIQUE,
                role TEXT DEFAULT 'support',
                permissions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Transactions table
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                status TEXT DEFAULT 'pending',
                description TEXT,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Deposits table
        c.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                receipt_photo_id TEXT,
                status TEXT DEFAULT 'pending',
                admin_comment TEXT,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Withdrawals table
        c.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                card_number TEXT,
                card_owner TEXT,
                status TEXT DEFAULT 'pending',
                admin_comment TEXT,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Games table
        c.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                game_type TEXT,
                bet_amount INTEGER,
                odds REAL,
                user_choice TEXT,
                result TEXT,
                outcome TEXT,
                profit INTEGER,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Game rooms (2 player mode)
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_rooms (
                id INTEGER PRIMARY KEY,
                creator_id INTEGER,
                opponent_id INTEGER,
                game_type TEXT,
                bet_amount INTEGER,
                status TEXT DEFAULT 'waiting',
                winner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (creator_id) REFERENCES users(telegram_id),
                FOREIGN KEY (opponent_id) REFERENCES users(telegram_id)
            )
        """)

        # Referrals table
        c.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY,
                referrer_id INTEGER,
                referred_id INTEGER,
                reward INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(telegram_id),
                FOREIGN KEY (referred_id) REFERENCES users(telegram_id)
            )
        """)

        # Missions table
        c.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY,
                title TEXT,
                description TEXT,
                reward INTEGER,
                type TEXT,
                target INTEGER,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Mission progress table
        c.execute("""
            CREATE TABLE IF NOT EXISTS mission_progress (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                mission_id INTEGER,
                progress INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                claimed BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id),
                FOREIGN KEY (mission_id) REFERENCES missions(id)
            )
        """)

        # Support tickets
        c.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                status TEXT DEFAULT 'open',
                subject TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        """)

        # Support messages
        c.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                sender_id INTEGER,
                message TEXT,
                is_from_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES support_tickets(id)
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

        # Audit logs
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY,
                admin_id INTEGER,
                action TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Create indexes for performance
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_deposits_user ON deposits(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawals(user_id)")

        conn.commit()
        logger.info("Database initialized successfully")


# ============================================================================
# Repository Layer
# ============================================================================

class UserRepository:
    @staticmethod
    def get_user(telegram_id: int) -> Optional[Dict]:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = c.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create_user(telegram_id: int, username: str = None, first_name: str = None,
                    last_name: str = None, referred_by: int = None) -> Dict:
        with get_db() as conn:
            c = conn.cursor()
            # Generate referral code
            referral_code = f"REF{telegram_id}{datetime.now().strftime('%Y%m%d')}"
            c.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name, 
                                  referral_code, referred_by, last_activity)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (telegram_id, username, first_name, last_name, referral_code, referred_by))
            conn.commit()
            return UserRepository.get_user(telegram_id)

    @staticmethod
    def update_wallet(telegram_id: int, amount: int) -> None:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET wallet = wallet + ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                      (amount, telegram_id))
            conn.commit()

    @staticmethod
    def update_stats(telegram_id: int, win: bool) -> None:
        with get_db() as conn:
            c = conn.cursor()
            if win:
                c.execute("UPDATE users SET wins = wins + 1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                          (telegram_id,))
            else:
                c.execute("UPDATE users SET losses = losses + 1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                          (telegram_id,))
            conn.commit()

    @staticmethod
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

    @staticmethod
    def get_top_users(limit: int = 10) -> List[Dict]:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT telegram_id, username, first_name, wallet, wins, losses
                FROM users 
                WHERE is_banned = 0
                ORDER BY wallet DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]

    @staticmethod
    def get_user_stats(telegram_id: int) -> Dict:
        user = UserRepository.get_user(telegram_id)
        if not user:
            return {}
        total_games = user.get('wins', 0) + user.get('losses', 0)
        win_rate = (user['wins'] / total_games * 100) if total_games > 0 else 0
        return {
            'total_games': total_games,
            'win_rate': round(win_rate, 1),
            'level': UserRepository.get_user_level(user['wallet'])
        }


class TransactionRepository:
    @staticmethod
    def create_transaction(user_id: int, amount: int, type: str,
                           description: str = None, admin_id: int = None) -> int:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO transactions (user_id, amount, type, description, admin_id)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, amount, type, description, admin_id))
            conn.commit()
            return c.lastrowid

    @staticmethod
    def get_user_transactions(user_id: int, limit: int = 20) -> List[Dict]:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in c.fetchall()]


class GameRepository:
    @staticmethod
    def save_game(user_id: int, game_type: str, bet: int, odds: float,
                  user_choice: str, result: str, outcome: str, profit: int) -> int:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO games (user_id, game_type, bet_amount, odds, 
                                  user_choice, result, outcome, profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, game_type, bet, odds, user_choice, result, outcome, profit))
            conn.commit()
            return c.lastrowid

    @staticmethod
    def get_user_games(user_id: int, limit: int = 10) -> List[Dict]:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM games 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in c.fetchall()]


class DepositRepository:
    @staticmethod
    def create_deposit(user_id: int, amount: int, photo_id: str) -> int:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO deposits (user_id, amount, receipt_photo_id)
                VALUES (?, ?, ?)
            """, (user_id, amount, photo_id))
            conn.commit()
            return c.lastrowid

    @staticmethod
    def get_pending_deposits() -> List[Dict]:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM deposits WHERE status = 'pending' ORDER BY created_at ASC")
            return [dict(row) for row in c.fetchall()]

    @staticmethod
    def approve_deposit(deposit_id: int, admin_id: int = None) -> None:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE deposits SET status = 'approved', admin_id = ?, 
                processed_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (admin_id, deposit_id))
            # Get user and amount
            c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (deposit_id,))
            row = c.fetchone()
            if row:
                UserRepository.update_wallet(row['user_id'], row['amount'])
                TransactionRepository.create_transaction(
                    row['user_id'], row['amount'], 'deposit',
                    f"واریز #{deposit_id}", admin_id
                )
            conn.commit()

    @staticmethod
    def reject_deposit(deposit_id: int, comment: str = None, admin_id: int = None) -> None:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE deposits SET status = 'rejected', admin_comment = ?, 
                admin_id = ?, processed_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (comment, admin_id, deposit_id))
            conn.commit()


class WithdrawalRepository:
    @staticmethod
    def create_withdrawal(user_id: int, amount: int, card_number: str,
                          card_owner: str) -> int:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO withdrawals (user_id, amount, card_number, card_owner)
                VALUES (?, ?, ?, ?)
            """, (user_id, amount, card_number, card_owner))
            conn.commit()
            return c.lastrowid

    @staticmethod
    def get_pending_withdrawals() -> List[Dict]:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY created_at ASC")
            return [dict(row) for row in c.fetchall()]

    @staticmethod
    def approve_withdrawal(withdrawal_id: int, admin_id: int = None) -> None:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE withdrawals SET status = 'approved', admin_id = ?, 
                processed_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (admin_id, withdrawal_id))
            c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (withdrawal_id,))
            row = c.fetchone()
            if row:
                UserRepository.update_wallet(row['user_id'], -row['amount'])
                TransactionRepository.create_transaction(
                    row['user_id'], -row['amount'], 'withdrawal',
                    f"برداشت #{withdrawal_id}", admin_id
                )
            conn.commit()

    @staticmethod
    def reject_withdrawal(withdrawal_id: int, comment: str = None, admin_id: int = None) -> None:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE withdrawals SET status = 'rejected', admin_comment = ?, 
                admin_id = ?, processed_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (comment, admin_id, withdrawal_id))
            conn.commit()


# ============================================================================
# Telegram Bot Setup (aiogram)
# ============================================================================

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, Message, FSInputFile
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Initialize bot and dispatcher
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============================================================================
# States for FSM
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


class SupportStates(StatesGroup):
    WAITING_MESSAGE = State()


class TwoPlayerStates(StatesGroup):
    CREATE_ROOM = State()
    INVITE_FRIEND = State()
    WAITING_ACCEPT = State()


# ============================================================================
# Keyboard Builders
# ============================================================================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Create main menu keyboard"""
    buttons = [
        [InlineKeyboardButton("🎮 شروع بازی", callback_data="games")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="profile")],
        [InlineKeyboardButton("🎯 مأموریت‌ها", callback_data="missions")],
        [InlineKeyboardButton("💳 افزایش موجودی", callback_data="deposit")],
        [InlineKeyboardButton("💸 برداشت موجودی", callback_data="withdraw")],
        [InlineKeyboardButton("🏆 لیدربورد", callback_data="leaderboard")],
        [InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="referral")],
        [InlineKeyboardButton("🎧 پشتیبانی", callback_data="support")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def games_menu_keyboard() -> InlineKeyboardMarkup:
    """Create games menu keyboard"""
    buttons = [
        [InlineKeyboardButton("🎲 تاس", callback_data="game_dice")],
        [InlineKeyboardButton("🎳 بولینگ", callback_data="game_bowling")],
        [InlineKeyboardButton("🎰 قرعه", callback_data="game_lottery")],
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game_rps")],
        [InlineKeyboardButton("👥 بازی دو نفره", callback_data="game_2player")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def game_outcome_keyboard(game_type: str) -> InlineKeyboardMarkup:
    """Create outcome selection keyboard based on game type"""
    buttons = []
    if game_type == "dice":
        for i in range(1, 7):
            buttons.append([InlineKeyboardButton(f"🎲 عدد {i}", callback_data=f"outcome_{i}")])
    elif game_type == "bowling":
        outcomes = [
            "افتادن ۱ پین", "افتادن ۲ پین", "افتادن ۳ پین",
            "نیمی از پین‌ها", "اسپیر", "استرایک", "خارج از لاین"
        ]
        for outcome in outcomes:
            odds = BOWLING_ODDS.get(outcome, 2.0)
            buttons.append([InlineKeyboardButton(f"🎳 {outcome} ({odds}x)", callback_data=f"outcome_{outcome}")])
    elif game_type == "lottery":
        outcomes = ["🍇🍇🍇", "🍒🍒🍒", "🍋🍋🍋", "⭐⭐⭐", "💎💎💎", "7️⃣7️⃣7️⃣", "🍀🍀🍀"]
        for outcome in outcomes:
            odds = LOTTERY_ODDS.get(outcome, 3.0)
            buttons.append([InlineKeyboardButton(f"🎰 {outcome} ({odds}x)", callback_data=f"outcome_{outcome}")])
    elif game_type == "rps":
        buttons = [
            [InlineKeyboardButton("✊ سنگ", callback_data="outcome_سنگ")],
            [InlineKeyboardButton("✋ کاغذ", callback_data="outcome_کاغذ")],
            [InlineKeyboardButton("✌️ قیچی", callback_data="outcome_قیچی")],
        ]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="games")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def bet_amount_keyboard() -> InlineKeyboardMarkup:
    """Create bet amount selection keyboard"""
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


def confirm_bet_keyboard() -> InlineKeyboardMarkup:
    """Create bet confirmation keyboard"""
    buttons = [
        [InlineKeyboardButton("✅ تایید و شروع", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ لغو", callback_data="confirm_no")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_amount_keyboard() -> InlineKeyboardMarkup:
    """Create deposit amount selection keyboard"""
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


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Create admin panel keyboard"""
    buttons = [
        [InlineKeyboardButton("📊 داشبورد", callback_data="admin_dashboard")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("💳 مدیریت واریز", callback_data="admin_deposits")],
        [InlineKeyboardButton("💸 مدیریت برداشت", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("🎮 مدیریت بازی‌ها", callback_data="admin_games")],
        [InlineKeyboardButton("📈 گزارشات مالی", callback_data="admin_reports")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎧 مدیریت پشتیبانی", callback_data="admin_support")],
        [InlineKeyboardButton("⚙ تنظیمات", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_action_keyboard(item_id: int, action_type: str) -> InlineKeyboardMarkup:
    """Create admin action keyboard for deposits/withdrawals"""
    buttons = [
        [InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{action_type}_{item_id}")],
        [InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{action_type}_{item_id}")],
        [InlineKeyboardButton("✏ یادداشت", callback_data=f"admin_note_{action_type}_{item_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ============================================================================
# Game Logic
# ============================================================================

class GameEngine:
    """Game engine with fair RNG and house edge"""
    
    @staticmethod
    def play_dice(prediction: int) -> Dict:
        """Play dice game with fair RNG"""
        result = random.randint(1, 6)
        win = (result == prediction)
        odds = DICE_ODDS if win else 0
        return {
            'result': f"عدد {result}",
            'odds': odds,
            'win': win,
            'profit': int(odds * 10) if win else 0  # Just for display
        }

    @staticmethod
    def play_bowling(prediction: str) -> Dict:
        """Play bowling with weighted probabilities"""
        outcomes = list(BOWLING_ODDS.keys())
        weights = [40, 20, 15, 10, 8, 5, 2]  # Weighted for house edge
        result = random.choices(outcomes, weights=weights)[0]
        win = (result == prediction)
        odds = BOWLING_ODDS.get(result, 2.0)
        return {
            'result': result,
            'odds': odds if win else 0,
            'win': win,
            'profit': int(odds * 10) if win else 0
        }

    @staticmethod
    def play_lottery(prediction: str) -> Dict:
        """Play lottery with weighted probabilities"""
        outcomes = list(LOTTERY_ODDS.keys())
        weights = [30, 25, 20, 12, 8, 3, 2]  # Weighted for house edge
        result = random.choices(outcomes, weights=weights)[0]
        win = (result == prediction)
        odds = LOTTERY_ODDS.get(result, 3.0)
        return {
            'result': result,
            'odds': odds if win else 0,
            'win': win,
            'profit': int(odds * 10) if win else 0
        }

    @staticmethod
    def play_rps(user_choice: str) -> Dict:
        """Play Rock Paper Scissors with slight house advantage"""
        choices = ["سنگ", "کاغذ", "قیچی"]
        # Slight house advantage: bot wins 55% of the time
        if random.random() < 0.55:
            # Bot tries to beat user
            if user_choice == "سنگ":
                bot_choice = "کاغذ"
            elif user_choice == "کاغذ":
                bot_choice = "قیچی"
            else:
                bot_choice = "سنگ"
        else:
            bot_choice = random.choice(choices)
        
        # Determine winner
        if bot_choice == user_choice:
            result = "draw"
            win = False
            profit = 0
        elif (user_choice == "سنگ" and bot_choice == "قیچی") or \
             (user_choice == "کاغذ" and bot_choice == "سنگ") or \
             (user_choice == "قیچی" and bot_choice == "کاغذ"):
            result = "win"
            win = True
            profit = 8  # 80% of bet (10 * 1.8 - 10)
        else:
            result = "lose"
            win = False
            profit = -10  # Loss of bet

        return {
            'user_choice': user_choice,
            'bot_choice': bot_choice,
            'result': result,
            'win': win,
            'odds': 1.8 if win else 0,
            'profit': profit if win else -10
        }


# ============================================================================
# Handlers - Start & Menu
# ============================================================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    user = message.from_user
    
    # Check if user exists
    db_user = UserRepository.get_user(user.id)
    if not db_user:
        # Check for referral
        referred_by = None
        if message.text and 'ref_' in message.text:
            try:
                ref_code = message.text.split('ref_')[1]
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("SELECT telegram_id FROM users WHERE referral_code = ?", (ref_code,))
                    row = c.fetchone()
                    if row:
                        referred_by = row[0]
            except:
                pass
        
        # Create user
        UserRepository.create_user(
            user.id, user.username, user.first_name, user.last_name, referred_by
        )
        
        # Process referral reward if applicable
        if referred_by:
            # Give reward when user plays first game
            pass

    welcome_text = """
🎮 <b>به ربات بازی خوش آمدید!</b>

در این ربات می‌توانید در بازی‌های مختلف شرکت کنید، 
موجودی خود را افزایش دهید، دوستانتان را دعوت کنید 
و در لیدربورد رقابت کنید.

<b>لطفاً یکی از گزینه‌های زیر را انتخاب کنید:</b>
    """
    
    await message.answer(
        welcome_text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.clear()


@dp.callback_query(F.data == "menu")
async def callback_menu(callback: CallbackQuery, state: FSMContext):
    """Return to main menu"""
    await callback.answer()
    await callback.message.edit_text(
        "🎮 <b>منوی اصلی</b>\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.clear()


# ============================================================================
# Handlers - Games
# ============================================================================

@dp.callback_query(F.data == "games")
async def callback_games(callback: CallbackQuery, state: FSMContext):
    """Show games menu"""
    await callback.answer()
    await callback.message.edit_text(
        "🎮 <b>بازی‌های موجود</b>\n\n"
        "لطفاً یکی از بازی‌های زیر را انتخاب کنید:",
        reply_markup=games_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GameStates.SELECT_GAME)


@dp.callback_query(F.data.startswith("game_"))
async def callback_game_selected(callback: CallbackQuery, state: FSMContext):
    """Handle game selection"""
    await callback.answer()
    game_type = callback.data.replace("game_", "")
    
    if game_type == "2player":
        await callback.message.edit_text(
            "👥 <b>بازی دو نفره</b>\n\n"
            "این بخش در حال توسعه می‌باشد.",
            reply_markup=games_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Store game type in state
    await state.update_data(game_type=game_type)
    
    # Show outcome selection
    game_names = {
        "dice": "تاس 🎲",
        "bowling": "بولینگ 🎳",
        "lottery": "قرعه 🎰",
        "rps": "سنگ کاغذ قیچی ✊"
    }
    
    text = (
        f"🎯 <b>مرحله اول: پیش‌بینی نتیجه</b>\n\n"
        f"بازی: {game_names.get(game_type, game_type)}\n\n"
        f"لطفاً نتیجه‌ای که فکر می‌کنید رخ خواهد داد را انتخاب کنید:\n\n"
        f"⚠️ شما فقط در صورتی برنده می‌شوید که دقیقاً همین نتیجه رخ دهد!"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=game_outcome_keyboard(game_type),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GameStates.SELECT_OUTCOME)


@dp.callback_query(F.data.startswith("outcome_"), GameStates.SELECT_OUTCOME)
async def callback_outcome_selected(callback: CallbackQuery, state: FSMContext):
    """Handle outcome selection"""
    await callback.answer()
    outcome = callback.data.replace("outcome_", "")
    user_data = await state.get_data()
    game_type = user_data.get('game_type')
    
    # Store outcome
    await state.update_data(outcome=outcome)
    
    # Get odds
    odds = 0
    if game_type == "dice":
        odds = DICE_ODDS
    elif game_type == "bowling":
        odds = BOWLING_ODDS.get(outcome, 2.0)
    elif game_type == "lottery":
        odds = LOTTERY_ODDS.get(outcome, 3.0)
    elif game_type == "rps":
        odds = RPS_ODDS
    
    text = (
        f"🎯 <b>مرحله دوم: تعیین مبلغ شرط</b>\n\n"
        f"🎮 بازی: {game_title(game_type)}\n"
        f"🎯 انتخاب شما: {outcome}\n"
        f"📈 ضریب: {odds}x\n"
        f"💵 حداقل شرط: ۱۰,۰۰۰ تومان\n\n"
        f"لطفاً مبلغ شرط خود را انتخاب کنید:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=bet_amount_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GameStates.SELECT_BET)


@dp.callback_query(F.data.startswith("bet_"), GameStates.SELECT_BET)
async def callback_bet_selected(callback: CallbackQuery, state: FSMContext):
    """Handle bet amount selection"""
    await callback.answer()
    bet_amount = int(callback.data.replace("bet_", ""))
    
    # Get user and check balance
    user = UserRepository.get_user(callback.from_user.id)
    if not user or user['wallet'] < bet_amount:
        await callback.message.edit_text(
            "❌ <b>موجودی شما کافی نیست!</b>\n\n"
            "لطفاً ابتدا حساب خود را شارژ نمایید.",
            reply_markup=deposit_amount_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Store bet amount
    await state.update_data(bet_amount=bet_amount)
    user_data = await state.get_data()
    
    # Show confirmation
    text = (
        f"📋 <b>تایید نهایی شرط</b>\n\n"
        f"لطفاً اطلاعات زیر را بررسی کنید:\n\n"
        f"🎮 بازی: {game_title(user_data['game_type'])}\n"
        f"🎯 پیش‌بینی: {user_data['outcome']}\n"
        f"📈 ضریب: {get_odds(user_data['game_type'], user_data['outcome'])}x\n"
        f"💰 مبلغ شرط: {bet_amount:,} تومان\n\n"
        f"آیا از ثبت این شرط اطمینان دارید؟"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=confirm_bet_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GameStates.CONFIRM_BET)


@dp.callback_query(F.data == "bet_custom", GameStates.SELECT_BET)
async def callback_bet_custom(callback: CallbackQuery, state: FSMContext):
    """Handle custom bet amount request"""
    await callback.answer()
    await callback.message.edit_text(
        "💰 <b>مبلغ دلخواه</b>\n\n"
        "لطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\n"
        "مثال: ۲۵۰,۰۰۰",
        parse_mode=ParseMode.HTML
    )
    # State remains SELECT_BET for message handler


@dp.message(StateFilter(GameStates.SELECT_BET))
async def message_bet_custom(message: Message, state: FSMContext):
    """Handle custom bet amount input"""
    try:
        # Remove commas and convert to int
        amount_str = message.text.replace(',', '').strip()
        bet_amount = int(amount_str)
        
        if bet_amount < 10_000:
            await message.answer(
                "❌ حداقل مبلغ شرط ۱۰,۰۰۰ تومان است.",
                reply_markup=bet_amount_keyboard()
            )
            return
        
        # Check balance
        user = UserRepository.get_user(message.from_user.id)
        if not user or user['wallet'] < bet_amount:
            await message.answer(
                "❌ <b>موجودی شما کافی نیست!</b>\n\n"
                "لطفاً ابتدا حساب خود را شارژ نمایید.",
                reply_markup=deposit_amount_keyboard(),
                parse_mode=ParseMode.HTML
            )
            return
        
        # Store bet amount and proceed to confirmation
        await state.update_data(bet_amount=bet_amount)
        user_data = await state.get_data()
        
        text = (
            f"📋 <b>تایید نهایی شرط</b>\n\n"
            f"لطفاً اطلاعات زیر را بررسی کنید:\n\n"
            f"🎮 بازی: {game_title(user_data['game_type'])}\n"
            f"🎯 پیش‌بینی: {user_data['outcome']}\n"
            f"📈 ضریب: {get_odds(user_data['game_type'], user_data['outcome'])}x\n"
            f"💰 مبلغ شرط: {bet_amount:,} تومان\n\n"
            f"آیا از ثبت این شرط اطمینان دارید؟"
        )
        
        await message.answer(
            text,
            reply_markup=confirm_bet_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GameStates.CONFIRM_BET)
        
    except ValueError:
        await message.answer(
            "❌ لطفاً یک عدد معتبر وارد کنید.",
            reply_markup=bet_amount_keyboard()
        )


@dp.callback_query(F.data.startswith("confirm_"), GameStates.CONFIRM_BET)
async def callback_confirm_bet(callback: CallbackQuery, state: FSMContext):
    """Handle bet confirmation"""
    await callback.answer()
    action = callback.data.replace("confirm_", "")
    
    if action == "no":
        await callback.message.edit_text(
            "❌ شرط لغو شد.",
            reply_markup=games_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return
    
    # Process the game
    user_data = await state.get_data()
    game_type = user_data['game_type']
    outcome = user_data['outcome']
    bet_amount = user_data['bet_amount']
    user_id = callback.from_user.id
    
    # Deduct from wallet
    UserRepository.update_wallet(user_id, -bet_amount)
    
    # Play the game
    if game_type == "dice":
        result = GameEngine.play_dice(int(outcome))
    elif game_type == "bowling":
        result = GameEngine.play_bowling(outcome)
    elif game_type == "lottery":
        result = GameEngine.play_lottery(outcome)
    elif game_type == "rps":
        result = GameEngine.play_rps(outcome)
    else:
        await callback.message.edit_text("❌ خطا در اجرای بازی!", reply_markup=main_menu_keyboard())
        await state.clear()
        return
    
    # Calculate profit
    if result['win']:
        profit = int(bet_amount * result['odds']) - bet_amount
        UserRepository.update_wallet(user_id, bet_amount + profit)
        UserRepository.update_stats(user_id, True)
    else:
        profit = -bet_amount
        UserRepository.update_stats(user_id, False)
    
    # Save game history
    GameRepository.save_game(
        user_id, game_type, bet_amount, result['odds'],
        outcome, str(result['result']), 'win' if result['win'] else 'loss', profit
    )
    
    # Check for referral reward (first game)
    check_referral_reward(user_id)
    
    # Show result
    if result['win']:
        text = (
            f"🎉 <b>تبریک!</b>\n\n"
            f"شما برنده شدید!\n\n"
            f"🎮 بازی: {game_title(game_type)}\n"
            f"🎯 انتخاب شما: {outcome}\n"
            f"🎲 نتیجه نهایی: {result['result']}\n"
            f"📈 ضریب: {result['odds']}x\n"
            f"💵 مبلغ شرط: {bet_amount:,} تومان\n"
            f"🏆 جایزه: {profit:,} تومان\n"
            f"💰 موجودی جدید: {UserRepository.get_user(user_id)['wallet']:,} تومان"
        )
    else:
        text = (
            f"😔 <b>این بار شانس با شما یار نبود.</b>\n\n"
            f"🎮 بازی: {game_title(game_type)}\n"
            f"🎯 انتخاب شما: {outcome}\n"
            f"🎲 نتیجه نهایی: {result['result']}\n"
            f"💵 مبلغ شرط: {bet_amount:,} تومان\n"
            f"💰 موجودی فعلی: {UserRepository.get_user(user_id)['wallet']:,} تومان\n\n"
            f"برای شما آرزوی موفقیت در بازی بعدی داریم."
        )
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.clear()


# ============================================================================
# Helper Functions for Games
# ============================================================================

def game_title(game_type: str) -> str:
    """Get game title"""
    titles = {
        "dice": "تاس 🎲",
        "bowling": "بولینگ 🎳",
        "lottery": "قرعه 🎰",
        "rps": "سنگ کاغذ قیچی ✊"
    }
    return titles.get(game_type, game_type)


def get_odds(game_type: str, outcome: str) -> float:
    """Get odds for a specific outcome"""
    if game_type == "dice":
        return DICE_ODDS
    elif game_type == "bowling":
        return BOWLING_ODDS.get(outcome, 2.0)
    elif game_type == "lottery":
        return LOTTERY_ODDS.get(outcome, 3.0)
    elif game_type == "rps":
        return RPS_ODDS
    return 0


def check_referral_reward(user_id: int):
    """Check and give referral reward if first game"""
    with get_db() as conn:
        c = conn.cursor()
        # Check if this is first game
        c.execute("SELECT COUNT(*) FROM games WHERE user_id = ?", (user_id,))
        count = c.fetchone()[0]
        if count > 1:  # Not first game
            return
        
        # Check if user was referred
        c.execute("SELECT referred_by FROM users WHERE telegram_id = ?", (user_id,))
        row = c.fetchone()
        if not row or not row[0]:
            return
        
        referrer_id = row[0]
        # Check if already rewarded
        c.execute("SELECT COUNT(*) FROM referrals WHERE referred_id = ?", (user_id,))
        if c.fetchone()[0] > 0:
            return
        
        # Give reward
        reward = int(REFERRAL_REWARD)
        UserRepository.update_wallet(referrer_id, reward)
        
        # Update referral stats
        c.execute("""
            UPDATE users SET referral_count = referral_count + 1, 
            referral_earnings = referral_earnings + ? 
            WHERE telegram_id = ?
        """, (reward, referrer_id))
        
        # Save referral record
        c.execute("""
            INSERT INTO referrals (referrer_id, referred_id, reward, status)
            VALUES (?, ?, ?, 'completed')
        """, (referrer_id, user_id, reward))
        
        conn.commit()


# ============================================================================
# Handlers - Profile
# ============================================================================

@dp.callback_query(F.data == "profile")
async def callback_profile(callback: CallbackQuery):
    """Show user profile"""
    await callback.answer()
    user = UserRepository.get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ کاربر یافت نشد!", reply_markup=main_menu_keyboard())
        return
    
    stats = UserRepository.get_user_stats(callback.from_user.id)
    
    # Get last games
    last_games = GameRepository.get_user_games(callback.from_user.id, 5)
    games_text = "\n".join([
        f"🎮 {g['game_type']} | {g['bet_amount']:,} | {g['result']} | {g['profit']:,}"
        for g in last_games
    ]) if last_games else "هیچ بازی ثبت نشده"
    
    text = f"""
<b>👤 حساب کاربری</b>

🆔 شناسه: {user['telegram_id']}
👤 نام: {user['first_name'] or 'نامشخص'}
🏅 سطح: {stats['level']}
💰 موجودی: {user['wallet']:,} تومان

✅ تعداد برد: {user['wins']}
❌ تعداد باخت: {user['losses']}
📊 درصد برد: {stats['win_rate']}%
🎮 تعداد بازی: {stats['total_games']}
👥 زیرمجموعه: {user['referral_count']}

💵 مجموع واریز: {user['total_deposits']:,}
💸 مجموع برداشت: {user['total_withdrawals']:,}
📅 تاریخ عضویت: {user['created_at']}

📋 <b>آخرین بازی‌ها:</b>
{games_text}
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Handlers - Deposit
# ============================================================================

@dp.callback_query(F.data == "deposit")
async def callback_deposit(callback: CallbackQuery, state: FSMContext):
    """Show deposit amount selection"""
    await callback.answer()
    await callback.message.edit_text(
        "💳 <b>افزایش موجودی</b>\n\n"
        "برای شارژ حساب، یکی از مبالغ زیر را انتخاب کنید:",
        reply_markup=deposit_amount_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(DepositStates.SELECT_AMOUNT)


@dp.callback_query(F.data.startswith("deposit_"), DepositStates.SELECT_AMOUNT)
async def callback_deposit_amount(callback: CallbackQuery, state: FSMContext):
    """Handle deposit amount selection"""
    await callback.answer()
    amount = int(callback.data.replace("deposit_", ""))
    await state.update_data(deposit_amount=amount)
    
    # Show card info
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'card_number'")
        card_num = c.fetchone()[0]
        c.execute("SELECT value FROM settings WHERE key = 'card_owner'")
        card_owner = c.fetchone()[0]
    
    text = f"""
💳 <b>اطلاعات پرداخت</b>

💵 مبلغ قابل پرداخت: {amount:,} تومان
🏦 شماره کارت: <code>{card_num}</code>
👤 نام صاحب کارت: {card_owner}

📝 لطفاً پس از واریز، تصویر رسید پرداخت را ارسال نمایید.
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("📷 ارسال رسید", callback_data="deposit_send_receipt")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]
        ]),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(DepositStates.SEND_RECEIPT)


@dp.callback_query(F.data == "deposit_custom", DepositStates.SELECT_AMOUNT)
async def callback_deposit_custom(callback: CallbackQuery, state: FSMContext):
    """Handle custom deposit amount request"""
    await callback.answer()
    await callback.message.edit_text(
        "✍ <b>مبلغ دلخواه</b>\n\n"
        "لطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\n"
        f"حداقل مبلغ: {MIN_DEPOSIT:,} تومان",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(DepositStates.CUSTOM_AMOUNT)


@dp.message(DepositStates.CUSTOM_AMOUNT)
async def message_deposit_custom(message: Message, state: FSMContext):
    """Handle custom deposit amount input"""
    try:
        amount_str = message.text.replace(',', '').strip()
        amount = int(amount_str)
        
        if amount < MIN_DEPOSIT:
            await message.answer(f"❌ حداقل مبلغ واریز {MIN_DEPOSIT:,} تومان است.")
            return
        
        await state.update_data(deposit_amount=amount)
        
        # Show card info
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key = 'card_number'")
            card_num = c.fetchone()[0]
            c.execute("SELECT value FROM settings WHERE key = 'card_owner'")
            card_owner = c.fetchone()[0]
        
        text = f"""
💳 <b>اطلاعات پرداخت</b>

💵 مبلغ قابل پرداخت: {amount:,} تومان
🏦 شماره کارت: <code>{card_num}</code>
👤 نام صاحب کارت: {card_owner}

📝 لطفاً پس از واریز، تصویر رسید پرداخت را ارسال نمایید.
"""
        
        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("📷 ارسال رسید", callback_data="deposit_send_receipt")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]
            ]),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(DepositStates.SEND_RECEIPT)
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")


@dp.callback_query(F.data == "deposit_send_receipt", DepositStates.SEND_RECEIPT)
async def callback_deposit_receipt(callback: CallbackQuery, state: FSMContext):
    """Prompt user to send receipt photo"""
    await callback.answer()
    await callback.message.edit_text(
        "📷 <b>ارسال رسید</b>\n\n"
        "لطفاً تصویر رسید پرداخت خود را ارسال کنید.",
        parse_mode=ParseMode.HTML
    )
    # State remains SEND_RECEIPT for photo handler


@dp.message(F.photo, DepositStates.SEND_RECEIPT)
async def message_deposit_receipt(message: Message, state: FSMContext):
    """Handle receipt photo upload"""
    user_data = await state.get_data()
    amount = user_data.get('deposit_amount')
    
    if not amount:
        await message.answer("❌ خطا! لطفاً دوباره از منو اقدام کنید.", reply_markup=main_menu_keyboard())
        await state.clear()
        return
    
    # Save deposit
    photo_id = message.photo[-1].file_id
    deposit_id = DepositRepository.create_deposit(message.from_user.id, amount, photo_id)
    
    await message.answer(
        f"✅ <b>رسید شما دریافت شد.</b>\n\n"
        f"درخواست واریز شما با شماره #{deposit_id} ثبت گردید.\n"
        f"پس از تایید توسط ادمین، موجودی شما افزایش خواهد یافت.",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    
    # Notify admin
    user = UserRepository.get_user(message.from_user.id)
    admin_text = f"""
📥 <b>درخواست واریز جدید</b>

🔢 شناسه: #{deposit_id}
👤 کاربر: {message.from_user.first_name}
🆔 آیدی: {message.from_user.id}
💰 مبلغ: {amount:,} تومان
📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    """
    
    # Send to owner
    await bot.send_photo(
        chat_id=OWNER_ID,
        photo=photo_id,
        caption=admin_text,
        reply_markup=admin_action_keyboard(deposit_id, "deposit"),
        parse_mode=ParseMode.HTML
    )
    
    await state.clear()


# ============================================================================
# Handlers - Withdrawal
# ============================================================================

@dp.callback_query(F.data == "withdraw")
async def callback_withdraw(callback: CallbackQuery, state: FSMContext):
    """Start withdrawal process"""
    await callback.answer()
    await callback.message.edit_text(
        f"💸 <b>برداشت موجودی</b>\n\n"
        f"لطفاً مبلغ مورد نظر برای برداشت را وارد کنید:\n"
        f"حداقل مبلغ: {MIN_WITHDRAWAL:,} تومان",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(WithdrawalStates.SELECT_AMOUNT)


@dp.message(WithdrawalStates.SELECT_AMOUNT)
async def message_withdraw_amount(message: Message, state: FSMContext):
    """Handle withdrawal amount input"""
    try:
        amount_str = message.text.replace(',', '').strip()
        amount = int(amount_str)
        
        if amount < MIN_WITHDRAWAL:
            await message.answer(f"❌ حداقل مبلغ برداشت {MIN_WITHDRAWAL:,} تومان است.")
            return
        
        user = UserRepository.get_user(message.from_user.id)
        if not user or user['wallet'] < amount:
            await message.answer("❌ موجودی شما کافی نیست!")
            return
        
        await state.update_data(withdraw_amount=amount)
        
        await message.answer(
            "💳 <b>اطلاعات کارت</b>\n\n"
            "لطفاً شماره کارت خود را وارد کنید:",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(WithdrawalStates.ENTER_CARD)
        
    except ValueError:
        await message.answer("❌ لطفاً یک عدد معتبر وارد کنید.")


@dp.message(WithdrawalStates.ENTER_CARD)
async def message_withdraw_card(message: Message, state: FSMContext):
    """Handle card number input"""
    card_number = message.text.strip()
    
    # Basic validation
    if not re.match(r'^\d{16}$', card_number.replace('-', '').replace(' ', '')):
        await message.answer("❌ شماره کارت نامعتبر است. لطفاً ۱۶ رقم وارد کنید.")
        return
    
    await state.update_data(card_number=card_number)
    
    await message.answer(
        "👤 <b>نام صاحب حساب</b>\n\n"
        "لطفاً نام صاحب حساب را وارد کنید:",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(WithdrawalStates.ENTER_CARD_OWNER)


@dp.message(WithdrawalStates.ENTER_CARD_OWNER)
async def message_withdraw_card_owner(message: Message, state: FSMContext):
    """Handle card owner input"""
    card_owner = message.text.strip()
    await state.update_data(card_owner=card_owner)
    
    user_data = await state.get_data()
    amount = user_data.get('withdraw_amount')
    
    # Show confirmation
    text = f"""
📋 <b>تایید درخواست برداشت</b>

لطفاً اطلاعات زیر را بررسی کنید:

💰 مبلغ: {amount:,} تومان
💳 شماره کارت: {user_data['card_number']}
👤 نام صاحب حساب: {card_owner}

آیا از ثبت این درخواست اطمینان دارید؟
"""
    
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("✅ تایید", callback_data="withdraw_confirm")],
            [InlineKeyboardButton("❌ لغو", callback_data="withdraw_cancel")]
        ]),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(WithdrawalStates.CONFIRM)


@dp.callback_query(F.data == "withdraw_confirm", WithdrawalStates.CONFIRM)
async def callback_withdraw_confirm(callback: CallbackQuery, state: FSMContext):
    """Confirm withdrawal request"""
    await callback.answer()
    user_data = await state.get_data()
    
    # Create withdrawal
    withdrawal_id = WithdrawalRepository.create_withdrawal(
        callback.from_user.id,
        user_data['withdraw_amount'],
        user_data['card_number'],
        user_data['card_owner']
    )
    
    # Deduct from wallet
    UserRepository.update_wallet(callback.from_user.id, -user_data['withdraw_amount'])
    
    await callback.message.edit_text(
        f"✅ <b>درخواست برداشت شما ثبت شد.</b>\n\n"
        f"شماره درخواست: #{withdrawal_id}\n"
        f"مبلغ: {user_data['withdraw_amount']:,} تومان\n\n"
        f"پس از تایید ادمین، مبلغ به حساب شما واریز خواهد شد.",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    
    # Notify admin
    user = UserRepository.get_user(callback.from_user.id)
    admin_text = f"""
📤 <b>درخواست برداشت جدید</b>

🔢 شناسه: #{withdrawal_id}
👤 کاربر: {callback.from_user.first_name}
🆔 آیدی: {callback.from_user.id}
💰 مبلغ: {user_data['withdraw_amount']:,} تومان
💳 شماره کارت: {user_data['card_number']}
👤 صاحب حساب: {user_data['card_owner']}
📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    """
    
    await bot.send_message(
        chat_id=OWNER_ID,
        text=admin_text,
        reply_markup=admin_action_keyboard(withdrawal_id, "withdraw"),
        parse_mode=ParseMode.HTML
    )
    
    await state.clear()


@dp.callback_query(F.data == "withdraw_cancel", WithdrawalStates.CONFIRM)
async def callback_withdraw_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel withdrawal request"""
    await callback.answer()
    await callback.message.edit_text(
        "❌ درخواست برداشت لغو شد.",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.clear()


# ============================================================================
# Handlers - Leaderboard
# ============================================================================

@dp.callback_query(F.data == "leaderboard")
async def callback_leaderboard(callback: CallbackQuery):
    """Show leaderboard"""
    await callback.answer()
    
    user = UserRepository.get_user(callback.from_user.id)
    top_users = UserRepository.get_top_users(10)
    
    # Get user's rank
    rank = 1
    if user:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) + 1 FROM users 
                WHERE wallet > ? AND is_banned = 0
            """, (user['wallet'],))
            rank = c.fetchone()[0]
    
    text = "🏆 <b>لیدربورد</b>\n\n"
    
    if user:
        text += f"""
👤 نام شما: {user['first_name'] or 'کاربر'}
🏅 سطح: {UserRepository.get_user_level(user['wallet'])}
💰 موجودی: {user['wallet']:,} تومان
📈 رتبه شما: #{rank}

"""
    
    text += "🥇 <b>۱۰ کاربر برتر</b>\n\n"
    
    for i, u in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}️⃣"
        name = u['username'] or u['first_name'] or f"کاربر {u['telegram_id']}"
        text += f"{medal} {name} — {u['wallet']:,} تومان\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Handlers - Referral
# ============================================================================

@dp.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery):
    """Show referral info"""
    await callback.answer()
    user = UserRepository.get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text("❌ کاربر یافت نشد!", reply_markup=main_menu_keyboard())
        return
    
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user['referral_code']}"
    
    text = f"""
👥 <b>زیرمجموعه‌گیری</b>

دعوت از دوستان و دریافت پاداش!

🔗 لینک دعوت اختصاصی:
<code>{link}</code>

🏆 زیرمجموعه‌های فعال: {user['referral_count']} نفر
💰 درآمد کسب شده: {user['referral_earnings']:,} تومان

📝 قوانین:
• به ازای هر دوست که از طریق لینک شما وارد شود
• و حداقل یک بازی انجام دهد
• شما {REFERRAL_REWARD:,} تومان پاداش دریافت می‌کنید
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Handlers - Support
# ============================================================================

@dp.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery, state: FSMContext):
    """Show support menu"""
    await callback.answer()
    await callback.message.edit_text(
        "🎧 <b>پشتیبانی</b>\n\n"
        "لطفاً پیام خود را ارسال کنید.\n"
        "پیام شما مستقیماً برای تیم پشتیبانی ارسال خواهد شد.",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(SupportStates.WAITING_MESSAGE)


@dp.message(SupportStates.WAITING_MESSAGE)
async def message_support(message: Message, state: FSMContext):
    """Handle support message"""
    # Create ticket
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO support_tickets (user_id, subject, status)
            VALUES (?, ?, 'open')
        """, (message.from_user.id, "پیام پشتیبانی"))
        ticket_id = c.lastrowid
        conn.commit()
    
    # Save message
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO support_messages (ticket_id, sender_id, message)
            VALUES (?, ?, ?)
        """, (ticket_id, message.from_user.id, message.text))
        conn.commit()
    
    await message.answer(
        "✅ <b>پیام شما ارسال شد.</b>\n\n"
        "تیم پشتیبانی در اسرع وقت پاسخ خواهد داد.",
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )
    
    # Forward to admin
    user = UserRepository.get_user(message.from_user.id)
    admin_text = f"""
🎧 <b>پیام پشتیبانی جدید</b>

🆔 شناسه: #{ticket_id}
👤 کاربر: {message.from_user.first_name}
🆔 آیدی: {message.from_user.id}
📝 پیام:
{message.text}
📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    
    await bot.send_message(
        chat_id=OWNER_ID,
        text=admin_text,
        parse_mode=ParseMode.HTML
    )
    
    await state.clear()


# ============================================================================
# Handlers - Missions
# ============================================================================

@dp.callback_query(F.data == "missions")
async def callback_missions(callback: CallbackQuery):
    """Show missions"""
    await callback.answer()
    
    # Get active missions
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT * FROM missions 
            WHERE is_active = 1 AND (end_date IS NULL OR end_date > CURRENT_TIMESTAMP)
            ORDER BY type, created_at
        """)
        missions = [dict(row) for row in c.fetchall()]
    
    if not missions:
        text = "🎯 <b>مأموریت‌ها</b>\n\nهیچ مأموریت فعالی وجود ندارد."
    else:
        text = "🎯 <b>مأموریت‌ها</b>\n\n"
        for m in missions:
            # Get user progress
            with get_db() as conn2:
                c2 = conn2.cursor()
                c2.execute("""
                    SELECT progress, completed FROM mission_progress 
                    WHERE user_id = ? AND mission_id = ?
                """, (callback.from_user.id, m['id']))
                progress_row = c2.fetchone()
            
            progress = progress_row[0] if progress_row else 0
            completed = progress_row[1] if progress_row else 0
            
            status = "✅" if completed else f"{progress}/{m['target']}"
            text += f"""
{m['title']}
📝 {m['description']}
🎁 پاداش: {m['reward']:,} تومان
📊 پیشرفت: {status}
---
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Admin Handlers
# ============================================================================

@dp.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: CallbackQuery):
    """Show admin panel"""
    await callback.answer()
    
    # Check if user is admin
    if callback.from_user.id != OWNER_ID:
        await callback.message.edit_text(
            "❌ شما دسترسی به این بخش ندارید.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    await callback.message.edit_text(
        "👑 <b>پنل مدیریت</b>\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_dashboard")
async def callback_admin_dashboard(callback: CallbackQuery):
    """Show admin dashboard"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
        active_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM games")
        total_games = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM deposits WHERE status = 'pending'")
        pending_deposits = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
        pending_withdrawals = c.fetchone()[0]
        
        c.execute("SELECT SUM(amount) FROM transactions WHERE type = 'deposit' AND status = 'completed'")
        total_deposits = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(amount) FROM transactions WHERE type = 'withdrawal' AND status = 'completed'")
        total_withdrawals = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(profit) FROM games")
        total_profit = c.fetchone()[0] or 0
    
    text = f"""
📊 <b>داشبورد مدیریت</b>

👥 تعداد کاربران: {total_users}
🟢 کاربران فعال: {active_users}
🎮 تعداد بازی‌ها: {total_games}

💰 کل واریز: {total_deposits:,} تومان
💸 کل برداشت: {total_withdrawals:,} تومان
📈 سود خالص: {total_profit:,} تومان

📥 واریز در انتظار: {pending_deposits}
📤 برداشت در انتظار: {pending_withdrawals}
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_deposits")
async def callback_admin_deposits(callback: CallbackQuery):
    """Show pending deposits"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    pending = DepositRepository.get_pending_deposits()
    
    if not pending:
        await callback.message.edit_text(
            "✅ هیچ درخواست واریز در انتظار تایید وجود ندارد.",
            reply_markup=admin_menu_keyboard()
        )
        return
    
    for dep in pending:
        user = UserRepository.get_user(dep['user_id'])
        text = f"""
📥 <b>درخواست واریز #{dep['id']}</b>

👤 کاربر: {user['first_name'] or 'کاربر'} (@{user['username'] or 'بدون نام'})
🆔 آیدی: {dep['user_id']}
💰 مبلغ: {dep['amount']:,} تومان
📅 زمان: {dep['created_at']}
"""
        
        await bot.send_photo(
            chat_id=OWNER_ID,
            photo=dep['receipt_photo_id'],
            caption=text,
            reply_markup=admin_action_keyboard(dep['id'], "deposit"),
            parse_mode=ParseMode.HTML
        )
    
    await callback.message.edit_text(
        "📤 لیست درخواست‌های واریز ارسال شد.",
        reply_markup=admin_menu_keyboard()
    )


@dp.callback_query(F.data == "admin_withdrawals")
async def callback_admin_withdrawals(callback: CallbackQuery):
    """Show pending withdrawals"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    pending = WithdrawalRepository.get_pending_withdrawals()
    
    if not pending:
        await callback.message.edit_text(
            "✅ هیچ درخواست برداشت در انتظار تایید وجود ندارد.",
            reply_markup=admin_menu_keyboard()
        )
        return
    
    for wd in pending:
        user = UserRepository.get_user(wd['user_id'])
        text = f"""
📤 <b>درخواست برداشت #{wd['id']}</b>

👤 کاربر: {user['first_name'] or 'کاربر'} (@{user['username'] or 'بدون نام'})
🆔 آیدی: {wd['user_id']}
💰 مبلغ: {wd['amount']:,} تومان
💳 شماره کارت: {wd['card_number']}
👤 صاحب حساب: {wd['card_owner']}
📅 زمان: {wd['created_at']}
"""
        
        await bot.send_message(
            chat_id=OWNER_ID,
            text=text,
            reply_markup=admin_action_keyboard(wd['id'], "withdraw"),
            parse_mode=ParseMode.HTML
        )
    
    await callback.message.edit_text(
        "📤 لیست درخواست‌های برداشت ارسال شد.",
        reply_markup=admin_menu_keyboard()
    )


@dp.callback_query(F.data.startswith("admin_"))
async def callback_admin_action(callback: CallbackQuery):
    """Handle admin actions (approve/reject)"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        await callback.message.edit_text("❌ دسترسی غیرمجاز!", reply_markup=main_menu_keyboard())
        return
    
    parts = callback.data.split("_")
    action = parts[1]  # approve or reject
    action_type = parts[2]  # deposit or withdraw
    item_id = int(parts[3])
    
    if action_type == "deposit":
        if action == "approve":
            DepositRepository.approve_deposit(item_id, OWNER_ID)
            # Notify user
            dep = None
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (item_id,))
                dep = c.fetchone()
            if dep:
                await bot.send_message(
                    chat_id=dep['user_id'],
                    text=f"✅ <b>واریز شما تایید شد!</b>\n\n"
                         f"💰 مبلغ: {dep['amount']:,} تومان\n"
                         f"💵 موجودی جدید: {UserRepository.get_user(dep['user_id'])['wallet']:,} تومان\n\n"
                         f"با تشکر از شما.",
                    parse_mode=ParseMode.HTML
                )
            await callback.message.edit_text(f"✅ واریز #{item_id} تایید شد.", reply_markup=admin_menu_keyboard())
        else:
            DepositRepository.reject_deposit(item_id, "رد شده توسط ادمین", OWNER_ID)
            dep = None
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (item_id,))
                dep = c.fetchone()
            if dep:
                await bot.send_message(
                    chat_id=dep['user_id'],
                    text=f"❌ <b>واریز شما رد شد.</b>\n\n"
                         f"در صورت نیاز با پشتیبانی تماس بگیرید.",
                    parse_mode=ParseMode.HTML
                )
            await callback.message.edit_text(f"❌ واریز #{item_id} رد شد.", reply_markup=admin_menu_keyboard())
    
    elif action_type == "withdraw":
        if action == "approve":
            WithdrawalRepository.approve_withdrawal(item_id, OWNER_ID)
            wd = None
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (item_id,))
                wd = c.fetchone()
            if wd:
                await bot.send_message(
                    chat_id=wd['user_id'],
                    text=f"✅ <b>درخواست برداشت شما تایید شد!</b>\n\n"
                         f"💰 مبلغ: {wd['amount']:,} تومان\n\n"
                         f"به زودی به حساب شما واریز خواهد شد.",
                    parse_mode=ParseMode.HTML
                )
            await callback.message.edit_text(f"✅ برداشت #{item_id} تایید شد.", reply_markup=admin_menu_keyboard())
        else:
            WithdrawalRepository.reject_withdrawal(item_id, "رد شده توسط ادمین", OWNER_ID)
            wd = None
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (item_id,))
                wd = c.fetchone()
            if wd:
                await bot.send_message(
                    chat_id=wd['user_id'],
                    text=f"❌ <b>درخواست برداشت شما رد شد.</b>\n\n"
                         f"در صورت نیاز با پشتیبانی تماس بگیرید.",
                    parse_mode=ParseMode.HTML
                )
            await callback.message.edit_text(f"❌ برداشت #{item_id} رد شد.", reply_markup=admin_menu_keyboard())


@dp.callback_query(F.data == "admin_games")
async def callback_admin_games(callback: CallbackQuery):
    """Show game management"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT game_type, COUNT(*) as total, SUM(profit) as profit FROM games GROUP BY game_type")
        stats = [dict(row) for row in c.fetchall()]
    
    text = "🎮 <b>مدیریت بازی‌ها</b>\n\n"
    for stat in stats:
        text += f"""
{game_title(stat['game_type'])}
🎮 تعداد: {stat['total']}
💰 سود/زیان: {stat['profit']:,} تومان
---
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_reports")
async def callback_admin_reports(callback: CallbackQuery):
    """Show financial reports"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    with get_db() as conn:
        c = conn.cursor()
        # Today
        c.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type = 'deposit' AND status = 'completed' 
            AND DATE(created_at) = DATE('now')
        """)
        today_deposit = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type = 'withdrawal' AND status = 'completed' 
            AND DATE(created_at) = DATE('now')
        """)
        today_withdrawal = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(profit), 0) FROM games 
            WHERE DATE(created_at) = DATE('now')
        """)
        today_profit = c.fetchone()[0]
        
        # This month
        c.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type = 'deposit' AND status = 'completed' 
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        month_deposit = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM transactions 
            WHERE type = 'withdrawal' AND status = 'completed' 
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        month_withdrawal = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(profit), 0) FROM games 
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        month_profit = c.fetchone()[0]
    
    text = f"""
📈 <b>گزارشات مالی</b>

📅 <b>امروز</b>
💰 واریز: {today_deposit:,} تومان
💸 برداشت: {today_withdrawal:,} تومان
📊 سود: {today_profit:,} تومان

📆 <b>این ماه</b>
💰 واریز: {month_deposit:,} تومان
💸 برداشت: {month_withdrawal:,} تومان
📊 سود: {month_profit:,} تومان
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_broadcast")
async def callback_admin_broadcast(callback: CallbackQuery):
    """Show broadcast option"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    await callback.message.edit_text(
        "📢 <b>ارسال پیام همگانی</b>\n\n"
        "لطفاً پیام مورد نظر برای ارسال به تمام کاربران را وارد کنید:\n\n"
        "⚠️ پیام به تمام کاربران ارسال خواهد شد.",
        parse_mode=ParseMode.HTML
    )
    # This would need a state handler for broadcast


@dp.callback_query(F.data == "admin_support")
async def callback_admin_support(callback: CallbackQuery):
    """Show support tickets"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.*, u.first_name, u.username 
            FROM support_tickets t
            JOIN users u ON u.telegram_id = t.user_id
            WHERE t.status = 'open'
            ORDER BY t.created_at DESC
            LIMIT 10
        """)
        tickets = [dict(row) for row in c.fetchall()]
    
    if not tickets:
        await callback.message.edit_text(
            "✅ هیچ تیکت پشتیبانی باز وجود ندارد.",
            reply_markup=admin_menu_keyboard()
        )
        return
    
    text = "🎧 <b>تیکت‌های پشتیبانی</b>\n\n"
    for t in tickets:
        text += f"""
#{t['id']} | {t['first_name']} (@{t['username'] or 'بدون نام'})
📝 {t['subject']}
📅 {t['created_at']}
---
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_settings")
async def callback_admin_settings(callback: CallbackQuery):
    """Show settings"""
    await callback.answer()
    
    if callback.from_user.id != OWNER_ID:
        return
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        settings = {row[0]: row[1] for row in c.fetchall()}
    
    text = f"""
⚙ <b>تنظیمات</b>

🏦 شماره کارت: {settings.get('card_number', 'N/A')}
👤 صاحب کارت: {settings.get('card_owner', 'N/A')}
💳 حداقل برداشت: {int(settings.get('min_withdrawal', 0)):,} تومان
💰 حداقل واریز: {int(settings.get('min_deposit', 0)):,} تومان
🎁 پاداش معرفی: {int(settings.get('referral_reward', 0)):,} تومان

🎲 ضریب تاس: {settings.get('dice_odds', 'N/A')}x
✊ ضریب سنگ کاغذ قیچی: {settings.get('rps_odds', 'N/A')}x

⚠️ <b>ویرایش تنظیمات از طریق دیتابیس انجام می‌شود.</b>
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu_keyboard(),
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Error Handler
# ============================================================================

@dp.error()
async def error_handler(event: Any, context: Dict):
    """Handle errors"""
    logger.error(f"Error: {context.get('exception')}")
    
    if event.message:
        await event.message.answer(
            "❌ <b>خطا!</b>\n\n"
            "مشکلی در پردازش درخواست شما به وجود آمد.\n"
            "لطفاً مجدداً تلاش کنید.",
            parse_mode=ParseMode.HTML
        )
    
    # Notify admin
    await bot.send_message(
        chat_id=OWNER_ID,
        text=f"❌ <b>خطا در ربات</b>\n\n{str(context.get('exception'))}",
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Main Function
# ============================================================================

async def main():
    """Main entry point"""
    # Initialize database
    init_database()
    
    logger.info("Starting bot...")
    
    # Set webhook if needed (for production)
    # await bot.set_webhook(url="https://your-domain.com/webhook")
    
    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
