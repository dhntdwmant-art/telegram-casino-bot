import logging
import sqlite3
import random
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# --- Configuration ---
BOT_TOKEN = "8913431377:AAFTtSDcpRViooI359BFw8J7qdbpl58d5ls"
OWNER_ID = 7548145568
CARD_NUMBER = "6062561009737464"
CARD_OWNER = "مجاور"
MIN_WITHDRAWAL = 100_000  # تومان
BOT_USERNAME = "tasbist_bot"

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Database ---
DB_PATH = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            level TEXT DEFAULT '🥉 برنزی',
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            referral_earnings INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS games_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            bet_amount INTEGER,
            odds REAL,
            outcome TEXT,
            result TEXT,
            profit INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            receipt_photo_id TEXT,
            admin_comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            admin_comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_user_id INTEGER,
            amount INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('card_number', ?)", (CARD_NUMBER,))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('card_owner', ?)", (CARD_OWNER,))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_withdrawal', ?)", (str(MIN_WITHDRAWAL),))
    conn.commit()
    conn.close()

# --- Helper Functions ---
def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id: int, username: str = None, first_name: str = None, referred_by: int = None):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (id, username, first_name, referred_by) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, referred_by)
    )
    conn.commit()
    conn.close()

def update_user_balance(user_id: int, amount: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_user_stats(user_id: int, win: bool):
    conn = get_db()
    c = conn.cursor()
    if win:
        c.execute("UPDATE users SET wins = wins + 1 WHERE id = ?", (user_id,))
    else:
        c.execute("UPDATE users SET losses = losses + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_level(balance: int) -> str:
    if balance >= 500_000:
        return "🥇 طلایی"
    elif balance >= 100_000:
        return "🥈 نقره‌ای"
    else:
        return "🥉 برنزی"

def add_game_history(user_id: int, game_type: str, bet: int, odds: float, outcome: str, result: str, profit: int):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO games_history
           (user_id, game_type, bet_amount, odds, outcome, result, profit)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, game_type, bet, odds, outcome, result, profit)
    )
    conn.commit()
    conn.close()

def get_last_games(user_id: int, limit: int = 5) -> list:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT game_type, bet_amount, result, profit, created_at
           FROM games_history
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_top_users(limit: int = 5) -> list:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, username, first_name, balance FROM users ORDER BY balance DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_pending_deposits():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM deposits WHERE status = 'pending' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_pending_withdrawals():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY created_at ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def create_deposit(user_id: int, amount: int, photo_id: str) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO deposits (user_id, amount, receipt_photo_id) VALUES (?, ?, ?)",
        (user_id, amount, photo_id)
    )
    deposit_id = c.lastrowid
    conn.commit()
    conn.close()
    return deposit_id

def create_withdrawal(user_id: int, amount: int) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)",
        (user_id, amount)
    )
    withdrawal_id = c.lastrowid
    conn.commit()
    conn.close()
    return withdrawal_id

def approve_deposit(deposit_id: int, admin_comment: str = None):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE deposits SET status = 'approved', processed_at = CURRENT_TIMESTAMP, admin_comment = ? WHERE id = ?",
        (admin_comment, deposit_id)
    )
    c.execute("SELECT user_id, amount FROM deposits WHERE id = ?", (deposit_id,))
    row = c.fetchone()
    if row:
        user_id, amount = row
        update_user_balance(user_id, amount)
    conn.commit()
    conn.close()

def reject_deposit(deposit_id: int, admin_comment: str = None):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE deposits SET status = 'rejected', processed_at = CURRENT_TIMESTAMP, admin_comment = ? WHERE id = ?",
        (admin_comment, deposit_id)
    )
    conn.commit()
    conn.close()

def approve_withdrawal(withdrawal_id: int, admin_comment: str = None):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE withdrawals SET status = 'approved', processed_at = CURRENT_TIMESTAMP, admin_comment = ? WHERE id = ?",
        (admin_comment, withdrawal_id)
    )
    c.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (withdrawal_id,))
    row = c.fetchone()
    if row:
        user_id, amount = row
        update_user_balance(user_id, -amount)
    conn.commit()
    conn.close()

