import asyncio

from backend.config import Config
from backend.core.media_server import Availability
from backend.core.store import MediaStore
from tests.test_coloc_rentals import _login_as_new_user
from tests.test_journal_api import FakeTMDB, client  # noqa: F401 (fixture)


def _store():
    return MediaStore(Config.DB_PATH)


def _new_list(client, name="Films à voir au ciné"):
    response = client.post("/api/lists", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_lists_are_shared_between_flatmates(client):
    film_list = _new_list(client)
    client.post(f"/api/lists/{film_list['id']}/items", json={"tmdb_id": 550})

    _login_as_new_user(client)

    lists = client.get("/api/lists").json()
    assert [(item["name"], item["item_count"], item["created_by_name"]) for item in lists] == [
        ("Films à voir au ciné", 1, "Hugo"),
    ]
    detail = client.get(f"/api/lists/{film_list['id']}").json()
    assert detail["items"][0]["added_by_name"] == "Hugo"
    assert detail["items"][0]["added_by_me"] is False
    assert detail["items"][0]["title"] == "Dune 2"

    renamed = client.patch(f"/api/lists/{film_list['id']}", json={"name": "Ciné"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Ciné"
    assert client.delete(f"/api/lists/{film_list['id']}/items/550").status_code == 204
    assert client.delete(f"/api/lists/{film_list['id']}/items/550").status_code == 404
    assert client.get(f"/api/lists/{film_list['id']}").json()["items"] == []


def test_adding_twice_keeps_one_item(client):
    film_list = _new_list(client)

    first = client.post(f"/api/lists/{film_list['id']}/items", json={"tmdb_id": 550})
    second = client.post(f"/api/lists/{film_list['id']}/items", json={"tmdb_id": 550})

    assert first.status_code == 200 and first.json()["added"] is True
    assert second.status_code == 200 and second.json()["added"] is False
    assert second.json()["item"]["tmdb_id"] == 550
    assert len(client.get(f"/api/lists/{film_list['id']}").json()["items"]) == 1


def test_list_item_outside_library_creates_no_media(client):
    film_list = _new_list(client)

    item = client.post(f"/api/lists/{film_list['id']}/items", json={"tmdb_id": 550}).json()["item"]

    assert item["library"] is None
    assert asyncio.run(_store().fetch_all()) == []


def test_list_item_shows_library_state(client):
    store = _store()
    asyncio.run(store.create({"id": "dune", "title": "Dune 2", "type": "Film", "tmdb_id": 550}))
    asyncio.run(store.upsert_availability(Availability(
        media_id="dune", provider="radarr", state="downloading", progress_percent=40,
    )))
    film_list = _new_list(client)

    item = client.post(f"/api/lists/{film_list['id']}/items", json={"tmdb_id": 550}).json()["item"]

    assert item["library"] == {"media_id": "dune", "state": "downloading", "progress_percent": 40, "ready": False}


def test_seen_mark_is_personal(client):
    film_list = _new_list(client)
    client.post(f"/api/lists/{film_list['id']}/items", json={"tmdb_id": 550})
    client.post("/api/journal", json={"tmdb_id": 550})

    assert client.get(f"/api/lists/{film_list['id']}").json()["items"][0]["seen_by_me"] is True

    _login_as_new_user(client)
    items = client.get(f"/api/lists/{film_list['id']}").json()["items"]
    assert [item["tmdb_id"] for item in items] == [550]
    assert items[0]["seen_by_me"] is False


def test_list_name_validation(client):
    assert client.post("/api/lists", json={"name": "   "}).status_code == 422
    assert client.post("/api/lists", json={"name": "x" * 61}).status_code == 422
    assert client.post("/api/lists", json={"name": "  Ciné  "}).json()["name"] == "Ciné"
    film_list = _new_list(client)
    assert client.patch(f"/api/lists/{film_list['id']}", json={"name": ""}).status_code == 422


def test_unknown_list_is_404_and_delete_works(client):
    assert client.get("/api/lists/nope").status_code == 404
    assert client.post("/api/lists/nope/items", json={"tmdb_id": 550}).status_code == 404
    film_list = _new_list(client)
    assert client.delete(f"/api/lists/{film_list['id']}").status_code == 204
    assert client.get("/api/lists").json() == []
