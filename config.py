import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")

SUPERADMIN_ID = int(os.environ.get("SUPERADMIN_ID", "0"))

# Railway Volume path (IMPORTANT)
DB_PATH = os.getenv("DB_PATH", "/data/baffy.db")
