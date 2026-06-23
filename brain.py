import json
from ai import call_ai
from db import get_history, get_user_xp, get_world

def build_context(chat_id, user_id):
    return {
        "history": get_history(chat_id, 20),
        "xp": get_user_xp(user_id, chat_id),
        "world": get_world(chat_id)
    }


def ask_baffy(chat_id, user_id, text, context):

    prompt = f"""
Ты — Baffy, AI управляющий живым Telegram миром.

Ты:
- модератор
- Game Master
- экономика
- сюжет
- события

МИР:
Season: {context['world'][0]}
Chaos: {context['world'][1]}

USER XP: {context['xp']}

HISTORY:
{context['history']}

MESSAGE:
{text}

---

Верни JSON:

{{
  "action": "message | event | game | reward | world_event",
  "text": "...",
  "xp": 0-100,
  "coins": 0-100,
  "chaos": -5 to 5,
  "game": "mafia | crocodile | quiz | none",
  "reason": "..."
}}
"""

    try:
        return json.loads(call_ai(prompt))
    except:
        return {
            "action": "message",
            "text": "..."
        }
