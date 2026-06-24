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
db.commit()

# ================= LIMITS =================

LIMITS = {"free": 25, "pro": 120, "ultra": 300}

# ================= UI =================

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="⚙️ Роль", callback_data="role")],
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
    vals = list(kw.values())
    vals.append(uid)
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", vals)
    db.commit()

# ================= AI CORE (FIXED STABLE) =================

MODELS = [
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768"
]

async def call_model(model, prompt):
    try:
        def run():
            return groq.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=15
            ).choices[0].message.content

        return await asyncio.to_thread(run)

    except Exception as e:
        print(f"[MODEL FAIL] {model} ->", e)
        return None


async def ask_ai(text, memory, role):
    prompt = f"""
Ты умный ассистент.
Роль: {role}
Память: {memory}

Пользователь: {text}
"""

    for model in MODELS:
        for attempt in range(2):  # retry
            res = await call_model(model, prompt)
            if res:
                return res
            await asyncio.sleep(0.3 * (attempt + 1))

    return "⚠️ Сейчас большая нагрузка на AI. Попробуй ещё раз через 10–20 секунд."

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    create(msg.from_user.id)
    await msg.answer("🤖 Привет! Просто напиши сообщение 👇", reply_markup=kb())

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
        return await msg.answer("🚫 Лимит исчерпан. Оформи подписку.")

    reply = await ask_ai(msg.text, memory, role)

    memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-6000:]

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
    await c.message.answer(f"⚙️ Роль: {new_role}")

@router.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💎 Подписка PRO / ULTRA\n(подключение через CryptoPay)")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ Нет доступа")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    await c.message.answer(f"👑 ADMIN\nUsers: {users}")

# ================= RUN =================

async def main():
    print("🚀 SAAS 4.0 STABLE RUNNING")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
