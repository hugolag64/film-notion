import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

from backend.core.backup import create_backup, get_backup_status


def test_sqlite_backup_is_readable_and_old_backups_are_pruned(tmp_path):
    db_path = tmp_path / "backstage.db"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE catalogue (title TEXT)")
        connection.execute("INSERT INTO catalogue VALUES ('Dune')")

    old_backup = backup_dir / "backstage-20200101-000000.db"
    backup_dir.mkdir()
    old_backup.write_bytes(b"old")
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    old_backup.touch()
    import os
    os.utime(old_backup, (old_time, old_time))

    result = create_backup(str(db_path), str(backup_dir), retention_days=7)

    with sqlite3.connect(result["path"]) as connection:
        assert connection.execute("SELECT title FROM catalogue").fetchone() == ("Dune",)
    assert result["integrity"] == "ok"
    assert not old_backup.exists()


def test_backup_status_reports_latest_backup(tmp_path):
    db_path = tmp_path / "backstage.db"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE health (ok INTEGER)")
    create_backup(str(db_path), str(backup_dir), retention_days=7)

    status = get_backup_status(str(backup_dir))

    assert status["configured"] is True
    assert status["latest"] is not None
    assert status["latest"]["integrity"] == "ok"
