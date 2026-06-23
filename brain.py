import json
from ai import call_ai
from db import get_history, get_user_xp
from world import get_world

def build_context(chat_id, user_id):
    history = get_history(chat_id, 20)
    world = get_world(chat_id)
    xp = get_user_xp(user_id, chat_id)

    return {
        "history": history,
        "world": world,
        "xp": xp
    }


def ask_baffy(chat_id, user_id, text, context):

    prompt = f"""
Ты — Baffy, AI Game Master Telegram мира.

Ты управляешь ВСЕМ:
- модерацией
- игрой
- экономикой
- XP
- классами
- событиями мира

Ты НЕ бот. Ты симулятор мира.

---

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
  "action": "message | event | game | reward | punishment | world_event",
  "text": "response",
  "xp": 0-100,
  "coins": 0-100,
  "chaos": -5 to +5,
  "game": "mafia | crocodile | quiz | none",
  "reason": "why"
}}
"""

    r = call_ai(prompt)

    try:
        return json.loads(r)
    except:
        return {
            "action": "message",
            "text": "..."
        }
