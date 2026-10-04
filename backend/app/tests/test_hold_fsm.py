from datetime import datetime, timedelta, timezone

import pytest

from app.engines.hold_fsm import (
    confirm_allowed,
    confirm_payload,
    expire_hold_if_due,
    hold_allowed,
    hold_payload,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_hold_allowed_on_open_and_released():
    assert hold_allowed("open", NOW)["ok"] is True
    assert hold_allowed("released", NOW)["ok"] is True


def test_parallel_hold_forbidden_on_live_hold():
    future = (NOW + timedelta(minutes=5)).isoformat()
    r = hold_allowed("held", NOW, future)
    assert r["ok"] is False and r["reason"] == "held"


def test_expired_hold_may_be_reheld():
    past = (NOW - timedelta(seconds=1)).isoformat()
    assert hold_allowed("held", NOW, past)["ok"] is True


def test_hold_blocked_on_claimed_and_fulfilled():
    assert hold_allowed("claimed", NOW)["reason"] == "locked"
    assert hold_allowed("fulfilled", NOW)["reason"] == "already_fulfilled"


def test_hold_payload_is_held_not_claimed():
    p = hold_payload("alice", NOW, 300)
    assert p["status"] == "held"
    assert p["hold_claimer"] == "alice"
    assert p["hold_until"] == (NOW + timedelta(seconds=300)).isoformat()
    assert "claimer" not in p and "expires_at" not in p


@pytest.mark.parametrize("bad", [0, -1, -3600])
def test_hold_seconds_non_positive_rejected(bad):
    with pytest.raises(ValueError):
        hold_payload("alice", NOW, bad)


def test_confirm_requires_intended_claimer():
    until = (NOW + timedelta(minutes=5)).isoformat()
    r = confirm_allowed("held", "alice", until, "bob", NOW)
    assert r["ok"] is False and r["reason"] == "claimer_mismatch"


def test_confirm_fails_after_hold_expiry():
    until = (NOW - timedelta(seconds=1)).isoformat()
    r = confirm_allowed("held", "alice", until, "alice", NOW)
    assert r["ok"] is False and r["reason"] == "hold_expired"


def test_confirm_requires_held_status():
    assert confirm_allowed("open", None, None, "alice", NOW)["reason"] == "not_held"


def test_confirm_payload_writes_ttl_expiry():
    p = confirm_payload("alice", NOW, 86400)
    assert p["status"] == "claimed" and p["claimer"] == "alice"
    assert p["expires_at"] == (NOW + timedelta(seconds=86400)).isoformat()


def test_hold_expiry_returns_open_without_release_ledger():
    past = (NOW - timedelta(seconds=1)).isoformat()
    rel = expire_hold_if_due("held", past, NOW)
    assert rel == {"status": "open", "hold_claimer": None, "hold_until": None}
    assert rel["status"] != "released"


def test_live_hold_not_expired():
    future = (NOW + timedelta(minutes=5)).isoformat()
    assert expire_hold_if_due("held", future, NOW) is None
    assert expire_hold_if_due("claimed", future, NOW) is None
