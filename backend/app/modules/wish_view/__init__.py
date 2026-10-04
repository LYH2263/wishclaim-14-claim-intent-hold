"""Read projections shared by wall cards, wish detail and "my claims".

All three surfaces must render the SAME hold countdown off one snapshot, so the
remaining seconds are derived here — never independently per page. The snapshot
also carries ``server_now`` so the client can keep ticking locally without
clock drift: remaining = hold_until - server_now at the instant of the read.
"""
from datetime import datetime

from app.engines.hold_machine import parse_ts


def _remain(ts: str | None, now: datetime) -> int | None:
    if not ts:
        return None
    return max(0, int((parse_ts(ts) - now).total_seconds()))


def project(row, now: datetime) -> dict:
    d = dict(row)
    d["server_now"] = now.isoformat()

    hold_alive = d.get("status") == "held" and not (
        d.get("hold_until") and parse_ts(d["hold_until"]) <= now
    )
    d["hold_active"] = hold_alive
    d["hold_remaining_seconds"] = _remain(d.get("hold_until"), now) if hold_alive else 0
    d["claim_remaining_seconds"] = (
        _remain(d.get("expires_at"), now) if d.get("status") == "claimed" else None
    )
    return d


def project_many(rows, now: datetime) -> list[dict]:
    return [project(r, now) for r in rows]
