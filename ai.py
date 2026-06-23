import requests
from config import GROQ_API_KEY, GROQ_MODEL

def call_ai(prompt):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4
        }
    )

    return r.json()["choices"][0]["message"]["content"]
