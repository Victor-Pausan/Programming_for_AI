# InstaKill — Starter Repo

Mini social-media platform. Mandatory backend: Python + FastAPI + SQLite (default) / PostgreSQL (allowed). See the full brief and grading rubric in `masterplan.md` (course root).

What the instructor provides (this starter):

- `app/main.py` — FastAPI hello-world with `GET /health`
- `app/db/database.py` — SQLite bootstrap (creates tables on startup)
- `app/domain/models.py` — `User` / `Post` schema
- `scripts/seed_db.py` — 5-10 synthetic users/posts
- `tests/test_health.py` — test skeleton

What it does **not** provide: the feed, ranking, ML models, search. Those are the team's work, in the following weeks.

## Running it

```bash
pip install -e .
uvicorn app.main:app --reload
# other terminal:
curl localhost:8000/health

python scripts/seed_db.py
pytest
```

## Semantic search (`GET /search`, Week 3)

```bash
python scripts/seed_db.py          # search only sees posts that exist at startup
uvicorn app.main:app --reload
curl "localhost:8000/search?q=vector%20search&limit=3"
```

The full request/response/error contract is in [`docs/api-contract.md`](docs/api-contract.md).

| Layer | Module | Responsibility |
|---|---|---|
| HTTP edge | `app/api/search.py`, `app/api/errors.py` | Parse `q`/`limit`, map errors to `422`, format JSON |
| Use case | `app/services/search.py` | `build_index`, `search_posts`: validates input and coordinates the parts below |
| Pure retrieval | `app/search/retrieval.py` | NumPy cosine similarity + deterministic top-k (score desc, `post_id` asc). No I/O |
| Model adapter | `app/search/encoder.py` | `TextEncoder` protocol; `SentenceTransformerEncoder` loads `all-MiniLM-L6-v2` on CPU |
| Repository | `app/db/repository.py` | `PostReader` protocol; `SqlitePostRepository.list_posts()` is the only SQL |

No vector database, hosted embedding API, search framework or `sklearn` neighbours are used. Cosine
similarity and top-k are implemented in this repository.

### Where the index is built

The in-memory index is built **once, at application startup**, in the `lifespan` function of
`create_app()` in `app/main.py`. It reads every post through the repository, encodes their `content`
with the encoder adapter, and stores a `SearchIndex` (posts + float32 embedding matrix) on
`app.state.search_index`. The first startup downloads the model, which is about 90 MB.

### How a new post will refresh it (not implemented yet)

Posts added after startup are not searchable yet. When post creation exists (`POST /posts`, see
`publish_post` in `app/services/posts.py`), the plan is:

1. After `publish_post` stores the post, the service encodes only the new post's content.
2. It appends that row to the index, creating a new `SearchIndex` with posts + the extra vector,
   and swaps `app.state.search_index` atomically, so readers never see a half-built index.
3. A full rebuild (`build_index`) stays available for edits/deletes, or on a schedule if the index
   drifts from the database.

Because the retrieval code is pure and only receives vectors, none of this touches
`app/search/retrieval.py`.

Tests use a fake bag-of-words encoder and an in-memory repository (`tests/fakes.py`), so `pytest`
needs neither the model nor network access.

## Feed (`GET /feed`, Week 4)

```bash
python scripts/seed_db.py      # resets users/posts/follows/likes to a known state
uvicorn app.main:app --reload
curl "localhost:8000/feed?user_id=1&limit=5"
curl "localhost:8000/feed?user_id=1&strategy=chronological"
pytest                         # one command: ranking unit tests + API test over the seeded DB
```

Contract: [`docs/api-contract.md`](docs/api-contract.md).

| Layer | Module | Responsibility |
|---|---|---|
| HTTP edge | `app/api/feed.py` | Parse `user_id` / `limit` / `strategy`, map errors (404, 422), format JSON |
| Use case | `app/services/feed.py` | `get_feed`: validates the request, loads candidates + signals, chooses the strategy |
| Pure ranking | `app/feed/ranking.py` | `rank_feed(candidates, signals, now, weights, limit)` and `chronological`, heap-based top-k. No I/O, no clock, no mutation |
| Repository | `app/db/repository.py` | `SqliteFeedRepository`: candidate posts, follows, likes per author, like counts |
| Data | `app/db/database.py`, `scripts/seed_db.py` | `follow` and `"like"` tables. The seed has 8 users, 20 posts, 15 follows and 26 likes |

`now` comes from `app.state.clock`, which is injected in `create_app()`. It is the only clock read, and it
happens at the API edge.

### Candidates and cold start

- **Candidates** are all posts except the requesting user's own posts and the posts they already liked.
- Followed authors are **not** a hard filter. Following an author only raises the affinity signal. With a
  small network, a "followed authors only" feed would often be empty.
- **Cold start:** a user who follows nobody and liked nothing (seeded user 8, `heidi`) has affinity 0 for
  every post. Their feed is therefore ranked by freshness + popularity, i.e. "what is new and liked
  right now". It is never empty while other people's posts exist.

### Signals and default weights

