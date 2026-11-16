# Evaluation protocol: offline time-split replay of the feed

Implemented by `scripts/evaluate.py`. Results are in `reports/baseline_table.md`, `reports/eval_results.csv` and
`reports/dashboard.html`.

**Question.** On our own data, which feed strategy puts the posts a user is going to like into their top 10, by how
much, for which users, and how sure are we? We compare four systems:
- `chronological`, `for_you` and `learned`: the strategies of `GET /feed`;
- `popularity`: the most-liked posts among the same candidates. This scorer exists only inside the evaluation script.

**Data.** The database is seeded from MovieLens `latest-small` by `scripts/seed_movielens.py`. A rating ≥ 4 becomes a
like at the rating's timestamp. A movie becomes a post, created when anybody first rated it, and its author is that
first rater; the author's own rating is not stored as a like. A follow is created at the moment a user likes a 3rd post
by the same author. That gives 610 users, 9,724 posts, 44,481 likes and 4,310 follows.

**Cut-off and snapshot.** The cut-off `T` defaults to the time of the like at the 80 % position of all likes,
2016-02-09 20:36:25 UTC on our data (`--cutoff` overrides it). The script copies the database to a temporary file. From
the copy it deletes every like, post and follow created at or after `T`, and every like on a deleted post. Follows are
derived from likes and created at the moment of the triggering like. Dropping follows at or after `T` therefore gives
exactly the follows that the snapshot's own likes would derive; `tests/test_evaluate.py` checks this equality. Nothing
in the snapshot depends on data from after `T`.

**Users.** We evaluate every user with at least 3 likes before `T` and at least 1 like after `T` on a post that exists
in the snapshot: 25 users on our data. MovieLens users rate in bursts, so few users are active on both sides of the
cut-off. This small number is the main reason the intervals are wide.

**Candidates.** For every strategy, the candidates are exactly what `GET /feed` would consider on the snapshot: every
post except the user's own and the ones the user already liked before `T`. The script calls the same service function
as the endpoint, `app.services.feed.get_feed`, with `now = T` and `limit = 10`. It does not re-implement any strategy,
so we evaluate the product, not a copy of it. A test counts these calls. `popularity` uses the same candidates through
the same repository, and ranks them by snapshot like count (ties: lower post id).

**Relevance.** A user's relevant posts are the snapshot posts that the user liked at or after `T`. There are 633 such
likes over the 25 users. A post created after `T` cannot be recommended at `T`, so it is not counted as a miss.

**Metric.** NDCG@10 with several relevant posts: `DCG = Σ rel_i / log2(i + 2)` over the 10 returned positions
(`i = 0..9`, `rel_i = 1` for a relevant post), divided by the DCG of a perfect top 10, i.e. all relevant posts first.
That gives one number per user, between 0 and 1, and we report the mean over users. These numbers are **not
comparable** to the lab's: there, each moment hides one like among 99 random items; here, a strategy ranks the whole
candidate set (about 7,800 posts) and every later like counts.

**Intervals.** We use a 95 % paired percentile bootstrap over users: 2,000 resamples, seed 42 (`--seed`). In every
resample, the same users are drawn for every strategy. This gives an interval for each strategy's mean, and for
`learned` minus the best baseline. The best baseline is the one of `chronological`, `popularity` and `for_you` with the
highest overall mean; on our data it is `popularity`. The verdict is `wins` if the whole interval of the difference is
above 0, `loses` if it is below 0, and `unclear` otherwise. Slices with fewer than 5 users are flagged as not
reliable, because one user gives a zero-width interval.

**Slices.** There are two sets of slices, and every slice is reported per strategy and as `learned` minus the best
baseline:
- **Activity:** the lab's groups, counted on likes before `T`: `new (<10)`, `casual (10-49)`, `regular (50-199)`,
  `power (200+)`.
- **Taste (our choice):** `fresh taste` if at least half of a user's relevant posts were less than 365 days old at
  `T`, otherwise `old taste`.

**Determinism.** The same database and arguments produce byte-identical `eval_results.csv` and `baseline_table.md`.
There is no randomness except the seeded bootstrap, the rows are sorted, and the floats have fixed formatting. The run
metadata records:
- a content fingerprint of the database (sha256 over the four tables);
- the git commit that last changed `app/`, `scripts/`, `models/` or `pyproject.toml`.

A commit that only updates `reports/` does not change the second value.

## Known limitations

1. **The model may have seen the future.** `models/like_model.npz` was trained in Lab 05 on MovieLens moments before
   the lab's `val` cut-off (2013-03-19). It was then tuned (`HIDDEN`, `LEARNING_RATE`, `EPOCHS`) on the `val` period up
   to 2016-07-10. Our cut-off `T` is 2016-02-09, so **none** of the 633 evaluation likes is in the training period.
   However, **210 of them (33 %)** fall in the lab's `val` period, which we used to choose the hyper-parameters. The
   weights never saw these likes, but our model choice did. `learned`'s score is therefore probably slightly
   optimistic. A clean run would use a cut-off after 2016-07-10, or retrain the model on likes before `T` only.
2. **The population is not InstaKill's.** MovieLens is mostly old movies rated years later. At `T`, the median snapshot
   post is 4,414 days (about 12 years) old, only 5.8 % of posts are less than a year old, and 0.04 % are less than a
   week old. A real social feed is mostly posts from the last few days. Our `fresh taste` slice has only 2 users, both
   at NDCG 0 for every strategy, so the slices cannot tell us which strategy wins on fresh posts. Two things are
   visible, though. `for_you` uses a 24-hour freshness half-life, which gives no signal at all on these years-old
   posts, and on this data it trails `popularity` (0.068 vs 0.119). On a feed of fresh posts, freshness and follows
   would carry real signal, and we would expect `for_you` to gain the most. Every MovieLens post is extremely old
   relative to the learned model's signals too (freshness ≈ 0, age at its cap), so `learned` mostly ranks by its
   lifetime-popularity and affinity signals, i.e. close to `popularity`. That matches the near-zero difference
   (+0.005, interval [-0.092, +0.103]).
3. **Small sample.** With 25 users, only a large difference could produce `wins` or `loses`. Today's `unclear` means
   "we cannot tell", not "they are equal".
