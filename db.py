import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER,
    user_id INTEGER,
    text TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER,
    chat_id INTEGER,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    PRIMARY KEY(user_id, chat_id)
)
""")

conn.commit()


def save_message(chat_id, user_id, text):
    cur.execute("INSERT INTO messages VALUES (?, ?, ?)", (chat_id, user_id, text))
    conn.commit()


def get_history(chat_id, limit=20):
    cur.execute("SELECT user_id, text FROM messages WHERE chat_id=? LIMIT ?", (chat_id, limit))
    return cur.fetchall()


def add_xp(user_id, chat_id, xp):
    cur.execute("""
    INSERT OR IGNORE INTO users (user_id, chat_id, xp, level)
    VALUES (?, ?, 0, 1)
    """, (user_id, chat_id))

    cur.execute("""
    UPDATE users SET xp = xp + ?
    WHERE user_id=? AND chat_id=?
    """, (xp, user_id, chat_id))

    conn.commit()


def get_user_xp(user_id, chat_id):
    cur.execute("SELECT xp FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    r = cur.fetchone()
    return r[0] if r else 0
