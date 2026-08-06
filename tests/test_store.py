import asyncio
from datetime import date, datetime, timedelta, timezone

from backend.core.store import MediaStore
from backend.core.media_server import Availability
from backend.core.models import Notification, Rental


def _store(tmp_path) -> MediaStore:
    store = MediaStore(str(tmp_path / "test.db"))
    store.init_schema()
    return store


def test_create_generates_id_when_absent(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))
    assert media.title == "Dune"
    assert media.id  # uuid4 généré
    assert media.type is None
    assert media.categories == []
    assert media.tmdb_ok is False


def test_create_sets_created_at(tmp_path):
    media = asyncio.run(_store(tmp_path).create({"title": "Dune"}))
    assert media.created_at is not None


def test_create_preserves_supplied_id(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"id": "notion-page-123", "title": "Arrival"}))
    assert media.id == "notion-page-123"


def test_create_persists_all_fields(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({
        "title": "Dune",
        "type": "Film",
        "status": "À regarder",
        "support": "Cinéma",
        "rating": "8",
        "release_date": date(2021, 10, 22),
        "director": "Denis Villeneuve",
        "categories": ["SF", "Aventure"],
        "synopsis": "Un noble héritier...",
        "tags": ["😌 Détente"],
        "review": "Excellent",
        "tmdb_ok": True,
        "cover_url": "http://example.com/dune.jpg",
    }))

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.title == "Dune"
    assert fetched.type == "Film"
    assert fetched.release_date == date(2021, 10, 22)
    assert fetched.categories == ["SF", "Aventure"]
    assert fetched.tags == ["😌 Détente"]
    assert fetched.tmdb_ok is True
    assert fetched.cover_url == "http://example.com/dune.jpg"


def test_fetch_all_returns_created_medias(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.create({"title": "Dune"}))
    asyncio.run(store.create({"title": "Arrival"}))

    all_medias = asyncio.run(store.fetch_all())
    assert {m.title for m in all_medias} == {"Dune", "Arrival"}


def test_fetch_one_returns_none_when_missing(tmp_path):
    store = _store(tmp_path)
    assert asyncio.run(store.fetch_one("unknown")) is None


def test_update_changes_only_given_fields(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "director": None}))

    ok = asyncio.run(store.update(media.id, {"director": "Denis Villeneuve", "tmdb_ok": True}))
    assert ok is True

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.director == "Denis Villeneuve"
    assert fetched.tmdb_ok is True
    assert fetched.title == "Dune"  # inchangé


def test_update_returns_false_for_unknown_id(tmp_path):
    store = _store(tmp_path)
    ok = asyncio.run(store.update("unknown", {"director": "X"}))
    assert ok is False


def test_delete_removes_media(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))

    ok = asyncio.run(store.delete(media.id))
    assert ok is True
    assert asyncio.run(store.fetch_one(media.id)) is None


def test_delete_returns_false_for_unknown_id(tmp_path):
    store = _store(tmp_path)
    ok = asyncio.run(store.delete("unknown"))
    assert ok is False


def test_update_silently_ignores_unknown_field_keys(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune"}))

    # Update with unknown field keys mixed with valid ones
    ok = asyncio.run(store.update(media.id, {
        "not_a_real_column": "x",
        "title": "Dune Remastered",
        "also_invalid": 123,
        "director": "Denis Villeneuve"
    }))
    assert ok is True

    fetched = asyncio.run(store.fetch_one(media.id))
    assert fetched.title == "Dune Remastered"
    assert fetched.director == "Denis Villeneuve"
    # Unknown keys did not cause an error, they were silently ignored


def test_upsert_and_fetch_availability(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))

    saved = asyncio.run(store.upsert_availability(Availability(
        media_id=media.id,
        provider="radarr",
        arr_id=42,
        state="downloading",
        progress_percent=63,
    )))

    assert saved.arr_id == 42
    assert asyncio.run(store.get_availability(media.id)).state == "downloading"


