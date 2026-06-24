import os
import asyncio
import sqlite3
import aiohttp
import time

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
    messages INTEGER DEFAULT 0
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

# ================= LIMITS =================

LIMITS = {"free": 30, "pro": 150, "ultra": 500}

# ================= UI =================

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="👑 Админ", callback_data="admin")]
    ])

# ================= DB =================

def get(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

def update(uid, **kw):
    keys = ",".join([f"{k}=?" for k in kw])
    vals = list(kw.values()) + [uid]
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", vals)
    db.commit()

# ================= MEMORY =================

def memory_pack(mem, u, a):
    return (mem + f"\nU:{u}\nA:{a}")[-3500:]

# ================= AI CORE =================

MODELS = [
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

async def call(model, prompt):
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


async def ai(text, memory, role):
    style = "коротко и точно" if role == "secretary" else "нормально"

    prompt = f"""
Ты ассистент.
Стиль: {style}
Память: {memory}

Пользователь: {text}
"""

    for m in MODELS:
        for i in range(2):
            res = await call(m, prompt)
            if res:
                return res
            await asyncio.sleep(0.2 * (i + 1))

    return "⚠️ AI перегружен"

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    create(msg.from_user.id)
    await msg.answer("🤖 SaaS Online. Пиши сообщение.", reply_markup=kb())

# ================= CHAT =================

@router.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get(uid)

    if not user:
        create(uid)
        user = get(uid)

    tier, role, memory, used = user[1], user[2], user[3], user[4]

    if used >= LIMITS[tier]:
        return await msg.answer("🚫 Лимит исчерпан")

    reply = await ai(msg.text, memory, role)

    memory = memory_pack(memory, msg.text, reply)

    update(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply, reply_markup=kb())

# ================= PAYMENTS (BASE STRUCTURE) =================

async def check_payment(invoice_id):
    url = f"https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}

    async with session.get(url, headers=headers) as r:
        data = await r.json()

    for inv in data.get("result", {}).get("items", []):
        if inv["invoice_id"] == invoice_id and inv["status"] == "paid":
            return True
    return False

# ================= ADMIN =================

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ Нет доступа")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM payments")
    pays = cur.fetchone()[0]

    await c.message.answer(
        f"👑 ADMIN PANEL\nUsers: {users}\nPayments: {pays}"
    )

# ================= SUBS =================

@router.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💳 CryptoPay готов к авто-активации (webhook слой можно подключить отдельно)")

# ================= RUN =================

async def main():
    print("🚀 PRODUCTION SAAS ONLINE")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
