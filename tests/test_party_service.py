import asyncio
import json
from datetime import datetime, timedelta

import pytest

from backend.core.cinema_site import Showtime
from backend.core.cinema_store import CinemaStore
from backend.core.gemini_recommendations import GeminiGroupPick
from backend.core.models import DiaryEntry
from backend.core.party_service import BOT_ID, PartyError, PartyService
from backend.core.store import MediaStore

T0 = datetime(2026, 11, 26, 19, 0)
HUGO = {"id": "hugo", "display_name": "Hugo"}
LEA = {"id": "lea", "display_name": "Léa"}
TOM = {"id": "tom", "display_name": "Tom"}
COLOC_ANSWERS = {"mood": "light", "runtime": "any", "era": "any"}


def run(coro):
    return asyncio.run(coro)


class FakeTMDB:
    def __init__(self, discovered=None, details=None):
        self.discovered = discovered if discovered is not None else [
            {"tmdb_id": i, "title": f"Film {i}", "genre_ids": [35]} for i in range(1, 6)
        ]
        self.details = details or {}

    async def discover_movies(self, **kwargs):
        return list(self.discovered)

    async def get_movie_details(self, tmdb_id):
        return self.details.get(tmdb_id)


class FakeGateway:
    enabled = True

    def __init__(self, picks=None, error=None):
        self.picks = picks
        self.error = error

    def select_group(self, profile, combined, candidates):
        if self.error:
            raise self.error
        return GeminiGroupPick(picks=self.picks or [])


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _service(tmp_path, tmdb=None, gateway=None, clock=None):
    store = MediaStore(str(tmp_path / "s.db"))
    store.init_schema()
    service = PartyService(
        store,
        tmdb_factory=lambda: tmdb or FakeTMDB(),
        gateway_factory=lambda: gateway or FakeGateway(),
        clock=clock or Clock(T0),
    )
    return store, service


def _status(error_info):
    return error_info.value.status


def _ready_party(service, *users):
    state = run(service.start(HUGO, "coloc"))
    for user in users:
        run(service.join(state["id"], user))
    for user in (HUGO, *users):
        run(service.answer(state["id"], user, COLOC_ANSWERS))
    return state["id"]


def test_start_posts_bot_card_and_joins_starter(tmp_path):
    store, service = _service(tmp_path)

    state = run(service.start(HUGO, "coloc"))

    message = run(store.list_chat_messages(None))[-1]
    assert message["author"]["id"] == BOT_ID
    assert message["payload"] == {"type": "party", "party_id": state["id"]}
    assert "Hugo" in message["body"]
    assert state["members"] == [{"name": "Hugo", "answered": False, "late": False}]
    assert state["status"] == "joining"
    assert state["me"]["member"] is True
    assert state["me"]["starter"] is True
    assert run(service.state(state["id"], "lea"))["me"]["starter"] is False


def test_second_party_refused_while_one_is_active(tmp_path):
    _, service = _service(tmp_path)
    run(service.start(HUGO, "coloc"))

    with pytest.raises(PartyError) as error:
        run(service.start(LEA, "cinema"))
    assert _status(error) == 409


def test_expired_party_does_not_block_a_new_one(tmp_path):
    clock = Clock(T0)
    _, service = _service(tmp_path, clock=clock)
    first = run(service.start(HUGO, "coloc"))

    clock.now = T0 + timedelta(hours=3)
    second = run(service.start(LEA, "coloc"))

    assert second["id"] != first["id"]
    assert run(service.state(first["id"], "hugo"))["status"] == "expired"


def test_only_starter_can_launch_and_close(tmp_path):
    _, service = _service(tmp_path)
    party_id = _ready_party(service, LEA)

    with pytest.raises(PartyError) as error:
        run(service.launch(party_id, LEA))
    assert _status(error) == 403
    run(service.launch(party_id, HUGO))
    with pytest.raises(PartyError) as error:
        run(service.close(party_id, LEA))
    assert _status(error) == 403


def test_launch_twice_is_refused(tmp_path):
    _, service = _service(tmp_path)
    party_id = _ready_party(service)
    run(service.launch(party_id, HUGO))

    with pytest.raises(PartyError) as error:
        run(service.launch(party_id, HUGO))
    assert _status(error) == 409


