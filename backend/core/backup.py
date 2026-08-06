"""Safe SQLite backups and lightweight backup health reporting."""
from datetime import datetime, timedelta, timezone
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
