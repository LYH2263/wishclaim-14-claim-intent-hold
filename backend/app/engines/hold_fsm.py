"""Hold (认领意向暂挂) state machine.

Chain: open -> held -> claimed -> fulfilled
                 held --hold expiry--> open        (no release ledger)
       claimed --ttl expiry--> open / --manual--> released

Decision (拍板): a wish allows NO parallel holds — a live hold blocks any
further hold/claim until it is confirmed or expires.
"""
from datetime import datetime, timedelta

from app.engines.claim_lock import parse_ts

HOLDABLE_STATUSES = ("open", "released")


def hold_allowed(status: str, now: datetime, hold_until: str | None = None) -> dict:
    """May a new hold be placed on this wish? Parallel holds are forbidden."""
    if status in HOLDABLE_STATUSES:
        return {"ok": True, "reason": ""}
    if status == "held":
        if hold_until and parse_ts(hold_until) <= now:
            return {"ok": True, "reason": "hold_expired_rehold"}
        return {"ok": False, "reason": "held"}
    if status == "claimed":
        return {"ok": False, "reason": "locked"}
    if status == "fulfilled":
        return {"ok": False, "reason": "already_fulfilled"}
    return {"ok": False, "reason": "bad_status"}


def hold_payload(claimer: str, now: datetime, hold_seconds: int) -> dict:
    """Build the held-state write. Never produces a direct claim."""
    if hold_seconds <= 0:
        raise ValueError("hold_seconds_must_be_positive")
    return {
        "status": "held",
        "hold_claimer": claimer,
        "hold_until": (now + timedelta(seconds=hold_seconds)).isoformat(),
    }


def confirm_allowed(status: str, hold_claimer: str | None, hold_until: str | None,
                    claimer: str, now: datetime) -> dict:
    """held -> claimed only for the intended claimer while the hold is live."""
    if status != "held":
        return {"ok": False, "reason": "not_held"}
    if hold_claimer != claimer:
        return {"ok": False, "reason": "claimer_mismatch"}
    if hold_until and parse_ts(hold_until) <= now:
        return {"ok": False, "reason": "hold_expired"}
    return {"ok": True, "reason": ""}


def confirm_payload(claimer: str, now: datetime, ttl_seconds: int) -> dict:
    """转正: held -> claimed, expires_at written per ttl_seconds."""
    return {
        "status": "claimed",
        "claimer": claimer,
        "claimed_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
    }


def expire_hold_if_due(status: str, hold_until: str | None, now: datetime) -> dict | None:
    """Expired hold falls straight back to open — no release ledger entry."""
    if status != "held" or not hold_until:
        return None
    if parse_ts(hold_until) <= now:
        return {"status": "open", "hold_claimer": None, "hold_until": None}
    return None
