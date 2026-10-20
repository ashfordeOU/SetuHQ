---
name: leaderboard-submission
description: Prepare a proposed Probe setting for SetuHQ's leaderboard (the threshold sweep scored on a search seed and confirmed on a held-out seed), and stop for the user's approval before anything leaves this computer. Use when the user wants to submit to, beat or improve the leaderboard.
---

# Submit to the leaderboard

SetuHQ's leaderboard (`docs/leaderboard.md`, `docs/leaderboard.json`) is the Probe threshold sweep. A
setting is scored by injection-recovery completeness on a search seed, with false positives over a budget
scoring zero, and it is promoted only if it also beats the default on a **held-out seed** that the search
never saw. There is no automatic submission service on this branch; a submission is a pull request that a
person opens.

Do this:

1. Read the current board with the `exoplan` MCP server's **`benchmark_results`** (`threshold_sweep`) and
   say what the default scores on the held-out seed.
2. Run the protocol locally: `python scripts/improve.py --out <a scratch directory>` (add the user's
   setting to `GRID` in a scratch copy if they propose one). Never change the held-out seed after seeing a
   result, and never tune on it.
3. Report the search and held-out scores and the decision rule's verdict, exactly as the script writes them.
   A setting that loses on the held-out seed is not a submission.
4. **Stop and ask.** Opening a pull request, pushing a branch or posting a result is outward-facing: show the
   user the diff and the scores, and do it only after they say yes. Never put a key in a file or a message.
