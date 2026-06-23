import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS economy (
    user_id INTEGER,
    chat_id INTEGER,
    coins INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, chat_id)
)
""")

conn.commit()


def add_coins(user_id, chat_id, coins):
    cur.execute("""
    INSERT OR IGNORE INTO economy VALUES (?, ?, 0)
    """, (user_id, chat_id))

    cur.execute("""
    UPDATE economy SET coins = coins + ?
    WHERE user_id=? AND chat_id=?
    """, (coins, user_id, chat_id))

    conn.commit()


def get_coins(user_id, chat_id):
    cur.execute("SELECT coins FROM economy WHERE user_id=? AND chat_id=?",
                (user_id, chat_id))
    r = cur.fetchone()
    return r[0] if r else 0
