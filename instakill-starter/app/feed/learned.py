"""Learned feed strategy: the six Lab 05 signals + the trained like model.

Pure: receives ``now`` and all counts as arguments, performs no I/O, never
mutates its inputs. The signal formulas follow the notebook exactly, with the
constants read from the model file. The only InstaKill adaptation: posts have
no genres, so the post's author plays the role of its single "genre".

    freshness  = 0.5 ** (age_days / half_life_days)
    affinity   = likes_by_user_on_author / likes_by_user                 (0 if the user liked nothing)
    popularity = recent_likes(post) / max(max recent_likes over all posts, 1)   (recent = last popularity_days)
    activity   = min(1, log1p(likes_by_user) / log1p(activity_cap))
    lifetime   = log1p(likes(post)) / log1p(max(max likes over all posts, 1))
    age        = min(1, age_days / age_cap_days)
"""
import heapq
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from numpy.typing import NDArray

from app.domain.models import Post
from app.feed.ranking import RankedPost
from app.ml.like_model import LikeModel, predict

DAY_SECONDS = 86_400


@dataclass(frozen=True)
class LearnedSignals:
    user_like_count: int = 0
    liked_author_counts: Mapping[int, int] = field(default_factory=dict)  # author -> likes by the user
    lifetime_likes: Mapping[int, int] = field(default_factory=dict)  # post -> likes ever (ALL posts)
    recent_likes: Mapping[int, int] = field(default_factory=dict)  # post -> likes in window (ALL posts)


def learned_features(posts: list[Post], signals: LearnedSignals, now: datetime,
                     model: LikeModel) -> NDArray[np.float64]:
    """(len(posts), 6) matrix of raw signals, each in [0, 1]."""
    if not posts:
        return np.zeros((0, 6))
    age_days = np.array([max(0.0, (now - p.created_at).total_seconds()) / DAY_SECONDS for p in posts])
    freshness = 0.5 ** (age_days / model.half_life_days)

    total = signals.user_like_count
    author_likes = np.array([signals.liked_author_counts.get(p.user_id, 0) for p in posts], dtype=float)
    affinity = author_likes / total if total > 0 else np.zeros(len(posts))

    recent = np.array([signals.recent_likes.get(p.id, 0) for p in posts], dtype=float)
    popularity = recent / max(max(signals.recent_likes.values(), default=0), 1)

    activity = np.full(len(posts), min(1.0, np.log1p(total) / np.log1p(model.activity_cap)))

    lifetime_counts = np.array([signals.lifetime_likes.get(p.id, 0) for p in posts], dtype=float)
    lifetime = np.log1p(lifetime_counts) / np.log1p(max(max(signals.lifetime_likes.values(), default=0), 1))

    age = np.minimum(1.0, age_days / model.age_cap_days)
    return np.column_stack([freshness, affinity, popularity, activity, lifetime, age])


def rank_learned(candidates: Iterable[Post], signals: LearnedSignals, now: datetime,
                 model: LikeModel, limit: int) -> list[RankedPost]:
    """Top ``limit`` posts by predicted P(like) descending; ties by ascending post id.

    O(C·6·H) for the forward pass plus O(C log k) for the heap.
    """
    if limit <= 0:
        return []
    posts = list(candidates)
    if not posts:
        return []
    probabilities = predict(model, learned_features(posts, signals, now, model))
    best = heapq.nsmallest(limit, zip(probabilities.tolist(), posts),
                           key=lambda pair: (-pair[0], pair[1].id))
    return [RankedPost(post=p, score=s) for s, p in best]
