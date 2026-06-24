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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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
    expire INTEGER DEFAULT 0,
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    messages INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS invoices(
    invoice_id TEXT PRIMARY KEY,
    user_id INTEGER,
    tier TEXT,
    status TEXT DEFAULT 'pending'
)
""")

db.commit()

# ================= TIERS =================

LIMITS = {
    "free": 20,
    "pro": 120,
    "ultra": 300
}

# ================= FSM =================

class StateSG(StatesGroup):
    menu = State()
    chat = State()

# ================= UI =================

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Chat", callback_data="chat")],
        [InlineKeyboardButton(text="💎 PRO", callback_data="buy_pro")],
        [InlineKeyboardButton(text="💎 ULTRA", callback_data="buy_ultra")],
        [InlineKeyboardButton(text="⚙️ Role", callback_data="role")],
        [InlineKeyboardButton(text="👑 Admin", callback_data="admin")]
    ])

def back():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back")]
    ])

# ================= AI =================

async def ask_ai(text, memory, role):
    try:
        def call():
            return groq.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": f"ROLE:{role}\nMEMORY:{memory}\nUSER:{text}"
                }]
            ).choices[0].message.content

        return await asyncio.to_thread(call)

    except Exception as e:
        print("AI ERROR:", e)
        return "⚠️ AI временно недоступен"

# ================= DB HELPERS =================

def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create_user(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()

def update(uid, **kw):
    keys = ", ".join([f"{k}=?" for k in kw])
    vals = list(kw.values())
    vals.append(uid)
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", vals)
    db.commit()

# ================= PAYMENT =================

async def create_invoice(tier):
    price = {"pro": 1, "ultra": 3}[tier]

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://pay.crypt.bot/api/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={
                "asset": "USDT",
                "amount": price,
                "description": f"Jarvis {tier}"
            }
        ) as r:
            data = await r.json()

    inv = data["result"]

    cur.execute(
        "INSERT OR REPLACE INTO invoices VALUES (?,?,?,?)",
        (inv["invoice_id"], 0, tier, "pending")
    )
    db.commit()

    return inv["pay_url"], inv["invoice_id"]


# ================= CHECK PAYMENTS =================

async def check_payments():
    while True:
        await asyncio.sleep(15)

        cur.execute("SELECT invoice_id, user_id, tier FROM invoices WHERE status='pending'")
        rows = cur.fetchall()

        for inv_id, uid, tier in rows:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://pay.crypt.bot/api/getInvoices?invoice_ids={inv_id}",
                        headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
                    ) as r:
                        data = await r.json()

                if data["result"]["items"][0]["status"] == "paid":
                    cur.execute("UPDATE invoices SET status='paid' WHERE invoice_id=?", (inv_id,))
                    cur.execute("UPDATE users SET tier=?, expire=? WHERE user_id=?",
                                (tier, int((datetime.utcnow() + timedelta(days=30)).timestamp()), uid))
                    db.commit()

                    await bot.send_message(uid, f"✅ Подписка активирована: {tier}")

            except Exception as e:
                print("PAY CHECK ERROR:", e)

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message, state: FSMContext):
    create_user(msg.from_user.id)
    await state.set_state(StateSG.menu)
    await msg.answer("🚀 FINAL SAAS ONLINE", reply_markup=menu())

# ================= MENU =================

@router.callback_query(F.data == "back")
async def back_handler(c: CallbackQuery, state: FSMContext):
    await state.set_state(StateSG.menu)
    await c.message.edit_text("🏠 Menu", reply_markup=menu())

@router.callback_query(F.data == "chat")
async def chat_open(c: CallbackQuery, state: FSMContext):
    await state.set_state(StateSG.chat)
    await c.message.answer("💬 Send message", reply_markup=back())

@router.callback_query(F.data == "role")
async def role(c: CallbackQuery):
    u = get_user(c.from_user.id)
    new_role = "secretary" if u[3] == "assistant" else "assistant"
    update(c.from_user.id, role=new_role)
    await c.message.answer(f"⚙️ Role: {new_role}")

@router.callback_query(F.data == "admin")
async def admin(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.message.answer("⛔ No access")

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    await c.message.answer(f"👑 ADMIN\nUsers: {users}")

# ================= PAY =================

@router.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    tier = c.data.replace("buy_", "")
    url, inv = await create_invoice(tier)
    await c.message.answer(f"💳 Pay here:\n{url}")

# ================= CHAT =================

@router.message(StateSG.chat)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get_user(uid)

    if not user:
        create_user(uid)
        user = get_user(uid)

    tier, _, role, memory, used = user[1], user[2], user[3], user[4], user[5]

    if used >= LIMITS[tier]:
        return await msg.answer("🚫 Limit reached")

    reply = await ask_ai(msg.text, memory, role)

    memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-4000:]

    update(uid,
        memory=memory,
        messages=used + 1
    )

    await msg.answer(reply)

# ================= MAIN =================

async def main():
    print("🚀 FINAL SAAS ONLINE")
    asyncio.create_task(check_payments())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
