import sqlite3

from backend.core.auth import AuthStore
from backend.core.store import MediaStore


def test_auth_tables_preserve_existing_media_and_episode_counts(tmp_path):
    db = tmp_path / "backstage.db"
    MediaStore(str(db)).init_schema()
    with sqlite3.connect(db) as connection:
        connection.executemany(
            "INSERT INTO media (id, title, type, tmdb_ok) VALUES (?, ?, ?, ?)",
            [(f"movie-{index}", f"Movie {index}", "Film", 1) for index in range(252)],
        )
        connection.execute(
            "UPDATE media SET type = 'Série' WHERE id = 'movie-0'"
        )
        connection.executemany(
            """
            INSERT INTO episode (id, media_id, season_number, episode_number, title)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (f"episode-{index}", "movie-0", index // 20 + 1, index % 20 + 1, f"Episode {index}")
                for index in range(1091)
            ],
        )

    AuthStore(str(db)).init_schema()

    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM media").fetchone() == (252,)
        assert connection.execute("SELECT COUNT(*) FROM episode").fetchone() == (1091,)
        assert connection.execute("SELECT title FROM media WHERE id = 'movie-1'").fetchone() == ("Movie 1",)