```text
score      = 1.0 * freshness + 1.5 * affinity + 1.0 * popularity         (each signal in [0, 1])
freshness  = 0.5 ** (age_hours / 24)                                     half-life 24 h
affinity   = 0.6 * [user follows the author] + 0.4 * likes_by_user_on_author / max_likes_by_user_on_any_author
popularity = log1p(likes of the post) / log1p(max likes among the candidates)
```

Why these weights (they are our own, not the Week 2 lab ranker):

- **Affinity 1.5:** in the Lab 4 ablation, genre affinity barely mattered. Genres were too coarse
  (failure case 3: almost every movie is a "Drama"). On InstaKill, affinity is built from **explicit**
  actions instead: a follow, or repeated likes of the same author. This is much stronger evidence, so it
  gets the largest weight. A followed author's fresh post should beat a stranger's popular one.
- **Popularity 1.0, with `log1p`:** the lab showed popularity is the strongest generic signal
  (NDCG 0.19 -> 0.03 without it). We keep it at full weight. `log1p` stops one viral post from
  crushing everything, because 10 likes vs 100 likes is a smaller gap than the raw counts suggest.
- **Freshness 1.0, half-life 24 h:** social posts age in hours, not years (the lab used 180 days for
  movies). After a day a post keeps half its freshness. After three days it keeps 1/8.

These are reasoned defaults, not tuned values. Formal evaluation against `chronological` comes in Week 7.

### Complexity of one `GET /feed` request

With *C* = candidate posts, *k* = `limit`:

- Repository: the candidate query scans the posts and checks likes through the primary key, so it is
  O(C). The like counts for the candidates are one grouped query, also O(C).
- Scoring: O(1) per candidate, so O(C) in total.
- Top-k with `heapq.nsmallest`: O(C log k). `chronological` is also O(C log k).
- **Total: O(C log k)** time and O(C) memory, because the candidates are materialised.

**Precompute first:** like counts per post (popularity). Today the counts are aggregated over the `like`
table on every request. A `like_count` column, or a counter updated when a like is written, would make
popularity an O(1) lookup. The next step is limiting *C* itself, e.g. only posts from the last N days,
or a cached candidate set per user.

## Learned feed (`GET /feed?strategy=learned`, Week 5)

```bash
curl "localhost:8000/feed?user_id=1&strategy=learned&limit=5"
```

`models/like_model.npz` (4 KB, 129 parameters) is the one-hidden-layer MLP trained in plain NumPy in
`lab-05-learn-the-scorer/week05.ipynb`. On the MovieLens exam it beat every baseline, including the linear model
(test NDCG@10 0.477 vs 0.427). It predicts **P(like)** for a user and a post from six signals. The feed returns
the top `limit` candidates by that probability, with ties broken by ascending `post_id`.

| Piece | Module |
|---|---|
| Model file + loader + pure `predict` (copied from the notebook) | `models/like_model.npz`, `app/ml/like_model.py` |
| The six signals and `rank_learned` (pure: `now` passed in, no I/O, heap top-k) | `app/feed/learned.py` |
| Extra reads: likes per user, lifetime + recent likes per post | `SqliteFeedRepository.user_like_count / like_stats` |
| Strategy dispatch; `503 model_unavailable` if the file is missing | `app/services/feed.py`, `app/api/feed.py` |

The model is loaded **once at startup**, in the `lifespan` of `create_app()`, from `models/like_model.npz`.

**Signal formulas.** These are the notebook's formulas, and the constants come from the `.npz`, not from our code:

| Signal | InstaKill formula |
|---|---|
| freshness | `0.5 ** (age_days / half_life_days)` |
| affinity | `likes by the user on this post's author / all likes by the user` (the author plays the role of the single "genre") |
| popularity | `likes in the last popularity_days / max over all posts` |
| activity | `min(1, log1p(likes by the user) / log1p(activity_cap))` |
| lifetime | `log1p(likes ever) / log1p(max over all posts)` |
| age | `min(1, age_days / age_cap_days)` |

**Train/serve skew (known limitation).** The model was trained on movies, with a 3-year half-life and a 25-year age
cap. InstaKill posts are hours old, so freshness is about 1.0 and age about 0.0 for **every** post: these two signals
do not separate posts here. The ranking is effectively driven by affinity, popularity, lifetime and activity. Also,
"author" is only a stand-in for "genre". The golden-row test (`tests/test_feed_learned.py`) proves that the
*arithmetic* matches the notebook. Whether the *ranking* is good on InstaKill data still has to be measured, and that
is the Week 7 evaluation. The `for_you` and `chronological` strategies are unchanged.

**Cost of one request:** signals O(C) + forward pass O(C·6·H) with H = 16, + heap O(C log k), so linear in the
number of candidates. The likes are aggregated once per request over the `like` table (O(L)). That aggregation is
the first thing to precompute, as a `like_count` / rolling-window counter per post.

## Milestones (see masterplan.md for full details)

W1 Repo+API → W3 CRUD+DB → W4 Feed v0 → W7 Baseline+eval plan → W9 ML+pretrained feature → W11 Profile+optimize → W13 Feature freeze+E2E → W14 Red-team+Demo Day.

At the end of each week: a demonstrable commit/tag.
