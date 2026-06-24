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
    role TEXT DEFAULT 'assistant',
    balance REAL DEFAULT 0,
    ref INTEGER DEFAULT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS invoices(
    invoice_id TEXT PRIMARY KEY,
    user_id INTEGER,
    tier TEXT,
    amount REAL,
    used INTEGER DEFAULT 0
)
""")

db.commit()

# ================= CONFIG =================

LIMITS = {
    "free": 15,
    "pro": 80,
    "ultra": 250
}

PRICES = {
    "pro": 1,
    "ultra": 3
}

REF_PERCENT = 0.20

# ================= UI =================

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат", callback_data="chat")],
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="bal")]
    ])

def subs_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="PRO", callback_data="buy_pro")],
        [InlineKeyboardButton(text="ULTRA", callback_data="buy_ultra")]
    ])

# ================= AI =================

async def ask_ai(text, memory, role):
    prompt = f"{role}\n{memory}\nUser:{text}"

    def call():
        return groq.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}]
        ).choices[0].message.content

    return await asyncio.to_thread(call)

# ================= LIMITS =================

def is_expired(exp):
    if not exp:
        return True
    return datetime.utcnow() > datetime.fromisoformat(exp)

# ================= START =================

@dp.message(F.text == "/start")
async def start(msg: Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id, ref) VALUES(?,?)",
                (msg.from_user.id, None))
    db.commit()

    await msg.answer("🤖 SaaS 4.0 ONLINE", reply_markup=menu())

# ================= CHAT =================

@dp.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id

    cur.execute("SELECT tier, expire, memory, role, messages FROM users WHERE user_id=?", (uid,))
    tier, exp, memory, role, used = cur.fetchone()

    if tier != "free" and is_expired(exp):
        tier = "free"
        cur.execute("UPDATE users SET tier='free' WHERE user_id=?", (uid,))
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

# ================= BALANCE =================

@dp.callback_query(F.data == "bal")
async def bal(c: CallbackQuery):
    cur.execute("SELECT balance FROM users WHERE user_id=?", (c.from_user.id,))
    b = cur.fetchone()[0]
    await c.message.answer(f"💰 Баланс: {b}$")

# ================= SUBS =================

@dp.callback_query(F.data == "subs")
async def subs(c: CallbackQuery):
    await c.message.answer("💎 Тарифы:", reply_markup=subs_menu())

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

    url, inv_id = await create_invoice(c.from_user.id, tier, PRICES[tier])

    await c.message.answer(f"💳 Оплата:\n{url}")

# ================= PAYMENT ENGINE =================

async def payment_worker():
    processed = set()

    while True:
        await asyncio.sleep(7)

        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://pay.crypt.bot/api/getInvoices",
                headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
            ) as r:
                data = await r.json()

        for inv in data["result"]["items"]:
            if inv["status"] != "paid":
                continue

            if inv["invoice_id"] in processed:
                continue

            cur.execute("SELECT user_id, tier FROM invoices WHERE invoice_id=?",
                        (inv["invoice_id"],))
            row = cur.fetchone()

            if not row:
                continue

            uid, tier = row

            # expire 30 days
            exp = (datetime.utcnow() + timedelta(days=30)).isoformat()

            # update user tier
            cur.execute("""
            UPDATE users
            SET tier=?, expire=?
            WHERE user_id=?
            """, (tier, exp, uid))

            # referral logic (optional placeholder)
            cur.execute("SELECT ref FROM users WHERE user_id=?", (uid,))
            ref = cur.fetchone()[0]

            if ref:
                bonus = PRICES[tier] * REF_PERCENT

                cur.execute("""
                UPDATE users SET balance = balance + ?
                WHERE user_id=?
                """, (bonus, ref))

            db.commit()

            processed.add(inv["invoice_id"])

# ================= RUN =================

async def main():
    asyncio.create_task(payment_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
