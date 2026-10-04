import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import seed
from app.db import connect
from app.modules import wish_lock

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def open_wish():
    seed.init_db()
    c = connect()
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
                    ("并发样例", "", "open", "clean"))
    c.commit(); wid = cur.lastrowid; c.close()
    return wid


def _row(wid):
    c = connect(); r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    return dict(r)


def test_create_hold_open_to_held_never_claimed(open_wish):
    out = wish_lock.create_hold(open_wish, "alice", 600, NOW)
    r = _row(open_wish)
    assert out["status"] == r["status"] == "held"
    assert r["hold_claimer"] == "alice" and r["claimer"] is None
    assert r["hold_until"] == (NOW + timedelta(seconds=600)).isoformat()


def test_parallel_holds_race_only_one_wins(open_wish):
    results = {}
    barrier = threading.Barrier(2)

    def worker(name):
        barrier.wait()
        try:
            wish_lock.create_hold(open_wish, name, 600, NOW)
            results[name] = "ok"
        except wish_lock.LockError as e:
            results[name] = e.reason

    t1 = threading.Thread(target=worker, args=("alice",))
    t2 = threading.Thread(target=worker, args=("bob",))
    t1.start(); t2.start(); t1.join(); t2.join()

    r = _row(open_wish)
    assert sorted(results.values()) == ["held", "ok"]          # exactly one winner
    assert r["status"] == "held"
    assert r["hold_claimer"] in ("alice", "bob")               # single intent, never both


def test_direct_claim_fails_while_held(open_wish):
    wish_lock.create_hold(open_wish, "alice", 600, NOW)
    with pytest.raises(wish_lock.LockError) as ei:
        wish_lock.claim(open_wish, "bob", NOW)
    assert ei.value.reason == "held"
    # Even the intent claimer cannot double-via claim; they must confirm.
    with pytest.raises(wish_lock.LockError) as ei:
        wish_lock.claim(open_wish, "alice", NOW)
    assert ei.value.reason == "held"


def test_confirm_promotes_and_writes_expires_at(open_wish):
    wish_lock.create_hold(open_wish, "alice", 600, NOW)
    out = wish_lock.confirm_hold(open_wish, "alice", NOW)
    r = _row(open_wish)
    assert out["status"] == r["status"] == "claimed"
    assert r["claimer"] == "alice" and r["hold_claimer"] is None and r["hold_until"] is None
    assert r["claimed_at"] == NOW.isoformat()
    ttl = int(_setting("ttl_seconds"))
    assert r["expires_at"] == (NOW + timedelta(seconds=ttl)).isoformat()


def test_confirm_rejects_other_intent(open_wish):
    wish_lock.create_hold(open_wish, "alice", 600, NOW)
    with pytest.raises(wish_lock.LockError) as ei:
        wish_lock.confirm_hold(open_wish, "bob", NOW)
    assert ei.value.reason == "claimer_mismatch"
    assert _row(open_wish)["status"] == "held"                  # nothing changed


def test_confirm_after_expiry_fails_and_reopens(open_wish):
    wish_lock.create_hold(open_wish, "alice", 600, NOW)
    later = NOW + timedelta(seconds=601)
    with pytest.raises(wish_lock.LockError) as ei:
        wish_lock.confirm_hold(open_wish, "alice", later)
    assert ei.value.reason == "hold_expired"
    r = _row(open_wish)
    assert r["status"] == "open" and r["hold_claimer"] is None and r["hold_until"] is None


def test_hold_seconds_le_zero_rejected_at_write(open_wish):
    for bad in (0, -5):
        with pytest.raises(wish_lock.LockError) as ei:
            wish_lock.create_hold(open_wish, "alice", bad, NOW)
        assert ei.value.reason == "bad_hold_seconds"
    assert _row(open_wish)["status"] == "open"


def test_sweep_expired_hold_reopens_without_release_ledger(open_wish):
    wish_lock.create_hold(open_wish, "alice", 600, NOW)
    later = NOW + timedelta(seconds=601)
    c = connect()
    n = wish_lock.sweep_all(c, later); c.close()
    assert n >= 1                                            # also sweeps the seed's stale lock
    r = _row(open_wish)
    assert r["status"] == "open"                               # straight back to open
    assert r["claimer"] is None and r["hold_claimer"] is None
    # No released row is created anywhere.
    c = connect()
    released = c.execute("SELECT COUNT(*) c FROM wishes WHERE status='released'").fetchone()["c"]
    c.close()
    assert released == 0


def _setting(key: str) -> str:
    c = connect(); v = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()["value"]; c.close()
    return v
