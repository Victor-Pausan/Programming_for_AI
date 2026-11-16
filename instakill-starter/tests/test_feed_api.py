"""API tests for GET /feed over the real seeded SQLite database (in a temp file)."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.seed_db import FOLLOWS, LIKES, POSTS, seed
from tests.fakes import BagOfWordsEncoder

ALICE = 1
HEIDI = 8  # follows nobody, liked nothing: cold start


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.database.DB_PATH", tmp_path / "seeded.db")
    seed()
    with TestClient(create_app(encoder=BagOfWordsEncoder())) as c:
        yield c


def author_of(post_id: int) -> int:
    return POSTS[post_id - 1][0]


def test_for_you_feed_over_seeded_db(client):
    response = client.get("/feed", params={"user_id": ALICE})
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == ALICE and body["strategy"] == "for_you"

    posts = body["posts"]
    own = {i for i, p in enumerate(POSTS, start=1) if p[0] == ALICE}
    expected_count = len(POSTS) - len(own) - len(LIKES[ALICE])
    assert len(posts) == expected_count  # default limit 20 > candidates
    returned = {p["post_id"] for p in posts}
    assert not returned & own, "own posts must be excluded"
    assert not returned & set(LIKES[ALICE]), "already liked posts must be excluded"

    for p in posts:
        assert {"post_id", "user_id", "content", "created_at", "score"} <= p.keys()
        datetime.fromisoformat(p["created_at"])
    keys = [(-p["score"], p["post_id"]) for p in posts]
    assert keys == sorted(keys), "descending score, ties by ascending post_id"
    assert author_of(posts[0]["post_id"]) in FOLLOWS[ALICE], "followed authors should lead"


def test_chronological_feed(client):
    body = client.get("/feed", params={"user_id": ALICE, "strategy": "chronological", "limit": 5}).json()
    posts = body["posts"]
    assert body["strategy"] == "chronological" and len(posts) == 5
    assert all("score" not in p for p in posts)
    keys = [(-datetime.fromisoformat(p["created_at"]).timestamp(), p["post_id"]) for p in posts]
    assert keys == sorted(keys)


def test_cold_start_user_gets_a_feed(client):
    posts = client.get("/feed", params={"user_id": HEIDI, "limit": 50}).json()["posts"]
    assert len(posts) == len(POSTS) - 1  # everything except heidi's own post


@pytest.mark.parametrize(
    "params, status, code",
    [
        ({"user_id": 999}, 404, "user_not_found"),
        ({}, 422, "validation_error"),
        ({"user_id": "abc"}, 422, "validation_error"),
        ({"user_id": ALICE, "limit": 0}, 422, "validation_error"),
        ({"user_id": ALICE, "limit": 51}, 422, "validation_error"),
        ({"user_id": ALICE, "strategy": "random"}, 422, "validation_error"),
    ],
)
def test_feed_errors(client, params, status, code):
    response = client.get("/feed", params=params)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
