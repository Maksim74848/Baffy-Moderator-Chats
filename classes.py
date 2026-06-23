import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS classes (
    user_id INTEGER,
    chat_id INTEGER,
    class TEXT,
    PRIMARY KEY(user_id, chat_id)
)
""")

conn.commit()


def assign_class(user_id, chat_id, xp):
    if xp > 500:
        c = "warrior"
    elif xp > 300:
        c = "mage"
    elif xp > 150:
        c = "trickster"
    else:
        c = "wanderer"

    cur.execute("""
    INSERT OR REPLACE INTO classes VALUES (?, ?, ?)
    """, (user_id, chat_id, c))

    conn.commit()
