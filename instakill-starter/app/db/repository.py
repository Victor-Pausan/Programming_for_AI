"""Read-side repository: the only place search touches SQLite."""
import sqlite3
from collections.abc import Callable
from typing import Protocol

from app.db.database import get_connection
from app.domain.models import Post


class PostReader(Protocol):
    def list_posts(self) -> list[Post]: ...


class SqlitePostRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection] = get_connection) -> None:
        self._connect = connect

    def list_posts(self) -> list[Post]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return [Post(**dict(row)) for row in rows]
