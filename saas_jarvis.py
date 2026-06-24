import os
import asyncio
import sqlite3
import aiohttp
from datetime import datetime

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
    messages INTEGER DEFAULT 0,
    memory TEXT DEFAULT ''
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS invoices(
    invoice_id TEXT,
    user_id INTEGER,
    tier TEXT,
    status TEXT DEFAULT 'pending'
)
""")

db.commit()

# ================= SAAS CONFIG =================

LIMITS = {
    "free": 15,
    "pro": 80,
    "ultra": 250
}

# ================= UI =================

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат", callback_data="chat")],
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")]
    ])

def subs_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="PRO - $1", callback_data="buy_pro")],
        [InlineKeyboardButton(text="ULTRA - $3", callback_data="buy_ultra")]
    ])

# ================= FAST AI =================

async def ask_ai(text, memory):
    def _call():
        return groq.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": memory + "\nUser:" + text}]
        ).choices[0].message.content

    return await asyncio.to_thread(_call)

# ================= LIMIT SYSTEM =================

def check_limit(uid):
    cur.execute("SELECT tier, messages FROM users WHERE user_id=?", (uid,))
    tier, used = cur.fetchone()

    if used >= LIMITS[tier]:
        return False
    return True

def add_msg(uid):
    cur.execute("UPDATE users SET messages = messages + 1 WHERE user_id=?", (uid,))
    db.commit()

# ================= START =================

@dp.message(F.text == "/start")
async def start(msg: Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (msg.from_user.id,))
    db.commit()
    await msg.answer("🤖 JARVIS SaaS ONLINE", reply_markup=menu())

# ================= CHAT =================

@dp.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id

    if not check_limit(uid):
        await msg.answer("🚫 Лимит исчерпан. Оформи подписку 💎")
        return

    add_msg(uid)

    cur.execute("SELECT memory FROM users WHERE user_id=?", (uid,))
    memory = cur.fetchone()[0]

    reply = await ask_ai(msg.text, memory)

    # memory update (lightweight)
    new_memory = memory + f"\nU:{msg.text}\nA:{reply}"
    if len(new_memory) > 2000:
        new_memory = new_memory[-2000:]

    cur.execute("UPDATE users SET memory=? WHERE user_id=?", (new_memory, uid))
    db.commit()

    await msg.answer(reply)

    # async voice (non-blocking)
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

# ================= SUBSCRIPTION FLOW =================

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

            cur.execute(
                "INSERT INTO invoices VALUES (?,?,?,?)",
                (inv["invoice_id"], uid, tier, "pending")
            )
            db.commit()

            return inv["pay_url"]

@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    tier = c.data.replace("buy_", "")

    prices = {
        "pro": 1,
        "ultra": 3
    }

    url = await create_invoice(c.from_user.id, tier, prices[tier])

    await c.message.answer(f"💳 Оплати:\n{url}")

# ================= PAYMENT CHECKER =================

async def payment_worker():
    while True:
        await asyncio.sleep(10)

        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://pay.crypt.bot/api/getInvoices",
                headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
            ) as r:
                data = await r.json()

        for inv in data["result"]["items"]:
            if inv["status"] == "paid":

                cur.execute(
                    "SELECT user_id, tier FROM invoices WHERE invoice_id=?",
                    (inv["invoice_id"],)
                )
                row = cur.fetchone()

                if row:
                    uid, tier = row

                    cur.execute("UPDATE users SET tier=? WHERE user_id=?", (tier, uid))
                    db.commit()

# ================= RUN =================

async def main():
    asyncio.create_task(payment_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
