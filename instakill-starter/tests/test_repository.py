import sqlite3

from app.db.database import SCHEMA
from app.db.repository import SqlitePostRepository


def test_list_posts_reads_all_posts_in_id_order(tmp_path):
    db = tmp_path / "repo.db"

    def connect():
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        return conn

    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO user (username) VALUES ('alice')")
        conn.execute("INSERT INTO post (user_id, content) VALUES (1, 'second?')")
        conn.execute("INSERT INTO post (user_id, content) VALUES (1, 'hello')")

    posts = SqlitePostRepository(connect).list_posts()
    assert [(p.id, p.user_id, p.content) for p in posts] == [(1, 1, "second?"), (2, 1, "hello")]
    assert all(p.created_at is not None for p in posts)
