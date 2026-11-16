import numpy as np
import pytest

from app.search.retrieval import ScoredId, cosine_similarity, rank, top_k


def test_cosine_basic_and_scale_invariant():
    scores = cosine_similarity([1.0, 0.0], [[1.0, 0.0], [0.0, 1.0], [0.5, 0.0], [-2.0, 0.0]])
    assert np.allclose(scores, [1.0, 0.0, 1.0, -1.0])


def test_cosine_zero_vectors_are_safe():
    assert np.allclose(cosine_similarity([1.0, 0.0], [[0.0, 0.0]]), [0.0])
    scores = cosine_similarity([0.0, 0.0], [[1.0, 0.0], [0.0, 0.0]])
    assert np.isfinite(scores).all() and np.allclose(scores, 0.0)


def test_cosine_empty_matrix_and_dimension_mismatch():
    assert cosine_similarity([1.0, 0.0], np.zeros((0, 2))).shape == (0,)
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0, 0.0], [[1.0, 0.0]])


def test_top_k_orders_by_score_then_ascending_id():
    hits = top_k([0.7, 0.9, 0.9, 0.1], [7, 5, 2, 1], k=3)
    assert hits == [ScoredId(2, 0.9), ScoredId(5, 0.9), ScoredId(7, 0.7)]


@pytest.mark.parametrize("k, expected", [(0, 0), (2, 2), (10, 3)])
def test_top_k_never_returns_more_than_k_or_available(k, expected):
    assert len(top_k([0.3, 0.2, 0.1], [1, 2, 3], k)) == expected


def test_rank_combines_cosine_and_top_k():
    hits = rank([1.0, 0.0], [[0.0, 1.0], [2.0, 0.0], [1.0, 0.0]], [10, 30, 20], k=2)
    assert [h.post_id for h in hits] == [20, 30]
    assert all(h.score == pytest.approx(1.0) for h in hits)
