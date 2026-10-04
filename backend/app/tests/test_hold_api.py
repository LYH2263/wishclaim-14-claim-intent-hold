import pytest
from fastapi.testclient import TestClient

from app import seed
from app.db import connect
from app.main import app


@pytest.fixture()
def client():
    seed.init_db()
    with TestClient(app) as c:
        yield c


def _create(client, title="礼物"):
    return client.post("/api/wishes", json={"title": title}).json()["id"]


def _force_held(wid, claimer="alice", hold_until="2020-01-01T00:00:00+00:00"):
    c = connect()
    c.execute("UPDATE wishes SET status='held', hold_claimer=?, hold_until=? WHERE id=?",
              (claimer, hold_until, wid))
    c.commit(); c.close()


# ---------- hold ----------

def test_api_hold_lands_held_with_countdown(client):
    wid = _create(client)
    r = client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    assert r.status_code == 200 and r.json()["status"] == "held"

    g = client.get(f"/api/wishes/{wid}").json()
    assert g["status"] == "held" and g["hold_claimer"] == "alice" and g["claimer"] is None
    assert g["hold_active"] is True
    assert 295 <= g["hold_remaining_seconds"] <= 300
    assert g["server_now"]


def test_api_hold_seconds_le_zero_rejected(client):
    wid = _create(client)
    r = client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 0})
    assert r.status_code == 400 and r.json()["detail"] == "bad_hold_seconds"
    r = client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": -10})
    assert r.status_code == 400
    assert client.get(f"/api/wishes/{wid}").json()["status"] == "open"


def test_api_parallel_hold_blocked(client):
    wid = _create(client)
    client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    r = client.post(f"/api/wishes/{wid}/hold", json={"claimer": "bob", "seconds": 300})
    assert r.status_code == 409 and r.json()["detail"] == "held"
    assert client.get(f"/api/wishes/{wid}").json()["hold_claimer"] == "alice"


# ---------- claim blocked during hold ----------

def test_api_claim_blocked_while_held(client):
    wid = _create(client)
    client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    for who in ("bob", "alice"):
        r = client.post(f"/api/wishes/{wid}/claim", json={"claimer": who})
        assert r.status_code == 409 and r.json()["detail"] == "held"
    assert client.get(f"/api/wishes/{wid}").json()["status"] == "held"


# ---------- confirm ----------

def test_api_confirm_promotes_with_ttl_expiry(client):
    wid = _create(client)
    client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    r = client.post(f"/api/wishes/{wid}/confirm", json={"claimer": "alice"})
    assert r.status_code == 200 and r.json()["status"] == "claimed"

    g = client.get(f"/api/wishes/{wid}").json()
    assert g["status"] == "claimed" and g["claimer"] == "alice"
    assert g["hold_claimer"] is None and g["hold_until"] is None and g["hold_active"] is False
    ttl = int(client.get("/api/settings").json()["ttl_seconds"])
    assert g["expires_at"]
    from app.engines.hold_machine import parse_ts
    # expires_at and claimed_at are written together at confirm: exact ttl span.
    assert (parse_ts(g["expires_at"]) - parse_ts(g["claimed_at"])).total_seconds() == ttl


def test_api_confirm_rejects_other_claimer(client):
    wid = _create(client)
    client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    r = client.post(f"/api/wishes/{wid}/confirm", json={"claimer": "bob"})
    assert r.status_code == 409 and r.json()["detail"] == "claimer_mismatch"
    assert client.get(f"/api/wishes/{wid}").json()["status"] == "held"


def test_api_confirm_after_expiry_reopens(client):
    wid = _create(client)
    _force_held(wid, "alice")
    r = client.post(f"/api/wishes/{wid}/confirm", json={"claimer": "alice"})
    assert r.status_code == 409 and r.json()["detail"] == "hold_expired"
    g = client.get(f"/api/wishes/{wid}").json()
    assert g["status"] == "open" and g["hold_claimer"] is None and g["hold_active"] is False


# ---------- projections across the three surfaces ----------

def test_api_mine_includes_intent_hold(client):
    wid = _create(client)
    client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    rows = client.get("/api/mine", params={"claimer": "alice"}).json()
    mine = [w for w in rows if w["id"] == wid]
    assert mine and mine[0]["hold_active"] is True
    assert client.get("/api/mine", params={"claimer": "bob"}).json() == []


def test_api_wall_pins_hold_countdown(client):
    wid = _create(client)
    client.post(f"/api/wishes/{wid}/hold", json={"claimer": "alice", "seconds": 300})
    card = next(w for w in client.get("/api/wishes").json() if w["id"] == wid)
    assert card["hold_active"] is True and 0 < card["hold_remaining_seconds"] <= 300
