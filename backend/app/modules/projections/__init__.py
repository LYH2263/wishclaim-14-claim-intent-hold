"""Read projections — wall card / wish detail / my claims.

Every projection pins the live hold countdown (hold_remaining_seconds) so
the wall, the detail page and the intended claimer's mine page all render
the same remaining time from the same hold_until.
"""
from datetime import datetime

from app.engines.claim_lock import parse_ts


def _remain(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    return max(0, int((parse_ts(iso) - now).total_seconds()))


def _base(row, now: datetime) -> dict:
    d = dict(row)
    d["hold_remaining_seconds"] = _remain(d.get("hold_until"), now) if d.get("status") == "held" else None
    d["claim_remaining_seconds"] = _remain(d.get("expires_at"), now) if d.get("status") == "claimed" else None
    return d


def wall_card(row, now: datetime) -> dict:
    """Masonry card: title/note/status + hold countdown badge data."""
    d = _base(row, now)
    return {k: d.get(k) for k in (
        "id", "title", "note", "status", "data_quality",
        "hold_claimer", "hold_until", "hold_remaining_seconds",
    )}


def wish_detail(row, now: datetime) -> dict:
    """Detail page: full row + both countdowns."""
    return _base(row, now)


def mine_entry(row, now: datetime) -> dict:
    """Intended claimer's list: held rows pin the hold countdown, claimed rows the ttl."""
    d = _base(row, now)
    return {k: d.get(k) for k in (
        "id", "title", "note", "status", "claimer", "expires_at", "claim_remaining_seconds",
        "hold_claimer", "hold_until", "hold_remaining_seconds",
    )}
