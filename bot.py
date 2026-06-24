import os
import asyncio
import sqlite3
import aiohttp
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

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
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    messages_today INTEGER DEFAULT 0,
    last_reset TEXT,
    memory TEXT DEFAULT ''
)
""")

db.commit()

# ================= LIMITS =================

LIMITS = {
    "free": 20,
    "pro": 100,
    "ultra": 300
}

# ================= UI =================

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат", callback_data="chat")],
        [InlineKeyboardButton(text="💎 Подписка", callback_data="subs")],
        [InlineKeyboardButton(text="🎤 Голос режим", callback_data="voice")]
    ])

# ================= RESET LIMIT =================

def reset_if_needed(uid):
    cur.execute("SELECT last_reset FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    today = str(datetime.now().date())

    if not row or row[0] != today:
        cur.execute("""
        UPDATE users
        SET messages_today=0, last_reset=?
        WHERE user_id=?
        """, (today, uid))
        db.commit()

# ================= LIMIT CHECK =================

def can_use(uid):
    cur.execute("SELECT tier, messages_today FROM users WHERE user_id=?", (uid,))
    tier, used = cur.fetchone()

    reset_if_needed(uid)

    return used < LIMITS[tier]

# ================= INCREMENT =================

def add_message(uid):
    cur.execute("""
    UPDATE users
    SET messages_today = messages_today + 1
    WHERE user_id=?
    """, (uid,))
    db.commit()

# ================= CHAT =================

async def ask_groq(text):
    res = groq.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role":"user","content":text}]
    )
    return res.choices[0].message.content

# ================= START =================

@dp.message(F.text == "/start")
async def start(msg: Message):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (msg.from_user.id,))
    db.commit()

    await msg.answer(
        "🤖 JARVIS AI ONLINE\n\n"
        "Я ассистент с памятью, голосом и подпиской.",
        reply_markup=menu()
    )

# ================= CHAT =================

@dp.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id

    if not can_use(uid):
        await msg.answer("🚫 Лимит сообщений исчерпан. Оформи подписку 💎")
        return

    add_message(uid)

    reply = await ask_groq(msg.text)

    # voice reply optional (short)
    tts = gTTS(reply[:200])
    path = f"{uid}.mp3"
    tts.save(path)

    await msg.answer(reply)
    await msg.answer_voice(open(path, "rb"))

# ================= VOICE INPUT =================

@dp.message(F.voice)
async def voice(msg: Message):
    file = await bot.get_file(msg.voice.file_id)
    path = f"{msg.from_user.id}.ogg"

    await bot.download_file(file.file_path, path)

    audio = open(path, "rb")

    transcript = groq.audio.transcriptions.create(
        file=audio,
        model="whisper-large-v3"
    ).text

    await msg.answer(f"🎤 Ты сказал: {transcript}")

    reply = await ask_groq(transcript)
    await msg.answer(reply)

# ================= SUBSCRIPTIONS =================

@dp.callback_query(F.data == "subs")
async def subs(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Free", callback_data="tier_free")],
        [InlineKeyboardButton(text="Pro - 5$", callback_data="tier_pro")],
        [InlineKeyboardButton(text="Ultra - 10$", callback_data="tier_ultra")]
    ])
    await cb.message.answer("💎 Выбери подписку:", reply_markup=kb)

@dp.callback_query(F.data.startswith("tier_"))
async def set_tier(cb: CallbackQuery):
    tier = cb.data.replace("tier_", "")

    cur.execute("""
    UPDATE users SET tier=? WHERE user_id=?
    """, (tier, cb.from_user.id))
    db.commit()

    await cb.message.answer(f"✅ Подписка активирована: {tier.upper()}")

# ================= RUN =================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
