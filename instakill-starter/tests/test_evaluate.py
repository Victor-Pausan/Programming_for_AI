"""Tests for scripts/evaluate.py. Fixture databases live in tmp_path, never in instakill.db."""
import math
import random
import sqlite3
from datetime import UTC, datetime

import pytest

import app.services.feed as feed_service
from scripts import evaluate as ev_mod
from scripts.evaluate import (
    STRATEGIES,
    connect,
    default_cutoff,
    evaluate,
    make_snapshot,
    ndcg_at_k,
    results_csv,
    write_reports,
)
from scripts.seed_movielens import build, derive_follows, write

START = 1_400_000_000  # 2014-05-13
DAY = 86_400


def synthetic_ratings(seed: int = 7):
    """30 users rating 40 movies over 200 days; the same seed gives the same ratings."""
    rng = random.Random(seed)
    ratings = []
    for user in range(1, 31):
        for movie in rng.sample(range(1, 41), 18):
            ts = START + rng.randrange(0, 200 * DAY)
            ratings.append((user, movie, rng.choice([2.0, 3.0, 4.0, 4.5, 5.0]), ts))
    movies = {m: (f"Movie {m} (2000)", "Drama|Comedy" if m % 2 else "Action") for m in range(1, 41)}
    return ratings, movies


@pytest.fixture
def fixture_db(tmp_path):
    path = tmp_path / "fixture.db"
    write(path, *build(*synthetic_ratings()))
    return path


# --- metric -----------------------------------------------------------------------------

def test_ndcg_no_relevant_post_in_ranking():
    assert ndcg_at_k([1, 2, 3], {9}) == 0.0
    assert ndcg_at_k([1, 2, 3], set()) == 0.0


def test_ndcg_all_relevant_first_is_perfect():
    assert ndcg_at_k([5, 6, 1, 2], {5, 6}) == pytest.approx(1.0)
    assert ndcg_at_k(list(range(10)), set(range(15))) == pytest.approx(1.0)  # more relevant than k


def test_ndcg_one_relevant_post_at_position_3():
    # position 3 means index i = 3 -> gain 1 / log2(5); ideal for one relevant post = 1
    assert ndcg_at_k([10, 11, 12, 7, 13], {7}) == pytest.approx(1 / math.log2(5))


def test_ndcg_only_first_ten_positions_count():
    assert ndcg_at_k(list(range(20)), {15}) == 0.0


# --- protocol -----------------------------------------------------------------------------

def test_snapshot_has_nothing_at_or_after_cutoff(fixture_db, tmp_path):
    cutoff = default_cutoff(connect(fixture_db))
    snap = tmp_path / "snap.db"
    make_snapshot(fixture_db, snap, cutoff)
    t = ev_mod.to_sqlite(cutoff)
    conn = sqlite3.connect(snap)
    for table in ('"like"', "post", "follow"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE created_at >= ?", (t,)).fetchone()[0] == 0
    orphan_likes = conn.execute('SELECT COUNT(*) FROM "like" WHERE post_id NOT IN (SELECT id FROM post)')
    assert orphan_likes.fetchone()[0] == 0
    original = sqlite3.connect(fixture_db)
    assert original.execute('SELECT COUNT(*) FROM "like" WHERE created_at >= ?', (t,)).fetchone()[0] > 0


def test_snapshot_follows_equal_follows_rederived_from_snapshot_likes(fixture_db, tmp_path):
    cutoff = default_cutoff(connect(fixture_db))
    snap = tmp_path / "snap.db"
    make_snapshot(fixture_db, snap, cutoff)
    conn = sqlite3.connect(snap)
    authors = dict(conn.execute("SELECT id, user_id FROM post"))
    likes = conn.execute('SELECT user_id, post_id, created_at FROM "like" ORDER BY created_at, user_id, post_id')
    rederived = {(f, t) for f, t, _ in derive_follows(likes.fetchall(), authors)}
    stored = set(conn.execute("SELECT follower_id, followee_id FROM follow"))
    assert stored == rederived


def test_users_meet_the_inclusion_rule(fixture_db):
    result = evaluate(fixture_db, seed=1)
    assert result.users, "the fixture must produce evaluation users"
    for u in result.users:
        assert u.likes_before >= 3 and len(u.relevant) >= 1


def test_two_runs_give_identical_reports(fixture_db, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_reports(evaluate(fixture_db, seed=42), a, dashboard=False)
    write_reports(evaluate(fixture_db, seed=42), b, dashboard=False)
    for name in ("eval_results.csv", "baseline_table.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_results_csv_shape(fixture_db):
    result = evaluate(fixture_db, seed=42)
    lines = results_csv(result).splitlines()
    assert lines[0] == "user_id,strategy,ndcg_at_10,n_relevant,user_group"
    assert len(lines) == 1 + len(result.users) * len(STRATEGIES)


def test_script_uses_the_feed_endpoint_service_function(fixture_db, monkeypatch):
    calls = []
    real = feed_service.get_feed

    def spy(user_id, repository, now, **kwargs):
        calls.append((user_id, kwargs["strategy"].value, now))
        return real(user_id, repository, now, **kwargs)

    monkeypatch.setattr(feed_service, "get_feed", spy)
    cutoff = datetime(2014, 10, 1, tzinfo=UTC)
    result = evaluate(fixture_db, cutoff=cutoff, seed=42)
    api_strategies = {"chronological", "for_you", "learned"}  # popularity is evaluation-only
    assert len(calls) == len(result.users) * len(api_strategies)
    assert {s for _, s, _ in calls} == api_strategies
    assert all(now == cutoff for _, _, now in calls)


def test_dashboard_is_self_contained(fixture_db, tmp_path):
    pytest.importorskip("matplotlib")
    paths = write_reports(evaluate(fixture_db, seed=42), tmp_path, dashboard=True)
    page = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
    assert tmp_path / "dashboard.html" in paths
    assert page.count("data:image/png;base64,") >= 3
    assert "<script" not in page and "http://" not in page and "https://" not in page
