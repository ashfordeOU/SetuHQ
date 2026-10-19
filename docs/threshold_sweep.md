# Threshold sweep: Probe settings on synthetic injections

Not the real-TOI leaderboard: that one scores whole methods on the frozen benchmark, in [docs/leaderboard/leaderboard.md](leaderboard/leaderboard.md). This sweep tunes Probe thresholds on synthetic light curves.

Score is mean completeness on the injection grid. A setting with false positives above the budget scores zero. Search and held-out seeds are different, and only a setting that wins on the held-out seed can be promoted.

| stage | snr threshold | miss prob | seed | completeness | FP / empty subject | score |
|---|---:|---:|---:|---:|---:|---:|
| search | 4.0 | 0.05 | 101 | 0.938 | 0.000 | 0.938 |
| search | 4.5 | 0.05 | 101 | 0.938 | 0.000 | 0.938 |
| search | 5.0 | 0.1 | 101 | 0.917 | 0.000 | 0.917 |
| search | 5.5 | 0.1 | 101 | 0.917 | 0.000 | 0.917 |
| search | 6.0 | 0.1 | 101 | 0.917 | 0.000 | 0.917 |
| holdout | 4.0 | 0.05 | 202 | 0.875 | 0.000 | 0.875 |
| holdout | 5.0 | 0.1 | 202 | 0.875 | 0.000 | 0.875 |

Decision: **keep default** → `{'snr_threshold': 5.0, 'miss_probability': 0.1}`
