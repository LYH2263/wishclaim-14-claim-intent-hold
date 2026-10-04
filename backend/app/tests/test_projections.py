from datetime import datetime, timedelta, timezone

from app.modules import projections

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

HELD = {
    "id": 1, "title": "键盘", "note": "红轴", "status": "held", "data_quality": "clean",
    "claimer": None, "claimed_at": None, "expires_at": None,
    "hold_claimer": "alice", "hold_until": (NOW + timedelta(seconds=90)).isoformat(),
}
CLAIMED = {
    "id": 2, "title": "围巾", "note": "羊毛", "status": "claimed", "data_quality": "clean",
    "claimer": "alice", "claimed_at": NOW.isoformat(),
    "expires_at": (NOW + timedelta(hours=1)).isoformat(),
    "hold_claimer": None, "hold_until": None,
}


def test_wall_card_pins_hold_countdown():
    d = projections.wall_card(HELD, NOW)
    assert d["status"] == "held"
    assert d["hold_claimer"] == "alice"
    assert d["hold_remaining_seconds"] == 90


def test_wish_detail_pins_hold_countdown():
    d = projections.wish_detail(HELD, NOW)
    assert d["hold_remaining_seconds"] == 90
    assert d["claim_remaining_seconds"] is None


def test_mine_entry_pins_hold_countdown():
    d = projections.mine_entry(HELD, NOW)
    assert d["hold_remaining_seconds"] == 90


def test_mine_entry_pins_claim_ttl_for_claimed():
    d = projections.mine_entry(CLAIMED, NOW)
    assert d["claim_remaining_seconds"] == 3600
    assert d["hold_remaining_seconds"] is None


def test_countdown_never_negative():
    late = NOW + timedelta(minutes=5)
    assert projections.wall_card(HELD, late)["hold_remaining_seconds"] == 0


def test_all_three_projections_agree():
    a = projections.wall_card(HELD, NOW)["hold_remaining_seconds"]
    b = projections.wish_detail(HELD, NOW)["hold_remaining_seconds"]
    c = projections.mine_entry(HELD, NOW)["hold_remaining_seconds"]
    assert a == b == c
