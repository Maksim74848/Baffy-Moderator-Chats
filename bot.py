import os
import asyncio
import aiohttp
import base64
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    Voice
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from groq import Groq
from PIL import Image
import pytesseract
from io import BytesIO

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("8470101764:AAF2QWP9bPUwSwmDsKPrOFkGC0amvz3cWlw")
GROQ_API_KEY = os.getenv("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")
CRYPTO_PAY_TOKEN = os.getenv("600210:AAazektG1ofJzATQOO6WUN0Ft5kZYfz4MV8")

BOT_NAME = "Jarvis"

# ================== INIT ==================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
groq = Groq(api_key=GROQ_API_KEY)

db = sqlite3.connect("db.sqlite3")
cursor = db.cursor()

# ================== DB ==================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    model TEXT DEFAULT 'basic_1',
    mood TEXT DEFAULT 'neutral',
    emoji INTEGER DEFAULT 1,
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    ref INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    invoice_id TEXT,
    user_id INTEGER,
    amount INTEGER
)
""")

db.commit()

# ================== FSM ==================

class Settings(StatesGroup):
    mood = State()
    emoji = State()
    role = State()

# ================== KEYBOARDS ==================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Диалог", callback_data="chat")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="💎 Версии ИИ", callback_data="models")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Рефералы", callback_data="ref")]
    ])

def settings_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😌 Настроение", callback_data="set_mood")],
        [InlineKeyboardButton(text="✨ Эмодзи", callback_data="set_emoji")],
        [InlineKeyboardButton(text="🗂 Роль (Секретарь)", callback_data="set_role")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

def models_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Basic 1", callback_data="model_basic_1")],
        [InlineKeyboardButton(text="Basic 2", callback_data="model_basic_2")],
        [InlineKeyboardButton(text="Pro 1", callback_data="model_pro_1")],
        [InlineKeyboardButton(text="Pro 2", callback_data="model_pro_2")],
        [InlineKeyboardButton(text="Ultra", callback_data="model_ultra")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

# ================== START ==================

@dp.message(F.text == "/start")
async def start(msg: Message):
    ref = msg.text.split(" ")[1] if len(msg.text.split()) > 1 else None
    cursor.execute("INSERT OR IGNORE INTO users(user_id, ref) VALUES (?,?)", (msg.from_user.id, ref))
    db.commit()
    await msg.answer(
        f"👋 Привет! Я {BOT_NAME}.\n\n"
        "Я умею помнить диалоги, быть секретарем, работать с голосом и изображениями.\n\n"
        "Выбери действие 👇",
        reply_markup=main_menu()
    )

# ================== CALLBACKS ==================

@dp.callback_query()
async def callbacks(call: CallbackQuery, state: FSMContext):
    data = call.data
    uid = call.from_user.id

    if data == "settings":
        await call.message.edit_text("⚙️ Настройки", reply_markup=settings_menu())

    elif data == "models":
        await call.message.edit_text("💎 Выбор версии ИИ", reply_markup=models_menu())

    elif data.startswith("model_"):
        cursor.execute("UPDATE users SET model=? WHERE user_id=?", (data.replace("model_", ""), uid))
        db.commit()
        await call.answer("✅ Модель выбрана")

    elif data == "balance":
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = cursor.fetchone()[0]
        await call.message.answer(f"💰 Баланс: {bal}₽")

    elif data == "ref":
        await call.message.answer(
            f"🎁 Твоя реферальная ссылка:\n"
            f"https://t.me/{(await bot.me()).username}?start={uid}\n\n"
            "Ты получаешь 20% с пополнений друзей."
        )

    elif data == "back":
        await call.message.edit_text("Главное меню", reply_markup=main_menu())

# ================== CHAT ==================

async def summarize(memory):
    prompt = f"Сделай краткое саммари:\n{memory}"
    res = groq.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role":"user","content":prompt}]
    )
    return res.choices[0].message.content[:800]

@dp.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id
    cursor.execute("SELECT memory, mood, emoji, role FROM users WHERE user_id=?", (uid,))
    memory, mood, emoji, role = cursor.fetchone()

    prompt = f"""
Ты {role}.
Настроение: {mood}.
Эмодзи: {'да' if emoji else 'нет'}.
Контекст:
{memory}

Пользователь: {msg.text}
"""

    res = groq.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role":"user","content":prompt}]
    )

    answer = res.choices[0].message.content

    new_memory = memory + f"\nUser: {msg.text}\nJarvis: {answer}"
    if len(new_memory) > 3000:
        new_memory = await summarize(new_memory)

    cursor.execute("UPDATE users SET memory=? WHERE user_id=?", (new_memory, uid))
    db.commit()

    await msg.answer(answer)

# ================== IMAGE OCR ==================

@dp.message(F.photo)
async def image_handler(msg: Message):
    file = await bot.get_file(msg.photo[-1].file_id)
    data = await bot.download_file(file.file_path)
    img = Image.open(BytesIO(data.read()))
    text = pytesseract.image_to_string(img, lang="rus+eng")
    await msg.answer(f"📄 Текст с картинки:\n{text}")

# ================== CRYPTOPAY ==================

async def create_invoice(uid, amount):
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://pay.crypt.bot/api/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={"asset":"USDT","amount":amount}
        ) as r:
            return (await r.json())["result"]

# ================== RUN ==================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
