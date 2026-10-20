<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SetuHQ governance

This document states how SetuHQ is governed: who makes decisions, how, and what the project will
and will not absorb. It is deliberately **light**, in proportion to the project's current size, and
honest about the present single-maintainer reality and the path to broader governance as the
community grows.

## Mission and scope

SetuHQ is an **open, reproducible, honestly measured transit search and benchmark** on public
sky data: a calibrated panel of AI Sentinels and deterministic Probes, a pipeline that vets and fits
every dip, a frozen blind benchmark on real TESS Objects of Interest with a public leaderboard, and
an app that explains every result. The mission sets the bar for every decision: provenance,
reproducibility and honest labels over breadth. What SetuHQ can and cannot claim is stated in the
README's Evidence and Honest limits sections; proposals are weighed against that, not against
feature count.

## Roles

- **Maintainer.** SetuHQ is maintained by its founder, Ashforde OÜ (contact:
  `contact@ashforde.org`). The maintainer is the final decision-maker on scope, design, releases,
  what is merged, and what enters the sweep catalogue and the leaderboard. This is a
  benevolent-maintainer model, stated plainly rather than dressed up as a committee that does not
  exist.
- **Contributors.** Anyone who opens an issue or a pull request, sends a sweep bundle or submits to
  the leaderboard. Contributions are held to the bar in [`CONTRIBUTING.md`](CONTRIBUTING.md) and
  accepted under the [Contributor Licence Agreement](CLA.md).
- **Future committers.** As sustained, high-quality contribution warrants it, commit rights will be
  extended to trusted contributors, and this document will move to a multi-maintainer model
  (decisions by lazy consensus, with the maintainer group resolving disagreements). Until then the
  path is: contribute, build a track record, and be invited.

## How decisions are made

1. **Discussion in the open.** Substantive changes start as a GitHub issue, so the rationale,
   alternatives and trade-offs are on the record.
2. **Lazy consensus.** A proposal with no sustained objection after reasonable time, and which
   passes the technical bar below, proceeds.
3. **Maintainer decides on disagreement.** Where consensus is not reached, the maintainer decides
   and records the reason. Disagreement is resolved by the mission and the technical bar, not by
   seniority or volume.

## The technical bar (non-negotiable)

These are hard invariants, enforced by CI and review, that no decision overrides:

- **Reproducibility.** A run is fixed by its config hash, the sha256 of every input file and the
  code fingerprint. A stored result must rebuild from what is committed, and every generated file
  (the site, the README's figures, the paper's numbers, the leaderboard) must match its `--check`.
- **No claim beyond the evidence.** SetuHQ's output is a candidate. Nothing is called a confirmed,
  validated or discovered planet, negative results are published beside positive ones, and every
  figure says whether it is real data, a model or an illustration.
- **The benchmark stays blind.** The real-TOI sample and its held-out half are frozen; a threshold
  is never tuned on the held-out half, and a rule is pre-registered before it is evaluated on it.
- **Honest AI labels.** Sentinels are labelled as AI, with their provider and model; an
  uncalibrated Sentinel votes at the floor weight.
- **Hygiene.** No credentials anywhere in the repository, bundles or records, and no
  automated-tool attribution trailers in commits.

A change that cannot meet the bar is declined, however useful it would be.

## The open / closed boundary

SetuHQ is **open-core**. This repository is, and stays, the complete open engine under the
AGPL-3.0-only, dual-licensed commercially by Ashforde OÜ (see [`LICENSING.md`](LICENSING.md)), with
its data, benchmark, leaderboard data and paper under CC BY 4.0.

The project will **not** accept into the open repository:

- **Customer- or partner-confidential data**, such as private target lists or embargoed
  photometry.
- **Copyleft (GPL, AGPL, LGPL, MPL) dependencies.** Not because they clash with the AGPL (they do
  not), but because they cannot be relicensed into the commercial edition: Ashforde OÜ can only
  offer a commercial licence over code it owns or that is permissively licensed.
- **Credentials or anything that would let one person's keys pay for another's run.**

Conversely, the project will **not** hollow out the open core to push proprietary value. The
search, the vetting, the benchmark and its leaderboard, the sweep and its catalogue, the MCP server
and the app stay open. A planned commercial overlay, SetuHQ Pro ([`docs/PRO.md`](docs/PRO.md)), may
only build on the open engine: it never forks it, never moves a free feature behind a licence and
adds no science of its own.

## Releases

- **Semantic Versioning.** Pre-1.0, file formats and the CLI may change; breaking changes are
  called out in [`CHANGELOG.md`](CHANGELOG.md). Data format names (for example
  `exoplan-leaderboard/2`) are versioned on their own.
- **Release authority.** Releases are cut by the maintainer. No workflow publishes a package to a
  registry; the site at https://setuhq.com is deployed from the default branch by
  `.github/workflows/pages.yml`.

## Code of conduct and security

- Conduct is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- Security issues follow the private disclosure process in [`SECURITY.md`](SECURITY.md). Do not
  open a public issue for a vulnerability.

## Trademark

"SetuHQ" and the Setu mark are trademarks of Ashforde OÜ ([`TRADEMARKS.md`](TRADEMARKS.md)). The
licences cover the **code** and the **data**, not the marks: a fork may use the code under the
licence, but not the SetuHQ name or the canonical identity. This keeps one traceable SetuHQ, which
is part of how the open benchmark stays a neutral reference.

## Amending this document

Changes to governance are themselves proposed as a pull request and decided by the process above.
As the project's scale changes, expect this document to grow a multi-maintainer decision model; it
will not lower the technical bar.

_Light by design. Honest about today, with a stated path for tomorrow._
