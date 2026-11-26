"""Routes du cinéma : horaires d'un film du Grand Sud."""

from fastapi import APIRouter, Depends, HTTPException

from backend.api import get_store
from backend.auth_api import get_current_user
from backend.core.cinema_bot import film_showtimes
from backend.core.cinema_store import CinemaStore
from backend.core.cinema_sync import reunion_now
from backend.core.store import MediaStore

cinema_router = APIRouter(prefix="/api/cinema", tags=["cinema"], dependencies=[Depends(get_current_user)])


@cinema_router.get("/films/{site_id}/showtimes")
async def get_film_showtimes(site_id: int, store: MediaStore = Depends(get_store)):
    detail = await film_showtimes(CinemaStore(store.db_path), site_id, reunion_now())
    if detail is None:
        raise HTTPException(status_code=404, detail="Film inconnu")
    return detail
