"""Pure feed ranking.

``rank_feed`` receives everything it needs as arguments, including ``now``. It
never reads the clock or the database, and never mutates its inputs. Same
input, same output.

Score of a candidate post p for the requesting user u:

    score = w_f * freshness + w_a * affinity + w_p * popularity      (each signal in [0, 1])

    freshness  = 0.5 ** (age_hours / half_life_hours)        1.0 when new, 0.5 after one half-life
    affinity   = 0.6 * [u follows author(p)]
               + 0.4 * likes_by_u_on_author(p) / max_author_likes_by_u
    popularity = log1p(likes(p)) / log1p(max likes over the candidates)
"""
import heapq
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models import Post

FOLLOW_SHARE = 0.6  # part of affinity that comes from following the author
LIKED_AUTHOR_SHARE = 1.0 - FOLLOW_SHARE


@dataclass(frozen=True, slots=True)
class FeedWeights:
    """Default weights for InstaKill (see README "Feed" for the justification)."""

    freshness: float = 1.0
    affinity: float = 1.5
    popularity: float = 1.0
    half_life_hours: float = 24.0

    def __post_init__(self) -> None:
        if min(self.freshness, self.affinity, self.popularity) < 0:
            raise ValueError("weights must be non-negative")
        if self.half_life_hours <= 0:
            raise ValueError("half_life_hours must be positive")


@dataclass(frozen=True)
class FeedSignals:
    """Per-request facts about the user and the candidates, precomputed by the service."""

    followed_authors: frozenset[int] = frozenset()
    liked_author_counts: Mapping[int, int] = field(default_factory=dict)  # author_id -> likes by user
    like_counts: Mapping[int, int] = field(default_factory=dict)  # post_id -> total likes


@dataclass(frozen=True, slots=True)
class RankedPost:
    post: Post
    score: float


def freshness(created_at: datetime, now: datetime, half_life_hours: float) -> float:
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)  # future posts count as brand new
    return 0.5 ** (age_hours / half_life_hours)


def affinity(author_id: int, signals: FeedSignals) -> float:
    follows = 1.0 if author_id in signals.followed_authors else 0.0
    max_liked = max(signals.liked_author_counts.values(), default=0)
    liked = signals.liked_author_counts.get(author_id, 0) / max_liked if max_liked else 0.0
    return FOLLOW_SHARE * follows + LIKED_AUTHOR_SHARE * liked


def popularity(post_id: int, signals: FeedSignals, max_log_likes: float) -> float:
    if max_log_likes == 0:
        return 0.0
    return math.log1p(signals.like_counts.get(post_id, 0)) / max_log_likes


def score_post(post: Post, signals: FeedSignals, now: datetime, weights: FeedWeights,
               max_log_likes: float) -> float:
    return (
        weights.freshness * freshness(post.created_at, now, weights.half_life_hours)
        + weights.affinity * affinity(post.user_id, signals)
        + weights.popularity * popularity(post.id, signals, max_log_likes)
    )


def rank_feed(
    candidates: Iterable[Post],
    signals: FeedSignals,
    now: datetime,
    weights: FeedWeights,
    limit: int,
) -> list[RankedPost]:
    """Top ``limit`` candidates by descending score; ties by ascending post id.

    O(C log k) for C candidates and k = limit: every candidate is scored once and
    ``heapq.nsmallest`` keeps only the best k.
    """
    if limit <= 0:
        return []
    posts = list(candidates)  # local copy: the caller's iterable is never modified
    max_log_likes = math.log1p(max((signals.like_counts.get(p.id, 0) for p in posts), default=0))
    scored = ((score_post(p, signals, now, weights, max_log_likes), p) for p in posts)
    best = heapq.nsmallest(limit, scored, key=lambda pair: (-pair[0], pair[1].id))
    return [RankedPost(post=p, score=s) for s, p in best]


def chronological(candidates: Iterable[Post], limit: int) -> list[Post]:
    """Newest ``created_at`` first; ties by ascending post id. O(C log k)."""
    if limit <= 0:
        return []
    return heapq.nsmallest(limit, candidates, key=lambda p: (-p.created_at.timestamp(), p.id))
