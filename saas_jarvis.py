import os
import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from groq import Groq
from gtts import gTTS

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
groq = Groq(api_key=GROQ_API_KEY)

# ================= DB =================

db = sqlite3.connect("jarvis.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    expire TEXT DEFAULT '',
    messages INTEGER DEFAULT 0,
    memory TEXT DEFAULT '',
    role TEXT DEFAULT 'assistant'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS invoices(
    invoice_id TEXT PRIMARY KEY,
    user_id INTEGER,
    tier TEXT,
    used INTEGER DEFAULT 0
)
""")

db.commit()

# ================= LIMITS =================

LIMITS = {
    "free": 15,
    "pro": 80,
    "ultra": 250
}

# ================= UI =================

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат", callback_data="chat")],
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="🧠 Роль", callback_data="role")]
    ])

def subs_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="PRO 30d - $1", callback_data="buy_pro")],
        [InlineKeyboardButton(text="ULTRA 30d - $3", callback_data="buy_ultra")]
    ])

# ================= AI =================

async def ask_ai(text, memory, role):
    prompt = f"""
Role: {role}
Memory: {memory}

User: {text}
"""

    def call():
        return groq.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}]
        ).choices[0].message.content

    return await asyncio.to_thread(call)

# ================= SUBS CHECK =================

def is_expired(expire_str):
    if not expire_str:
        return True
    return datetime.utcnow() > datetime.fromisoformat(expire_str)

# ================= START =================

@dp.message(F.text == "/start")
async def start(msg: Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (msg.from_user.id,))
    db.commit()
    await msg.answer("🤖 JARVIS SaaS 3.0 ONLINE", reply_markup=menu())

# ================= CHAT =================

@dp.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id

    cur.execute("SELECT tier, expire, memory, role, messages FROM users WHERE user_id=?", (uid,))
    tier, expire, memory, role, used = cur.fetchone()

    if tier != "free" and is_expired(expire):
        tier = "free"
        cur.execute("UPDATE users SET tier='free', expire='' WHERE user_id=?", (uid,))
        db.commit()

    if used >= LIMITS[tier]:
        await msg.answer("🚫 Лимит исчерпан")
        return

    cur.execute("UPDATE users SET messages = messages + 1 WHERE user_id=?", (uid,))
    db.commit()

    reply = await ask_ai(msg.text, memory, role)

    memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-2500:]

    cur.execute("UPDATE users SET memory=? WHERE user_id=?", (memory, uid))
    db.commit()

    await msg.answer(reply)

    asyncio.create_task(send_voice(uid, reply))

# ================= VOICE =================

async def send_voice(uid, text):
    try:
        tts = gTTS(text[:200])
        path = f"{uid}.mp3"
        tts.save(path)
        await bot.send_voice(uid, open(path, "rb"))
    except:
        pass

# ================= SUBS =================

@dp.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💎 Выбери тариф:", reply_markup=subs_menu())

async def create_invoice(uid, tier, amount):
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://pay.crypt.bot/api/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={
                "asset": "USDT",
                "amount": amount,
                "description": f"Jarvis {tier}"
            }
        ) as r:
            data = await r.json()
            inv = data["result"]

            cur.execute("""
            INSERT OR IGNORE INTO invoices VALUES (?,?,?,0)
            """, (inv["invoice_id"], uid, tier))
            db.commit()

            return inv["pay_url"], inv["invoice_id"]

@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    tier = c.data.replace("buy_", "")

    prices = {
        "pro": 1,
        "ultra": 3
    }

    url, inv_id = await create_invoice(c.from_user.id, tier, prices[tier])

    await c.message.answer(f"💳 Оплата:\n{url}")

# ================= PAYMENT ENGINE =================

async def payment_worker():
    while True:
        await asyncio.sleep(8)

        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://pay.crypt.bot/api/getInvoices",
                headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
            ) as r:
                data = await r.json()

        for inv in data["result"]["items"]:
            if inv["status"] != "paid":
                continue

            cur.execute("SELECT used FROM invoices WHERE invoice_id=?", (inv["invoice_id"],))
            row = cur.fetchone()

            if not row:
                continue

            # already processed
            if row[0] == 1:
                continue

            cur.execute("SELECT user_id, tier FROM invoices WHERE invoice_id=?", (inv["invoice_id"],))
            uid, tier = cur.fetchone()

            expire = (datetime.utcnow() + timedelta(days=30)).isoformat()

            cur.execute("""
            UPDATE users
            SET tier=?, expire=?
            WHERE user_id=?
            """, (tier, expire, uid))

            cur.execute("UPDATE invoices SET used=1 WHERE invoice_id=?", (inv["invoice_id"],))
            db.commit()

# ================= RUN =================

async def main():
    asyncio.create_task(payment_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
