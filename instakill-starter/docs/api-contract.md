# InstaKill API contract

| Endpoint        | Status          | Since  |
|-----------------|-----------------|--------|
| `GET /health`   | implemented     | Week 1 |
| `GET /search`   | implemented     | Week 3 |
| `GET /feed`     | **implemented** | Week 4 (`strategy=learned`: Week 5) |
| `POST /posts`   | planned only    | Week 2 |

All errors share one JSON shape (implemented in `app/api/errors.py`):

```json
{ "error": { "code": "validation_error", "message": "limit: Input should be less than or equal to 20" } }
```

## `GET /feed` (implemented)

Returns the personalised feed of one user. Layers: `app/api/feed.py` → `app/services/feed.py` →
`app/feed/ranking.py` (pure `rank_feed`), with `app/db/repository.py` (`SqliteFeedRepository`) for reads.

### Request

```http
GET /feed?user_id=1&limit=20&strategy=for_you
```

| Parameter  | Type    | Required | Rules                                                     |
|------------|---------|----------|-----------------------------------------------------------|
| `user_id`  | integer | yes      | Must be an existing user (otherwise `404`).               |
| `limit`    | integer | no       | 1–50 inclusive; default `20`.                             |
| `strategy` | string  | no       | `for_you` (default), `chronological`, or `learned`.       |

**Candidates** (both strategies): every post except the user's own posts and the posts the user already
liked. A user who follows nobody still gets a feed, ranked by freshness and popularity. See the README
for the formula.

### Successful response — `200 OK`

`for_you`. The posts are seed data; scores and times are only illustrative:

```json
{
  "user_id": 1,
  "strategy": "for_you",
  "posts": [
    { "post_id": 8,  "user_id": 3, "content": "cheap dinner spot near campus, ramen under ten euros",
      "created_at": "2026-11-15T16:00:00Z", "score": 2.253706 },
    { "post_id": 17, "user_id": 3, "content": "my cat walked on the keyboard and fixed a bug",
      "created_at": "2026-11-16T02:00:00Z", "score": 2.149145 }
  ]
}
```

`chronological` has the same shape, but there is **no** `score` field.

`learned` has the same shape as `for_you`. There, `score` is the like model's predicted probability **P(like)**,
in (0, 1) and rounded to 6 decimals. It comes from `models/like_model.npz`, trained in Lab 05.

- `posts` holds at most `limit` items, and fewer if there are fewer candidates. It is `[]` when nothing qualifies.
- `user_id` inside a post is the **author**. The top-level `user_id` is the requesting user.
- `created_at` is ISO 8601 in UTC.
- `score` (only for `for_you`) is `1.0·freshness + 1.5·affinity + 1.0·popularity`. It is in [0, 3.5] and
  rounded to 6 decimals.
- Ordering: `for_you` and `learned` by `score` descending; `chronological` by `created_at` descending (newest first).
  In both, equal values are ordered by ascending `post_id`.

### Errors

| Status | `code`             | When                                                                            |
|--------|--------------------|---------------------------------------------------------------------------------|
| 404    | `user_not_found`   | No user has id `user_id`.                                                       |
| 422    | `validation_error` | `user_id` is missing or not an integer; `limit` is not an integer or is outside 1–50; `strategy` is not `for_you`/`chronological`/`learned`. |
| 503    | `model_unavailable`| `strategy=learned`, but `models/like_model.npz` was not found at startup.    |
| 500    | `internal_error`   | Unexpected failure. This status is not yet mapped by a dedicated handler.       |

### Examples

| Request                                     | Response                |
|---------------------------------------------|-------------------------|
| `/feed?user_id=1`                           | `200`, up to 20 posts with `score` |
| `/feed?user_id=1&strategy=chronological`    | `200`, newest first, no `score`    |
| `/feed?user_id=8&limit=5`                   | `200`, cold-start feed  |
| `/feed?user_id=1&strategy=learned`          | `200`, `score` = P(like) |
| `/feed?user_id=999`                         | `404 user_not_found`    |
| `/feed`                                     | `422 validation_error`  |
| `/feed?user_id=1&limit=51`                  | `422 validation_error`  |
| `/feed?user_id=1&strategy=random`           | `422 validation_error`  |

## `GET /search` (implemented)

Semantic search over all posts that were in the database when the app started.

Layers: `app/api/search.py` (HTTP parsing/formatting) → `app/services/search.py` (use case) →
`app/search/retrieval.py` (pure NumPy cosine + top-k), with `app/search/encoder.py` (model adapter)
and `app/db/repository.py` (SQLite reads) behind small protocols.

### Request

```http
GET /search?q=vector%20search&limit=2
```

| Parameter | Type    | Required | Rules                                                                    |
|-----------|---------|----------|--------------------------------------------------------------------------|
| `q`       | string  | yes      | 1–500 characters; it must contain at least one non-whitespace character. |
| `limit`   | integer | no       | 1–20 inclusive; default `10`.                                            |

