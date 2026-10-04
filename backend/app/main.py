from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import release_if_expired
from app.engines.hold_fsm import expire_hold_if_due
from app.engines.hold_lock import confirm_hold, place_hold
from app.modules import projections

app = FastAPI(title="Wishclaim", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def _setting(c, key, default):
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return int(row["value"] if row else default)

def ttl():
    c = connect(); v = _setting(c, "ttl_seconds", 86400); c.close(); return v

def hold_ttl():
    c = connect(); v = _setting(c, "hold_seconds", seed.DEFAULT_HOLD_SECONDS); c.close(); return v

def sweep(c):
    """Lazy expiry: claimed ttl -> open; held hold_until -> open (no release ledger)."""
    ts = now()
    for r in c.execute("SELECT * FROM wishes WHERE status IN ('claimed','held')"):
        if r["status"] == "claimed":
            rel = release_if_expired(r["status"], r["expires_at"], ts)
            if rel:
                c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                          (rel["status"], None, None, None, r["id"]))
        else:
            rel = expire_hold_if_due(r["status"], r["hold_until"], ts)
            if rel:
                c.execute("UPDATE wishes SET status=?, hold_claimer=?, hold_until=? WHERE id=?",
                          (rel["status"], None, None, r["id"]))

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    rows = [projections.wall_card(r, now()) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]
    c.close(); return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    if not r: raise HTTPException(404, "not found")
    return projections.wish_detail(r, now())

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
                    (body.title, body.note, "open", "clean"))
    c.commit(); wid = cur.lastrowid; c.close(); return {"id": wid}

class ClaimIn(BaseModel):
    claimer: str
    hold_seconds: int | None = None

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    """认领意向暂挂: open -> held. Never claims directly."""
    c = connect(); sweep(c); c.commit()
    seconds = body.hold_seconds if body.hold_seconds is not None else hold_ttl()
    res = place_hold(c, wid, body.claimer, now(), seconds)
    c.close()
    if not res["ok"]:
        raise HTTPException(res["code"], res["reason"])
    return res["payload"]

class ConfirmIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/confirm")
def confirm(wid: int, body: ConfirmIn):
    """确认转正: held -> claimed, expires_at = now + ttl_seconds."""
    c = connect()
    res = confirm_hold(c, wid, body.claimer, now(), ttl())
    c.close()
    if not res["ok"]:
        raise HTTPException(res["code"], res["reason"])
    return res["payload"]

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    c.execute("UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "released"}

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "fulfilled"}

@app.get("/api/mine")
def mine(claimer: str):
    """我的认领: claimed by me + holds where I am the intended claimer."""
    c = connect(); sweep(c); c.commit()
    rows = [projections.mine_entry(r, now()) for r in c.execute(
        "SELECT * FROM wishes WHERE claimer=? OR hold_claimer=? ORDER BY id DESC", (claimer, claimer))]
    c.close(); return rows

@app.get("/api/done")
def done():
    c = connect()
    rows = [dict(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'")]; c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "hold": "认领先暂挂(held)：写 hold_until 与意向认领人，不直接成交",
        "hold_mutex": "同一愿望禁止并行多个暂挂",
        "confirm": "暂挂期内意向人确认转正为 claimed，并按 ttl_seconds 写 expires_at",
        "hold_expiry": "暂挂过期自动回 open，不写释放台账",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
    }
