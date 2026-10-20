# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""How independent are the Sentinels? Pairwise agreement (φ) on the same stars.

Two reviewers that share a model make correlated errors and count as one voter, not two:
on the stated 40-star subsample of the real-TOI benchmark the two Claude personas agree with
φ = 0.89. Sentinels on different providers may disagree more, which is what makes a panel
worth having. This module measures it, from per-star outcomes only:

    hits = {star: {reviewer_id: True/False}}   # did the reviewer mark the TOI's dip as a planet

φ is the Pearson correlation of two binary outcomes (the Matthews coefficient):

    φ = (n11·n00 − n10·n01) / sqrt((n11+n10)(n01+n00)(n11+n01)(n10+n00))

It is None when either reviewer gave the same answer on every star (the denominator is zero).
Only stars both reviewers answered are compared. ``scripts/benchmark_real_tois.py sentinels``
collects the outcomes; its ``report`` step writes the table.
"""

from __future__ import annotations

from itertools import combinations


def phi(pairs: list[tuple[bool, bool]]) -> dict:
    """Agreement of two reviewers over paired binary outcomes: counts, fraction agreeing and φ."""
    n11 = sum(1 for a, b in pairs if a and b)
    n00 = sum(1 for a, b in pairs if not a and not b)
    n10 = sum(1 for a, b in pairs if a and not b)
    n01 = sum(1 for a, b in pairs if not a and b)
    den = ((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)) ** 0.5
    return {"n": len(pairs), "agree": n11 + n00, "n11": n11, "n10": n10, "n01": n01, "n00": n00,
            "phi": (n11 * n00 - n10 * n01) / den if den else None}


def pairwise(hits: dict[str, dict[str, bool]], reviewers: list[str] | None = None,
             identities: dict[str, dict] | None = None) -> list[dict]:
    """φ for every pair of reviewers, over the stars both answered.

    ``identities`` ({reviewer: {"provider": ..., "model": ...}}) labels each pair as the same model
    (two personas of one model: expect high φ) or different providers/models (the diversity being measured).
    """
    ids = reviewers or sorted({rid for per in hits.values() for rid in per})
    identities = identities or {}
    out = []
    for a, b in combinations(ids, 2):
        pairs = [(per[a], per[b]) for per in hits.values() if a in per and b in per]
        ia, ib = identities.get(a) or {}, identities.get(b) or {}
        same = bool(ia) and bool(ib) and (ia.get("provider"), ia.get("model")) == (ib.get("provider"), ib.get("model"))
        out.append({"a": a, "b": b, **phi(pairs),
                    "same_model": same if ia and ib else None,
                    "a_provider": ia.get("provider"), "a_model": ia.get("model"),
                    "b_provider": ib.get("provider"), "b_model": ib.get("model")})
    return out


def constant_reviewers(hits: dict[str, dict[str, bool]], reviewers: list[str]) -> list[str]:
    """Reviewers that gave the same answer on every star they answered (or answered none). φ with them is
    undefined, so they carry no information about independence and are left out of the voter count."""
    out = []
    for rid in reviewers:
        answers = {per[rid] for per in hits.values() if rid in per}
        if len(answers) < 2:
            out.append(rid)
    return out


def effective_voters(table: list[dict], reviewers: list[str], exclude: list[str] = ()) -> float | None:
    """A rough count of independent voters: k / (1 + (k − 1)·mean φ), with φ < 0 treated as 0.

    k reviewers whose outcomes all correlate at φ act like this many independent ones (the design-effect
    formula). ``exclude`` (:func:`constant_reviewers`) is left out of k and of the pairs, so k counts only
    reviewers whose every pair has a φ. None when fewer than two remain, or a remaining pair has no φ
    (no stars in common).
    """
    keep = [r for r in reviewers if r not in set(exclude)]
    pairs = [p for p in table if p["a"] in keep and p["b"] in keep]
    k = len(keep)
    if k < 2 or not pairs or any(p["phi"] is None for p in pairs):
        return None
    mean = sum(max(0.0, p["phi"]) for p in pairs) / len(pairs)
    return k / (1 + (k - 1) * mean)
