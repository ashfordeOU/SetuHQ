# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Target status: is the target on the Reserved Target List, and what does the public archive hold for it.

RTL matching is done three ways, and any one is enough to flag the target:

* by name, after normalising case, spaces, dashes and the usual spelling variants ("Alpha Centauri B" and
  "AlphaCenB", "TOI-396" and "TOI 396");
* by alias: every identifier SIMBAD lists for the target (so "HD 197481" finds the RTL's "AU Mic", and a TIC
  number finds the TOI name the RTL uses);
* by position: an RTL entry within ``radius_arcsec`` of the target's coordinates. ESA's own rule is to check by
  coordinates, not names (P&P section 5.2.3.3), and reservations are by line of sight. Entries within
  ``near_arcsec`` are reported for a manual check.

This restates a public list; ESA's Target Checker gives the definitive status at submission time, and its
screenshot is a required proposal file (PDF #4).
"""

from __future__ import annotations

import math
import re

GREEK = {"alf": "alpha", "bet": "beta", "gam": "gamma", "del": "delta", "eps": "epsilon", "pi.": "pi", "tau": "tau"}


def normalise(name: str) -> str:
    """A comparison key for a star name: lower case, SIMBAD's prefixes ('*', 'V*', 'NAME') dropped, Greek
    abbreviations expanded,
    'Centauri' to 'Cen', and every space, dash, underscore and dot removed."""
    s = re.sub(r"^\s*(?:NAME\s+|V\*\s*|\*\*\s*|\*\s*)", "", str(name or ""))  # SIMBAD's prefixes
    s = " ".join(s.replace("*", " ").split()).lower()
    words = [GREEK.get(w, w) for w in s.split()]
    s = " ".join(words)
    s = re.sub(r"\bcentauri\b", "cen", s)
    s = re.sub(r"\balf\b", "alpha", s)
    return re.sub(r"[\s\-_.]", "", s)


def separation_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation (haversine), in arcseconds."""
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    h = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((r2 - r1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h)))) * 3600.0


def match_rtl(entries, *, name: str, aliases=(), ra: float | None = None, dec: float | None = None,
              radius_arcsec: float = 20.0, near_arcsec: float = 120.0) -> dict:
    """Matches of one target against RTL entries (objects with name, ra, dec, list_label)."""
    keys = {normalise(name)} | {normalise(a) for a in aliases if a}
    keys.discard("")
    reserved, nearby = [], []
    for e in entries:
        how = []
        if normalise(e.name) in keys:
            how.append("name" if normalise(e.name) == normalise(name) else "alias")
        sep = None
        if None not in (ra, dec, e.ra, e.dec):
            sep = separation_arcsec(ra, dec, e.ra, e.dec)
            if sep <= radius_arcsec:
                how.append(f"position ({sep:.1f}\" ≤ {radius_arcsec:g}\")")
        row = {"rtl_name": e.name, "list": e.list_label, "ra": e.ra, "dec": e.dec, "notes": e.notes,
               "separation_arcsec": None if sep is None else round(sep, 2)}
        if how:
            reserved.append(row | {"matched_by": how})
        elif sep is not None and sep <= near_arcsec:
            nearby.append(row)
    return {"reserved": bool(reserved), "matches": reserved, "nearby": nearby,
            "radius_arcsec": radius_arcsec, "near_arcsec": near_arcsec}


def coordinate_warnings(source: str | None, user_ra: float | None = None, user_dec: float | None = None,
                        ref_ra: float | None = None, ref_dec: float | None = None,
                        pmra: float | None = None, pmdec: float | None = None) -> list[str]:
    """Warnings about where coordinates came from. ExoFOP and Gaia give ICRS at epoch J2015.5 (or J2016.0),
    not the J2000 the call requires; and a user position offset from SIMBAD's by about 15.5 years of proper motion
    is probably such a position."""
    out = []
    src = (source or "").lower()
    if src in ("exofop", "gaia"):
        out.append(f"Coordinates from {source} are not accepted as given: ExoFOP and Gaia list ICRS positions at "
                   "epoch J2015.5/J2016.0, and the call requires ICRS, epoch J2000. Take them from the Target "
                   "Checker, SIMBAD or MAST instead.")
    if None not in (user_ra, user_dec, ref_ra, ref_dec):
        sep = separation_arcsec(user_ra, user_dec, ref_ra, ref_dec)
        if pmra is not None and pmdec is not None:
            pm = math.hypot(pmra, pmdec) / 1000.0  # arcsec per year
            moved = pm * 15.5
            if moved > 0.3 and abs(sep - moved) < max(0.3, 0.25 * moved):
                out.append(f"The supplied position is {sep:.2f}\" from SIMBAD's J2000 position, about what "
                           f"{pm * 1000:.0f} mas/yr of proper motion gives over 15.5 years: it looks like a "
                           "J2015.5 (Gaia/ExoFOP) position. Use J2000.")
        if sep > 2.0:
            out.append(f"The supplied position is {sep:.1f}\" from SIMBAD's; check which star you mean.")
    return out
