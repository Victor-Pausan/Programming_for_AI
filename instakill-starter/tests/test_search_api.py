import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import SAMPLE_POSTS, BagOfWordsEncoder, InMemoryPosts


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.database.DB_PATH", tmp_path / "test.db")
    app = create_app(encoder=BagOfWordsEncoder(), repository=InMemoryPosts(SAMPLE_POSTS))
    with TestClient(app) as c:  # runs lifespan -> builds the index
        yield c


def test_search_returns_ranked_results(client):
    response = client.get("/search", params={"q": "cheap dinner", "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "cheap dinner"
    assert [r["post_id"] for r in body["results"]] == [1, 4]
    first = body["results"][0]
    assert set(first) == {"post_id", "user_id", "content", "score"}
    assert isinstance(first["score"], float)


def test_search_default_limit(client):
    body = client.get("/search", params={"q": "jazz"}).json()
    assert len(body["results"]) == len(SAMPLE_POSTS)  # default 10 > 6 posts
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "params, code",
    [
        ({}, "validation_error"),
        ({"q": ""}, "validation_error"),
        ({"q": "   "}, "invalid_query"),
        ({"q": "jazz", "limit": 0}, "validation_error"),
        ({"q": "jazz", "limit": 21}, "validation_error"),
        ({"q": "jazz", "limit": "ten"}, "validation_error"),
    ],
)
def test_search_client_errors(client, params, code):
    response = client.get("/search", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"]


def test_health_still_ok(client):
    assert client.get("/health").json() == {"status": "ok"}
