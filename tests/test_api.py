import asyncio

from backend.api import UpdateMediaRequest, update_media
from backend.core.models import Media


class FakeStore:
    def __init__(self):
        self.media = Media(id="1", title="Dune", status="Terminé", rating="5")
        self.updates = None

    async def fetch_one(self, media_id):
        return self.media if media_id == self.media.id else None

    async def update(self, media_id, fields):
        self.updates = fields
        self.media = self.media.model_copy(update=fields)
        return True


def test_watching_later_clears_rating():
    store = FakeStore()
    result = asyncio.run(update_media("1", UpdateMediaRequest(status="À regarder"), store))

    assert result.status == "À regarder"
    assert result.rating is None
    assert store.updates == {"status": "À regarder", "rating": None}
