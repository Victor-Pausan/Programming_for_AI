"""Offline evaluation of the feed strategies: a time-split replay on our own database.

    python scripts/evaluate.py [--db instakill.db] [--cutoff ISO-date] [--seed 42] [--out reports/]

Protocol (details in docs/evaluation-protocol.md):

1. cut-off T (default: the moment by which 80 % of the likes had happened);
2. snapshot = copy of the database without any like, post or follow at or after T;
3. users with >= 3 likes before T and >= 1 like after T on a snapshot post;
4. for each user and strategy, the top 10 from the SAME service function GET /feed calls
   (``app.services.feed.get_feed``), on the snapshot, with now = T. ``popularity`` is a
   scorer that exists only here (it is not a GET /feed strategy);
5. NDCG@10 against the snapshot posts the user liked after T;
6. 95 % paired bootstrap intervals over users, fixed seed; slices by activity and taste.

Deterministic: the same database and arguments give byte-identical eval_results.csv and
baseline_table.md. Writes reports/eval_results.csv, reports/baseline_table.md and
reports/dashboard.html (the dashboard needs the ``eval`` extra: matplotlib).
"""
import argparse
import csv
import hashlib
import heapq
import io
import math
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):  # allow `python scripts/evaluate.py` without installing
    sys.path.insert(0, str(ROOT))

from app.db import database  # noqa: E402
from app.db.repository import SqliteFeedRepository  # noqa: E402
from app.ml.like_model import DEFAULT_MODEL_PATH, LikeModel, load_like_model  # noqa: E402
from app.services import feed as feed_service  # noqa: E402

K = 10
STRATEGIES = ("chronological", "popularity", "for_you", "learned")
BASELINES = ("chronological", "popularity", "for_you")
MIN_LIKES_BEFORE = 3
CUTOFF_QUANTILE = 0.8
BOOTSTRAP_SAMPLES = 2000
MIN_SLICE_USERS = 5
FRESH_DAYS = 365
ACTIVITY_GROUPS = (("new (<10)", 0, 10), ("casual (10-49)", 10, 50),
                   ("regular (50-199)", 50, 200), ("power (200+)", 200, math.inf))
TASTE_GROUPS = ("fresh taste", "old taste")


# --- time helpers ----------------------------------------------------------------

