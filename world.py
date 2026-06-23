import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS world (
    chat_id INTEGER PRIMARY KEY,
    season INTEGER DEFAULT 1,
    chaos INTEGER DEFAULT 0
)
""")

conn.commit()


def get_world(chat_id):
    cur.execute("SELECT season, chaos FROM world WHERE chat_id=?", (chat_id,))
    r = cur.fetchone()
    if not r:
        cur.execute("INSERT INTO world VALUES (?, 1, 0)", (chat_id,))
        conn.commit()
        return (1, 0)
    return r


def update_chaos(chat_id, value):
    cur.execute("INSERT OR IGNORE INTO world VALUES (?, 1, 0)", (chat_id,))
    cur.execute("UPDATE world SET chaos = chaos + ? WHERE chat_id=?", (value, chat_id))
    conn.commit()
