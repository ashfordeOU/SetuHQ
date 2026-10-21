# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Proposal preparation packs: help a researcher prepare a CHEOPS Guest Observers proposal (Running Call).

``setuhq propose cheops <target>`` writes one new directory with a rules check (orbit limits, cycle, deadline,
earliest start), the target's status (the public Reserved Target List, public archive metadata, J2000
coordinates from SIMBAD or MAST), SetuHQ's own evidence where it exists (candidates, ephemeris, TESS noise per
timescale), rough planning estimates (precision per orbit, orbits for a target S/N, the ephemeris uncertainty in
the window), anonymised drafts with an anonymity lint, and ESA's seven-step checklist with links.

SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS mission
or the CHEOPS Consortium. It does not replace ESA's Target Checker, Visibility Tool, Exposure Time Calculator,
Scheduling Feasibility Checker or the Policies & Procedures document; the official call and tools govern. It
reads public pages and metadata only, never logs in, never submits, and never touches ESA's proposal tools.

Modules: :mod:`.rules` (calendar and limits), :mod:`.sources` (public reads, rate-limited and cached),
:mod:`.targets` (RTL matching, coordinate warnings), :mod:`.planning` (estimates), :mod:`.evidence` (stored
SetuHQ outputs and optional stellar hooks), :mod:`.draft` (drafts, lint, checklist), :mod:`.pack` (the pack),
:mod:`.cli` (the command line).
"""

from setuhq.propose.draft import DISCLAIMER

__all__ = ["DISCLAIMER"]