def test_non_member_cannot_vote_or_answer(tmp_path):
    _, service = _service(tmp_path)
    party_id = _ready_party(service)

    with pytest.raises(PartyError) as error:
        run(service.answer(party_id, TOM, COLOC_ANSWERS))
    assert _status(error) == 403
    run(service.launch(party_id, HUGO))
    with pytest.raises(PartyError) as error:
        run(service.vote(party_id, TOM, 1, 1))
    assert _status(error) == 403


def test_invalid_answers_are_rejected(tmp_path):
    _, service = _service(tmp_path)
    state = run(service.start(HUGO, "coloc"))

    with pytest.raises(PartyError) as error:
        run(service.answer(state["id"], HUGO, {"mood": "sad"}))
    assert _status(error) == 422


def test_late_member_can_vote_and_is_flagged_late(tmp_path):
    _, service = _service(tmp_path)
    party_id = _ready_party(service)
    run(service.launch(party_id, HUGO))

    state = run(service.join(party_id, TOM))
    run(service.vote(party_id, TOM, 1, 1))

    assert {"name": "Tom", "answered": False, "late": True} in state["members"]
    assert run(service.state(party_id, "tom"))["me"]["votes"] == {1: 1}


def test_all_votes_close_the_party_with_majority_winner(tmp_path):
    store, service = _service(tmp_path)
    party_id = _ready_party(service, LEA, TOM)
    launched = run(service.launch(party_id, HUGO))
    assert [p["rank"] for p in launched["proposals"]] == [1, 2, 3]

    for user, liked in ((HUGO, 2), (LEA, 2), (TOM, 1)):
        for rank in (1, 2, 3):
            run(service.vote(party_id, user, rank, 1 if rank == liked else -1))

    state = run(service.state(party_id, "hugo"))
    assert state["status"] == "done"
    assert state["winner_rank"] == 2
    last = run(store.list_chat_messages(None))[-1]
    assert last["body"].startswith("🏆 Ce soir : ")
    assert launched["proposals"][1]["title"] in last["body"]


def test_vote_can_be_changed_until_closed(tmp_path):
    _, service = _service(tmp_path)
    party_id = _ready_party(service, LEA)
    run(service.launch(party_id, HUGO))
    run(service.vote(party_id, HUGO, 1, 1))
    run(service.vote(party_id, HUGO, 1, -1))

    state = run(service.state(party_id, "hugo"))
    assert state["me"]["votes"] == {1: -1}
    assert state["scores"][1] == {"up": 0, "down": 1}


def test_coloc_excludes_films_seen_by_any_member(tmp_path):
    store, service = _service(tmp_path)
    run(store.create_diary_entry(DiaryEntry(id="d1", backstage_user_id="lea", tmdb_id=5, created_at=T0, updated_at=T0)))
    party_id = _ready_party(service, LEA)

    state = run(service.launch(party_id, HUGO))

    assert 5 not in [p["tmdb_id"] for p in state["proposals"]]
    assert len(state["proposals"]) == 3


def test_cinema_without_showtime_ends_empty_with_bot_message(tmp_path):
    store, service = _service(tmp_path)
    state = run(service.start(HUGO, "cinema"))

    state = run(service.launch(state["id"], HUGO))

    assert state["status"] == "empty"
    assert run(store.list_chat_messages(None))[-1]["body"] == "Plus de séance ce soir au Grand Sud qui vous convienne."


def test_cinema_proposes_tonight_showtimes(tmp_path):
    store, service = _service(tmp_path)
    cinema = CinemaStore(store.db_path)
    run(cinema.upsert_site_film(1, "Dune", "https://cine/1", None))
    run(cinema.replace_showtimes({1: [Showtime(T0 + timedelta(hours=1), "VF", "https://b/1")]}))
    state = run(service.start(HUGO, "cinema"))

    state = run(service.launch(state["id"], HUGO))

    assert state["status"] == "voting"
    assert state["proposals"][0]["showtime"] == {"time": "20:00", "version": "VF", "booking_url": "https://b/1"}


