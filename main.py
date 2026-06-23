import telebot
import json

from config import BOT_TOKEN
from brain import ask_baffy, build_context
from db import save_message, add_xp
from economy import add_coins
from classes import assign_class
from world import update_chaos

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(func=lambda m: True)
def handle(m):

    chat_id = m.chat.id
    user_id = m.from_user.id
    text = m.text or ""

    save_message(chat_id, user_id, text)

    context = build_context(chat_id, user_id)

    ai = ask_baffy(chat_id, user_id, text, context)

    # XP
    add_xp(user_id, chat_id, ai.get("xp", 0))

    # COINS
    add_coins(user_id, chat_id, ai.get("coins", 0))

    # CLASS SYSTEM
    assign_class(user_id, chat_id, context["xp"])

    # WORLD CHAOS
    update_chaos(chat_id, ai.get("chaos", 0))

    # ACTIONS
    if ai["action"] in ["message", "event", "world_event"]:
        bot.send_message(chat_id, ai.get("text", ""))

    elif ai["action"] == "reward":
        bot.send_message(chat_id, f"✨ +XP +Coins")

    elif ai["action"] == "game":
        if ai.get("game") == "mafia":
            bot.send_message(chat_id, "🕵️ Мафия началась!")
        elif ai.get("game") == "crocodile":
            bot.send_message(chat_id, "🎭 Крокодил старт!")
        else:
            bot.send_message(chat_id, "❓ Викторина")

    elif ai["action"] == "punishment":
        bot.send_message(chat_id, "⚠️ Нарушение зафиксировано")


bot.infinity_polling()
