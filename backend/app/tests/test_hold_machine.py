from datetime import datetime, timedelta, timezone

from app.engines import hold_machine as hm

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
FUTURE = (NOW + timedelta(minutes=10)).isoformat()
PAST = (NOW - timedelta(seconds=1)).isoformat()


# ---------- hold creation ----------

def test_open_can_be_held_and_lands_held_not_claimed():
    assert hm.hold_allowed("open", None, NOW)["ok"] is True
    built = hm.hold_patch("alice", NOW, 600)
    p = built["patch"]
    assert p["status"] == "held"
    assert p["hold_claimer"] == "alice"
    assert p["claimer"] is None and p["expires_at"] is None
    assert hm.parse_ts(p["hold_until"]) == NOW + timedelta(seconds=600)


def test_hold_seconds_le_zero_rejected():
    for bad in (0, -1, -600):
        built = hm.hold_patch("alice", NOW, bad)
        assert built["ok"] is False and built["reason"] == "bad_hold_seconds"


def test_hold_seconds_must_be_real_int():
    assert hm.hold_patch("alice", NOW, True)["ok"] is False  # bool is not a duration
    assert hm.hold_patch("alice", NOW, 1.5)["ok"] is False


def test_parallel_hold_forbidden_by_default():
    # Standing live hold: a second intent must be refused.
    r = hm.hold_allowed("held", FUTURE, NOW)
    assert r["ok"] is False and r["reason"] == "held"
    assert hm.ALLOW_PARALLEL_HOLDS is False


def test_expired_hold_can_be_replaced():
    r = hm.hold_allowed("held", PAST, NOW)
    assert r["ok"] is True and r["reason"] == "hold_expired_rehold"


def test_hold_blocked_on_claimed_and_fulfilled():
    assert hm.hold_allowed("claimed", None, NOW)["reason"] == "locked"
    assert hm.hold_allowed("fulfilled", None, NOW)["reason"] == "already_fulfilled"


# ---------- hold expiry ----------

def test_expired_hold_collapses_to_open_without_release():
    patch = hm.expire_hold("held", PAST, NOW)
    assert patch["status"] == "open"
    assert patch["hold_claimer"] is None and patch["hold_until"] is None
    # No release-ledger marker — plain open, exactly as if never held.
    assert "released" not in patch.values()


def test_live_hold_does_not_collapse():
    assert hm.expire_hold("held", FUTURE, NOW) is None
    assert hm.expire_hold("claimed", None, NOW) is None


# ---------- confirmation ----------

def test_confirm_succeeds_for_intent_claimer_before_ttl():
    r = hm.confirm_allowed("held", "alice", FUTURE, "alice", NOW)
    assert r["ok"] is True
    patch = hm.confirm_patch(NOW, 86400)
    assert patch["status"] == "claimed"
    assert patch["hold_claimer"] is None and patch["hold_until"] is None
    assert hm.parse_ts(patch["expires_at"]) == NOW + timedelta(seconds=86400)


def test_confirm_rejects_other_claimer():
    r = hm.confirm_allowed("held", "alice", FUTURE, "bob", NOW)
    assert r["ok"] is False and r["reason"] == "claimer_mismatch"


def test_confirm_rejects_after_hold_expiry():
    r = hm.confirm_allowed("held", "alice", PAST, "alice", NOW)
    assert r["ok"] is False and r["reason"] == "hold_expired"


def test_confirm_only_from_held():
    assert hm.confirm_allowed("open", None, None, "alice", NOW)["reason"] == "not_held"
    assert hm.confirm_allowed("claimed", None, None, "alice", NOW)["reason"] == "not_held"
