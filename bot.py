import os
import asyncio
import sqlite3
import aiohttp
import hashlib
import traceback
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from groq import Groq
from gtts import gTTS

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

groq = Groq(api_key=GROQ_API_KEY)

# ================= DB =================

db = sqlite3.connect("jarvis.db", check_same_thread=False)
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
    ref INTEGER,
    total_paid REAL DEFAULT 0
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

cur.execute("""
CREATE TABLE IF NOT EXISTS cache(
    key TEXT PRIMARY KEY,
    response TEXT,
    created TEXT
)
""")

db.commit()

# ================= CONFIG =================

LIMITS = {"free": 15, "pro": 80, "ultra": 250}
PRICES = {"pro": 1, "ultra": 3}
REF_PERCENT = 0.2
CACHE_TTL = 30

# ================= UTILS =================

def now():
    return datetime.utcnow()

def is_expired(exp):
    if not exp:
        return True
    return now() > datetime.fromisoformat(exp)

def make_key(text, role):
    return hashlib.md5((text + role).encode()).hexdigest()

# ================= CACHE =================

def get_cache(key):
    cur.execute("SELECT response, created FROM cache WHERE key=?", (key,))
    row = cur.fetchone()
    if not row:
        return None

    resp, created = row
    created = datetime.fromisoformat(created)

    if now() - created > timedelta(minutes=CACHE_TTL):
        return None

    return resp

def set_cache(key, resp):
    cur.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                (key, resp, now().isoformat()))
    db.commit()

# ================= AI =================

async def ask_ai(text, memory, role):
    key = make_key(text, role)

    cached = get_cache(key)
    if cached:
        return cached

    prompt = f"ROLE:{role}\nMEM:{memory}\nUSER:{text}"

    try:
        def call():
            return groq.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}]
            ).choices[0].message.content

        resp = await asyncio.to_thread(call)

    except Exception as e:
        resp = "⚠️ AI ошибка. Попробуй позже."

    set_cache(key, resp)
    return resp

# ================= LIMIT =================

def check_limit(uid):
    cur.execute("SELECT tier, messages FROM users WHERE user_id=?", (uid,))
    tier, used = cur.fetchone()
    return used < LIMITS[tier]

def inc(uid):
    cur.execute("UPDATE users SET messages = messages + 1 WHERE user_id=?", (uid,))
    db.commit()

# ================= START =================

@router.message(F.text == "/start")
async def start(msg: Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (msg.from_user.id,))
    db.commit()

    await msg.answer("🚀 SaaS 5.0 ONLINE")

# ================= MAIN ENGINE (FIXED) =================

@router.message(F.text)
async def engine(msg: Message):
    uid = msg.from_user.id

    try:
        cur.execute("SELECT tier, expire, memory, role, messages FROM users WHERE user_id=?", (uid,))
        tier, exp, memory, role, used = cur.fetchone()

        if tier != "free" and is_expired(exp):
            tier = "free"
            cur.execute("UPDATE users SET tier='free' WHERE user_id=?", (uid,))
            db.commit()

        if used >= LIMITS[tier]:
            await msg.answer("🚫 Лимит исчерпан")
            return

        inc(uid)

        reply = await ask_ai(msg.text, memory, role)

        memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-3000:]

        cur.execute("UPDATE users SET memory=? WHERE user_id=?", (memory, uid))
        db.commit()

        await msg.answer(reply)

        asyncio.create_task(send_voice(uid, reply))

    except Exception as e:
        await msg.answer("⚠️ Ошибка обработки запроса")
        print(traceback.format_exc())

# ================= VOICE =================

async def send_voice(uid, text):
    try:
        tts = gTTS(text[:200])
        path = f"{uid}.mp3"
        tts.save(path)
        await bot.send_voice(uid, open(path, "rb"))
    except:
        pass

# ================= RUN =================

async def main():
    asyncio.create_task(payment_worker())
    await dp.start_polling(bot)

async def payment_worker():
    while True:
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
