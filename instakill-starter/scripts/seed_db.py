"""Seeds the InstaKill database with synthetic users, posts, follows and likes.

Running it resets those four tables to the same known state every time
(post timestamps are relative to "now", so freshness stays meaningful).
"""
from app.db.database import get_connection, init_db

USERS = ["alice", "bob", "carol", "dave", "erin", "frank", "grace", "heidi"]

# (author_id, content, hours_ago). The first six are the original Week 1 posts.
POSTS = [
    (1, "hello world, this is my first post", 240),
    (1, "does anyone else think the feed is chronological only? boring", 72),
    (2, "just shipped a cosine similarity search, feels great", 30),
    (3, "spam spam spam buy now click here", 200),
    (4, "benchmarking my ranker against popularity baseline today", 12),
    (5, "red-team week is going to be brutal, good luck everyone", 5),
    (2, "heapq.nsmallest is the cleanest top-k trick I know", 3),
    (3, "cheap dinner spot near campus, ramen under ten euros", 20),
    (4, "half-life decay for freshness: 24 hours feels right for a social feed", 8),
    (5, "evening run along the river, 5k done", 48),
    (6, "first post! learning FastAPI this week", 2),
    (6, "SQLite is underrated for small projects", 26),
    (7, "quiet jazz playlist for studying, links in comments", 15),
    (7, "anyone up for a hackathon this weekend?", 1),
    (1, "tuned my feed weights on MovieLens, affinity matters most", 6),
    (2, "reading group: chapter 3 of the algorithms book tonight", 36),
    (3, "my cat walked on the keyboard and fixed a bug", 10),
    (5, "presentation slides for the lightning demo are ready", 4),
    (8, "hi all, just joined InstaKill", 0.5),
    (4, "popularity alone is a terrible feed, change my mind", 60),
]

# follower -> followees. heidi (8) follows nobody: the cold-start user.
FOLLOWS = {
    1: [2, 3],
    2: [1, 4, 5],
    3: [1, 2],
    4: [3, 5, 6],
    5: [1],
    6: [2, 3, 7],
    7: [4],
}

# user -> liked post ids
LIKES = {
    1: [3, 7, 16],
    2: [5, 9, 15, 20],
    3: [3, 7, 15],
    4: [3, 6, 8, 18],
    5: [3, 5, 9, 15],
    6: [3, 7, 8, 13, 17],
    7: [5, 9, 20],
}


def seed() -> None:
    init_db()
    with get_connection() as conn:
        for table in ('"like"', "follow", "post", "user"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('user', 'post')")

        for user_id, username in enumerate(USERS, start=1):
            conn.execute("INSERT INTO user (id, username) VALUES (?, ?)", (user_id, username))
        for post_id, (author_id, content, hours_ago) in enumerate(POSTS, start=1):
            conn.execute(
                "INSERT INTO post (id, user_id, content, created_at) "
                "VALUES (?, ?, ?, datetime('now', ?))",
                (post_id, author_id, content, f"-{hours_ago * 3600:.0f} seconds"),
            )
        conn.executemany(
            "INSERT INTO follow (follower_id, followee_id) VALUES (?, ?)",
            [(f, t) for f, followees in FOLLOWS.items() for t in followees],
        )
        conn.executemany(
            'INSERT INTO "like" (user_id, post_id) VALUES (?, ?)',
            [(u, p) for u, posts in LIKES.items() for p in posts],
        )
    n_follows = sum(map(len, FOLLOWS.values()))
    n_likes = sum(map(len, LIKES.values()))
    print(f"Seeded {len(USERS)} users, {len(POSTS)} posts, {n_follows} follows, {n_likes} likes.")


if __name__ == "__main__":
    seed()
