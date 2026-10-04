"""Write-lock tests against a real (in-memory) sqlite — the 拍板 decision
'no parallel holds' is verified at the DB transition layer, not just the fsm."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.engines.hold_lock import confirm_hold, place_hold

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
TTL = 86400


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE wishes(id INTEGER PRIMARY KEY, title TEXT, note TEXT, status TEXT,"
        " claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT,"
        " hold_claimer TEXT, hold_until TEXT)"
    )
    c.execute("INSERT INTO wishes(id,title,status,data_quality) VALUES (1,'键盘','open','clean')")
    c.commit()
    yield c
    c.close()


def row(c, wid=1):
    return c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()


def test_place_hold_writes_held(db):
    res = place_hold(db, 1, "alice", NOW, 300)
    assert res["ok"] is True
    r = row(db)
    assert r["status"] == "held" and r["hold_claimer"] == "alice"
    assert r["hold_until"] == (NOW + timedelta(seconds=300)).isoformat()
    assert r["claimer"] is None and r["expires_at"] is None  # 不得直接 claimed


def test_place_hold_rejects_non_positive_seconds(db):
    assert place_hold(db, 1, "alice", NOW, 0)["ok"] is False
    assert place_hold(db, 1, "alice", NOW, -5)["code"] == 400
    assert row(db)["status"] == "open"


def test_parallel_hold_forbidden(db):
    assert place_hold(db, 1, "alice", NOW, 300)["ok"] is True
    second = place_hold(db, 1, "bob", NOW, 300)
    assert second["ok"] is False and second["code"] == 409
    assert second["reason"] == "held"
    assert row(db)["hold_claimer"] == "alice"  # first hold untouched


def test_confirm_promotes_and_writes_expiry(db):
    place_hold(db, 1, "alice", NOW, 300)
    res = confirm_hold(db, 1, "alice", NOW + timedelta(seconds=10), TTL)
    assert res["ok"] is True
    r = row(db)
    assert r["status"] == "claimed" and r["claimer"] == "alice"
    assert r["expires_at"] == (NOW + timedelta(seconds=10) + timedelta(seconds=TTL)).isoformat()
    assert r["hold_claimer"] is None and r["hold_until"] is None


def test_confirm_rejects_wrong_claimer(db):
    place_hold(db, 1, "alice", NOW, 300)
    res = confirm_hold(db, 1, "bob", NOW + timedelta(seconds=10), TTL)
    assert res["ok"] is False and res["reason"] == "claimer_mismatch"
    assert row(db)["status"] == "held"


def test_confirm_rejects_expired_hold(db):
    place_hold(db, 1, "alice", NOW, 60)
    late = NOW + timedelta(seconds=61)
    res = confirm_hold(db, 1, "alice", late, TTL)
    assert res["ok"] is False and res["reason"] == "hold_expired"
    assert row(db)["status"] == "held"  # sweep (not confirm) returns it to open


def test_confirm_without_hold_fails(db):
    res = confirm_hold(db, 1, "alice", NOW, TTL)
    assert res["ok"] is False and res["reason"] == "not_held"


def test_missing_wish_404(db):
    assert place_hold(db, 99, "alice", NOW, 300)["code"] == 404
    assert confirm_hold(db, 99, "alice", NOW, TTL)["code"] == 404
