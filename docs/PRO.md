<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SetuHQ Pro

**Status: planned, not built.** Nothing on this page is available yet, and none of it is in this
repository. It states what Ashforde OÜ plans to offer around the open engine, so that anyone who
would use it can say so early. There are no prices here: every route starts with a message to
[contact@ashforde.org](mailto:contact@ashforde.org?subject=SetuHQ%20Pro%20evaluation).

Open SetuHQ is, and stays, the whole engine: the search, the Sentinels and Probes, the vetting and
fits, the frozen real-TOI benchmark and its public leaderboard, the sweep, the MCP server and the
app, under the AGPL-3.0-only or a commercial licence ([`LICENSING.md`](../LICENSING.md)). Pro is for
what a public repository cannot give an institution: **scale, privacy, packaging and
accountability.** It never sells better science. SetuHQ's own leaderboard shows that the Probes do
not yet beat a catalogue-metadata floor, and Pro will never imply otherwise.

## What Pro is, and what it will never be

- **A strict superset of open SetuHQ.** Pro depends on the open engine and never forks it. Every
  open feature stays open, and no free feature moves behind a licence.
- **No new science.** Pro adds no detection, vetting or fitting method and changes none. Every Pro
  number comes from open-engine runs that anyone can repeat with the free code.
- **Candidates, never confirmations.** Nothing Pro produces is a confirmation or validation of a
  planet. Pro produces candidates, like the open engine, with the same labels.
- **Honest about the reviewers.** Pro never gives an uncalibrated AI reviewer a calibrated weight,
  and never hides which provider and model reviewed.
- **Customer data stays the customer's.** Pro never publishes a customer's targets or photometry
  without consent, and never uses them to train anything.
- **No claim of more planets.** Pro is never marketed as finding more planets than the open engine.

## Planned products

Each one names what in the open code it would build on, and what would still have to be built.

| Product | What it would be | Built on, in the open code | Still to build |
|---|---|---|---|
| **Pro Calibrate** (lead product) | A calibration certificate for any AI reviewer on the frozen 662-TOI benchmark: its weight, its agreement with the reference panel, and the stars it was tested on | per-provider and per-model calibration, floor weights for uncalibrated Sentinels, `--panel`, agreement (φ) and the effective number of voters | a signed report format, a versioned certificate, renewal on each benchmark version |
| **Pro Workspace** | Private target lists, embargoed candidates, team roles, single sign-on and a signed audit trail, hosted or on-premises | provenance hashes, the append-only ingest ledger, the locked-down MCP server | accounts, multi-tenancy, cryptographic signing (bundles are content-hashed today, not signed) |
| **Pro Sweeps** | Hosted searches over whole sectors or target lists, with AI review calls brought by the customer (their own key) or paid for. Results come back as open contribution bundles that anyone can re-run for free | the all-sky sweep, contribution bundles, multi-provider Sentinels | a job queue, quotas, billing, a measured cost per star |
| **Pro Follow-up** | One command that turns a candidate into a follow-up packet: an ExoFOP-style export, an ephemeris with its uncertainty, and when the target is observable from the customer's own telescopes | the ephemeris and ExoFOP-style export, DV-style vetting, the reduced FPP | an observability planner, site profiles, the packet layout |
| **SetuHQ Education & Dome** | A classroom edition with graded vetting exercises (known TOI outcomes are the answer key), and a planetarium edition: offline, kiosk mode, a fulldome Galaxy, a nightly feed | the Galaxy, the Methods chapters, the catalogue, the benchmark's labels | rosters and grading, fulldome output, a kiosk shell |
| **Commercial licence & SDK** | The engine inside a closed product without the AGPL's source obligation: transit fit and vetting on a user's own photometry, with a stable API | AGPL plus CLA dual licensing, the transit fit, the MCP tools | licence terms with counsel, a versioned API, SDK documentation |

**Custom studies**, done for a customer under a fixed scope: a sector sweep, a candidate dossier,
or a yield study for a proposed instrument. They run the open engine as it is and need no new code.

Embargoed Pro sweeps can be released into the open catalogue with the customer's consent, through
the same contribution bundles and ingest as anyone else's, so Pro grows the free catalogue.

## How to start

| Route | Start with |
|---|---|
| A Pro evaluation, or to say you would use a product above | [contact@ashforde.org, "SetuHQ Pro evaluation"](mailto:contact@ashforde.org?subject=SetuHQ%20Pro%20evaluation) |
| A custom study | [contact@ashforde.org, "SetuHQ custom study"](mailto:contact@ashforde.org?subject=SetuHQ%20custom%20study) |
| A commercial licence for the open engine (available now) | [contact@ashforde.org, "SetuHQ commercial licence"](mailto:contact@ashforde.org?subject=SetuHQ%20commercial%20licence) |

The commercial licence for the open engine is the one route available today; see
[`LICENSING.md`](../LICENSING.md). Pro products will be built only when the people who would use
them ask for them in writing, and this page will say when any of them exists.

## What Pro is not

- **Pro is not open source,** and it is not part of this repository or offered under the AGPL.
- **Pro is not a confirmation service.** A planet is confirmed by follow-up observations, not by
  software; nothing Pro produces is a confirmation or validation of a planet.
- **Pro is not a better pipeline.** It runs the open engine; its science is exactly as good as the
  open benchmark says, and no better.
