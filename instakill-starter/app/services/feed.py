"""Feed use case: loads candidates and signals through the repository, then ranks them.

No HTTP and no SQL here. ``now`` is passed in by the caller, so the service is
deterministic in tests.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.db.repository import FeedReader
from app.domain.models import Post
from app.feed.ranking import FeedSignals, FeedWeights, chronological, rank_feed

MIN_LIMIT = 1
MAX_LIMIT = 50
DEFAULT_LIMIT = 20


class FeedStrategy(StrEnum):
    FOR_YOU = "for_you"
    CHRONOLOGICAL = "chronological"


class FeedError(Exception):
    """Base class for expected feed failures."""


class InvalidFeedRequestError(FeedError, ValueError):
    pass


class UserNotFoundError(FeedError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"user {user_id} does not exist")
        self.user_id = user_id


@dataclass(frozen=True, slots=True)
class FeedItem:
    post: Post
    score: float | None  # None for the chronological strategy


@dataclass(frozen=True, slots=True)
class FeedPage:
    user_id: int
    strategy: FeedStrategy
    items: list[FeedItem]


def get_feed(
    user_id: int,
    repository: FeedReader,
    now: datetime,
    limit: int = DEFAULT_LIMIT,
    strategy: FeedStrategy = FeedStrategy.FOR_YOU,
    weights: FeedWeights = FeedWeights(),
) -> FeedPage:
    """Build the feed of ``user_id``.

    Candidates: every post except the user's own and the ones they already liked.
    Followed authors are not a hard filter. They raise the affinity signal, so a user
    who follows nobody (cold start) still gets a feed ranked by freshness and popularity.

    Raises:
        InvalidFeedRequestError: limit outside [MIN_LIMIT, MAX_LIMIT] or unknown strategy.
        UserNotFoundError: no such user.
    """
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        raise InvalidFeedRequestError(f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}")
    try:
        strategy = FeedStrategy(strategy)
    except ValueError as exc:
        raise InvalidFeedRequestError(f"unknown strategy {strategy!r}") from exc
    if repository.get_user(user_id) is None:
        raise UserNotFoundError(user_id)

    candidates = repository.candidate_posts(user_id)

    if strategy is FeedStrategy.CHRONOLOGICAL:
        items = [FeedItem(post=p, score=None) for p in chronological(candidates, limit)]
    else:
        signals = FeedSignals(
            followed_authors=frozenset(repository.followed_authors(user_id)),
            liked_author_counts=repository.liked_author_counts(user_id),
            like_counts=repository.like_counts([p.id for p in candidates]),
        )
        items = [FeedItem(post=r.post, score=r.score)
                 for r in rank_feed(candidates, signals, now, weights, limit)]
    return FeedPage(user_id=user_id, strategy=strategy, items=items)
