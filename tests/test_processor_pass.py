import asyncio

from backend.core.processor import EnrichmentProcessor
from backend.core.models import Media


def _media(i):
    return Media(id=f"id-{i}", title=f"Film {i}")


def test_run_auto_pass_counts_and_collects_ambiguous():
    p = object.__new__(EnrichmentProcessor)

    async def fake_process_one(media, force=False):
        n = int(media.id.split("-")[1])
        if n == 0:
            return {"status": "PROCESSED", "title": media.title, "tmdb_id": n}
        if n == 1:
            return {"status": "SKIPPED", "reason": "complète"}
        if n == 2:
            return {"status": "ERROR", "error": "boom"}
        return {"status": "AMBIGUOUS", "candidates": [], "media_id": media.id,
                "original_title": media.title}

    p.process_one_media = fake_process_one

    medias = [_media(i) for i in range(4)]
    seen = []
    counters = asyncio.run(
        p.run_auto_pass(medias, progress_cb=lambda d, t, r: seen.append(d), concurrency=2)
    )

    assert counters["processed"] == 1
    assert counters["skipped"] == 1
    assert counters["errors"] == 1
    assert len(counters["ambiguous"]) == 1
    assert counters["ambiguous"][0]["media_id"] == "id-3"
    # progress_cb appelé une fois par média
    assert sorted(seen) == [1, 2, 3, 4]
