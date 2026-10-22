# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Permanent website addresses for a run's dips: ``/candidates/pi-men/dip-2/``.

A candidate id is ``{subject}-{rank}``, so a re-run that ranks the dips differently would give an id to another dip.
An address is therefore pinned to the dip itself: its subject and its mid-time. ``runs/<run>/slugs.json`` keeps, for
every address ever given, the subject, the mid-time and the duration of its dip (and the id it had, for reference):

    {"dips": [{"slug": "pi-men/dip-2", "subject": "tess-fa3483ce6f83", "t_center": 1331.7711,
               "duration_hours": 2.455, "id": "tess-fa3483ce6f83-000"}, ...]}

On every build each pinned address is matched to the run's dip in the same subject whose mid-time lies within the
pinned dip's duration, and never more than half a day, nearest first, one dip per address. An address that matches
no dip is gone: it keeps its entry, so its number is never given to another dip, and its page answers "no longer in
the run". A dip that matches no address gets the next free number of its star. Standard library only.
"""

from __future__ import annotations

import json
from pathlib import Path

SLUGS_FILE = "slugs.json"
MAX_SHIFT_DAYS = 0.5
NOTE = ("Each dip's address on the website (/candidates/<slug>/), given once and never changed. An address belongs to "
        "a dip by its subject and mid-time (within its duration, at most half a day), not by its candidate id, which "
        "is a rank. Written by setuhq site; a dip that leaves the run keeps its entry, so its number is never reused.")


def _num(slug: str) -> tuple[str, int]:
    star, _, n = slug.rpartition("/dip-")
    return star, int(n) if n.isdigit() else 0


def load(run_dir: str | Path) -> list[dict]:
    """The pinned entries, or none. An older file (``{"slugs": {id: slug}}``) has no times; it is read as such and
    matched by id once (see pin), then rewritten with times."""
    try:
        raw = json.loads((Path(run_dir) / SLUGS_FILE).read_text())
    except (OSError, ValueError):
        return []
    if isinstance(raw.get("dips"), list):
        return [dict(e) for e in raw["dips"] if isinstance(e, dict) and e.get("slug")]
    return [{"slug": s, "id": i} for i, s in (raw.get("slugs") or {}).items()]


def _entry(c: dict, slug: str, star: str | None) -> dict:
    e = {"slug": slug, "subject": c.get("subject_id") or c.get("target") or "", "t_center": c["t_center"],
         "duration_hours": c.get("duration_hours"), "id": c["candidate_id"]}
    return {**e, "star": star} if star else e


def pin(cands: list[dict], pinned: list[dict], star_slug, star_name=None) -> tuple[dict[str, str], list[str], list[dict]]:
    """Match the run's dips to the pinned addresses. ``star_slug(c)`` names a dip's star in an address ("pi-men"),
    ``star_name(c)`` in words ("pi Men", kept in the entry for pages that do not know it, such as the plates).
    Returns {candidate id: slug} for the dips in the run, the slugs that are gone, and the entries to keep."""
    name = star_name or (lambda c: None)
    entries = [dict(e) for e in pinned]
    taken: dict[str, str] = {}
    # Pairs (address, dip) within tolerance, nearest first; each address and each dip used once.
    pairs = []
    for k, e in enumerate(entries):
        if e.get("t_center") is None:  # an older file: matched by id, then given the dip's time
            c = next((c for c in cands if c["candidate_id"] == e.get("id")), None)
            if c:
                pairs.append((0.0, k, c["candidate_id"]))
            continue
        tol = min((float(e.get("duration_hours") or 0) / 24.0) or MAX_SHIFT_DAYS, MAX_SHIFT_DAYS)
        for c in cands:
            if (c.get("subject_id") or c.get("target") or "") != e.get("subject"):
                continue
            dt = abs(float(c["t_center"]) - float(e["t_center"]))
            if dt <= tol:
                pairs.append((dt, k, c["candidate_id"]))
    used_e: set[int] = set()
    by_id = {c["candidate_id"]: c for c in cands}
    for dt, k, cid in sorted(pairs):
        if k in used_e or cid in taken:
            continue
        used_e.add(k)
        taken[cid] = entries[k]["slug"]
        if entries[k].get("t_center") is None:
            entries[k] = _entry(by_id[cid], entries[k]["slug"], name(by_id[cid]))
        else:
            entries[k]["id"] = cid  # the id it has now, for reference only
            if name(by_id[cid]) and not entries[k].get("star"):
                entries[k]["star"] = name(by_id[cid])
    gone = sorted(e["slug"] for k, e in enumerate(entries) if k not in used_e)
    top: dict[str, int] = {}
    for e in entries:
        star, n = _num(e["slug"])
        top[star] = max(top.get(star, 0), n)
    for c in sorted(cands, key=lambda c: (c["t_center"], c["candidate_id"])):
        if c["candidate_id"] in taken:
            continue
        star = star_slug(c)
        top[star] = top.get(star, 0) + 1
        slug = f"{star}/dip-{top[star]}"
        taken[c["candidate_id"]] = slug
        entries.append(_entry(c, slug, name(c)))
    entries.sort(key=lambda e: _num(e["slug"]))
    return taken, gone, entries


def save(run_dir: str | Path, entries: list[dict], before: list[dict]) -> None:
    """Write the entries when they changed. A read-only run folder is left as it is."""
    if entries == before:
        return
    try:
        (Path(run_dir) / SLUGS_FILE).write_text(json.dumps({"note": NOTE, "dips": entries}, indent=1) + "\n")
    except OSError:
        pass
