from datetime import datetime, timezone
from typing import Optional


def format_relative_timestamp(ts_iso: str, now: Optional[datetime] = None) -> str:
    """Formate un timestamp ISO en libellé relatif court pour la timeline Historique."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    ts = datetime.fromisoformat(ts_iso)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    seconds = (now - ts).total_seconds()

    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {int(seconds // 60)} min"

    time_str = ts.strftime("%H:%M")
    day_delta = (now.date() - ts.date()).days
    if day_delta == 0:
        return f"aujourd'hui à {time_str}"
    if day_delta == 1:
        return f"hier à {time_str}"
    return ts.strftime("%d/%m/%Y à %H:%M")
