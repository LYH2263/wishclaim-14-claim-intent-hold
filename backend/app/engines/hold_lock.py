"""Write-locked hold transitions (转正写锁) against sqlite.

Each transition runs inside BEGIN IMMEDIATE and lands via a conditional
UPDATE whose rowcount proves the precondition still held at write time —
so a confirm can never race a hold expiry or a parallel hold.
"""
from datetime import datetime

from app.engines.hold_fsm import (
    HOLDABLE_STATUSES,
    confirm_allowed,
    confirm_payload,
    hold_allowed,
    hold_payload,
)


def _begin_tx(conn):
    conn.rollback()  # drop any implicit deferred txn so BEGIN IMMEDIATE is clean
    conn.execute("BEGIN IMMEDIATE")


def place_hold(conn, wid: int, claimer: str, now: datetime, hold_seconds: int) -> dict:
    """open/released -> held. One hold per wish: the conditional UPDATE is the mutex."""
    try:
        p = hold_payload(claimer, now, hold_seconds)
    except ValueError as e:
        return {"ok": False, "code": 400, "reason": str(e)}
    _begin_tx(conn)
    try:
        r = conn.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
        if not r:
            conn.rollback()
            return {"ok": False, "code": 404, "reason": "not_found"}
        allowed = hold_allowed(r["status"], now, r["hold_until"])
        if not allowed["ok"]:
            conn.rollback()
            return {"ok": False, "code": 409, "reason": allowed["reason"]}
        marks = ",".join("?" for _ in HOLDABLE_STATUSES)
        cur = conn.execute(
            f"UPDATE wishes SET status=?, hold_claimer=?, hold_until=? "
            f"WHERE id=? AND status IN ({marks})",
            (p["status"], p["hold_claimer"], p["hold_until"], wid, *HOLDABLE_STATUSES),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return {"ok": False, "code": 409, "reason": "hold_race_lost"}
        conn.commit()
        return {"ok": True, "payload": p}
    except Exception:
        conn.rollback()
        raise


def confirm_hold(conn, wid: int, claimer: str, now: datetime, ttl_seconds: int) -> dict:
    """held -> claimed under the write lock; mismatch or expired hold fails."""
    _begin_tx(conn)
    try:
        r = conn.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
        if not r:
            conn.rollback()
            return {"ok": False, "code": 404, "reason": "not_found"}
        allowed = confirm_allowed(r["status"], r["hold_claimer"], r["hold_until"], claimer, now)
        if not allowed["ok"]:
            conn.rollback()
            return {"ok": False, "code": 409, "reason": allowed["reason"]}
        p = confirm_payload(claimer, now, ttl_seconds)
        cur = conn.execute(
            "UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=?, "
            "hold_claimer=NULL, hold_until=NULL "
            "WHERE id=? AND status='held' AND hold_claimer=? AND hold_until>?",
            (p["status"], p["claimer"], p["claimed_at"], p["expires_at"],
             wid, claimer, now.isoformat()),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return {"ok": False, "code": 409, "reason": "confirm_race_lost"}
        conn.commit()
        return {"ok": True, "payload": p}
    except Exception:
        conn.rollback()
        raise
