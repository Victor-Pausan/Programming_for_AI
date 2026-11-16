"""Seed InstaKill from MovieLens `latest-small`: a realistic past with timestamps.

    python scripts/seed_movielens.py --data path/to/ml-latest-small [--db instakill.db]

Mapping (the same proxy as Labs 04 and 05):

- every MovieLens user becomes an InstaKill user (same id, username ``ml_<id>``),
  created at the moment of their first rating;
- every movie becomes a post (same id). It is created at the moment **anybody first
  rated it**, and its author is that first rater (ties: lowest user id);
- every rating >= 4 becomes a like at the rating's timestamp, except a rating by the
  author of the post (nobody likes their own post);
- **follows are derived from likes**: u follows a as soon as u has liked
  ``FOLLOW_AFTER_LIKES`` posts by a. The follow's ``created_at`` is the time of that
  like, so a follow never exists before the likes that caused it.

The MovieLens files are NOT part of the repository (see the dataset's README for its
terms). The script is deterministic: the same files always give the same database.
"""
import argparse
import csv
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):  # allow `python scripts/seed_movielens.py` without installing
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database  # noqa: E402

LIKE_THRESHOLD = 4.0
FOLLOW_AFTER_LIKES = 3


def sqlite_ts(unix_seconds: int) -> str:
    return datetime.fromtimestamp(unix_seconds, UTC).strftime("%Y-%m-%d %H:%M:%S")


def derive_follows(likes, post_author):
    """likes: iterable of (user_id, post_id, ts) in time order -> list of (follower, followee, ts)."""
    per_pair = Counter()
    follows = []
    for user_id, post_id, ts in likes:
        author = post_author[post_id]
        per_pair[(user_id, author)] += 1
        if per_pair[(user_id, author)] == FOLLOW_AFTER_LIKES:
            follows.append((user_id, author, ts))
    return follows


def load_movielens(data_dir: Path):
    with open(data_dir / "ratings.csv", newline="", encoding="utf-8") as f:
        ratings = [(int(r["userId"]), int(r["movieId"]), float(r["rating"]), int(r["timestamp"]))
                   for r in csv.DictReader(f)]
    with open(data_dir / "movies.csv", newline="", encoding="utf-8") as f:
        movies = {int(r["movieId"]): (r["title"], r["genres"].replace("|", ", ")) for r in csv.DictReader(f)}
    return ratings, movies


def build(ratings, movies):
    ratings = sorted(ratings, key=lambda r: (r[3], r[0], r[1]))  # time, user, movie
    first_rating = {}
    user_first = {}
    for user_id, movie_id, _, ts in ratings:
        first_rating.setdefault(movie_id, (ts, user_id))  # sorted: first occurrence = earliest, lowest user
        user_first.setdefault(user_id, ts)

    posts = []
    post_author = {}
    for movie_id, (ts, author) in sorted(first_rating.items()):
        title, genres = movies.get(movie_id, (f"movie {movie_id}", ""))
        posts.append((movie_id, author, f"{title} [{genres}]" if genres else title, ts))
        post_author[movie_id] = author

    likes = [(u, m, ts) for u, m, rating, ts in ratings
             if rating >= LIKE_THRESHOLD and post_author[m] != u]
    follows = derive_follows(likes, post_author)
    users = sorted(user_first.items())
    return users, posts, likes, follows


def write(db_path: Path, users, posts, likes, follows) -> None:
    previous = database.DB_PATH
    database.DB_PATH = db_path
    try:
        database.init_db()
        with database.get_connection() as conn:
            for table in ('"like"', "follow", "post", "user"):
                conn.execute(f"DELETE FROM {table}")
            conn.executemany("INSERT INTO user (id, username, created_at) VALUES (?, ?, ?)",
                             [(u, f"ml_{u}", sqlite_ts(ts)) for u, ts in users])
            conn.executemany("INSERT INTO post (id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
                             [(p, a, c, sqlite_ts(ts)) for p, a, c, ts in posts])
            conn.executemany('INSERT INTO "like" (user_id, post_id, created_at) VALUES (?, ?, ?)',
                             [(u, p, sqlite_ts(ts)) for u, p, ts in likes])
            conn.executemany("INSERT INTO follow (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
                             [(f, t, sqlite_ts(ts)) for f, t, ts in follows])
    finally:
        database.DB_PATH = previous


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("ml-latest-small"),
                        help="folder with ratings.csv and movies.csv")
    parser.add_argument("--db", type=Path, default=database.DB_PATH)
    args = parser.parse_args(argv)
    if not (args.data / "ratings.csv").exists():
        parser.error(f"{args.data / 'ratings.csv'} not found: download ml-latest-small.zip from GroupLens and unzip it")
    users, posts, likes, follows = build(*load_movielens(args.data))
    write(args.db, users, posts, likes, follows)
    print(f"Seeded {args.db}: {len(users)} users, {len(posts)} posts, {len(likes)} likes, {len(follows)} follows.")


if __name__ == "__main__":
    main()
