import os
import asyncio
import asyncpg
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart

from groq import Groq

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
groq = Groq(api_key=GROQ_API_KEY)

db = None

# ================= DB =================

async def init_db():
    global db
    db = await asyncpg.create_pool(DATABASE_URL)

    async with db.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id BIGINT PRIMARY KEY,
            tier TEXT DEFAULT 'free',
            messages INT DEFAULT 0,
            memory TEXT DEFAULT '',
            is_admin BOOLEAN DEFAULT FALSE
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS payments(
            invoice TEXT PRIMARY KEY,
            user_id BIGINT,
            tier TEXT,
            status TEXT
        );
        """)

# ================= AI =================

async def ask_ai(prompt, memory):
    full = f"{memory}\nUSER: {prompt}"

    try:
        def run():
            return groq.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": full}],
                temperature=0.6,
                max_tokens=700
            ).choices[0].message.content

        return await asyncio.to_thread(run)

    except:
        return "⚠️ ИИ временно недоступен"

# ================= MEMORY =================

def update_memory(old, user, ai):
    text = old + f"\nU:{user}\nA:{ai}"
    return text[-6000:]

# ================= UI =================

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Подписка", callback_data="sub")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="set")]
    ])

def sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="PRO $3", callback_data="buy_pro")],
        [InlineKeyboardButton(text="ULTRA $10", callback_data="buy_ultra")]
    ])

# ================= START =================

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "🤖 Jarvis активен\nПросто напиши сообщение.",
        reply_markup=main_kb()
    )

# ================= CHAT =================

@dp.message(F.text)
async def chat(m: Message):
    uid = m.from_user.id
    text = m.text

    async with db.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)

        if not user:
            await conn.execute("INSERT INTO users(user_id) VALUES($1)", uid)
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)

        limit = 30 if user["tier"] == "free" else 1000

        if user["messages"] >= limit:
            return await m.answer("🚫 Лимит исчерпан", reply_markup=sub_kb())

        ai = await ask_ai(text, user["memory"])

        memory = update_memory(user["memory"], text, ai)

        await conn.execute("""
            UPDATE users
            SET messages = messages + 1,
                memory = $1
            WHERE user_id=$2
        """, memory, uid)

    await m.answer(ai, reply_markup=main_kb())

# ================= SUBS =================

@dp.callback_query(F.data == "sub")
async def sub(c: CallbackQuery):
    await c.message.answer("Выбери тариф:", reply_markup=sub_kb())

async def create_invoice(user_id, tier):
    async with aiohttp.ClientSession() as s:
        r = await s.post(
            "https://pay.crypt.bot/api/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={
                "asset": "USDT",
                "amount": 3 if tier == "pro" else 10,
                "payload": f"{user_id}:{tier}"
            }
        )
        data = await r.json()
        return data["result"]["pay_url"], data["result"]["invoice_id"]

@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery):
    tier = c.data.replace("buy_", "")

    url, invoice = await create_invoice(c.from_user.id, tier)

    async with db.acquire() as conn:
        await conn.execute(
            "INSERT INTO payments VALUES($1,$2,$3,'pending')",
            invoice, c.from_user.id, tier
        )

    await c.message.answer(f"💳 Оплата: {url}")

# ================= WEBHOOK =================

from aiohttp import web

async def crypto_webhook(request):
    data = await request.json()

    payload = data["payload"]
    invoice = data["invoice_id"]

    user_id, tier = payload.split(":")

    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET tier=$1 WHERE user_id=$2", tier, int(user_id))
        await conn.execute("UPDATE payments SET status='paid' WHERE invoice=$1", invoice)

    return web.json_response({"ok": True})

# ================= ADMIN =================

@dp.message(F.text == ADMIN_PASSWORD)
async def admin(m: Message):
    if m.from_user.id == ADMIN_ID:
        async with db.acquire() as conn:
            users = await conn.fetch("SELECT COUNT(*) FROM users")
        await m.answer(f"👑 Users: {users[0][0]}")

# ================= RUN =================

async def main():
    await init_db()
    asyncio.create_task(dp.start_polling(bot))

    app = web.Application()
    app.router.add_post("/crypto", crypto_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()

    print("RUNNING")

if __name__ == "__main__":
    asyncio.run(main())
