import os
import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from groq import Groq

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

groq = Groq(api_key=GROQ_API_KEY)

# ================== DB ==================

db = sqlite3.connect("jarvis.db")
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    memory TEXT DEFAULT '',
    role TEXT DEFAULT 'assistant',
    messages INTEGER DEFAULT 0
)
""")
db.commit()

# ================== FSM ==================

class UI(StatesGroup):
    menu = State()
    chat = State()

# ================== UI ==================

def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат", callback_data="chat")],
        [InlineKeyboardButton(text="⚙️ Роль", callback_data="role")],
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

# ================== AI ==================

def ask_ai_sync(text, memory, role):
    prompt = f"""
Ты — {role}.
Контекст:
{memory}

Сообщение пользователя:
{text}
"""
    result = groq.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}]
    )
    return result.choices[0].message.content

# ================== START ==================

@router.message(F.text == "/start")
async def start(msg: Message, state: FSMContext):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (msg.from_user.id,))
    db.commit()
    await state.set_state(UI.menu)
    await msg.answer("🚀 Jarvis SaaS 5.1.1", reply_markup=menu_kb())

# ================== MENU ==================

@router.callback_query(F.data == "back")
async def back(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(UI.menu)
    await c.message.edit_text("🏠 Главное меню", reply_markup=menu_kb())

@router.callback_query(F.data == "chat")
async def open_chat(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(UI.chat)
    await c.message.edit_text("💬 Напиши сообщение", reply_markup=back_kb())

@router.callback_query(F.data == "role")
async def role(c: CallbackQuery):
    await c.answer()
    cur.execute("SELECT role FROM users WHERE user_id=?", (c.from_user.id,))
    role = cur.fetchone()["role"]
    new_role = "секретарь" if role == "assistant" else "assistant"
    cur.execute("UPDATE users SET role=? WHERE user_id=?", (new_role, c.from_user.id))
    db.commit()
    await c.message.answer(f"⚙️ Роль изменена: {new_role}")

# ================== CHAT ==================

@router.message(UI.chat)
async def chat(msg: Message):
    uid = msg.from_user.id

    try:
        cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        user = cur.fetchone()

        reply = await asyncio.get_event_loop().run_in_executor(
            None,
            ask_ai_sync,
            msg.text,
            user["memory"],
            user["role"]
        )

        memory = (user["memory"] + f"\nU:{msg.text}\nA:{reply}")[-3000:]

        cur.execute(
            "UPDATE users SET memory=?, messages=messages+1 WHERE user_id=?",
            (memory, uid)
        )
        db.commit()

        await msg.answer(reply)

    except Exception as e:
        print("AI ERROR:", e)
        await msg.answer("⚠️ Внутренняя ошибка. Попробуй ещё раз.")

# ================== RUN ==================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