def test_rentals_are_scoped_and_count_active_items(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    rental = Rental(
        id="rental-1", media_id=media.id, backstage_user_id="hugo",
        requested_at=now, created_at=now, updated_at=now,
    )

    saved = asyncio.run(store.create_rental(rental))

    assert saved.id == "rental-1"
    assert [item.id for item in asyncio.run(store.list_user_rentals("hugo"))] == ["rental-1"]
    assert asyncio.run(store.list_user_rentals("ophelie")) == []
    assert asyncio.run(store.count_active_rentals("hugo")) == 1
    assert asyncio.run(store.find_active_rental("hugo", media.id)).id == "rental-1"


def test_rental_updates_expiry_and_keep_state(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    rental = Rental(
        id="rental-1", media_id=media.id, backstage_user_id="hugo",
        requested_at=now, created_at=now, updated_at=now,
    )
    asyncio.run(store.create_rental(rental))

    updated = asyncio.run(store.update_rental("rental-1", {
        "status": "keep_requested", "keep_requested_at": now, "expires_at": now,
    }))

    assert updated.status == "keep_requested"
    assert updated.keep_requested_at == now
    assert asyncio.run(store.count_active_rentals("hugo")) == 1


def test_rental_decisions_protect_or_extend_and_notifications_are_scoped(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    rental = Rental(
        id="rental-1", media_id=media.id, backstage_user_id="hugo", status="keep_requested",
        requested_at=now, expires_at=now, keep_requested_at=now, created_at=now, updated_at=now,
    )
    asyncio.run(store.create_rental(rental))

    kept = asyncio.run(store.decide_rental("rental-1", "accepted", "admin-id", now))
    assert kept.status == "kept"
    assert kept.storage_policy == "permanent"
    assert kept.expires_at is None
    assert kept.decided_by == "admin-id"

    notification = asyncio.run(store.create_notification(Notification(
        id="notification-1", backstage_user_id="hugo", kind="retention_accepted",
        message="Film conservé définitivement", created_at=now,
    )))
    assert notification.id == "notification-1"
    assert len(asyncio.run(store.list_notifications("hugo"))) == 1
    assert asyncio.run(store.list_notifications("other")) == []
    assert asyncio.run(store.mark_notification_read("notification-1", "hugo", now)) is True
    assert asyncio.run(store.list_notifications("hugo"))[0].read_at == now


def test_rental_refusal_and_extension_keep_the_file_temporary(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Arrival", "type": "Film"}))
    now = datetime.now(timezone.utc)
    rental = Rental(
        id="rental-2", media_id=media.id, backstage_user_id="hugo", status="keep_requested",
        requested_at=now, expires_at=now, keep_requested_at=now, created_at=now, updated_at=now,
    )
    asyncio.run(store.create_rental(rental))

    refused = asyncio.run(store.decide_rental("rental-2", "refused", "admin-id", now))
    assert refused.status == "available"
    assert refused.storage_policy == "temporary"
    assert refused.keep_requested_at is None
    extended = asyncio.run(store.extend_rental("rental-2", now))
    assert extended.expires_at > now


def test_cleanup_preview_only_marks_unprotected_expired_rentals(tmp_path):
    store = _store(tmp_path)
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    for media_id, title in (("delete", "Delete me"), ("kept", "Keep me"), ("pending", "Pending")):
        asyncio.run(store.create({"id": media_id, "title": title, "type": "Film"}))
    asyncio.run(store.create_rental(Rental(
        id="delete-rental", media_id="delete", backstage_user_id="hugo", status="available",
        requested_at=expired, expires_at=expired, created_at=expired, updated_at=expired,
    )))
    asyncio.run(store.create_rental(Rental(
        id="kept-rental", media_id="kept", backstage_user_id="hugo", status="kept",
        storage_policy="permanent", requested_at=expired, expires_at=None,
        created_at=expired, updated_at=expired,
    )))
    asyncio.run(store.create_rental(Rental(
        id="pending-rental", media_id="pending", backstage_user_id="hugo", status="keep_requested",
        requested_at=expired, expires_at=expired, keep_requested_at=expired,
        created_at=expired, updated_at=expired,
    )))

    preview = asyncio.run(store.cleanup_preview(datetime.now(timezone.utc)))
    actions = {item["rental_id"]: item["action"] for item in preview}
    reasons = {item["rental_id"]: item["reason"] for item in preview}
    assert actions["delete-rental"] == "would_delete"
    assert actions["kept-rental"] == "protected"
    assert reasons["kept-rental"] == "permanent"
    assert actions["pending-rental"] == "protected"
    assert reasons["pending-rental"] == "conservation_pending"


def test_active_temporary_storage_is_counted_per_user(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_rental(Rental(
        id="sized-rental", media_id=media.id, backstage_user_id="hugo", status="available",
        size_bytes=3 * 1024**3, requested_at=now, created_at=now, updated_at=now,
    )))

    assert asyncio.run(store.active_temporary_bytes("hugo")) == 3 * 1024**3
    assert asyncio.run(store.active_temporary_bytes("other")) == 0


def test_admin_rentals_include_media_titles(tmp_path):
    store = _store(tmp_path)
    media = asyncio.run(store.create({"title": "Dune", "type": "Film"}))
    now = datetime.now(timezone.utc)
    asyncio.run(store.create_rental(Rental(
        id="admin-rental", media_id=media.id, backstage_user_id="hugo", status="available",
        requested_at=now, expires_at=now + timedelta(days=2), created_at=now, updated_at=now,
    )))

    rentals = asyncio.run(store.list_admin_rentals())

    assert rentals[0]["media_title"] == "Dune"
    assert rentals[0]["rental"].id == "admin-rental"
