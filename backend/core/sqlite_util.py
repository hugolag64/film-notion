"""Shared SQLite settings.

The web requests, the 60-second media sync and the playback sync all write to
the same file. In SQLite's default rollback-journal mode a writer blocks every
reader, and a reader that waits too long fails with « database is locked »,
which reaches people as an internal error. WAL lets readers run while a write
is in progress; the busy timeout makes writers queue instead of failing.
"""
import sqlite3

SQLITE_BUSY_TIMEOUT_SEC = 30.0


def enable_wal(conn: sqlite3.Connection) -> None:
    """Switch the database file to WAL (a persistent, per-file setting)."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
