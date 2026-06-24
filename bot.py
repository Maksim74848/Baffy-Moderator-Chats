import os
import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from groq import Groq

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("BOT_TOKEN or GROQ_API_KEY is missing")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

groq = Groq(api_key=GROQ_API_KEY)

# ================== FSM ==================

class AppState(StatesGroup):
    menu = State()
    chat = State()

# ================== DATABASE ==================

db = sqlite3.connect("jarvis.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    messages INTEGER DEFAULT 0
)
""")

db.commit()

# ================== LIMITS ==================

MESSAGE_LIMIT = 20

# ================== UI ==================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Chat", callback_data="chat")],
        [InlineKeyboardButton(text="⚙️ Role", callback_data="role")],
        [InlineKeyboardButton(text="📊 Status", callback_data="status")]
    ])

def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back")]
    ])

# ================== AI ==================

async def ask_ai(user_text: str, memory: str, role: str) -> str:
    prompt = f"""
You are an AI with role: {role}.
Conversation memory:
{memory}

User message:
{user_text}
"""

    try:
        def call():
            resp = groq.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                timeout=20
            )
            return resp.choices[0].message.content

        return await asyncio.to_thread(call)

    except Exception as e:
        print("GROQ ERROR:", e)
        return "⚠️ ИИ временно недоступен. Попробуй позже."

# ================== START ==================

@router.message(F.text == "/start")
async def start(msg: Message, state: FSMContext):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (msg.from_user.id,))
    db.commit()

    await state.set_state(AppState.menu)
    await msg.answer(
        "🤖 **JARVIS SaaS 5.1**\nВыбери действие:",
        reply_markup=main_menu()
    )

# ================== MENU ==================

@router.callback_query(F.data == "back")
async def back(c: CallbackQuery, state: FSMContext):
    await state.set_state(AppState.menu)
    await c.message.edit_text("🏠 Главное меню", reply_markup=main_menu())

@router.callback_query(F.data == "chat")
async def open_chat(c: CallbackQuery, state: FSMContext):
    await state.set_state(AppState.chat)
    await c.message.edit_text(
        "💬 Напиши сообщение для JARVIS",
        reply_markup=back_menu()
    )

@router.callback_query(F.data == "status")
async def status(c: CallbackQuery):
    cur.execute(
        "SELECT role, messages FROM users WHERE user_id=?",
        (c.from_user.id,)
    )
    role, used = cur.fetchone()

    await c.message.answer(
        f"📊 Статус:\n"
        f"Роль: {role}\n"
        f"Сообщений: {used}/{MESSAGE_LIMIT}"
    )

@router.callback_query(F.data == "role")
async def change_role(c: CallbackQuery):
    cur.execute("SELECT role FROM users WHERE user_id=?", (c.from_user.id,))
    current = cur.fetchone()[0]

    new_role = "secretary" if current == "assistant" else "assistant"

    cur.execute(
        "UPDATE users SET role=? WHERE user_id=?",
        (new_role, c.from_user.id)
    )
    db.commit()

    await c.message.answer(f"⚙️ Роль изменена: {new_role}")

# ================== CHAT ==================

@router.message(AppState.chat)
async def chat(msg: Message):
    uid = msg.from_user.id

    cur.execute(
        "SELECT role, memory, messages FROM users WHERE user_id=?",
        (uid,)
    )
    role, memory, used = cur.fetchone()

    if used >= MESSAGE_LIMIT:
        await msg.answer("🚫 Лимит сообщений исчерпан")
        return

    cur.execute(
        "UPDATE users SET messages = messages + 1 WHERE user_id=?",
        (uid,)
    )
    db.commit()

    reply = await ask_ai(msg.text, memory, role)

    new_memory = (memory + f"\nUSER: {msg.text}\nAI: {reply}")[-3000:]

    cur.execute(
        "UPDATE users SET memory=? WHERE user_id=?",
        (new_memory, uid)
    )
    db.commit()

    await msg.answer(reply)

# ================== RUN ==================

async def main():
    print("🚀 JARVIS SaaS 5.1 ONLINE")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
