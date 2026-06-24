import os
import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from groq import Groq

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

groq = Groq(api_key=GROQ_API_KEY)

# ================= DB =================

db = sqlite3.connect("saas.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    expire TEXT DEFAULT '',
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    messages INTEGER DEFAULT 0
)
""")

db.commit()

# ================= LIMITS =================

LIMITS = {
    "free": 20,
    "pro": 100,
    "ultra": 300
}

# ================= FSM =================

class StateSG(StatesGroup):
    menu = State()
    chat = State()

# ================= UI =================

def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Chat", callback_data="chat")],
        [InlineKeyboardButton(text="💎 Buy PRO", callback_data="buy_pro")],
        [InlineKeyboardButton(text="💎 Buy ULTRA", callback_data="buy_ultra")],
        [InlineKeyboardButton(text="⚙️ Role", callback_data="role")]
    ])

# ================= AI =================

async def ask_ai(text, memory, role):
    try:
        def call():
            return groq.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[
                    {"role": "user", "content": f"role:{role}\nmemory:{memory}\n{text}"}
                ]
            ).choices[0].message.content

        return await asyncio.to_thread(call)

    except Exception as e:
        print("AI ERROR:", e)
        return "⚠️ ИИ временно недоступен"

# ================= USER HELPERS =================

def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create_user(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

def update_user(uid, **kwargs):
    keys = ", ".join([f"{k}=?" for k in kwargs])
    values = list(kwargs.values())
    values.append(uid)
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", values)
    db.commit()

# ================= PAYMENT =================

async def create_invoice(tier: str):
    price = {"pro": 1, "ultra": 3}[tier]

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://pay.crypt.bot/api/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={
                "asset": "USDT",
                "amount": price,
                "description": f"SaaS {tier}"
            }
        ) as r:
            data = await r.json()

    return data["result"]["pay_url"]

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message, state: FSMContext):
    create_user(msg.from_user.id)
    await state.set_state(StateSG.menu)
    await msg.answer("🚀 SaaS ONLINE", reply_markup=menu_kb())

# ================= MENU =================

@router.callback_query(F.data == "chat")
async def chat_open(c: CallbackQuery, state: FSMContext):
    await state.set_state(StateSG.chat)
    await c.message.answer("💬 Пиши сообщение")

@router.callback_query(F.data == "role")
async def role(c: CallbackQuery):
    u = get_user(c.from_user.id)
    new_role = "secretary" if u[3] == "assistant" else "assistant"
    update_user(c.from_user.id, role=new_role)
    await c.message.answer(f"⚙️ Role: {new_role}")

# ================= PAY =================

@router.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    tier = c.data.replace("buy_", "")
    url = await create_invoice(tier)
    await c.message.answer(f"💳 Pay here:\n{url}")

# ================= CHAT =================

@router.message(StateSG.chat)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get_user(uid)

    if not user:
        create_user(uid)
        user = get_user(uid)

    tier, memory, role, used = user[1], user[4], user[3], user[5]

    if used >= LIMITS[tier]:
        await msg.answer("🚫 Limit reached")
        return

    reply = await ask_ai(msg.text, memory, role)

    memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-3000:]

    update_user(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply)

# ================= RUN =================

async def main():
    print("🚀 SAAS ONEFILE RUNNING")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
