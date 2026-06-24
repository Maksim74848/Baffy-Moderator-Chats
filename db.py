import sqlite3
from datetime import datetime

db = sqlite3.connect("saas.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    tier TEXT DEFAULT 'free',
    expire TEXT DEFAULT '',
    role TEXT DEFAULT 'assistant',
    memory TEXT DEFAULT '',
    messages INTEGER DEFAULT 0,
    ref INTEGER DEFAULT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS payments(
    invoice_id TEXT PRIMARY KEY,
    user_id INTEGER,
    tier TEXT,
    status TEXT DEFAULT 'pending'
)
""")

db.commit()


def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def create_user(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    db.commit()


def set_tier(uid, tier, days=30):
    exp = datetime.utcnow().timestamp() + days * 86400
    cur.execute("UPDATE users SET tier=?, expire=? WHERE user_id=?", (tier, exp, uid))
    db.commit()


def update_memory(uid, memory):
    cur.execute("UPDATE users SET memory=? WHERE user_id=?", (memory, uid))
    db.commit()