def to_sqlite(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def from_sqlite(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def parse_cutoff(value: str) -> datetime:
    ts = datetime.fromisoformat(value)
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# --- metric ----------------------------------------------------------------------

def ndcg_at_k(ranked: list[int], relevant: set[int], k: int = K) -> float:
    """DCG = sum(rel_i / log2(i + 2)) over the first k positions, divided by the ideal DCG."""
    if not relevant:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, post_id in enumerate(ranked[:k]) if post_id in relevant)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / ideal


def activity_group(n_likes_before: int) -> str:
    for name, low, high in ACTIVITY_GROUPS:
        if low <= n_likes_before < high:
            return name
    raise ValueError(n_likes_before)


# --- protocol steps ------------------------------------------------------------------

def default_cutoff(conn: sqlite3.Connection, quantile: float = CUTOFF_QUANTILE) -> datetime:
    """The first like time by which `quantile` of all likes had happened."""
    times = [r[0] for r in conn.execute('SELECT created_at FROM "like" ORDER BY created_at')]
    if not times:
        raise SystemExit("the database has no likes: seed it first (scripts/seed_movielens.py)")
    return from_sqlite(times[min(len(times) - 1, int(quantile * len(times)))])


def make_snapshot(source: Path, target: Path, cutoff: datetime) -> None:
    """Copy the database and delete every like, post and follow at or after the cut-off.

    Follows are derived from likes by the seeder (created at the moment of the like that
    triggered them), so dropping follows created at or after T is the same as re-deriving
    them from the snapshot's likes. tests/test_evaluate.py checks this equivalence.
    """
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
    t = to_sqlite(cutoff)
    with dst:
        dst.execute('DELETE FROM "like" WHERE created_at >= ? '
                    'OR post_id IN (SELECT id FROM post WHERE created_at >= ?)', (t, t))
        dst.execute("DELETE FROM follow WHERE created_at >= ?", (t,))
        dst.execute("DELETE FROM post WHERE created_at >= ?", (t,))
    dst.close()


@dataclass
class EvalUser:
    user_id: int
    likes_before: int
    relevant: set[int]
    fresh_share: float
    activity: str = ""
    taste: str = ""


def select_users(original: sqlite3.Connection, snapshot: sqlite3.Connection, cutoff: datetime) -> list[EvalUser]:
    t = to_sqlite(cutoff)
    likes_before = {r[0]: r[1] for r in snapshot.execute(
        'SELECT user_id, COUNT(*) FROM "like" GROUP BY user_id')}
    snapshot_posts = {r[0]: from_sqlite(r[1]) for r in snapshot.execute("SELECT id, created_at FROM post")}
    relevant = defaultdict(set)
    for user_id, post_id in original.execute(
            'SELECT user_id, post_id FROM "like" WHERE created_at >= ? ORDER BY user_id, post_id', (t,)):
        if post_id in snapshot_posts:
            relevant[user_id].add(post_id)
    fresh_since = cutoff - timedelta(days=FRESH_DAYS)
    users = []
    for user_id in sorted(relevant):
        n = likes_before.get(user_id, 0)
        if n < MIN_LIKES_BEFORE:
            continue
        rel = relevant[user_id]
        fresh = sum(snapshot_posts[p] >= fresh_since for p in rel) / len(rel)
        users.append(EvalUser(user_id, n, rel, fresh, activity_group(n),
                              TASTE_GROUPS[0] if fresh >= 0.5 else TASTE_GROUPS[1]))
    return users


def popularity_top_k(repository: SqliteFeedRepository, user_id: int, k: int = K) -> list[int]:
    """Evaluation-only baseline: most-liked snapshot posts among the same candidates."""
    candidates = repository.candidate_posts(user_id)
    counts = repository.like_counts([p.id for p in candidates])
    return [p.id for p in heapq.nsmallest(k, candidates, key=lambda p: (-counts.get(p.id, 0), p.id))]


def top_k(strategy: str, user_id: int, repository, now: datetime, model: LikeModel | None) -> list[int]:
    if strategy == "popularity":
        return popularity_top_k(repository, user_id)
    page = feed_service.get_feed(user_id, repository, now=now, limit=K,
                                 strategy=feed_service.FeedStrategy(strategy), like_model=model)
    return [item.post.id for item in page.items]


# --- statistics ------------------------------------------------------------------------

@dataclass
class Interval:
    mean: float
    low: float
    high: float
    n: int

    @property
    def verdict(self) -> str:
        return "wins" if self.low > 0 else "loses" if self.high < 0 else "unclear"


def paired_intervals(scores: dict[str, np.ndarray], rng: np.random.Generator,
                     samples: int = BOOTSTRAP_SAMPLES) -> dict[str, Interval]:
    """95 % percentile intervals of each mean, all from the SAME resampled users (paired)."""
    n = len(next(iter(scores.values())))
    idx = rng.integers(0, n, size=(samples, n)) if n else None
    out = {}
    for name, values in scores.items():
        if n == 0:
            out[name] = Interval(float("nan"), float("nan"), float("nan"), 0)
            continue
        means = values[idx].mean(axis=1)
        out[name] = Interval(float(values.mean()), float(np.percentile(means, 2.5)),
                             float(np.percentile(means, 97.5)), n)
    return out


@dataclass
class Evaluation:
    cutoff: datetime
    seed: int
    users: list[EvalUser]
    ndcg: dict[str, np.ndarray]  # strategy -> one value per user (same order as users)
    best_baseline: str = ""
    overall: dict[str, Interval] = field(default_factory=dict)
    slices: dict[str, dict[str, Interval]] = field(default_factory=dict)  # slice -> {strategy..., "diff"}
    metadata: dict[str, str] = field(default_factory=dict)


def summarize(ev: Evaluation) -> None:
    rng = np.random.default_rng(ev.seed)
    ev.best_baseline = max(BASELINES, key=lambda s: (float(ev.ndcg[s].mean()), s))
    diff = ev.ndcg["learned"] - ev.ndcg[ev.best_baseline]
    ev.overall = paired_intervals({**ev.ndcg, "diff": diff}, rng)
    for name in [g[0] for g in ACTIVITY_GROUPS] + list(TASTE_GROUPS):
        mask = np.array([name in (u.activity, u.taste) for u in ev.users], dtype=bool)
        ev.slices[name] = paired_intervals({**{s: v[mask] for s, v in ev.ndcg.items()}, "diff": diff[mask]}, rng)


# --- run ---------------------------------------------------------------------------------

def database_fingerprint(conn: sqlite3.Connection) -> str:
    """sha256 over the content of the four tables, independent of the file layout."""
    h = hashlib.sha256()
    for table, order in (("user", "id"), ("post", "id"), ('"like"', "user_id, post_id"),
                         ("follow", "follower_id, followee_id")):
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
            h.update(repr(tuple(row)).encode())
    return h.hexdigest()[:16]


def code_version() -> str:
    """Last commit that touched the evaluated code (stable when only reports/ change)."""
    try:
        return subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", "app", "scripts", "models", "pyproject.toml"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def evaluate(db: Path, cutoff: datetime | None = None, seed: int = 42,
             model: LikeModel | None = None) -> Evaluation:
    if model is None:
        model = load_like_model(DEFAULT_MODEL_PATH)
    with tempfile.TemporaryDirectory() as tmp:
        original = connect(db)
        try:
            cutoff = cutoff or default_cutoff(original)
            fingerprint = database_fingerprint(original)
            snapshot_path = Path(tmp) / "snapshot.db"
            make_snapshot(db, snapshot_path, cutoff)
            snapshot = connect(snapshot_path)
            try:
                users = select_users(original, snapshot, cutoff)
            finally:
                snapshot.close()
        finally:
            original.close()

        repository = SqliteFeedRepository(connect=lambda: connect(snapshot_path))
        ndcg = {s: np.array([ndcg_at_k(top_k(s, u.user_id, repository, cutoff, model), u.relevant)
                             for u in users]) for s in STRATEGIES}

    ev = Evaluation(cutoff=cutoff, seed=seed, users=users, ndcg=ndcg)
    ev.metadata = {
        "cut-off T": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": str(seed),
        "bootstrap resamples": str(BOOTSTRAP_SAMPLES),
        "users evaluated": str(len(users)),
        "relevant likes (after T, on snapshot posts)": str(sum(len(u.relevant) for u in users)),
        "database fingerprint (sha256/16)": fingerprint,
        "code version (git)": code_version(),
        "model": f"models/like_model.npz ({model.n_parameters} parameters)",
    }
    if users:
        summarize(ev)
    return ev


