import copy
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models import Post
from app.feed.ranking import (
    FeedSignals,
    FeedWeights,
    affinity,
    chronological,
    freshness,
    rank_feed,
)

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def post(post_id: int, author: int, hours_ago: float) -> Post:
    return Post(id=post_id, user_id=author, content=f"post {post_id}",
                created_at=NOW - timedelta(hours=hours_ago))


CANDIDATES = [
    post(1, author=2, hours_ago=1),    # fresh, followed author
    post(2, author=3, hours_ago=1),    # fresh, unknown author
    post(3, author=4, hours_ago=48),   # old but very popular
    post(4, author=3, hours_ago=1),    # identical to post 2 -> tie
    post(5, author=5, hours_ago=200),  # old, unpopular, unknown
]
SIGNALS = FeedSignals(
    followed_authors=frozenset({2}),
    liked_author_counts={2: 3, 4: 1},
    like_counts={3: 9, 1: 1},
)


def ids(ranked):
    return [r.post.id for r in ranked]


def test_signals_are_in_unit_range_and_behave():
    assert freshness(NOW, NOW, 24) == 1.0
    assert freshness(NOW - timedelta(hours=24), NOW, 24) == pytest.approx(0.5)
    assert freshness(NOW + timedelta(hours=5), NOW, 24) == 1.0  # clock skew: no score above 1
    assert affinity(2, SIGNALS) == pytest.approx(1.0)  # followed + most-liked author
    assert affinity(4, SIGNALS) == pytest.approx(0.4 / 3)
    assert affinity(99, SIGNALS) == 0.0
    assert affinity(2, FeedSignals()) == 0.0  # cold start


def test_rank_feed_orders_by_descending_score():
    ranked = rank_feed(CANDIDATES, SIGNALS, NOW, FeedWeights(), limit=5)
    assert ids(ranked)[0] == 1  # fresh + followed + liked author
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ids(ranked)[-1] == 5


def test_rank_feed_ties_break_by_ascending_post_id():
    ranked = rank_feed(list(reversed(CANDIDATES)), SIGNALS, NOW, FeedWeights(), limit=5)
    by_id = {r.post.id: r.score for r in ranked}
    assert by_id[2] == by_id[4]
    assert ids(ranked).index(2) == ids(ranked).index(4) - 1


def test_rank_feed_respects_limit():
    assert len(rank_feed(CANDIDATES, SIGNALS, NOW, FeedWeights(), limit=2)) == 2
    assert len(rank_feed(CANDIDATES, SIGNALS, NOW, FeedWeights(), limit=50)) == len(CANDIDATES)
    assert rank_feed(CANDIDATES, SIGNALS, NOW, FeedWeights(), limit=0) == []
    assert rank_feed([], SIGNALS, NOW, FeedWeights(), limit=5) == []


def test_rank_feed_is_deterministic_regardless_of_input_order():
    a = rank_feed(CANDIDATES, SIGNALS, NOW, FeedWeights(), limit=5)
    b = rank_feed(list(reversed(CANDIDATES)), SIGNALS, NOW, FeedWeights(), limit=5)
    c = rank_feed(iter(CANDIDATES), SIGNALS, NOW, FeedWeights(), limit=5)  # works on a one-shot iterator
    assert a == b == c


def test_rank_feed_does_not_mutate_inputs():
    candidates = list(CANDIDATES)
    signals = FeedSignals(
        followed_authors=frozenset({2}),
        liked_author_counts={2: 3, 4: 1},
        like_counts={3: 9, 1: 1},
    )
    before = (copy.deepcopy(candidates), copy.deepcopy(signals))
    rank_feed(candidates, signals, NOW, FeedWeights(), limit=3)
    assert (candidates, signals) == before


def test_weights_change_the_order():
    popular_first = rank_feed(CANDIDATES, SIGNALS, NOW,
                              FeedWeights(freshness=0, affinity=0, popularity=1), limit=1)
    assert ids(popular_first) == [3]


def test_cold_start_user_still_gets_a_feed():
    ranked = rank_feed(CANDIDATES, FeedSignals(like_counts={3: 9}), NOW, FeedWeights(), limit=5)
    assert len(ranked) == 5  # ranked by freshness + popularity only


def test_negative_weights_rejected():
    with pytest.raises(ValueError):
        FeedWeights(affinity=-1)


def test_chronological_newest_first_with_id_tie_break():
    assert [p.id for p in chronological(CANDIDATES, 5)] == [1, 2, 4, 3, 5]
    assert [p.id for p in chronological(CANDIDATES, 2)] == [1, 2]
