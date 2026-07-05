"""Client HTTP asynchrone partagé + retry/backoff sur rate-limit (429)."""
import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Retourne un client httpx partagé (keep-alive / pooling), créé à la demande."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def aclose() -> None:
    """Ferme le client partagé (à appeler à l'arrêt de l'application)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = 4,
    base_delay: float = 1.0,
    **kwargs,
) -> httpx.Response:
    """
    Exécute une requête via le client partagé, en réessayant sur 429 (rate-limit)
    avec backoff exponentiel. Respecte l'en-tête `Retry-After` si présent.
    Retourne la dernière réponse (le code de statut reste à vérifier par l'appelant).
    """
    client = get_client()
    delay = base_delay
    response: Optional[httpx.Response] = None

    for attempt in range(max_retries):
        response = await client.request(method, url, **kwargs)
        if response.status_code != 429:
            return response

        retry_after = response.headers.get("Retry-After")
        wait = float(retry_after) if retry_after else delay
        logger.warning(
            "429 rate-limited sur %s (tentative %s/%s), nouvelle tentative dans %ss",
            url, attempt + 1, max_retries, wait,
        )
        await asyncio.sleep(wait)
        delay *= 2

    return response  # dernière réponse 429 si tout a échoué
