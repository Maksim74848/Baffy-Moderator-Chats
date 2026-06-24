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

# HTTP SESSION (FAST FIX)
session = aiohttp.ClientSession()

groq = Groq(api_key=GROQ_API_KEY)

# ================= DB =================

db = sqlite3.connect("saas.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    expire INTEGER DEFAULT 0,
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    messages INTEGER DEFAULT 0
)
""")
db.commit()

# ================= LIMITS =================

LIMITS = {"free": 20, "pro": 120, "ultra": 300}

# ================= UI (MINIMAL) =================

def buttons():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="👑 Админ", callback_data="admin")]
    ])

# ================= AI (FAST + STABLE) =================

async def ask_ai(text, memory, role):
    prompt = f"Ты ИИ помощник. Роль: {role}. Память: {memory}. Пользователь: {text}"

    models = [
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768"
    ]

    for model in models:
        try:
            def call():
                return groq.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=12
                ).choices[0].message.content

            return await asyncio.to_thread(call)

        except Exception as e:
            print("MODEL FAIL:", model, e)
            continue

    return "⚠️ AI временно недоступен. Попробуй снова."

# ================= DB HELPERS =================

def get(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

def update(uid, **kw):
    keys = ",".join([f"{k}=?" for k in kw])
    vals = list(kw.values())
    vals.append(uid)
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", vals)
    db.commit()

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    create(msg.from_user.id)
    await msg.answer("🤖 Привет! Просто напиши сообщение 👇", reply_markup=buttons())

# ================= CHAT (NO MODES) =================

@router.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get(uid)

    if not user:
        create(uid)
        user = get(uid)

    tier, _, role, memory, used = user[1], user[2], user[3], user[4], user[5]

    if used >= LIMITS[tier]:
        return await msg.answer("🚫 Лимит исчерпан. Оформи подписку.")

    reply = await ask_ai(msg.text, memory, role)

    memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-4000:]

    update(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply, reply_markup=buttons())

# ================= CALLBACKS =================

@router.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💎 Подписка:\nPRO / ULTRA\n(подключается через CryptoPay)")

@router.callback_query(F.data == "settings")
async def settings(c: CallbackQuery):
    u = get(c.from_user.id)
    new_role = "secretary" if u[3] == "assistant" else "assistant"
    update(c.from_user.id, role=new_role)
    await c.message.answer(f"⚙️ Роль: {new_role}")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ Нет доступа")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    await c.message.answer(f"👑 ADMIN\nUsers: {users}")

# ================= RUN =================

async def main():
    print("🚀 SAAS 2.0 ONLINE")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