### Successful response — `200 OK`

The posts below come from the seed data. The scores are only illustrative.

```json
{
  "query": "vector search",
  "results": [
    { "post_id": 3, "user_id": 2, "content": "just shipped a cosine similarity search, feels great", "score": 0.512345 },
    { "post_id": 5, "user_id": 4, "content": "benchmarking my ranker against popularity baseline today", "score": 0.181734 }
  ]
}
```

- `query` is echoed exactly as received.
- `results` holds at most `limit` items. It holds fewer if there are fewer posts, and it is `[]`
  when the database had no posts at startup.
- `score` is the cosine similarity between the query embedding and the post embedding. It is in
  [-1, 1] and rounded to 6 decimals. Higher means more similar. Results are not filtered by any
  minimum score.
- Ordering: `score` descending. Equal scores are ordered by ascending `post_id`, so the output is
  deterministic.
- Posts created after startup are not searchable until the index is rebuilt. See the README.

### Errors

| Status | `code`             | When                                                                  |
|--------|--------------------|-----------------------------------------------------------------------|
| 422    | `validation_error` | `q` is missing or empty, or longer than 500 characters; `limit` is not an integer or is outside 1–20. |
| 422    | `invalid_query`    | `q` contains only whitespace.                                         |
| 500    | `internal_error`   | Unexpected failure. This status is not yet mapped by a dedicated handler. |

### Examples

| Request                          | Response                 |
|----------------------------------|--------------------------|
| `/search?q=cheap%20dinner`       | `200`, up to 10 results  |
| `/search?q=jazz&limit=3`         | `200`, up to 3 results   |
| `/search`                        | `422 validation_error`   |
| `/search?q=`                     | `422 validation_error`   |
| `/search?q=%20%20`               | `422 invalid_query`      |
| `/search?q=jazz&limit=0`         | `422 validation_error`   |
| `/search?q=jazz&limit=21`        | `422 validation_error`   |

## `POST /posts` (planned, not implemented)

Status: **written contract only**. No route exists yet. When it is built, it will be a thin
HTTP adapter around `app.services.posts.publish_post`. It will map the JSON body to a
`PublishPostRequest` and the service's exceptions to the status codes listed below.

### Purpose

Publish a new text post on behalf of an existing user.

### Request

```http
POST /posts
Content-Type: application/json
```

```json
{
  "author_id": 1,
  "content": "just shipped a cosine similarity search, feels great"
}
```

| Field       | Type    | Required | Rules                                                                 |
|-------------|---------|----------|-----------------------------------------------------------------------|
| `author_id` | integer | yes      | Positive integer; must reference an existing user.                    |
| `content`   | string  | yes      | Leading/trailing whitespace is stripped; the result must be 1–2200 characters. |

Unknown extra fields are rejected.

> Authentication is out of scope for now: `author_id` is sent in the body. Once auth exists,
> the author will come from the authenticated user and this field will be removed.

### Successful response — `201 Created`

Header `Location: /posts/{id}`.

```json
{
  "id": 7,
  "user_id": 1,
  "content": "just shipped a cosine similarity search, feels great",
  "created_at": "2026-11-23T10:15:00Z"
}
```

The body is the domain `Post` model (`app/domain/models.py`). `content` is returned
already stripped. `created_at` is set by the server in UTC, ISO 8601.

### Errors

All errors use one shape:

```json
{ "error": { "code": "invalid_content", "message": "content must not be empty" } }
```

| Status | `code`              | When                                                                   | Source                                  |
|--------|---------------------|------------------------------------------------------------------------|-----------------------------------------|
| 400    | `malformed_json`    | Body is not valid JSON.                                                | HTTP layer                              |
| 422    | `validation_error`  | A field is missing, has the wrong type, `author_id` ≤ 0, or there are extra fields. | HTTP layer (request schema)  |
| 422    | `invalid_content`   | `content` is empty/blank after stripping, or longer than 2200 characters. | `InvalidPostError`                   |
| 404    | `author_not_found`  | No user has id `author_id`.                                            | `AuthorNotFoundError`                   |
| 500    | `internal_error`    | Unexpected failure (e.g. database unavailable). No internals are leaked. | Any other exception                   |

For `validation_error`, `message` names the offending field(s). For example:
`"author_id: field required"`.

### Examples

| Request body                                  | Response                    |
|-----------------------------------------------|-----------------------------|
| `{"author_id": 1, "content": "hello"}`        | `201`, post with `id`       |
| `{"author_id": 1, "content": "   "}`         | `422 invalid_content`       |
| `{"author_id": 1, "content": "<2201 chars>"}` | `422 invalid_content`       |
| `{"author_id": 99, "content": "hello"}`       | `404 author_not_found`      |
| `{"content": "hello"}`                        | `422 validation_error`      |
| `{"author_id": "one", "content": "hello"}`    | `422 validation_error`      |
