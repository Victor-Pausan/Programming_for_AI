# Feed evaluation: baseline table

Time-split replay on our own database; protocol in `docs/evaluation-protocol.md`.
NDCG@10 per user, mean over users, 95 % paired bootstrap interval over users.

## Strategies

| strategy | mean NDCG@10 [95 % CI] | users |
|---|---|---|
| `chronological` | 0.0000 [0.0000, 0.0000] | 25 |
| `popularity` (best baseline) | 0.1191 [0.0414, 0.2190] | 25 |
| `for_you` | 0.0676 [0.0119, 0.1389] | 25 |
| `learned` | 0.1242 [0.0449, 0.2213] | 25 |

## `learned` minus the best baseline (`popularity`)

| slice | users | learned | popularity | difference [95 % CI] | verdict |
|---|---|---|---|---|---|
| all users | 25 | 0.1242 [0.0449, 0.2213] | 0.1191 [0.0414, 0.2190] | 0.0051 [-0.0916, 0.1025] | unclear |
| new (<10) | 1 | 0.0000 [0.0000, 0.0000] | 0.7656 [0.7656, 0.7656] | -0.7656 [-0.7656, -0.7656] | loses (only 1 user: not reliable) |
| casual (10-49) | 10 | 0.2118 [0.0756, 0.3546] | 0.1919 [0.0373, 0.3642] | 0.0199 [-0.0516, 0.0998] | unclear |
| regular (50-199) | 7 | 0.0091 [0.0000, 0.0273] | 0.0314 [0.0000, 0.0943] | -0.0224 [-0.0671, 0.0000] | unclear |
| power (200+) | 7 | 0.1321 [0.0000, 0.3567] | 0.0105 [0.0000, 0.0314] | 0.1216 [-0.0210, 0.3567] | unclear |
| fresh taste | 2 | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | unclear (only 2 users: not reliable) |
| old taste | 23 | 0.1350 [0.0544, 0.2370] | 0.1295 [0.0404, 0.2331] | 0.0056 [-0.0963, 0.1120] | unclear |

Verdict: `wins` if the whole interval is above 0, `loses` if below 0, otherwise `unclear`. Slices with fewer than 5 users are flagged: their bootstrap interval is too narrow to mean anything.

## Mean NDCG@10 per slice and strategy

| slice | users | `chronological` | `popularity` | `for_you` | `learned` |
|---|---|---|---|---|---|
| new (<10) | 1 | 0.0000 [0.0000, 0.0000] | 0.7656 [0.7656, 0.7656] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] |
| casual (10-49) | 10 | 0.0000 [0.0000, 0.0000] | 0.1919 [0.0373, 0.3642] | 0.1606 [0.0297, 0.3041] | 0.2118 [0.0756, 0.3546] |
| regular (50-199) | 7 | 0.0000 [0.0000, 0.0000] | 0.0314 [0.0000, 0.0943] | 0.0000 [0.0000, 0.0000] | 0.0091 [0.0000, 0.0273] |
| power (200+) | 7 | 0.0000 [0.0000, 0.0000] | 0.0105 [0.0000, 0.0314] | 0.0122 [0.0000, 0.0365] | 0.1321 [0.0000, 0.3567] |
| fresh taste | 2 | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] | 0.0000 [0.0000, 0.0000] |
| old taste | 23 | 0.0000 [0.0000, 0.0000] | 0.1295 [0.0404, 0.2331] | 0.0735 [0.0166, 0.1497] | 0.1350 [0.0544, 0.2370] |

## Run metadata

| key | value |
|---|---|
| cut-off T | 2016-02-09T20:36:25Z |
| seed | 42 |
| bootstrap resamples | 2000 |
| users evaluated | 25 |
| relevant likes (after T, on snapshot posts) | 633 |
| database fingerprint (sha256/16) | a19e282034b71cfa |
| code version (git) | 5e467c6 |
| model | models/like_model.npz (129 parameters) |
