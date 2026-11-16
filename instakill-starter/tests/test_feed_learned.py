import copy
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.domain.models import Post
from app.feed.learned import LearnedSignals, learned_features, rank_learned
from app.ml.like_model import EXPECTED_FEATURES, LikeModel, predict

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def tiny_model(w2_sign: float = 1.0) -> LikeModel:
    """Hand-made model: hidden unit j copies standardized signal j (identity W1)."""
    return LikeModel(
        W1=np.eye(6, 6), b1=np.zeros(6),
        W2=np.full((6, 1), w2_sign), b2=np.zeros(1),
        mu=np.zeros(6), sd=np.ones(6),
        features=EXPECTED_FEATURES,
        half_life_days=1.0, popularity_days=7.0, activity_cap=500.0, age_cap_days=10.0,
    )


def post(post_id, author, days_ago):
    return Post(id=post_id, user_id=author, content=f"p{post_id}", created_at=NOW - timedelta(days=days_ago))


POSTS = [post(1, 2, 0), post(2, 3, 1), post(3, 3, 1), post(4, 4, 5)]
SIGNALS = LearnedSignals(
    user_like_count=4,
    liked_author_counts={3: 3, 4: 1},
    lifetime_likes={1: 1, 4: 9, 99: 3},  # post 99 is not a candidate but counts for the maximum
    recent_likes={1: 1, 99: 2},
)


def test_signal_formulas_match_the_notebook():
    f = learned_features(POSTS, SIGNALS, NOW, tiny_model())
    assert f.shape == (4, 6) and f.min() >= 0 and f.max() <= 1
    fresh, aff, pop, act, life, age = f.T
    assert fresh[0] == 1.0 and fresh[1] == pytest.approx(0.5)            # half-life 1 day
    assert aff.tolist() == pytest.approx([0.0, 0.75, 0.75, 0.25])         # author share of the user's likes
    assert pop.tolist() == pytest.approx([0.5, 0.0, 0.0, 0.0])            # 1 / max recent (2, from post 99)
    assert act == pytest.approx(np.log1p(4) / np.log1p(500))
    assert life[3] == 1.0 and life[0] == pytest.approx(np.log1p(1) / np.log1p(9))
    assert age.tolist() == pytest.approx([0.0, 0.1, 0.1, 0.5])


def test_cold_start_user_has_zero_affinity_and_activity():
    f = learned_features(POSTS, LearnedSignals(), NOW, tiny_model())
    assert not f[:, 1].any() and not f[:, 3].any()


def test_rank_learned_orders_by_probability_with_id_tie_break():
    ranked = rank_learned(POSTS, SIGNALS, NOW, tiny_model(), limit=4)
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < s < 1 for s in scores)
    ids = [r.post.id for r in ranked]
    assert ids.index(2) == ids.index(3) - 1  # posts 2 and 3 have identical signals -> lower id first


def test_rank_learned_is_deterministic_and_does_not_mutate():
    posts, signals = list(POSTS), copy.deepcopy(SIGNALS)
    a = rank_learned(posts, signals, NOW, tiny_model(), limit=3)
    b = rank_learned(list(reversed(POSTS)), SIGNALS, NOW, tiny_model(), limit=3)
    assert a == b and len(a) == 3
    assert posts == POSTS and signals == SIGNALS


def test_rank_learned_limits():
    assert rank_learned(POSTS, SIGNALS, NOW, tiny_model(), limit=0) == []
    assert rank_learned([], SIGNALS, NOW, tiny_model(), limit=5) == []


def test_predict_is_a_sigmoid_of_the_network():
    x = np.zeros((1, 6))
    assert predict(tiny_model(), x)[0] == pytest.approx(0.5)  # all-zero input -> logit 0
    assert predict(tiny_model(), np.ones((1, 6)))[0] > 0.5 > predict(tiny_model(-1.0), np.ones((1, 6)))[0]


# --- the real trained model (models/like_model.npz, exported by Lab 05) ---------

GOLDEN_ROWS = [  # printed by the notebook's export cell: signals -> P(like)
    ([0.020159, 0.15, 0.0, 0.222999, 0.518748, 0.675891], 0.279697),
    ([0.387413, 0.1, 0.0, 0.222999, 0.0, 0.164167], 0.013497),
    ([0.023264, 0.1, 0.0, 0.222999, 0.459336, 0.651094], 0.16609),
]


def test_trained_model_reproduces_notebook_golden_rows():
    from app.ml.like_model import DEFAULT_MODEL_PATH, load_like_model

    model = load_like_model(DEFAULT_MODEL_PATH)
    assert model.n_parameters == 129
    assert (model.half_life_days, model.popularity_days) == (3 * 365, 365)
    x = np.array([row for row, _ in GOLDEN_ROWS])
    assert predict(model, x) == pytest.approx([p for _, p in GOLDEN_ROWS], abs=1e-5)
