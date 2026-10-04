"""Hold-intent state machine (pure functions, no IO).

Transitions:
    open --hold(seconds>0)--> held --confirm(intent claimer)--> claimed --fulfill--> fulfilled
                                |                                  └--release--> released
                                └--hold_until passes--> open   (auto, no release ledger)

Rules enforced here:
  * hold can only be created on an ``open`` wish; it lands ``held``, never ``claimed``;
  * parallel holds on one wish are FORBIDDEN (see ALLOW_PARALLEL_HOLDS); a second
    intent while an unexpired hold stands is rejected with ``held``;
  * hold seconds <= 0 are rejected (``bad_hold_seconds``);
  * while held, anyone else's direct claim is rejected (``held``);
  * confirm only succeeds for the original intent claimer, before hold_until;
    mismatch -> ``claimer_mismatch``, expired -> ``hold_expired``;
  * an expired hold collapses back to ``open`` without a release ledger entry.
"""
from datetime import datetime, timedelta, timezone

# 拍板：同一愿望同一时刻只允许一个 hold，默认禁止并行多个 hold。
ALLOW_PARALLEL_HOLDS = False


def parse_ts(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_expired(ts: str | None, now: datetime) -> bool:
    return bool(ts) and parse_ts(ts) <= now


def hold_allowed(status: str, hold_until: str | None, now: datetime) -> dict:
    """Whether a new hold may be placed. Only open wishes may be held."""
    if status == "fulfilled":
        return {"ok": False, "reason": "already_fulfilled"}
    if status == "claimed":
        return {"ok": False, "reason": "locked"}
    if status == "held":
        if is_expired(hold_until, now):
            # Sweep should have collapsed it, but be defensive under concurrency.
            return {"ok": True, "reason": "hold_expired_rehold"}
        if ALLOW_PARALLEL_HOLDS:
            return {"ok": True, "reason": "parallel_hold"}
        return {"ok": False, "reason": "held"}
    if status == "open":
        return {"ok": True, "reason": ""}
    return {"ok": False, "reason": "bad_status"}


def hold_patch(claimer: str, now: datetime, seconds: int) -> dict:
    """Build the column patch for open -> held. seconds must be a positive int."""
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
        return {"ok": False, "reason": "bad_hold_seconds"}
    until = now + timedelta(seconds=seconds)
    return {
        "ok": True,
        "patch": {
            "status": "held",
            "hold_claimer": claimer,
            "hold_until": until.isoformat(),
            "claimer": None,
            "claimed_at": None,
            "expires_at": None,
        },
    }


def expire_hold(status: str, hold_until: str | None, now: datetime) -> dict | None:
    """Reset patch when a held wish has aged out; back to open, no release ledger."""
    if status != "held":
        return None
    if not is_expired(hold_until, now):
        return None
    return {
        "status": "open",
        "hold_claimer": None,
        "hold_until": None,
        "claimer": None,
        "claimed_at": None,
        "expires_at": None,
    }


def confirm_allowed(status: str, hold_claimer: str | None, hold_until: str | None,
                    claimer: str, now: datetime) -> dict:
    """held -> claimed only when invoked by the intent claimer before the TTL."""
    if status != "held":
        return {"ok": False, "reason": "not_held"}
    if is_expired(hold_until, now):
        return {"ok": False, "reason": "hold_expired"}
    if claimer != hold_claimer:
        return {"ok": False, "reason": "claimer_mismatch"}
    return {"ok": True, "reason": ""}


def confirm_patch(now: datetime, ttl_seconds: int) -> dict:
    """Column patch for held -> claimed; clears hold columns and writes claim TTL."""
    exp = now + timedelta(seconds=ttl_seconds)
    return {
        "status": "claimed",
        "claimed_at": now.isoformat(),
        "expires_at": exp.isoformat(),
        "hold_claimer": None,
        "hold_until": None,
    }
