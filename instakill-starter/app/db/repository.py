"""Read-side repositories: the only modules (with database.py) that touch SQLite."""
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.db.database import get_connection
from app.domain.models import Post, User

Connect = Callable[[], sqlite3.Connection]


def _utc(value: str | None) -> datetime | None:
    """SQLite datetime('now') strings are naive UTC; make them timezone-aware."""
    if value is None:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _row_to_post(row: sqlite3.Row) -> Post:
    return Post(id=row["id"], user_id=row["user_id"], content=row["content"],
                created_at=_utc(row["created_at"]))


class _SqliteReader:
    def __init__(self, connect: Connect = get_connection) -> None:
        self._connect = connect

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()


# --- search (Week 3) ---------------------------------------------------------

class PostReader(Protocol):
    def list_posts(self) -> list[Post]: ...


class SqlitePostRepository(_SqliteReader):
    def list_posts(self) -> list[Post]:
        rows = self._all("SELECT id, user_id, content, created_at FROM post ORDER BY id")
        return [_row_to_post(r) for r in rows]


# --- feed (Week 4) -----------------------------------------------------------

class FeedReader(Protocol):
    def get_user(self, user_id: int) -> User | None: ...

    def candidate_posts(self, user_id: int) -> list[Post]:
        """Posts not written by and not already liked by ``user_id``."""
        ...

    def followed_authors(self, user_id: int) -> set[int]: ...

    def liked_author_counts(self, user_id: int) -> dict[int, int]:
        """author_id -> how many of that author's posts ``user_id`` liked."""
        ...

    def like_counts(self, post_ids: list[int]) -> dict[int, int]: ...

    def user_like_count(self, user_id: int) -> int: ...

    def like_stats(self, since: datetime) -> tuple[dict[int, int], dict[int, int]]:
        """(lifetime likes per post, likes at or after ``since`` per post), over ALL posts."""
        ...


def _sqlite_ts(value: datetime) -> str:
    """Format like SQLite's datetime('now'): naive UTC 'YYYY-MM-DD HH:MM:SS'."""
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


class SqliteFeedRepository(_SqliteReader):
    def user_like_count(self, user_id: int) -> int:
        return self._all('SELECT COUNT(*) AS n FROM "like" WHERE user_id = ?', (user_id,))[0]["n"]

    def like_stats(self, since: datetime) -> tuple[dict[int, int], dict[int, int]]:
        rows = self._all(
            'SELECT post_id, COUNT(*) AS total, SUM(created_at >= ?) AS recent '
            'FROM "like" GROUP BY post_id',
            (_sqlite_ts(since),),
        )
        return ({r["post_id"]: r["total"] for r in rows},
                {r["post_id"]: r["recent"] for r in rows if r["recent"]})

    def get_user(self, user_id: int) -> User | None:
        rows = self._all("SELECT id, username, created_at FROM user WHERE id = ?", (user_id,))
        if not rows:
            return None
        r = rows[0]
        return User(id=r["id"], username=r["username"], created_at=_utc(r["created_at"]))

    def candidate_posts(self, user_id: int) -> list[Post]:
        rows = self._all(
            """
            SELECT p.id, p.user_id, p.content, p.created_at
            FROM post p
            WHERE p.user_id <> ?
              AND NOT EXISTS (SELECT 1 FROM "like" l WHERE l.post_id = p.id AND l.user_id = ?)
            ORDER BY p.id
            """,
            (user_id, user_id),
        )
        return [_row_to_post(r) for r in rows]

    def followed_authors(self, user_id: int) -> set[int]:
        rows = self._all("SELECT followee_id FROM follow WHERE follower_id = ?", (user_id,))
        return {r["followee_id"] for r in rows}

    def liked_author_counts(self, user_id: int) -> dict[int, int]:
        rows = self._all(
            """
            SELECT p.user_id AS author_id, COUNT(*) AS n
            FROM "like" l JOIN post p ON p.id = l.post_id
            WHERE l.user_id = ?
            GROUP BY p.user_id
            """,
            (user_id,),
        )
        return {r["author_id"]: r["n"] for r in rows}

    def like_counts(self, post_ids: list[int]) -> dict[int, int]:
        if not post_ids:
            return {}
        placeholders = ",".join("?" * len(post_ids))
        rows = self._all(
            f'SELECT post_id, COUNT(*) AS n FROM "like" WHERE post_id IN ({placeholders}) GROUP BY post_id',
            tuple(post_ids),
        )
        return {r["post_id"]: r["n"] for r in rows}
