"""
Recommandations de films via l'API Claude (optionnel).

Activé uniquement si ANTHROPIC_API_KEY est défini. Dégradation propre sinon :
les fonctions lèvent AIUnavailable, gérée par l'appelant.
"""
import logging
from typing import List, Dict

from backend.config import Config

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-8"


class AIUnavailable(RuntimeError):
    pass


def _client():
    if not Config.ai_enabled():
        raise AIUnavailable("ANTHROPIC_API_KEY non configurée")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise AIUnavailable("Le paquet 'anthropic' n'est pas installé") from e
    return AsyncAnthropic(api_key=Config.ANTHROPIC_API_KEY)


def _fmt(items: List[Dict], with_rating: bool) -> str:
    lines = []
    for it in items:
        genres = ", ".join(it.get("genres", []))
        if with_rating and it.get("rating"):
            lines.append(f"- {it['title']} (note {it['rating']}) — {genres}")
        else:
            lines.append(f"- {it['title']} — {genres}")
    return "\n".join(lines) if lines else "(aucun)"


async def recommend(watched: List[Dict], candidates: List[Dict], n: int = 3) -> str:
    """
    À partir des films notés (goûts) et de la liste « à regarder », recommande
    `n` titres parmi les candidats, avec une justification courte et sans spoiler.
    """
    client = _client()
    if not candidates:
        return "Aucun film « à regarder » à recommander pour le moment."

    system = (
        "Tu es un conseiller cinéma. À partir des goûts de l'utilisateur (films notés), "
        "recommande des films de sa liste « à regarder ». Réponds en français, de façon "
        "concise, sans spoiler. Ne recommande QUE des titres présents dans la liste des candidats."
    )
    user = (
        f"Films notés par l'utilisateur (ses goûts) :\n{_fmt(watched, with_rating=True)}\n\n"
        f"Liste « à regarder » (candidats) :\n{_fmt(candidates, with_rating=False)}\n\n"
        f"Recommande {n} titres maximum de la liste des candidats. Pour chacun : titre + 1 phrase de justification."
    )

    try:
        msg = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    except Exception as e:
        logger.error("Erreur appel Claude: %s", e)
        raise AIUnavailable(str(e)) from e
