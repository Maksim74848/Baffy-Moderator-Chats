import os
import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from groq import Groq
from db import get_user, create_user, update_memory

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

groq = Groq(api_key=GROQ_API_KEY)

# ========== AI ==========
async def ask_ai(text, memory, role):
    def call():
        return groq.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "user", "content": text}]
        ).choices[0].message.content

    return await asyncio.to_thread(call)


# ========== START ==========
@router.message(F.text == "/start")
async def start(msg: Message):
    create_user(msg.from_user.id)
    await msg.answer("🚀 SaaS ONLINE")


# ========== CHAT ==========
@router.message(F.text)
async def chat(msg: Message):
    uid = msg.from_user.id
    user = get_user(uid)

    if not user:
        create_user(uid)
        user = get_user(uid)

    memory = user[4] or ""
    role = user[3]

    reply = await ask_ai(msg.text, memory, role)

    memory = (memory + f"\nU:{msg.text}\nA:{reply}")[-3000:]
    update_memory(uid, memory)

    await msg.answer(reply)


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
