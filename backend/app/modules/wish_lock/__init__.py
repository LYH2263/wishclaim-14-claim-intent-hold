"""Write path for wishes: claim holds and held->claimed confirmation.

Every state-changing operation runs inside ``BEGIN IMMEDIATE`` so SQLite takes
the reserved write lock up front: two intents racing for the same wish are
serialized at the database, and the loser re-reads the winner's ``held`` row
and is rejected by the state machine instead of double-writing.
"""
from datetime import datetime, timezone

from app.db import connect
from app.engines import hold_machine as hm
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired

# Wait this long for a competing IMMEDIATE transaction instead of failing BUSY.
BUSY_TIMEOUT_MS = 5000


class LockError(Exception):
    def __init__(self, reason: str, http_code: int = 409):
        super().__init__(reason)
        self.reason = reason
        self.http_code = http_code


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ttl_seconds(c) -> int:
    row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone()
    return int(row["value"] if row else 86400)


def _apply(c, wid: int, patch: dict):
    keys = ("status", "claimer", "claimed_at", "expires_at", "hold_claimer", "hold_until")
    sets = ", ".join(f"{k}=?" for k in keys)
    c.execute(f"UPDATE wishes SET {sets} WHERE id=?",
              tuple(patch.get(k) for k in keys) + (wid,))


def sweep_all(c, now: datetime | None = None) -> int:
    """Reset expired claimed TTLs and expired holds back to open.

    Expired holds return straight to ``open``; no ``released`` row/ledger is
    written. Returns the number of wishes swept.
    """
    now = now or utcnow()
    n = 0
    for r in c.execute("SELECT * FROM wishes WHERE status IN ('claimed','held')").fetchall():
        patch = release_if_expired(r["status"], r["expires_at"], now)
        if patch is None:
            patch = hm.expire_hold(r["status"], r["hold_until"], now)
        if patch is not None:
            _apply(c, r["id"], patch)
            n += 1
    c.commit()
    return n


def create_hold(wid: int, claimer: str, seconds: int, now: datetime | None = None) -> dict:
    """open -> held. Never lands claimed. Parallel holds are forbidden."""
    now = now or utcnow()
    built = hm.hold_patch(claimer, now, seconds)
    if not built["ok"]:
        raise LockError(built["reason"], 400)
    patch = built["patch"]
    c = connect()
    try:
        c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
        if row is None:
            c.rollback(); raise LockError("not_found", 404)
        row = _collapse_in_tx(c, row, now)
        allowed = hm.hold_allowed(row["status"], row["hold_until"], now)
        if not allowed["ok"]:
            c.rollback(); raise LockError(allowed["reason"], 409)
        _apply(c, wid, patch)
        c.commit()
        return {"id": wid, **patch}
    finally:
        c.close()


def confirm_hold(wid: int, claimer: str, now: datetime | None = None) -> dict:
    """held -> claimed for the intent claimer, if the hold has not aged out."""
    now = now or utcnow()
    c = connect()
    try:
        c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
        if row is None:
            c.rollback(); raise LockError("not_found", 404)
        expired_hold = hm.expire_hold(row["status"], row["hold_until"], now)
        if expired_hold is not None:
            _apply(c, wid, expired_hold)
            c.commit()
            raise LockError("hold_expired", 409)
        allowed = hm.confirm_allowed(row["status"], row["hold_claimer"],
                                     row["hold_until"], claimer, now)
        if not allowed["ok"]:
            c.rollback(); raise LockError(allowed["reason"], 409)
        patch = hm.confirm_patch(now, _ttl_seconds(c))
        # claimer is carried over from hold_claimer; pin it explicitly.
        patch["claimer"] = row["hold_claimer"]
        _apply(c, wid, patch)
        c.commit()
        return {"id": wid, **patch}
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Direct claim (legacy path): open/expired -> claimed. Held wishes are blocked.
# ---------------------------------------------------------------------------

def claim(wid: int, claimer: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    c = connect()
    try:
        c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
        if row is None:
            c.rollback(); raise LockError("not_found", 404)
        row = _collapse_in_tx(c, row, now)
        allowed = claim_allowed(row["status"], row["claimer"], now,
                                row["expires_at"], row["hold_until"])
        if not allowed["ok"]:
            c.rollback(); raise LockError(allowed["reason"], 409)
        payload = lock_payload(claimer, now, _ttl_seconds(c))
        patch = {"status": payload["status"], "claimer": payload["claimer"],
                 "claimed_at": payload["claimed_at"], "expires_at": payload["expires_at"],
                 "hold_claimer": None, "hold_until": None}
        _apply(c, wid, patch)
        c.commit()
        return {"id": wid, **patch}
    finally:
        c.close()


def _collapse_in_tx(c, row, now: datetime):
    """Like _collapse but inside an already-open IMMEDIATE transaction."""
    patch = release_if_expired(row["status"], row["expires_at"], now)
    if patch is None:
        patch = hm.expire_hold(row["status"], row["hold_until"], now)
    if patch is not None:
        _apply(c, row["id"], patch)
        return c.execute("SELECT * FROM wishes WHERE id=?", (row["id"],)).fetchone()
    return row
