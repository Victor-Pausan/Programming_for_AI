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

## Milestones (see masterplan.md for full details)

W1 Repo+API → W3 CRUD+DB → W4 Feed v0 → W7 Baseline+eval plan → W9 ML+pretrained feature → W11 Profile+optimize → W13 Feature freeze+E2E → W14 Red-team+Demo Day.

At the end of each week: a demonstrable commit/tag.
