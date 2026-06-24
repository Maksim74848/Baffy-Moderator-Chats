import os
import asyncio
import sqlite3
import aiohttp
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

from groq import Groq

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

groq = Groq(api_key=GROQ_API_KEY)
session = aiohttp.ClientSession()

# ================= DB =================

db = sqlite3.connect("saas.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    messages INTEGER DEFAULT 0,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS payments(
    invoice_id TEXT PRIMARY KEY,
    user_id INTEGER,
    tier TEXT,
    status TEXT DEFAULT 'pending'
)
""")

db.commit()

# ================= TIERS =================

LIMITS = {
    "free": 30,
    "pro": 150,
    "ultra": 500
}

# ================= UI =================

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="👑 Админ", callback_data="admin")]
    ])

# ================= DB =================

def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create_user(uid):
    cur.execute(
        "INSERT OR IGNORE INTO users(user_id, created_at) VALUES(?, ?)",
        (uid, datetime.utcnow().isoformat())
    )
    db.commit()

def update_user(uid, **fields):
    keys = ",".join([f"{k}=?" for k in fields])
    vals = list(fields.values()) + [uid]
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", vals)
    db.commit()

# ================= MEMORY ENGINE =================

def memory_engine(mem, user, ai):
    merged = mem + f"\nU:{user}\nA:{ai}"
    return merged[-4000:]

# ================= AI ENGINE =================

MODELS = [
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

async def groq_call(model, prompt):
    try:
        def run():
            return groq.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=12
            ).choices[0].message.content

        return await asyncio.to_thread(run)
    except:
        return None


async def ai_engine(text, memory, role):
    style = "коротко и по делу" if role == "secretary" else "обычный стиль"

    prompt = f"""
Ты AI ассистент.

Стиль ответа: {style}

Память:
{memory}

Запрос:
{text}
"""

    for model in MODELS:
        for _ in range(2):
            res = await groq_call(model, prompt)
            if res:
                return res
            await asyncio.sleep(0.2)

    return "⚠️ AI временно перегружен"

# ================= SUBSCRIPTION GUARD =================

def is_limit_exceeded(user):
    tier, messages = user[1], user[4]
    return messages >= LIMITS.get(tier, 0)

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    create_user(msg.from_user.id)
    await msg.answer("🤖 Jarvis SaaS v1 онлайн. Просто пиши сообщение.", reply_markup=main_kb())

# ================= CHAT FLOW =================

@router.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get_user(uid)

    if not user:
        create_user(uid)
        user = get_user(uid)

    if is_limit_exceeded(user):
        return await msg.answer("🚫 Лимит исчерпан. Оформи подписку 💎")

    tier, role, memory, used = user[1], user[2], user[3], user[4]

    reply = await ai_engine(msg.text, memory, role)

    memory = memory_engine(memory, msg.text, reply)

    update_user(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply, reply_markup=main_kb())

# ================= ADMIN PANEL =================

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ Нет доступа")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM payments")
    payments = cur.fetchone()[0]

    await c.message.answer(
        f"""👑 JARVIS SAAS ADMIN

👤 Users: {users}
💳 Payments: {payments}
"""
    )

# ================= SUBSCRIPTIONS =================

@router.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer(
        "💎 Подписка:\n\n"
        "PRO — 150 сообщений\n"
        "ULTRA — 500 сообщений\n\n"
        "⚡ Оплата через CryptoPay (webhook активирует автоматически)"
    )

# ================= CRYPTO PAY WEBHOOK (KEY PART) =================

async def verify_payment(invoice_id: str):
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}

    async with session.get(url, headers=headers) as r:
        data = await r.json()

    for inv in data.get("result", {}).get("items", []):
        if inv["invoice_id"] == invoice_id and inv["status"] == "paid":
            return True
    return False


async def activate_subscription(user_id, tier):
    update_user(user_id, tier=tier, messages=0)

# ================= RUN =================

async def main():
    print("🚀 JARVIS COMMERCIAL SAAS v1 ONLINE")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
