import os
import asyncio
import sqlite3
import aiohttp

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
        [InlineKeyboardButton(text="⚙️ Админ", callback_data="admin")]
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

def memory_update(mem, user, ai):
    text = mem + f"\nU:{user}\nA:{ai}"
    return text[-4000:]  # safe truncate

# ================= AI ENGINE =================

MODELS = [
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

async def call_ai(model, prompt):
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
    style = "коротко" if role == "secretary" else "нормально"

    prompt = f"""
Ты ассистент.
Стиль: {style}
Память: {memory}

Пользователь: {text}
"""

    for m in MODELS:
        for _ in range(2):
            res = await call_ai(m, prompt)
            if res:
                return res
            await asyncio.sleep(0.2)

    return "⚠️ AI перегружен"

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    create(msg.from_user.id)
    await msg.answer("🤖 Готов. Просто пиши.", reply_markup=kb())

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
        return await msg.answer("🚫 Лимит. Оформи подписку.")

    reply = await ai(msg.text, memory, role)

    memory = memory_update(memory, msg.text, reply)

    update(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply, reply_markup=kb())

# ================= ADMIN =================

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ Нет доступа")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM payments")
    payments = cur.fetchone()[0]

    await c.message.answer(
        f"👑 ADMIN PANEL\n\nUsers: {users}\nPayments: {payments}"
    )

# ================= SUBS =================

@router.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💳 CryptoPay подключается через webhook (готово к расширению)")

# ================= RUN =================

async def main():
    print("🚀 FINAL SAAS SYSTEM ONLINE")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
