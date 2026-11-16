import pytest

from app.services.search import InvalidSearchError, build_index, search_posts
from tests.fakes import SAMPLE_POSTS, BagOfWordsEncoder, InMemoryPosts


@pytest.fixture
def encoder():
    return BagOfWordsEncoder()


@pytest.fixture
def index(encoder):
    return build_index(InMemoryPosts(SAMPLE_POSTS), encoder)


def test_build_index_encodes_every_post_once(index, encoder):
    assert len(index.posts) == len(SAMPLE_POSTS)
    assert index.vectors.shape == (len(SAMPLE_POSTS), 10)
    assert encoder.calls == [[p.content for p in SAMPLE_POSTS]]


def test_search_orders_by_score_with_id_tie_break(index, encoder):
    hits = search_posts("cheap dinner", 3, index, encoder)
    assert [h.post.id for h in hits] == [1, 4, 2]  # 1 and 4 tie; 2 is first of the zero-score rest
    assert hits[0].score == pytest.approx(hits[1].score)
    assert hits[0].score > hits[2].score


def test_search_respects_limit(index, encoder):
    assert len(search_posts("python", 1, index, encoder)) == 1
    assert len(search_posts("python", 20, index, encoder)) == len(SAMPLE_POSTS)


@pytest.mark.parametrize("query, limit", [("", 5), ("   ", 5), ("ok", 0), ("ok", 21)])
def test_search_rejects_invalid_input(index, encoder, query, limit):
    with pytest.raises(InvalidSearchError):
        search_posts(query, limit, index, encoder)


def test_search_on_empty_index(encoder):
    empty = build_index(InMemoryPosts([]), encoder)
    assert search_posts("anything", 5, empty, encoder) == []
