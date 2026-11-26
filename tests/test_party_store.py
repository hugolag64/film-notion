import asyncio
import sqlite3
from datetime import datetime

from backend.core.party_store import PartyStore
from backend.core.store import MediaStore

T0 = datetime(2026, 11, 26, 19, 0)


def _party_store(tmp_path):
    store = MediaStore(str(tmp_path / "p.db"))
    store.init_schema()
    return PartyStore(store.db_path)


def run(coro):
    return asyncio.run(coro)


def test_init_schema_creates_party_tables(tmp_path):
    parties = _party_store(tmp_path)
    with sqlite3.connect(parties.db_path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"parties", "party_members", "party_proposals", "party_votes"} <= names


def test_active_party_ignores_finished_ones(tmp_path):
    parties = _party_store(tmp_path)
    run(parties.create_party("old", "coloc", "hugo", "Hugo", T0))
    run(parties.set_status("old", "done", at=T0))
    run(parties.create_party("new", "cinema", "hugo", "Hugo", T0))

    assert run(parties.active_party())["id"] == "new"
    run(parties.set_status("new", "expired", at=T0))
    assert run(parties.active_party()) is None


def test_set_status_only_moves_active_parties(tmp_path):
    parties = _party_store(tmp_path)
    run(parties.create_party("p", "coloc", "hugo", "Hugo", T0))

    assert run(parties.set_status("p", "voting", at=T0)) is True
    assert run(parties.set_status("p", "done", at=T0, winner_tmdb_id=7)) is True
    party = run(parties.get_party("p"))
    assert party["winner_tmdb_id"] == 7
    assert party["closed_at"] is not None
    assert party["launched_at"] == T0
    assert run(parties.set_status("p", "voting", at=T0)) is False


def test_add_member_twice_keeps_one_row(tmp_path):
    parties = _party_store(tmp_path)
    run(parties.create_party("p", "coloc", "hugo", "Hugo", T0))
    run(parties.add_member("p", "lea", "Léa", T0, late=False))
    run(parties.add_member("p", "lea", "Léa", T0, late=True))

    members = run(parties.list_members("p"))
    assert [(m["user_id"], m["late"], m["answers"]) for m in members] == [("lea", False, None)]


def test_answers_round_trip(tmp_path):
    parties = _party_store(tmp_path)
    run(parties.create_party("p", "coloc", "hugo", "Hugo", T0))
    run(parties.add_member("p", "hugo", "Hugo", T0, late=False))
    run(parties.set_answers("p", "hugo", {"mood": "light", "runtime": "105"}))

    assert run(parties.list_members("p"))[0]["answers"] == {"mood": "light", "runtime": "105"}


def test_vote_replaces_previous_value(tmp_path):
    parties = _party_store(tmp_path)
    run(parties.create_party("p", "coloc", "hugo", "Hugo", T0))
    run(parties.set_vote("p", "hugo", 1, 1))
    run(parties.set_vote("p", "hugo", 1, -1))

    assert run(parties.list_votes("p")) == [{"user_id": "hugo", "rank": 1, "value": -1}]


def test_proposals_round_trip_with_showtime(tmp_path):
    parties = _party_store(tmp_path)
    run(parties.create_party("p", "cinema", "hugo", "Hugo", T0))
    showtime = {"time": "20:15", "version": "VF", "booking_url": "https://x"}
    base = {"poster_url": None, "reason": "", "site_id": None, "showtime": None}
    run(parties.replace_proposals("p", [
        {**base, "rank": 2, "tmdb_id": None, "title": "B", "source": "cinema", "site_id": 9, "showtime": showtime},
        {**base, "rank": 1, "tmdb_id": 5, "title": "A", "source": "tmdb"},
    ]))

    proposals = run(parties.list_proposals("p"))
    assert [p["title"] for p in proposals] == ["A", "B"]
    assert proposals[1]["showtime"] == showtime
    assert proposals[0]["showtime"] is None
