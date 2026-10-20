---
name: leaderboard-submission
description: Prepare a method's entry for SetuHQ's real-TOI leaderboard (the frozen 662-TOI benchmark, scored on the held-out half and ranked by Youden's J against a metadata-only floor), score it locally, and stop for the user's approval before anything leaves this computer. Use when the user wants to submit to, beat or improve the leaderboard.
---

# Submit to the leaderboard

SetuHQ's leaderboard is the **real-TOI leaderboard** (`docs/leaderboard/leaderboard.md`, data in
`docs/leaderboard/leaderboard.json`; the protocol is `docs/leaderboard/README.md`). It scores a method's
detected events on the held-out half of the frozen 662-TOI benchmark and ranks by Youden's J with one predicate
(a clean candidate) on both sides. A metadata-only floor that never reads a light curve is ranked too, and the
benchmark cannot show that the Probes beat it: judge a method against that floor, not against zero. Measured on
a stated benchmark; nothing here is a discovery.

The Probe threshold sweep on synthetic injections (`docs/threshold_sweep.md`, `scripts/improve.py`) is a
different thing and is not the leaderboard.

There is no automatic submission service; a submission is a pull request that a person opens.

Do this:

1. Read the current board with the `setuhq` MCP server's **`benchmark_results`** (`leaderboard`) and say
   where the floor and the Probes stand, with their intervals.
2. Build the method on the tuning half (`docs/leaderboard/tuning_inputs.json`) or on nothing. Never read the
   held-out labels, and never tune on the held-out half.
3. Write the submission in the `exoplan-leaderboard/2` format of `docs/leaderboard/README.md`: one prediction
   per held-out star, the two control lists for every searched star, the hashes and the provenance.
4. Score it locally with `setuhq leaderboard <submission.json>` and report J, its interval and the paired
   comparison with the floor exactly as the command writes them. A refused submission lists its reasons; fix
   them, do not work around the whitelist.
5. **Stop and ask.** Opening a pull request, pushing a branch or posting a result is outward-facing: show the
   user the file and the scores, and do it only after they say yes. Never put a key in a file or a message.
