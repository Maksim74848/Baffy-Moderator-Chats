import asyncio
import sqlite3
import tempfile
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from groq import Groq
import easyocr

# ================= НАСТРОЙКИ =================

BOT_TOKEN = "ТВОЙ_BOT_TOKEN"
GROQ_API_KEY = "ТВОЙ_GROQ_KEY"
PAYMENT_PROVIDER_TOKEN = "ТВОЙ_WALLET_PAY_TOKEN"

MODEL_NAME = "llama-3.1-70b-versatile"
MAX_MEMORY = 20

# ================= ИНИЦИАЛИЗАЦИЯ =================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
groq = Groq(api_key=GROQ_API_KEY)
ocr = easyocr.Reader(["ru", "en"])

# ================= БАЗА ДАННЫХ =================

db = sqlite3.connect("jarvis.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    mood TEXT DEFAULT 'дружелюбный',
    style TEXT DEFAULT 'нормально',
    emoji TEXT DEFAULT 'мало',
    tier TEXT DEFAULT 'simple_1'
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id INTEGER,
    role TEXT,
    content TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS summary (
    user_id INTEGER PRIMARY KEY,
    content TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    user_id INTEGER PRIMARY KEY,
    ref_code TEXT,
    invited INTEGER DEFAULT 0
)
""")

db.commit()

# ================= FSM =================

class Menu(StatesGroup):
    main = State()
    chat = State()

# ================= КНОПКИ =================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Диалог с Jarvis", callback_data="chat")],
        [InlineKeyboardButton(text="🗂 Режим секретаря", callback_data="secretary")],
        [InlineKeyboardButton(text="🧠 Настройки ИИ", callback_data="settings")],
        [InlineKeyboardButton(text="🖼 Текст с картинки", callback_data="ocr")],
        [InlineKeyboardButton(text="💎 Версии Jarvis", callback_data="tiers")],
        [InlineKeyboardButton(text="🗑 Очистить память", callback_data="clear")]
    ])

def settings_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🙂 Настроение", callback_data="mood")],
        [InlineKeyboardButton(text="⚡ Стиль ответа", callback_data="style")],
        [InlineKeyboardButton(text="😄 Эмодзи", callback_data="emoji")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

def choice_menu(param, values):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=v, callback_data=f"set_{param}_{v}")]
        for v in values
    ] + [[InlineKeyboardButton(text="⬅ Назад", callback_data="settings")]])

def tiers_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Simple 1 (бесплатно)", callback_data="tier_simple_1")],
        [InlineKeyboardButton(text="Simple 2 — 5₽", callback_data="buy_simple_2")],
        [InlineKeyboardButton(text="Pro 1 — 15₽", callback_data="buy_pro_1")],
        [InlineKeyboardButton(text="Pro 2 — 25₽", callback_data="buy_pro_2")],
        [InlineKeyboardButton(text="Pro 3 — 49₽", callback_data="buy_pro_3")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

# ================= ЛОГИКА =================

def get_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
    db.commit()
    cur.execute("SELECT mood, style, emoji, tier FROM users WHERE user_id=?", (user_id,))
    return cur.fetchone()

def system_prompt(profile):
    mood, style, emoji, tier = profile
    return (
        "Ты — ИИ Jarvis.\n"
        "Роль: персональный секретарь.\n"
        f"Настроение: {mood}\n"
        f"Стиль ответа: {style}\n"
        f"Эмодзи: {emoji}\n"
        "Отвечай полезно, понятно и по делу."
    )

def load_memory(user_id):
    cur.execute("SELECT role, content FROM memory WHERE user_id=?", (user_id,))
    return [{"role": r, "content": c} for r, c in cur.fetchall()[-MAX_MEMORY:]]

def save_memory(user_id, role, text):
    cur.execute("INSERT INTO memory VALUES (?,?,?)", (user_id, role, text))
    db.commit()

def summarize(user_id):
    cur.execute("SELECT role, content FROM memory WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    if len(rows) < MAX_MEMORY:
        return

    text = "\n".join([f"{r}: {c}" for r, c in rows[:-5]])

    summary = groq.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "Сделай краткое саммари диалога."},
            {"role": "user", "content": text}
        ]
    ).choices[0].message.content

    cur.execute("INSERT OR REPLACE INTO summary VALUES (?,?)", (user_id, summary))
    cur.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
    db.commit()

def ask_jarvis(user_id, text):
    summarize(user_id)
    profile = get_user(user_id)

    messages = [{"role": "system", "content": system_prompt(profile)}]

    cur.execute("SELECT content FROM summary WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        messages.append({"role": "system", "content": f"История: {row[0]}"})

    messages += load_memory(user_id)
    messages.append({"role": "user", "content": text})

    reply = groq.chat.completions.create(
        model=MODEL_NAME,
        messages=messages
    ).choices[0].message.content

    save_memory(user_id, "user", text)
    save_memory(user_id, "assistant", reply)
    return reply

def get_ref_link(user_id, bot_username):
    cur.execute(
        "INSERT OR IGNORE INTO referrals VALUES (?,?,0)",
        (user_id, str(uuid.uuid4())[:8])
    )
    db.commit()
    cur.execute("SELECT ref_code FROM referrals WHERE user_id=?", (user_id,))
    code = cur.fetchone()[0]
    return f"https://t.me/{bot_username}?start={code}"

# ================= ХЕНДЛЕРЫ =================

@dp.message(F.text.startswith("/start"))
async def start(msg: Message, state: FSMContext):
    if len(msg.text.split()) > 1:
        ref = msg.text.split()[1]
        cur.execute("UPDATE referrals SET invited = invited + 1 WHERE ref_code=?", (ref,))
        db.commit()

    await state.set_state(Menu.main)
    bot_name = (await bot.me()).username
    ref_link = get_ref_link(msg.from_user.id, bot_name)

    await msg.answer(
        "👋 Привет, я **Jarvis**.\n\n"
        "Я умею помнить диалоги, работать с картинками и быть твоим секретарём.\n\n"
        f"🔗 Твоя реферальная ссылка:\n{ref_link}",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "chat")
async def chat(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Menu.chat)
    await cb.message.edit_text(
        "💬 Пиши — я слушаю.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="back")]]
        )
    )

@dp.message(Menu.chat, F.text)
async def dialog(msg: Message):
    await msg.answer("⌛ Думаю…")
    reply = ask_jarvis(msg.from_user.id, msg.text)
    await msg.answer(reply)

@dp.callback_query(F.data == "secretary")
async def secretary(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Menu.chat)
    await cb.message.edit_text(
        "🗂 Режим секретаря активирован.\n"
        "Можешь давать задачи, планы и поручения.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="back")]]
        )
    )

@dp.message(F.photo)
async def image(msg: Message):
    file = await bot.get_file(msg.photo[-1].file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        await bot.download_file(file.file_path, f.name)
        text = "\n".join(ocr.readtext(f.name, detail=0))
    await msg.answer("📄 Найденный текст:\n\n" + (text or "Пусто"))

@dp.callback_query(F.data == "settings")
async def settings(cb: CallbackQuery):
    await cb.message.edit_text("🧠 Настройки", reply_markup=settings_menu())

@dp.callback_query(F.data.startswith("set_"))
async def set_param(cb: CallbackQuery):
    _, key, val = cb.data.split("_", 2)
    cur.execute(f"UPDATE users SET {key}=? WHERE user_id=?", (val, cb.from_user.id))
    db.commit()
    await cb.message.edit_text("✅ Обновлено", reply_markup=settings_menu())

@dp.callback_query(F.data == "clear")
async def clear(cb: CallbackQuery):
    cur.execute("DELETE FROM memory WHERE user_id=?", (cb.from_user.id,))
    cur.execute("DELETE FROM summary WHERE user_id=?", (cb.from_user.id,))
    db.commit()
    await cb.message.edit_text("🗑 Память очищена", reply_markup=main_menu())

@dp.callback_query(F.data == "tiers")
async def tiers(cb: CallbackQuery):
    await cb.message.edit_text("💎 Версии Jarvis", reply_markup=tiers_menu())

@dp.callback_query(F.data.startswith("buy_"))
async def buy(cb: CallbackQuery):
    tier = cb.data.replace("buy_", "")
    prices = {"simple_2":5,"pro_1":15,"pro_2":25,"pro_3":49}
    await bot.send_invoice(
        cb.from_user.id,
        title=f"Jarvis {tier}",
        description="Доступ к версии",
        payload=tier,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label=tier, amount=prices[tier]*100)]
    )

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(msg: Message):
    tier = msg.successful_payment.invoice_payload
    cur.execute("UPDATE users SET tier=? WHERE user_id=?", (tier, msg.from_user.id))
    db.commit()
    await msg.answer("💎 Версия активирована!", reply_markup=main_menu())

@dp.callback_query(F.data == "back")
async def back(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Menu.main)
    await cb.message.edit_text("🏠 Главное меню", reply_markup=main_menu())

# ================= ЗАПУСК =================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
