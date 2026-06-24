import os
import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta

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

session = aiohttp.ClientSession()
groq = Groq(api_key=GROQ_API_KEY)

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

# ================= TIERS =================

LIMITS = {"free": 25, "pro": 150, "ultra": 400}

# ================= UI =================

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="⚙️ Режим", callback_data="role")],
        [InlineKeyboardButton(text="👑 Админ", callback_data="admin")]
    ])

# ================= MEMORY (SMART) =================

def compress_memory(memory: str) -> str:
    if len(memory) < 2000:
        return memory
    return memory[-2000:]  # MVP compression

# ================= AI CORE =================

MODELS = [
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

async def ai_call(model, prompt):
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


async def ask_ai(text, memory, role):
    style = "коротко и по делу" if role == "secretary" else "обычный стиль"

    prompt = f"""
Ты AI ассистент.
Стиль ответа: {style}
Память: {memory}
Пользователь: {text}
"""

    for m in MODELS:
        for _ in range(2):
            res = await ai_call(m, prompt)
            if res:
                return res

    return "⚠️ AI временно перегружен"

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

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    create(msg.from_user.id)
    await msg.answer("🤖 Jarvis SaaS ONLINE. Просто пиши 👇", reply_markup=kb())

# ================= CHAT (NO MODES) =================

@router.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get(uid)

    if not user:
        create(uid)
        user = get(uid)

    tier, role, memory, used = user[1], user[2], user[3], user[4]

    if used >= LIMITS[tier]:
        return await msg.answer("🚫 Лимит. Подпишись.")

    reply = await ask_ai(msg.text, memory, role)

    memory = compress_memory(memory + f"\nU:{msg.text}\nA:{reply}")

    update(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply, reply_markup=kb())

# ================= CALLBACKS =================

@router.callback_query(F.data == "role")
async def role(c: CallbackQuery):
    u = get(c.from_user.id)
    new_role = "secretary" if u[2] == "assistant" else "assistant"
    update(c.from_user.id, role=new_role)
    await c.message.answer(f"⚙️ Режим: {new_role}")

@router.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💎 Подписка через CryptoPay (auto webhook будет в следующем апгрейде)")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ Нет доступа")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    await c.message.answer(f"""
👑 ADMIN PANEL

Users: {users}
""")

# ================= RUN =================

async def main():
    print("🚀 SAAS 5.0 FINAL RUNNING")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
