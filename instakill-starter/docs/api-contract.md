# API contract — `POST /posts` (planned, not implemented)

Status: **written contract only**. No route exists yet. When it is built, it will be a thin
HTTP adapter around `app.services.posts.publish_post`. It will map the JSON body to a
`PublishPostRequest` and the service's exceptions to the status codes listed below.

## Purpose

Publish a new text post on behalf of an existing user.

## Request

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

## Successful response — `201 Created`

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

## Errors

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

## Examples

| Request body                                  | Response                    |
|-----------------------------------------------|-----------------------------|
| `{"author_id": 1, "content": "hello"}`        | `201`, post with `id`       |
| `{"author_id": 1, "content": "   "}`         | `422 invalid_content`       |
| `{"author_id": 1, "content": "<2201 chars>"}` | `422 invalid_content`       |
| `{"author_id": 99, "content": "hello"}`       | `404 author_not_found`      |
| `{"content": "hello"}`                        | `422 validation_error`      |
| `{"author_id": "one", "content": "hello"}`    | `422 validation_error`      |
