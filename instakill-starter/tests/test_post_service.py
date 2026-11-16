from datetime import datetime

import pytest

from app.domain.models import Post, User
from app.services.posts import (
    MAX_CONTENT_LENGTH,
    AuthorNotFoundError,
    InvalidPostError,
    PublishPostRequest,
    publish_post,
)


class FakeStore:
    """In-memory PostStore used only by tests."""

    def __init__(self, users: list[User]) -> None:
        self.users = {u.id: u for u in users}
        self.posts: list[Post] = []

    def get_user(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    def add_post(self, post: Post) -> Post:
        saved = post.model_copy(
            update={"id": len(self.posts) + 1, "created_at": datetime(2026, 1, 1)}
        )
        self.posts.append(saved)
        return saved


@pytest.fixture
def store() -> FakeStore:
    return FakeStore([User(id=1, username="alice")])


def test_publish_post_returns_stored_post(store):
    post = publish_post(PublishPostRequest(author_id=1, content="  hello  "), store)

    assert post.id == 1
    assert post.user_id == 1
    assert post.content == "hello"
    assert post.created_at is not None
    assert store.posts == [post]


@pytest.mark.parametrize("content", ["", "   ", "x" * (MAX_CONTENT_LENGTH + 1)])
def test_publish_post_rejects_invalid_content(store, content):
    with pytest.raises(InvalidPostError):
        publish_post(PublishPostRequest(author_id=1, content=content), store)
    assert store.posts == []


def test_publish_post_accepts_max_length(store):
    post = publish_post(PublishPostRequest(author_id=1, content="x" * MAX_CONTENT_LENGTH), store)
    assert len(post.content) == MAX_CONTENT_LENGTH


def test_publish_post_unknown_author(store):
    with pytest.raises(AuthorNotFoundError) as exc:
        publish_post(PublishPostRequest(author_id=99, content="hi"), store)
    assert exc.value.author_id == 99
    assert store.posts == []
