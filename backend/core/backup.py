"""Safe SQLite backups and lightweight backup health reporting."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Optional


def _integrity(path: Path) -> str:
    try:
        with sqlite3.connect(path) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        return "ok" if result and result[0] == "ok" else str(result[0] if result else "unknown")
    except sqlite3.Error as error:
        return f"error: {error}"


def verify_backup(path: str) -> dict[str, Any]:
    backup_path = Path(path)
    integrity = _integrity(backup_path)
    readable = False
    if integrity == "ok":
        try:
            with sqlite3.connect(backup_path) as connection:
                connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            readable = True
        except sqlite3.Error:
            readable = False
    return {
        "path": str(backup_path),
        "integrity": integrity,
        "readable": readable,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def create_backup(
    db_path: str,
    backup_dir: str,
    *,
    retention_days: int = 7,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Create a consistent SQLite copy, verify it, and prune old backup files."""
    source_path = Path(db_path)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    target_path = target_dir / f"backstage-{now.strftime('%Y%m%d-%H%M%S')}.db"

    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)
        target.commit()
    integrity = _integrity(target_path)
    if integrity != "ok":
        raise RuntimeError(f"Backup SQLite invalide : {integrity}")

    cutoff = now.timestamp() - max(0, retention_days) * 86400
    removed = 0
    for candidate in target_dir.glob("backstage-*.db"):
        if candidate == target_path:
            continue
        if candidate.stat().st_mtime < cutoff:
            candidate.unlink()
            removed += 1
    return {
        "path": str(target_path),
        "created_at": now.isoformat(),
        "size_bytes": target_path.stat().st_size,
        "integrity": integrity,
        "removed": removed,
    }


def get_backup_status(backup_dir: str) -> dict[str, Any]:
    target_dir = Path(backup_dir)
    files = sorted(target_dir.glob("backstage-*.db"), key=lambda path: path.stat().st_mtime, reverse=True) if target_dir.exists() else []
    if not files:
        return {"configured": True, "directory": str(target_dir), "latest": None}
    latest = files[0]
    created_at = datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat()
    return {
        "configured": True,
        "directory": str(target_dir),
        "latest": {
            "path": str(latest),
            "created_at": created_at,
            "size_bytes": latest.stat().st_size,
            "integrity": _integrity(latest),
        },
    }


def get_backup_health(backup_dir: str, *, max_age_hours: float, now: Optional[datetime] = None) -> dict[str, Any]:
    status = get_backup_status(backup_dir)
    latest = status.get("latest")
    if not latest:
        return {"status": "error", "reason": "missing"}
    now = now or datetime.now(timezone.utc)
    created_at = datetime.fromisoformat(latest["created_at"])
    age_hours = max(0, (now - created_at).total_seconds() / 3600)
    if latest["integrity"] != "ok":
        return {"status": "error", "reason": "invalid", "age_hours": round(age_hours, 2)}
    if age_hours > max_age_hours:
        return {"status": "error", "reason": "stale", "age_hours": round(age_hours, 2)}
    return {
        "status": "ok",
        "reason": "healthy",
        "age_hours": round(age_hours, 2),
        "created_at": latest["created_at"],
    }
