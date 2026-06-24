import os
import aiohttp
from fastapi import FastAPI, Request
from db import set_tier, cur, db

app = FastAPI()

CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")


# ========== CREATE INVOICE ==========
@app.get("/create_invoice")
async def create_invoice(user_id: int, tier: str):
    price = {"pro": 1, "ultra": 3}[tier]

    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://pay.crypt.bot/api/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={
                "asset": "USDT",
                "amount": price,
                "description": f"SaaS {tier}"
            }
        ) as r:
            data = await r.json()

    inv = data["result"]

    cur.execute(
        "INSERT OR REPLACE INTO payments VALUES (?,?,?,?)",
        (inv["invoice_id"], user_id, tier, "pending")
    )
    db.commit()

    return {"pay_url": inv["pay_url"]}


# ========== WEBHOOK ==========
@app.post("/crypto_webhook")
async def crypto_webhook(req: Request):
    data = await req.json()

    if data["status"] != "paid":
        return {"ok": False}

    invoice_id = data["invoice_id"]

    cur.execute("SELECT user_id, tier FROM payments WHERE invoice_id=?", (invoice_id,))
    row = cur.fetchone()

    if not row:
        return {"ok": False}

    uid, tier = row

    set_tier(uid, tier)

    cur.execute("UPDATE payments SET status='paid' WHERE invoice_id=?", (invoice_id,))
    db.commit()

    return {"ok": True}


# ========== ADMIN ==========
@app.get("/admin/stats")
def stats():
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM payments WHERE status='paid'")
    paid = cur.fetchone()[0]

    return {
        "users": users,
        "paid": paid
  }