def test_gemini_failure_falls_back_to_local_ranking(tmp_path):
    _, service = _service(tmp_path, gateway=FakeGateway(error=RuntimeError("quota")))
    party_id = _ready_party(service)

    state = run(service.launch(party_id, HUGO))

    assert len(state["proposals"]) == 3
    assert all(p["reason"] == "" for p in state["proposals"])


def test_gemini_reasons_are_kept(tmp_path):
    picks = [{"tmdb_id": 3, "reason": "Pour rire"}, {"tmdb_id": 1, "reason": "b"}, {"tmdb_id": 2, "reason": "c"}]
    _, service = _service(tmp_path, gateway=FakeGateway(picks=picks))
    party_id = _ready_party(service)

    state = run(service.launch(party_id, HUGO))

    assert (state["proposals"][0]["tmdb_id"], state["proposals"][0]["reason"]) == (3, "Pour rire")


def test_state_never_exposes_answers_or_member_ids(tmp_path):
    _, service = _service(tmp_path)
    party_id = _ready_party(service, LEA)

    state = run(service.state(party_id, "hugo"))

    assert all(set(member) == {"name", "answered", "late"} for member in state["members"])
    assert "answers" not in json.dumps(state)
    assert '"lea"' not in json.dumps(state)


def test_chat_command_starts_coloc_party_and_help_without_argument(tmp_path):
    store, service = _service(tmp_path)

    help_message = run(service.handle_chat_message("@soiree", HUGO))
    assert help_message["payload"]["type"] == "cine_help"
    assert [c["command"] for c in help_message["payload"]["commands"]] == ["@soirée coloc", "@soirée ciné"]

    run(service.handle_chat_message("@Soirée coloc", HUGO))
    party = run(service.parties.active_party())
    assert party["mode"] == "coloc"

    refused = run(service.handle_chat_message("@soirée ciné", LEA))
    assert refused["body"] == "Une soirée est déjà en cours."
    assert run(service.handle_chat_message("salut", HUGO)) is None


def test_launch_failure_ends_party_and_frees_the_flat(tmp_path):
    store = MediaStore(str(tmp_path / "f.db"))
    store.init_schema()

    def broken_tmdb():
        raise ValueError("TMDB_API_KEY manquante")

    service = PartyService(store, tmdb_factory=broken_tmdb, gateway_factory=lambda: FakeGateway(), clock=Clock(T0))
    party_id = _ready_party(service)

    state = run(service.launch(party_id, HUGO))

    assert state["status"] == "empty"
    assert run(store.list_chat_messages(None))[-1]["body"] == "Pas de film trouvé pour ce soir."
    assert run(service.start(LEA, "coloc"))["status"] == "joining"


def test_starter_can_cancel_a_party(tmp_path):
    store, service = _service(tmp_path)
    party_id = _ready_party(service, LEA)

    with pytest.raises(PartyError) as error:
        run(service.cancel(party_id, LEA))
    assert _status(error) == 403
    state = run(service.cancel(party_id, HUGO))

    assert state["status"] == "cancelled"
    assert run(store.list_chat_messages(None))[-1]["body"] == "Soirée annulée par Hugo."
    assert run(service.start(LEA, "cinema"))["status"] == "joining"


def test_cinema_gemini_ignores_films_without_tmdb_id(tmp_path):
    seen = {}

    class Recorder(FakeGateway):
        def select_group(self, profile, combined, candidates):
            seen["ids"] = [c["tmdb_id"] for c in candidates]
            return None

    store, service = _service(tmp_path, gateway=Recorder())
    cinema = CinemaStore(store.db_path)
    run(cinema.upsert_site_film(1, "Sans TMDB", "https://cine/1", None))
    run(cinema.upsert_site_film(2, "Avec TMDB", "https://cine/2", None))
    for site_id in (2, 3, 4):
        if site_id != 2:
            run(cinema.upsert_site_film(site_id, f"Film {site_id}", f"https://cine/{site_id}", None))
        run(cinema.set_tmdb_match(site_id, site_id * 11, T0))
    tonight = [Showtime(T0 + timedelta(hours=1), "VF", None)]
    run(cinema.replace_showtimes({site_id: tonight for site_id in (1, 2, 3, 4)}))
    state = run(service.start(HUGO, "cinema"))

    run(service.launch(state["id"], HUGO))

    assert sorted(seen["ids"]) == [22, 33, 44]
