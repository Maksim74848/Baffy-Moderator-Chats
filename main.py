import telebot
import json

from config import BOT_TOKEN
from db import (
    save_message,
    add_xp,
    add_coins,
    update_chaos
)
from brain import ask_baffy, build_context

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(func=lambda m: True)
def handle(m):

    chat_id = m.chat.id
    user_id = m.from_user.id
    text = m.text or ""

    save_message(chat_id, user_id, text)

    context = build_context(chat_id, user_id)

    ai = ask_baffy(chat_id, user_id, text, context)

    # XP + COINS
    add_xp(user_id, chat_id, ai.get("xp", 0))
    add_coins(user_id, chat_id, ai.get("coins", 0))

    # WORLD CHAOS
    update_chaos(chat_id, ai.get("chaos", 0))

    # RESPONSE
    if ai.get("text"):
        bot.send_message(chat_id, ai["text"])

    # EVENTS
    if ai["action"] == "event":
        bot.send_message(chat_id, "🎲 " + ai.get("text", "Event"))

    if ai["action"] == "game":
        bot.send_message(chat_id, f"🎮 Game started: {ai.get('game')}")

    if ai["action"] == "reward":
        bot.send_message(chat_id, "✨ Reward given!")


print("Baffy running on Railway...")
bot.infinity_polling()
