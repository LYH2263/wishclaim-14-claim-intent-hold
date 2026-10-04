from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from app import seed
from app.db import connect
from app.modules import wish_lock
from app.modules.wish_view import project, project_many

app = FastAPI(title="Wishclaim", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def hold_default():
    c = connect()
    row = c.execute("SELECT value FROM settings WHERE key='hold_seconds_default'").fetchone(); c.close()
    return int(row["value"] if row else 600)

def sweep(c):
    wish_lock.sweep_all(c, now())

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c)
    rows = project_many(c.execute("SELECT * FROM wishes ORDER BY id DESC").fetchall(), now()); c.close()
    return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c)
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    if not r: raise HTTPException(404, "not found")
    return project(r, now())

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

class HoldIn(BaseModel):
    claimer: str
    seconds: Optional[int] = None

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    try:
        return wish_lock.claim(wid, body.claimer, now())
    except wish_lock.LockError as e:
        raise HTTPException(e.http_code, e.reason)

@app.post("/api/wishes/{wid}/hold")
def hold(wid: int, body: HoldIn):
    """Open -> held (intent hold). Never claimed directly."""
    seconds = hold_default() if body.seconds is None else body.seconds
    try:
        return wish_lock.create_hold(wid, body.claimer, seconds, now())
    except wish_lock.LockError as e:
        raise HTTPException(e.http_code, e.reason)

@app.post("/api/wishes/{wid}/confirm")
def confirm(wid: int, body: ClaimIn):
    """held -> claimed, writing expires_at from ttl_seconds."""
    try:
        return wish_lock.confirm_hold(wid, body.claimer, now())
    except wish_lock.LockError as e:
        raise HTTPException(e.http_code, e.reason)

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    c.execute("UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL,"
              " hold_claimer=NULL, hold_until=NULL WHERE id=?", (wid,))
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
    """My claims AND my intent holds — both pin the same hold countdown."""
    c = connect(); sweep(c)
    q = ("SELECT * FROM wishes WHERE claimer=? OR hold_claimer=? ORDER BY id DESC")
    rows = project_many(c.execute(q, (claimer, claimer)).fetchall(), now()); c.close()
    return rows

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
        "hold": "认领前先暂挂意向：open 可暂挂为 held，同一时刻仅允许一个意向暂挂，暂挂期他人无法认领",
        "hold_ttl": "意向人须在暂挂倒计时结束前确认转正；超时自动回 open，不留释放台账",
        "confirm": "仅意向暂挂本人可确认转正，转正后按 ttl_seconds 写 expires_at",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
    }
