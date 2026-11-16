"""Post publishing use case.

Public operation: :func:`publish_post`. It validates a publish request against
the application's rules and hands a domain :class:`~app.domain.models.Post` to
whatever store implements :class:`PostStore`. The future ``POST /posts``
endpoint (see ``docs/api-contract.md``) will be a thin adapter around it.
"""
from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Post, User

MAX_CONTENT_LENGTH = 2200


@dataclass(frozen=True, slots=True)
class PublishPostRequest:
    """Input of the use case, independent of any transport format."""

    author_id: int
    content: str


class PostServiceError(Exception):
    """Base class for expected, caller-facing failures of the post service."""


class InvalidPostError(PostServiceError):
    """The request breaks a content rule (empty, too long, ...)."""


class AuthorNotFoundError(PostServiceError):
    """The referenced author does not exist."""

    def __init__(self, author_id: int) -> None:
        super().__init__(f"user {author_id} does not exist")
        self.author_id = author_id


class PostStore(Protocol):
    """Persistence port the service depends on; implemented later in ``app.db``."""

    def get_user(self, user_id: int) -> User | None: ...

    def add_post(self, post: Post) -> Post:
        """Persist ``post`` and return it with ``id`` and ``created_at`` set."""
        ...


def publish_post(request: PublishPostRequest, store: PostStore) -> Post:
    """Publish a new post for an existing user.

    Content is stripped of surrounding whitespace before validation and storage.

    Raises:
        InvalidPostError: content is empty/blank or longer than MAX_CONTENT_LENGTH.
        AuthorNotFoundError: ``request.author_id`` does not match a user.
    """
    content = request.content.strip()
    if not content:
        raise InvalidPostError("content must not be empty")
    if len(content) > MAX_CONTENT_LENGTH:
        raise InvalidPostError(
            f"content must be at most {MAX_CONTENT_LENGTH} characters (got {len(content)})"
        )

    if store.get_user(request.author_id) is None:
        raise AuthorNotFoundError(request.author_id)

    return store.add_post(Post(user_id=request.author_id, content=content))