def reject_withdrawal(withdrawal_id: int, admin_comment: str = None):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE withdrawals SET status = 'rejected', processed_at = CURRENT_TIMESTAMP, admin_comment = ? WHERE id = ?",
        (admin_comment, withdrawal_id)
    )
    conn.commit()
    conn.close()

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def check_referral_earnings(user_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referral_earnings WHERE referred_user_id = ?", (user_id,))
    count = c.fetchone()[0]
    if count > 0:
        conn.close()
        return
    c.execute("SELECT referred_by FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0] is not None:
        referrer_id = row[0]
        reward = 10_000
        update_user_balance(referrer_id, reward)
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET referral_count = referral_count + 1, referral_earnings = referral_earnings + ? WHERE id = ?", (reward, referrer_id))
        c.execute("INSERT INTO referral_earnings (referrer_id, referred_user_id, amount) VALUES (?, ?, ?)", (referrer_id, user_id, reward))
        conn.commit()
        conn.close()

# --- Game Logic ---
DICE_ODDS = 5.0

def play_dice(prediction: int) -> Tuple[int, float, bool]:
    result = random.randint(1, 6)
    win = (result == prediction)
    return result, DICE_ODDS, win

BOWLING_OUTCOMES = [
    {"name": "افتادن 1 پین", "odds": 1.8, "weight": 40},
    {"name": "نیمی از پین", "odds": 3.0, "weight": 30},
    {"name": "خارج از لاین", "odds": 2.0, "weight": 30},
]

def play_bowling(prediction: str) -> Tuple[str, float, bool]:
    choices = [o["name"] for o in BOWLING_OUTCOMES]
    weights = [o["weight"] for o in BOWLING_OUTCOMES]
    result = random.choices(choices, weights=weights)[0]
    win = (result == prediction)
    odds = next(o["odds"] for o in BOWLING_OUTCOMES if o["name"] == result)
    return result, odds, win

LOTTERY_OUTCOMES = [
    {"name": "سه تا انگور", "odds": 2.0, "weight": 50},
    {"name": "یه تا 7", "odds": 3.0, "weight": 30},
    {"name": "دو تا هفت", "odds": 5.0, "weight": 15},
    {"name": "سه تا هفت", "odds": 10.0, "weight": 5},
]

def play_lottery(prediction: str) -> Tuple[str, float, bool]:
    choices = [o["name"] for o in LOTTERY_OUTCOMES]
    weights = [o["weight"] for o in LOTTERY_OUTCOMES]
    result = random.choices(choices, weights=weights)[0]
    win = (result == prediction)
    odds = next(o["odds"] for o in LOTTERY_OUTCOMES if o["name"] == result)
    return result, odds, win

RPS_CHOICES = ["سنگ", "کاغذ", "قیچی"]

def play_rps(user_choice: str) -> Tuple[str, float, bool, str]:
    beat_map = {"سنگ": "کاغذ", "کاغذ": "قیچی", "قیچی": "سنگ"}
    lose_map = {"سنگ": "قیچی", "کاغذ": "سنگ", "قیچی": "کاغذ"}
    r = random.random()
    if r < 0.6:
        bot_choice = beat_map[user_choice]
    elif r < 0.8:
        bot_choice = user_choice
    else:
        bot_choice = lose_map[user_choice]
    if bot_choice == user_choice:
        result = "draw"
        win = False
    elif (user_choice == "سنگ" and bot_choice == "قیچی") or \
         (user_choice == "کاغذ" and bot_choice == "سنگ") or \
         (user_choice == "قیچی" and bot_choice == "کاغذ"):
        result = "win"
        win = True
    else:
        result = "lose"
        win = False
    odds = 1.8 if win else 1.0 if result == "draw" else 0.0
    return bot_choice, odds, win, result

# --- Keyboard Builders ---
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎮 بازی‌ها", callback_data="games")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="profile")],
        [InlineKeyboardButton("💰 افزایش موجودی", callback_data="deposit")],
        [InlineKeyboardButton("💳 برداشت موجودی", callback_data="withdraw")],
        [InlineKeyboardButton("📊 لیدربورد", callback_data="leaderboard")],
        [InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="referral")],
        [InlineKeyboardButton("🎧 پشتیبانی", callback_data="support")],
    ]
    if OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 مدیریت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def games_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎲 تاس", callback_data="game_dice")],
        [InlineKeyboardButton("🎳 بولینگ", callback_data="game_bowling")],
        [InlineKeyboardButton("🎰 قرعه", callback_data="game_lottery")],
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game_rps")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def game_outcome_keyboard(game: str, outcomes: list):
    buttons = []
    for item in outcomes:
        if game == "dice":
            label = f"🎯 عدد {item}"
            callback = f"outcome_{game}_{item}"
        elif game in ["bowling", "lottery"]:
            label = f"🎯 {item['name']} ({item['odds']}x)"
            callback = f"outcome_{game}_{item['name']}"
        elif game == "rps":
            label = f"✊ {item}"
            callback = f"outcome_{game}_{item}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="games")])
    return InlineKeyboardMarkup(buttons)