# --- reports -------------------------------------------------------------------------------

def results_csv(ev: Evaluation) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["user_id", "strategy", "ndcg_at_10", "n_relevant", "user_group"])
    for i, u in enumerate(ev.users):
        for s in STRATEGIES:
            writer.writerow([u.user_id, s, f"{ev.ndcg[s][i]:.6f}", len(u.relevant), u.activity])
    return buf.getvalue()


def fmt(iv: Interval) -> str:
    return "n/a" if iv.n == 0 else f"{iv.mean:.4f} [{iv.low:.4f}, {iv.high:.4f}]"


def baseline_table_md(ev: Evaluation) -> str:
    lines = ["# Feed evaluation: baseline table", "",
             "Time-split replay on our own database; protocol in `docs/evaluation-protocol.md`.",
             "NDCG@10 per user, mean over users, 95 % paired bootstrap interval over users.", ""]
    if not ev.users:
        return "\n".join(lines + ["No user qualifies for evaluation at this cut-off.", ""])
    lines += ["## Strategies", "", "| strategy | mean NDCG@10 [95 % CI] | users |", "|---|---|---|"]
    for s in STRATEGIES:
        note = " (best baseline)" if s == ev.best_baseline else ""
        lines.append(f"| `{s}`{note} | {fmt(ev.overall[s])} | {ev.overall[s].n} |")
    lines += ["", f"## `learned` minus the best baseline (`{ev.best_baseline}`)", "",
              "| slice | users | learned | " + ev.best_baseline + " | difference [95 % CI] | verdict |",
              "|---|---|---|---|---|---|"]
    rows = [("all users", ev.overall)] + list(ev.slices.items())
    for name, iv in rows:
        d = iv["diff"]
        verdict = "n/a" if d.n == 0 else d.verdict
        if 0 < d.n < MIN_SLICE_USERS:
            verdict += f" (only {d.n} user{'s' if d.n > 1 else ''}: not reliable)"
        lines.append(f"| {name} | {d.n} | {fmt(iv['learned'])} | {fmt(iv[ev.best_baseline])} | "
                     f"{fmt(d)} | {verdict} |")
    lines += ["", "Verdict: `wins` if the whole interval is above 0, `loses` if below 0, otherwise `unclear`. "
              f"Slices with fewer than {MIN_SLICE_USERS} users are flagged: their bootstrap interval is "
              "too narrow to mean anything.",
              "", "## Mean NDCG@10 per slice and strategy", "",
              "| slice | users | " + " | ".join(f"`{s}`" for s in STRATEGIES) + " |",
              "|---|---|" + "---|" * len(STRATEGIES)]
    for name, iv in ev.slices.items():
        lines.append(f"| {name} | {iv['diff'].n} | " + " | ".join(fmt(iv[s]) for s in STRATEGIES) + " |")
    lines += ["", "## Run metadata", "", "| key | value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in ev.metadata.items()]
    return "\n".join(lines) + "\n"


def write_reports(ev: Evaluation, out: Path, dashboard: bool = True) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (("eval_results.csv", results_csv(ev)), ("baseline_table.md", baseline_table_md(ev))):
        path = out / name
        path.write_bytes(text.encode("utf-8"))  # bytes: no platform newline translation
        written.append(path)
    if dashboard and ev.users:
        from scripts.eval_dashboard import dashboard_html  # matplotlib lives in the `eval` extra
        path = out / "dashboard.html"
        path.write_bytes(dashboard_html(ev).encode("utf-8"))
        written.append(path)
    return written


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Offline time-split evaluation of the feed strategies.")
    parser.add_argument("--db", type=Path, default=database.DB_PATH)
    parser.add_argument("--cutoff", type=parse_cutoff, default=None, help="ISO date/time, UTC if no offset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    if not args.db.exists():
        parser.error(f"{args.db} not found: seed it first (scripts/seed_movielens.py)")
    ev = evaluate(args.db, args.cutoff, args.seed)
    for path in write_reports(ev, args.out):
        print(f"wrote {path}")
    if ev.users:
        d = ev.overall["diff"]
        print(f"{len(ev.users)} users; learned - {ev.best_baseline} = {fmt(d)} -> {d.verdict}")


if __name__ == "__main__":
    main()
