"""Claim mutex + TTL release for wishes."""
from datetime import datetime, timedelta, timezone
from app.engines.hold_machine import is_expired

def parse_ts(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def claim_allowed(status: str, claimer: str | None, now: datetime, expires_at: str | None,
                  hold_until: str | None = None) -> dict:
    """Only open wishes (or expired locks) can be claimed directly.

    A standing hold blocks everyone (including the intent claimer — they must
    confirm rather than claim again). An expired hold behaves like open.
    """
    if status == "fulfilled":
        return {"ok": False, "reason": "already_fulfilled"}
    if status == "held":
        if is_expired(hold_until, now):
            return {"ok": True, "reason": "hold_expired_reclaim"}
        return {"ok": False, "reason": "held"}
    if status == "claimed" and claimer:
        if expires_at and parse_ts(expires_at) <= now:
            return {"ok": True, "reason": "ttl_expired_reclaim"}
        return {"ok": False, "reason": "locked"}
    if status in ("open", "released"):
        return {"ok": True, "reason": ""}
    return {"ok": False, "reason": "bad_status"}

def lock_payload(claimer: str, now: datetime, ttl_seconds: int) -> dict:
    exp = now + timedelta(seconds=ttl_seconds)
    return {
        "status": "claimed",
        "claimer": claimer,
        "claimed_at": now.isoformat(),
        "expires_at": exp.isoformat(),
    }

def release_if_expired(status: str, expires_at: str | None, now: datetime) -> dict | None:
    if status != "claimed" or not expires_at:
        return None
    if parse_ts(expires_at) <= now:
        return {"status": "open", "claimer": None, "claimed_at": None, "expires_at": None,
                "hold_claimer": None, "hold_until": None}
    return None