def bet_amount_keyboard():
    amounts = [10, 50, 100, 150, 300, 500, 750, 1000, 2500, 5000]
    keyboard = []
    row = []
    for i, amt in enumerate(amounts):
        label = f"💰 {amt:,} تومان"
        row.append(InlineKeyboardButton(label, callback_data=f"bet_{amt}"))
        if (i+1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("💰 مبلغ دلخواه", callback_data="bet_custom")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="games")])
    return InlineKeyboardMarkup(keyboard)

def confirm_bet_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ تایید و شروع", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ لغو", callback_data="confirm_no")],
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 مدیریت واریز", callback_data="admin_deposits")],
        [InlineKeyboardButton("💳 مدیریت برداشت", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_action_keyboard(item_id: int, action_type: str):
    keyboard = [
        [InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{action_type}_{item_id}")],
        [InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{action_type}_{item_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Conversation States ---
(GAME_CHOOSE, GAME_BET, GAME_CONFIRM,
 DEPOSIT_AMOUNT, DEPOSIT_RECEIPT,
 WITHDRAW_AMOUNT) = range(6)

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""
    first_name = user.first_name or "کاربر"
    db_user = get_user(user_id)
    if not db_user:
        ref_id = None
        if context.args and context.args[0].startswith("ref_"):
            try:
                ref_id = int(context.args[0][4:])
                if ref_id == user_id:
                    ref_id = None
            except:
                pass
        create_user(user_id, username, first_name, ref_id)
    await update.message.reply_text(
        "🌟 به ربات بازی‌ها خوش آمدید!\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_keyboard()
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🌟 به ربات بازی‌ها خوش آمدید!\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu_keyboard()
    )

async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎮 بازی‌های موجود:\nلطفاً یک بازی را انتخاب کنید:",
        reply_markup=games_menu_keyboard()
    )

async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    game = query.data.split("_")[1]
    context.user_data["game"] = game
    
    if game == "dice":
        outcomes = [1,2,3,4,5,6]
        text = "🎯 مرحله اول: پیش‌بینی نتیجه\n\nبازی: تاس 🎲\nلطفاً عددی که فکر می‌کنید می‌افتد را انتخاب کنید:\n⚠️ شما فقط در صورتی برنده می‌شوید که دقیقاً همین عدد رخ دهد!"
        keyboard = game_outcome_keyboard("dice", outcomes)
    elif game == "bowling":
        outcomes = BOWLING_OUTCOMES
        text = "🎯 مرحله اول: پیش‌بینی نتیجه\n\nبازی: بولینگ 🎳\nلطفاً نتیجه‌ای که فکر می‌کنید رخ می‌دهد را انتخاب کنید:\n⚠️ شما فقط در صورتی برنده می‌شوید که دقیقاً همین اتفاق رخ دهد!"
        keyboard = game_outcome_keyboard("bowling", outcomes)
    elif game == "lottery":
        outcomes = LOTTERY_OUTCOMES
        text = "🎯 مرحله اول: پیش‌بینی نتیجه\n\nبازی: قرعه 🎰\nلطفاً نتیجه‌ای که فکر می‌کنید رخ می‌دهد را انتخاب کنید:\n⚠️ شما فقط در صورتی برنده می‌شوید که دقیقاً همین اتفاق رخ دهد!"
        keyboard = game_outcome_keyboard("lottery", outcomes)
    elif game == "rps":
        outcomes = RPS_CHOICES
        text = "🎯 مرحله اول: پیش‌بینی نتیجه\n\nبازی: سنگ کاغذ قیچی ✊\nلطفاً انتخاب خود را بکنید:"
        keyboard = game_outcome_keyboard("rps", outcomes)
    else:
        await query.edit_message_text("بازی نامعتبر!", reply_markup=main_menu_keyboard())
        return
    
    await query.edit_message_text(text, reply_markup=keyboard)
    return GAME_CHOOSE

async def game_outcome_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    game = data[1]
    choice = "_".join(data[2:])
    context.user_data["game_outcome"] = choice
    
    odds = None
    if game == "dice":
        odds = DICE_ODDS
        choice_display = f"عدد {choice}"
    elif game == "bowling":
        odds = next((o["odds"] for o in BOWLING_OUTCOMES if o["name"] == choice), None)
        choice_display = choice
    elif game == "lottery":
        odds = next((o["odds"] for o in LOTTERY_OUTCOMES if o["name"] == choice), None)
        choice_display = choice
    elif game == "rps":
        choice_display = choice
        odds = "متغیر"
    else:
        await query.edit_message_text("خطا!", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    context.user_data["game_odds"] = odds
    text = (
        f"🎯 مرحله دوم: تعیین مبلغ شرط\n\n"
        f"بازی: {game_title(game)}\n"
        f"پیش‌بینی شما: {choice_display}\n\n"
        f"📊 ضریب برد این حالت: {odds if odds else 'متغیر'}x\n"
        f"💰 حداقل مبلغ شرط: ۱۰ تومان\n\n"
        f"لطفاً مبلغ شرط خود را انتخاب نمایید:"
    )
    await query.edit_message_text(text, reply_markup=bet_amount_keyboard())
    return GAME_BET

def game_title(game: str) -> str:
    titles = {
        "dice": "تاس 🎲",
        "bowling": "بولینگ 🎳",
        "lottery": "قرعه 🎰",
        "rps": "سنگ کاغذ قیچی ✊"
    }
    return titles.get(game, game)

async def game_bet_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "bet_custom":
        await query.edit_message_text("لطفاً مبلغ مورد نظر خود را به عدد وارد کنید (حداقل ۱۰ تومان):")
        return GAME_BET
    elif data.startswith("bet_"):
        amount = int(data.split("_")[1])
        context.user_data["bet_amount"] = amount
        return await show_confirm(update, context)
    else:
        await query.edit_message_text("لطفاً از دکمه‌ها استفاده کنید.", reply_markup=bet_amount_keyboard())
        return GAME_BET

async def game_bet_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 10:
            await update.message.reply_text("حداقل مبلغ شرط ۱۰ تومان است. لطفاً عدد بزرگتر وارد کنید.")
            return GAME_BET
        context.user_data["bet_amount"] = amount
        return await show_confirm_message(update, context)
    except ValueError:
        await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید (مثال: ۱۰۰).")
        return GAME_BET

async def show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await show_confirm_message(query, context)

async def show_confirm_message(update_or_msg, context: ContextTypes.DEFAULT_TYPE):
    game = context.user_data["game"]
    outcome = context.user_data["game_outcome"]
    odds = context.user_data.get("game_odds", "متغیر")
    bet = context.user_data["bet_amount"]
    user_id = update_or_msg.effective_user.id
    user = get_user(user_id)
    
    if user["balance"] < bet:
        msg = "⚠️ موجودی شما کافی نیست! لطفاً حساب خود را شارژ کنید."
        if isinstance(update_or_msg, Update):
            await update_or_msg.message.reply_text(msg, reply_markup=main_menu_keyboard())
        else:
            await update_or_msg.edit_message_text(msg, reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    text = (
        f"📋 تایید نهایی پیش‌بینی\n\n"
        f"لطفاً اطلاعات شرط خود را پیش از شروع بازی به دقت بررسی کنید.\n\n"
        f"🎮 بازی انتخابی: {game_title(game)}\n"
        f"🎯 پیش‌بینی شما: {outcome}\n"
        f"📈 ضریب برد این حالت: {odds}x\n"
        f"💰 مبلغ شرط شما: {bet:,} تومان\n\n"
        f"آیا از ثبت این شرط اطمینان دارید؟"
    )
    if isinstance(update_or_msg, Update):
        await update_or_msg.message.reply_text(text, reply_markup=confirm_bet_keyboard())
    else:
        await update_or_msg.edit_message_text(text, reply_markup=confirm_bet_keyboard())
    return GAME_CONFIRM

async def game_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "confirm_no":
        await query.edit_message_text("❌ شرط لغو شد.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    elif data == "confirm_yes":
        game = context.user_data["game"]
        outcome = context.user_data["game_outcome"]
        bet = context.user_data["bet_amount"]
        user_id = update.effective_user.id
        user = get_user(user_id)
        
        if user["balance"] < bet:
            await query.edit_message_text("⚠️ موجودی شما کافی نیست! لطفاً شارژ کنید.", reply_markup=main_menu_keyboard())
            return ConversationHandler.END
        
        update_user_balance(user_id, -bet)
        
        if game == "dice":
            result_num, odds, win = play_dice(int(outcome))
            result_str = f"عدد {result_num}"
        elif game == "bowling":
            result_str, odds, win = play_bowling(outcome)
        elif game == "lottery":
            result_str, odds, win = play_lottery(outcome)
        elif game == "rps":
            bot_choice, odds, win, result = play_rps(outcome)
            result_str = bot_choice
        else:
            await query.edit_message_text("❌ خطا در اجرای بازی!", reply_markup=main_menu_keyboard())
            return ConversationHandler.END

        if win:
            profit = int(bet * odds) - bet
            update_user_balance(user_id, profit + bet)
            update_user_stats(user_id, True)
            result_text = "🎉 شما برنده شدید!"
            profit_display = f"+{profit:,}"
        elif game == "rps" and result == "draw":
            update_user_balance(user_id, bet)
            profit = 0
            update_user_stats(user_id, False)
            result_text = "🤝 مساوی! مبلغ شما بازگردانده شد."
            profit_display = "۰"
        else:
            profit = -bet
            update_user_stats(user_id, False)
            result_text = "😞 شما باختید!"
            profit_display = f"-{bet:,}"

        add_game_history(user_id, game, bet, odds, outcome, "win" if win else "loss", profit)
        check_referral_earnings(user_id)

        new_balance = user["balance"] + profit
        result_msg = (
            f"{result_text}\n\n"
            f"🎮 بازی: {game_title(game)}\n"
            f"پیش‌بینی شما: {outcome}\n"
            f"نتیجه: {result_str}\n"
            f"ضریب: {odds}x\n"
            f"مبلغ شرط: {bet:,} تومان\n"
            f"سود/زیان: {profit_display} تومان\n"
            f"موجودی جدید: {new_balance:,} تومان"
        )
        await query.edit_message_text(result_msg, reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    else:
        await query.edit_message_text("❌ خطا!", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

# --- Profile ---
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await query.edit_message_text("کاربر یافت نشد! لطفاً /start را بزنید.", reply_markup=main_menu_keyboard())
        return
    
    level = get_user_level(user["balance"])
    last_games = get_last_games(user_id, 5)
    games_text = "\n".join([f"{g['game_type']} - {g['bet_amount']:,} تومان - {g['result']} ({g['profit']:,})" for g in last_games]) if last_games else "هیچ بازی ثبت نشده."
    
    text = (
        f"👤 بخش حساب کاربری\n\n"
        f"اطلاعات دقیق حساب شما در سیستم:\n\n"
        f"🏅 سطح شما: {level}\n"
        f"📌 آیدی عددی: {user_id}\n"
        f"💎 موجودی پول: {user['balance']:,} تومان\n\n"
        f"✅ تعداد برد: {user['wins']}\n"
        f"❌ تعداد باخت: {user['losses']}\n\n"
        f"📋 نتایج آخرین بازی‌ها:\n{games_text}"
    )
    await query.edit_message_text(text, reply_markup=main_menu_keyboard())

# --- Deposit ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    amounts = [10, 50, 100, 150, 300, 500, 750, 1000, 2500, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000, 5000000]
    keyboard = []
    row = []
    for i, amt in enumerate(amounts):
        label = f"💰 {amt:,} تومان"
        row.append(InlineKeyboardButton(label, callback_data=f"deposit_{amt}"))
        if (i+1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("💰 مبلغ دلخواه", callback_data="deposit_custom")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu")])
    
    await query.edit_message_text(
        "💰 افزایش موجودی\n\n"
        "لطفاً مبلغ مورد نظر برای شارژ حساب خود را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DEPOSIT_AMOUNT

async def deposit_amount_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "deposit_custom":
        await query.edit_message_text("لطفاً مبلغ مورد نظر خود را به عدد وارد کنید (حداقل ۱۰ تومان):")
        return DEPOSIT_AMOUNT
    else:
        amount = int(data.split("_")[1])
        context.user_data["deposit_amount"] = amount
        return await send_card_info(update, context)

async def deposit_amount_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 10:
            await update.message.reply_text("حداقل مبلغ ۱۰ تومان است. لطفاً عدد بزرگتر وارد کنید.")
            return DEPOSIT_AMOUNT
        context.user_data["deposit_amount"] = amount
        return await send_card_info_message(update, context)
    except ValueError:
        await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
        return DEPOSIT_AMOUNT

async def send_card_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await send_card_info_message(query, context)

async def send_card_info_message(update_or_msg, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data["deposit_amount"]
    card_num = CARD_NUMBER
    card_owner = CARD_OWNER
    
    text = (
        f"💳 برای شارژ حساب خود مبلغ {amount:,} تومان را به شماره کارت زیر واریز کنید:\n\n"
        f"🏦 شماره کارت: `{card_num}`\n"
        f"👤 نام صاحب کارت: {card_owner}\n\n"
        f"پس از واریز، لطفاً تصویر رسید را برای ما ارسال کنید.\n"
        f"لطفاً رسید را به صورت عکس ارسال کنید."
    )
    if isinstance(update_or_msg, Update):
        await update_or_msg.message.reply_text(text, parse_mode="Markdown")
    else:
        await update_or_msg.edit_message_text(text, parse_mode="Markdown")
    return DEPOSIT_RECEIPT

async def deposit_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file_id = photo.file_id
    amount = context.user_data.get("deposit_amount")
    
    if not amount:
        await update.message.reply_text("❌ خطا! لطفاً دوباره از منو اقدام کنید.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    deposit_id = create_deposit(user_id, amount, file_id)
    
    await update.message.reply_text(
        f"✅ رسید شما دریافت شد. درخواست واریز شما با شماره #{deposit_id} ثبت گردید.\n"
        f"پس از تایید توسط ادمین، موجودی شما افزایش خواهد یافت.",
        reply_markup=main_menu_keyboard()
    )
    
    if OWNER_ID:
        user = get_user(user_id)
        caption = (
            f"📥 درخواست واریز جدید\n"
            f"شناسه: #{deposit_id}\n"
            f"کاربر: {user_id} ({user['username'] or 'بدون نام'})\n"
            f"مبلغ: {amount:,} تومان\n"
            f"وضعیت: در انتظار تایید"
        )
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=file_id,
            caption=caption,
            reply_markup=admin_action_keyboard(deposit_id, "deposit")
        )
    return ConversationHandler.END

# --- Withdrawal ---
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        f"💳 برداشت موجودی\n\n"
        f"لطفاً مبلغ مورد نظر برای برداشت را وارد کنید (حداقل {MIN_WITHDRAWAL:,} تومان):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]])
    )
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < MIN_WITHDRAWAL:
            await update.message.reply_text(f"حداقل مبلغ برداشت {MIN_WITHDRAWAL:,} تومان است. لطفاً عدد بزرگتر وارد کنید.")
            return WITHDRAW_AMOUNT
        
        user_id = update.effective_user.id
        user = get_user(user_id)
        if user["balance"] < amount:
            await update.message.reply_text("موجودی شما کافی نیست!")
            return WITHDRAW_AMOUNT
        
        withdrawal_id = create_withdrawal(user_id, amount)
        await update.message.reply_text(
            f"✅ درخواست برداشت شما به مبلغ {amount:,} تومان ثبت شد.\n"
            f"شماره درخواست: #{withdrawal_id}\n"
            f"پس از تایید ادمین، مبلغ از حساب شما کسر و واریز خواهد شد.",
            reply_markup=main_menu_keyboard()
        )
        
        if OWNER_ID:
            user = get_user(user_id)
            caption = (
                f"📤 درخواست برداشت جدید\n"
                f"شناسه: #{withdrawal_id}\n"
                f"کاربر: {user_id} ({user['username'] or 'بدون نام'})\n"
                f"مبلغ: {amount:,} تومان\n"
                f"موجودی کاربر: {user['balance']:,} تومان\n"
                f"وضعیت: در انتظار تایید"
            )
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=caption,
                reply_markup=admin_action_keyboard(withdrawal_id, "withdraw")
            )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
        return WITHDRAW_AMOUNT

# --- Leaderboard ---
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user(user_id)
    top_users = get_top_users(5)
    
    if not top_users:
        await query.edit_message_text("هنوز کاربری در لیدربورد وجود ندارد.", reply_markup=main_menu_keyboard())
        return
    
    text = "📊 لیدربورد (برترین‌های ربات)\n\nبا بازی بیشتر، جایگاه خود را در لیدربورد ارتقا دهید!\n\n"
    
    if user:
        level = get_user_level(user["balance"])
        text += f"👤 کاربر: @{user['username'] or 'بدون نام'}\n"
        text += f"🏅 سطح شما: {level}\n"
        text += f"💎 موجودی شما: {user['balance']:,} تومان\n\n"
    
    text += "لیست برترین‌ها:\n"
    for i, u in enumerate(top_users, 1):
        name = u['username'] or u['first_name'] or f"کاربر {u['id']}"
        text += f"{i}️⃣ | {name} - {u['balance']:,} تومان\n"
    
    await query.edit_message_text(text, reply_markup=main_menu_keyboard())

# --- Referral ---
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("کاربر یافت نشد.", reply_markup=main_menu_keyboard())
        return
    
    link = get_referral_link(user_id)
    text = (
        f"👥 بخش زیرمجموعه‌گیری\n\n"
        f"با دعوت دوستان خود موجودی رایگان دریافت کنید!\n\n"
        f"✏️ لینک دعوت اختصاصی شما:\n`{link}`\n\n"
        f"🏆 زیرمجموعه‌های فعال: {user['referral_count']} نفر\n"
        f"💰 درآمد کسب شده: {user['referral_earnings']:,} تومان\n\n"
        f"⚠️ به ازای هر دوستی که از طریق لینک شما وارد ربات شده و حداقل یک بازی انجام دهد، شما ۱۰,۰۰۰ تومان دریافت می‌کنید."
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

# --- Support ---
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎧 بخش پشتیبانی\n\n"
        "ما اینجا هستیم تا به مشکلات و سوالات شما پاسخ دهیم!\n\n"
        "لطفاً پیام خود را بفرستید. ادمین‌ها در اسرع وقت پاسخ خواهند داد:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu")]])
    )

async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    if OWNER_ID:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"📩 پیام پشتیبانی از کاربر {user.id} (@{user.username or 'بدون نام'}):\n\n{text}"
        )
    await update.message.reply_text("✅ پیام شما به پشتیبانی ارسال شد. در اسرع وقت پاسخ داده می‌شود.", reply_markup=main_menu_keyboard())

# --- Admin Panel ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        await query.edit_message_text("شما دسترسی به این بخش ندارید.", reply_markup=main_menu_keyboard())
        return
    await query.edit_message_text("👑 پنل مدیریت\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=admin_panel_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        await query.edit_message_text("دسترسی غیرمجاز!", reply_markup=main_menu_keyboard())
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM games_history")
    total_games = c.fetchone()[0]
    c.execute("SELECT SUM(profit) FROM games_history WHERE result='win'")
    total_wins_profit = c.fetchone()[0] or 0
    c.execute("SELECT SUM(profit) FROM games_history WHERE result='loss'")
    total_losses = c.fetchone()[0] or 0
    conn.close()
    
    text = (
        f"📊 آمار کلی ربات\n\n"
        f"👥 تعداد کاربران: {total_users}\n"
        f"💰 مجموع موجودی کاربران: {total_balance:,} تومان\n"
        f"🎮 تعداد کل بازی‌ها: {total_games}\n"
        f"✅ سود کل از بردها: {total_wins_profit:,} تومان\n"
        f"❌ زیان کل از باخت‌ها: {total_losses:,} تومان\n"
        f"💹 سود خالص ربات: {total_losses - total_wins_profit:,} تومان"
    )
    await query.edit_message_text(text, reply_markup=admin_panel_keyboard())

async def admin_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return
    
    pending = get_pending_deposits()
    if not pending:
        await query.edit_message_text("هیچ درخواست واریز در انتظار تایید وجود ندارد.", reply_markup=admin_panel_keyboard())
        return
    
    for dep in pending:
        user = get_user(dep["user_id"])
        caption = (
            f"📥 درخواست واریز #{dep['id']}\n"
            f"کاربر: {dep['user_id']} ({user['username'] or 'بدون نام'})\n"
            f"مبلغ: {dep['amount']:,} تومان\n"
            f"زمان: {dep['created_at']}"
        )
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=dep["receipt_photo_id"],
            caption=caption,
            reply_markup=admin_action_keyboard(dep["id"], "deposit")
        )
    await query.edit_message_text("لیست درخواست‌های واریز ارسال شد.", reply_markup=admin_panel_keyboard())

async def admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return
    
    pending = get_pending_withdrawals()
    if not pending:
        await query.edit_message_text("هیچ درخواست برداشت در انتظار تایید وجود ندارد.", reply_markup=admin_panel_keyboard())
        return
    
    for wd in pending:
        user = get_user(wd["user_id"])
        text = (
            f"📤 درخواست برداشت #{wd['id']}\n"
            f"کاربر: {wd['user_id']} ({user['username'] or 'بدون نام'})\n"
            f"مبلغ: {wd['amount']:,} تومان\n"
            f"موجودی کاربر: {user['balance']:,} تومان\n"
            f"زمان: {wd['created_at']}"
        )
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=text,
            reply_markup=admin_action_keyboard(wd["id"], "withdraw")
        )
    await query.edit_message_text("لیست درخواست‌های برداشت ارسال شد.", reply_markup=admin_panel_keyboard())

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    await query.edit_message_text(f"👥 تعداد کل کاربران: {count}", reply_markup=admin_panel_keyboard())

async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        await query.edit_message_text("دسترسی غیرمجاز!", reply_markup=main_menu_keyboard())
        return
    
    data = query.data.split("_")
    action = data[1]
    action_type = data[2]
    item_id = int(data[3])
    
    if action_type == "deposit":
        if action == "approve":
            approve_deposit(item_id)
            await query.edit_message_text(f"✅ واریز #{item_id} تایید شد.", reply_markup=admin_panel_keyboard())
            dep = get_db().execute("SELECT user_id, amount FROM deposits WHERE id = ?", (item_id,)).fetchone()
            if dep:
                await context.bot.send_message(
                    chat_id=dep["user_id"],
                    text=f"✅ واریز شما به مبلغ {dep['amount']:,} تومان تایید و به حساب شما اضافه شد."
                )
        else:
            reject_deposit(item_id)
            await query.edit_message_text(f"❌ واریز #{item_id} رد شد.", reply_markup=admin_panel_keyboard())
            dep = get_db().execute("SELECT user_id, amount FROM deposits WHERE id = ?", (item_id,)).fetchone()
            if dep:
                await context.bot.send_message(
                    chat_id=dep["user_id"],
                    text=f"❌ متأسفانه درخواست واریز شما به مبلغ {dep['amount']:,} تومان رد شد. لطفاً با پشتیبانی تماس بگیرید."
                )
    elif action_type == "withdraw":
        if action == "approve":
            approve_withdrawal(item_id)
            await query.edit_message_text(f"✅ برداشت #{item_id} تایید شد.", reply_markup=admin_panel_keyboard())
            wd = get_db().execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (item_id,)).fetchone()
            if wd:
                await context.bot.send_message(
                    chat_id=wd["user_id"],
                    text=f"✅ درخواست برداشت شما به مبلغ {wd['amount']:,} تومان تایید و از حساب شما کسر شد. مبلغ به کارت شما واریز خواهد شد."
                )
        else:
            reject_withdrawal(item_id)
            await query.edit_message_text(f"❌ برداشت #{item_id} رد شد.", reply_markup=admin_panel_keyboard())
            wd = get_db().execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (item_id,)).fetchone()
            if wd:
                await context.bot.send_message(
                    chat_id=wd["user_id"],
                    text=f"❌ متأسفانه درخواست برداشت شما به مبلغ {wd['amount']:,} تومان رد شد. لطفاً با پشتیبانی تماس بگیرید."
                )

# --- Cancel and Fallback ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("دستور نامعتبر! لطفاً از دکمه‌ها استفاده کنید.", reply_markup=main_menu_keyboard())

# --- Main ---
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handlers
    game_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(game_selected, pattern="^game_")],
        states={
            GAME_CHOOSE: [CallbackQueryHandler(game_outcome_chosen, pattern="^outcome_")],
            GAME_BET: [
                CallbackQueryHandler(game_bet_chosen, pattern="^bet_"),
                CallbackQueryHandler(game_bet_chosen, pattern="^bet_custom$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, game_bet_custom),
            ],
            GAME_CONFIRM: [CallbackQueryHandler(game_confirm, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(menu, pattern="^menu$")],
        map_to_parent={
            ConversationHandler.END: None
        }
    )

    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="^deposit$")],
        states={
            DEPOSIT_AMOUNT: [
                CallbackQueryHandler(deposit_amount_chosen, pattern="^deposit_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_custom),
            ],
            DEPOSIT_RECEIPT: [MessageHandler(filters.PHOTO, deposit_receipt)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(menu, pattern="^menu$")],
    )

    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="^withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(menu, pattern="^menu$")],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(games_menu, pattern="^games$"))
    app.add_handler(CallbackQueryHandler(profile, pattern="^profile$"))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_deposits, pattern="^admin_deposits$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^admin_"))

    app.add_handler(game_conv)
    app.add_handler(deposit_conv)
    app.add_handler(withdraw_conv)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, support_message))
    app.add_handler(MessageHandler(filters.ALL, fallback))

    logger.info("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
