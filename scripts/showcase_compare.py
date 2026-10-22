#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The worked examples: each stored example run against the published values, written for the site and the docs.

    python scripts/showcase_compare.py --fetch    # query the NASA Exoplanet Archive once, store the rows
    python scripts/showcase_compare.py            # compare the stored runs with the stored rows (no network)

``--fetch`` stores every row of the archive's ``ps`` table for each example planet in
docs/results/showcase_reference.json (with the query and the time it ran). The comparison reads only stored
files: each run's candidates.json and subjects (runs/<run>/), the stored archive rows, and for the known false
positive the TOI table row the real-TOI benchmark froze (docs/results/benchmark_toi_sample.json). It writes

* docs/results/showcase.json: one entry per run, in the order the site shows them (what kind of example it is,
  why it was chosen, its sectors, the reproduce command, and the comparison), read by ``setuhq site``;
* docs/results/showcase/<run>.md: the comparison as a table, embedded in that run's report on the site.

A planet's published ephemeris (the archive row with a mid-time, preferring its default row) predicts its transits
in the run's data; a dip is on it when its mid-time is within max(T14 / 2, 1 h) of a predicted transit. For the dips on
it, SetuHQ's stored limb-darkened fit (Rp/R★, T14, depth) and BLS period are compared with the discovery paper's
values. A value the archive does not hold for that paper is not compared, and no value is invented. Nothing here
calls a SetuHQ dip confirmed: the planets are known from the literature, which is cited.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REFERENCE = ROOT / "docs/results/showcase_reference.json"
SHOWCASE = ROOT / "docs/results/showcase.json"
MD_DIR = ROOT / "docs/results/showcase"
TOI_SAMPLE = ROOT / "docs/results/benchmark_toi_sample.json"
ARCHIVE_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
COLUMNS = ("pl_name", "hostname", "default_flag", "pl_refname", "disc_refname", "pl_orbper", "pl_orbpererr1", "pl_tranmid",
           "pl_ratror", "pl_ratrorerr1", "pl_trandep", "pl_trandur", "pl_trandurerr1", "pl_rade")
BTJD = 2457000.0

# The examples, in the order the site shows them. The lead run (pi Men) is the reference check against
# Huang et al. 2018, recorded in docs/results/pi_men_validation.md; it is listed last and not recomputed here.
RUNS = [
    {"run": "tess-wasp-126-s1", "star": "WASP-126", "tic": 25155310, "config": "configs/showcase/tess-wasp-126-s1.toml",
     "kind": "Hot Jupiter", "planets": ["WASP-126 b"], "paper": "MAXTED_ET_AL__2016",
     "summary": "A Jupiter-sized planet on a 3.3-day orbit: deep, easy transits, in the TESS southern continuous viewing zone.",
     "why": ("The easy case: a transit about 0.6% deep that any search should find, so it shows the whole path from light curve "
             "to fit with little doubt about the signal.")},
    {"run": "tess-toi-270-s5", "star": "TOI-270", "tic": 259377017, "config": "configs/showcase/tess-toi-270-s5.toml",
     "kind": "Multi-planet system", "planets": ["TOI-270 b", "TOI-270 c", "TOI-270 d"], "paper": "G_UUML_NTHER_ET_AL__2019",
     "summary": "An M dwarf with three known transiting planets at 3.4, 5.7 and 11.4 days: several periods in one star.",
     "why": ("One light curve, three periods. It shows what the search does when a star has more than one planet, and which "
             "of them a 13-day subject can hold.")},
    {"run": "tess-hd-15337-s4", "star": "HD 15337", "tic": 120896927, "config": "configs/showcase/tess-hd-15337-s4.toml",
     "kind": "Small planets near the limit", "planets": ["HD 15337 b", "HD 15337 c"], "paper": "GANDOLFI_ET_AL__2019",
     "summary": "A bright K dwarf with two small known planets: b (about 1.6 Earth radii, 4.8 days, roughly 350 ppm deep) and c (17.2 days).",
     "why": ("A small planet whose single transits are near the noise of one sector: it shows what the panel and vetting do "
             "at the edge of what a 10-minute-binned search can see, and the page says what it missed.")},
    {"run": "tess-toi-236-s2", "star": "TOI-236", "tic": 9727392, "config": "configs/showcase/tess-toi-236-s2.toml",
     "kind": "Known false positive", "toi": "236.01",
     "summary": "A TESS Object of Interest the TOI table dispositions as a false positive (FP): a 2.4% dip every 4.5 days.",
     "why": ("A test SetuHQ must fail to pass: TOI-236.01 is in the real-TOI benchmark's false-positive set. The page says what the "
             "vetting did with it, whatever it did.")},
    {"run": "tess-pi-men-s1", "star": "pi Men", "tic": 261136679, "config": "configs/tess_pi_men_s1.toml",
     "kind": "Reference check", "planets": ["pi Men c"], "lead": True,
     "summary": "A sun-like star with a super-Earth on a 6.3-day orbit: the run checked in full against Huang et al. 2018.",
     "why": ("The reference check: the one run with the Sentinels as well as the Probes, its limb-darkened fit compared with the "
             "discovery paper in docs/results/pi_men_validation.md."),
     "validation": "docs/results/pi_men_validation.md"},
]


def _ref(html: str | None) -> dict:
    """The archive's reference cell (an HTML link) as its code, its label and its address."""
    html = html or ""
    code = re.search(r"refstr=([A-Za-z0-9_]+)", html)
    url = re.search(r"href=(\S+?)(?: |>)", html)
    import html as _html

    label = _html.unescape(re.sub(r"<[^>]+>", "", html)).strip()
    return {"code": code.group(1) if code else label, "label": label, "url": url.group(1) if url else ""}


def fetch() -> dict:
    """Every archive row (table ps) for each example planet; the query and its time are stored with them."""
    import csv
    import io
    import urllib.parse
    import urllib.request

    names = [p for r in RUNS if not r.get("lead") for p in r.get("planets") or []]
    query = (f"select {','.join(COLUMNS)} from ps where pl_name in ("
             + ",".join("'" + n.replace("'", "''") + "'" for n in names) + ") order by pl_name, default_flag desc")
    url = ARCHIVE_URL + "?" + urllib.parse.urlencode({"query": query, "format": "csv"})
    with urllib.request.urlopen(url, timeout=120) as resp:
        text = resp.read().decode()
    rows: dict[str, list[dict]] = {}
    for r in csv.DictReader(io.StringIO(text)):
        row = {}
        for k in COLUMNS:
            v = r.get(k, "")
            if k in ("pl_refname", "disc_refname"):
                row[k] = _ref(v)
            elif k in ("pl_name", "hostname"):
                row[k] = v
            else:
                row[k] = float(v) if v not in ("", None) else None
        row["default_flag"] = bool(row["default_flag"])
        rows.setdefault(r["pl_name"], []).append(row)
    out = {"source": "NASA Exoplanet Archive, table ps (every row for each planet)", "url": ARCHIVE_URL, "query": query,
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "note": "pl_trandep is in percent (x 10^4 for ppm); pl_trandur in hours; pl_tranmid in BJD (TDB).",
           "rows": rows}
    REFERENCE.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return out


# ---------------------------------------------------------------------------------------------------------------------


def _subjects(run_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((run_dir / "subjects").glob("*.json"))]


def _covered(t: float, subjects: list[dict], half: float) -> bool:
    """True when the run's stored light curve has points within ``half`` days of ``t`` on both sides."""
    for s in subjects:
        ts = s.get("time") or []
        if ts and ts[0] <= t <= ts[-1]:
            before = any(t - half <= x < t for x in ts)
            after = any(t < x <= t + half for x in ts)
            if before and after:
                return True
    return False


def _ephemeris_row(rows: list[dict]) -> dict | None:
    """The row whose ephemeris predicts the transits: the default row when it has a mid-time, else the most recent
    row that has one (the archive lists rows newest first within a flag, so the first with a mid-time)."""
    with_t = [r for r in rows if r.get("pl_tranmid") and r.get("pl_orbper")]
    return next((r for r in with_t if r["default_flag"]), with_t[0] if with_t else None)


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _ratio(a, b):
    return round(a / b, 3) if a is not None and b else None


def on_ephemeris(cands: list[dict], subjects: list[dict], period: float, t0_btjd: float, t14_h: float) -> dict:
    """The predicted transits in the run's span (those with data on both sides), and the dips within
    max(T14 / 2, 1 h) of one."""
    tol = max(t14_h / 48.0, 1 / 24)
    lo = min(s["start"] for s in subjects)
    hi = max(s["end"] for s in subjects)
    n0, n1 = int((lo - t0_btjd) // period), int((hi - t0_btjd) // period) + 1
    predicted = [t0_btjd + n * period for n in range(n0, n1 + 1) if lo <= t0_btjd + n * period <= hi]
    predicted = [t for t in predicted if _covered(t, subjects, max(tol, 0.5 * t14_h / 24))]
    dips = []
    for c in cands:
        near = [t for t in predicted if abs(c["t_center"] - t) <= tol]
        if near:
            dips.append({"c": c, "predicted": near[0], "offset_min": round((c["t_center"] - near[0]) * 1440, 1)})
    recovered = sorted({round(d["predicted"], 5) for d in dips})
    return {"predicted": predicted, "dips": dips, "recovered": recovered}


def _flags(c: dict) -> list[str]:
    f = c.get("flags") or []
    return [x for x in (f.split(";") if isinstance(f, str) else f) if x]


def outcome_of(c: dict) -> str:
    """A dip's vetting outcome as the site names it (setuhq.docket)."""
    from setuhq.docket import outcome, vetting_checks

    return outcome(vetting_checks({**c, "flags": _flags(c)}), _flags(c), c.get("passed"))


def compare_planet(name: str, rows: list[dict], paper: str, cands: list[dict], subjects: list[dict]) -> dict:
    eph = _ephemeris_row(rows)
    ref = next((r for r in rows if r["pl_refname"]["code"] == paper), None)
    out = {"planet": name, "reference": ref["pl_refname"] if ref else None,
           "ephemeris_from": eph["pl_refname"] if eph else None}
    if not eph:
        out["note"] = "No archive row holds a mid-time for this planet, so its transits are not predicted."
        return out
    t14 = next((r["pl_trandur"] for r in (ref, eph) if r and r.get("pl_trandur")), None) or \
        next((r["pl_trandur"] for r in rows if r.get("pl_trandur")), 2.0)
    m = on_ephemeris(cands, subjects, eph["pl_orbper"], eph["pl_tranmid"] - BTJD, t14)
    dips = [d["c"] for d in m["dips"]]
    outs = [outcome_of(c) for c in dips]
    passed = [c for c, o in zip(dips, outs) if o != "rejected"] or dips
    # The BLS period: one value when the dips agree (within 1%); dips with different periods are listed, not averaged.
    periods = sorted({round(c["period_days"], 5) for c in passed if c.get("period_days")})
    agree = bool(periods) and periods[-1] <= periods[0] * 1.01
    ours = {"period_days": _median([c.get("period_days") for c in passed]) if agree else None,
            "rp_rs": _median([c.get("fit_k") for c in passed]),
            "t14_hours": _median([c.get("fit_t14_hours") for c in passed]),
            "depth_ppm": _median([c.get("fit_depth_ppm") for c in passed])}
    def values(r):
        return {"period_days": r.get("pl_orbper"), "rp_rs": r.get("pl_ratror"), "t14_hours": r.get("pl_trandur"),
                "depth_ppm": r["pl_trandep"] * 1e4 if r.get("pl_trandep") else None} if r else {}

    theirs = values(ref)
    default = next((r for r in rows if r["default_flag"]), None)
    if default is not None and default is not ref:
        out["archive_default"] = {"reference": default["pl_refname"], "values": values(default),
                                  "ratio": {k: _ratio(ours[k], v) for k, v in values(default).items() if v}}
    out |= {
        "dip_ids": [c["candidate_id"] for c in dips], "periods_each": periods if not agree else [],
        "predicted_transits": len(m["predicted"]), "recovered_transits": len(m["recovered"]),
        "dips_on_ephemeris": len(dips),
        "outcomes": {k: outs.count(k) for k in ("passed", "flagged", "rejected") if outs.count(k)},
        "mean_offset_min": round(statistics.mean(d["offset_min"] for d in m["dips"]), 1) if m["dips"] else None,
        "setuhq": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in ours.items()},
        "published": theirs,
        "ratio": {k: _ratio(ours[k], theirs.get(k)) for k in ours if theirs.get(k)},
    }
    return out


def compare_fp(spec: dict, cands: list[dict], subjects: list[dict]) -> dict:
    sample = json.loads(TOI_SAMPLE.read_text())
    toi = next(t for t in sample["tois"] if t["toi"] == spec["toi"])
    m = on_ephemeris(cands, subjects, toi["period"], toi["tranmid_bjd"] - BTJD, toi["duration_hours"])
    dips = [d["c"] for d in m["dips"]]
    outs = [outcome_of(c) for c in dips]
    flags = sorted({f for c in dips for f in _flags(c)})
    return {
        "toi": spec["toi"], "disposition": toi["disposition"],
        "toi_source": f"{sample['source']}, fetched {sample['fetched_at'][:10]} (the real-TOI benchmark's frozen sample, sha256 {sample['sha256'][:16]}…)",
        "published": {"period_days": toi["period"], "depth_ppm": toi["depth_ppm"], "t14_hours": toi["duration_hours"],
                      "radius_re": toi["radius_re"]},
        "predicted_transits": len(m["predicted"]), "recovered_transits": len(m["recovered"]),
        "dips_on_ephemeris": len(dips), "outcomes": {k: outs.count(k) for k in ("passed", "flagged", "rejected") if outs.count(k)},
        "flags": flags,
        "setuhq": {"period_days": _median([c.get("period_days") for c in dips]), "depth_ppm": _median([c.get("depth_ppm") for c in dips]),
                   "t14_hours": _median([c.get("fit_t14_hours") for c in dips]),
                   "secondary_snr": _median([c.get("secondary_snr") for c in dips])},
    }


def run_entry(spec: dict, reference: dict) -> dict:
    from setuhq.names import dip_count, panel_mode

    run_dir = ROOT / "runs" / spec["run"]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    cands = json.loads((run_dir / "candidates.json").read_text())
    subjects = _subjects(run_dir)
    entry = {k: spec[k] for k in ("run", "star", "tic", "kind", "summary", "why", "config") if k in spec}
    entry |= {
        "sectors": sorted({i["sector"] for i in manifest["inputs"]}),
        "inputs": [{"file": i.get("file"), "file_sha256": i.get("file_sha256"), "sector": i.get("sector")} for i in manifest["inputs"]],
        "config_sha256": manifest.get("config_sha256"), "code": manifest.get("code"), "created_at": manifest.get("created_at"),
        "panel": panel_mode(manifest),
        "count": dip_count([outcome_of(c) for c in cands]),
        "reproduce": f"setuhq run {spec['config']} --out runs/{spec['run']} && setuhq crossmatch runs/{spec['run']}",
    }
    if spec.get("lead"):
        entry["reproduce"] = "python scripts/rerun_pi_men.py --out runs/tess-pi-men-s1-new"
        entry["validation"] = spec["validation"]
        entry["outcome"] = "Rp/R★ and T14 within 5% of Huang et al. 2018 (docs/results/pi_men_validation.md)."
        entry["reference"] = "Huang et al. 2018"
        return entry
    if spec.get("toi"):
        fp = compare_fp(spec, cands, subjects)
        entry["false_positive"] = fp
        entry["reference"] = f"TOI table (NASA Exoplanet Archive): TOI-{spec['toi']} dispositioned {fp['disposition']}"
        verdict = ("rejected" if fp["outcomes"].get("rejected") and not fp["outcomes"].get("passed")
                   else "flagged" if fp["outcomes"].get("flagged") or fp["outcomes"].get("rejected") else "passed")
        if not fp["dips_on_ephemeris"]:
            entry["outcome"] = "No dip on the TOI's ephemeris: the panel did not mark its transits in this sector."
        elif verdict == "passed":
            entry["outcome"] = ("Its dips passed vetting: SetuHQ did not catch this known false positive here, and says so. "
                                f"Flags: {', '.join(fp['flags']) or 'none'}.")
        else:
            n = fp["dips_on_ephemeris"]
            entry["outcome"] = (f"Caught: {'all ' + str(n) + ' dips' if n > 1 else 'its dip'} on the TOI ephemeris "
                                f"{'were' if n > 1 else 'was'} {verdict} by vetting "
                                f"({', '.join(fp['flags']) or 'no flag'}), so none is a candidate.")
        return entry
    planets = []
    for name in spec["planets"]:
        rows = (reference.get("rows") or {}).get(name) or []
        planets.append(compare_planet(name, rows, spec["paper"], cands, subjects))
    entry["planets"] = planets
    ref = next((p["reference"] for p in planets if p.get("reference")), None)
    entry["reference"] = ref["label"] if ref else ""
    entry["reference_url"] = ref["url"] if ref else ""
    found = [p for p in planets if p.get("recovered_transits")]
    for p in planets:
        r = (p.get("ratio") or {}).get("period_days")
        p["period_recovered"] = bool(r and abs(r - 1) <= 0.02)
        # Dips whose stored BLS period is known not to be this planet's (a different one, or several disagreeing).
        p["period_wrong"] = bool(p.get("dip_ids")) and not p["period_recovered"] and bool(
            p.get("periods_each") or (p.get("setuhq") or {}).get("period_days"))
    entry["bls_period_not_planets"] = sorted({i for p in planets if p["period_wrong"] for i in p["dip_ids"]})

    def said(p):
        o = p.get("outcomes") or {}
        words = {"passed": ("candidate", "candidates"), "flagged": ("flagged", "flagged"), "rejected": ("rejected", "rejected")}
        return ", ".join(f"{v} {words[k][v != 1]}" for k, v in o.items())

    # Led by the transit counts, planet by planet; then what was not recovered.
    lines = []
    for p in planets:
        if not p.get("predicted_transits") and not p.get("dip_ids"):
            continue
        if p.get("recovered_transits"):
            note = ("no period" if not (p.get("setuhq") or {}).get("period_days") and not p.get("periods_each")
                    else "BLS period not the planet's" if p["period_wrong"] else "")
            lines.append(f"{p['planet']}: {p['recovered_transits']} of {p['predicted_transits']} transits ({said(p)}"
                         + (f"; {note}" if note else "") + ")")
        else:
            lines.append(f"{p['planet']}: none of {p['predicted_transits']} transits")
    entry["outcome"] = "; ".join(lines) + "."
    entry["caveat"] = caveat(planets)
    return entry


def caveat(planets: list[dict]) -> str:
    """One plain line on what this run did not recover, for every page that shows the run ('' when it recovered
    every predicted transit of every planet, with its period)."""
    short = {p["planet"]: p["planet"].split()[-1] for p in planets}
    parts = []
    found = [p for p in planets if p.get("recovered_transits")]
    if found and any(p["recovered_transits"] < p["predicted_transits"] or p["period_wrong"] or
                     not ((p.get("setuhq") or {}).get("period_days") or p.get("periods_each")) for p in found):
        bits = []
        for p in found:
            n, m, x = p["recovered_transits"], p["predicted_transits"], short[p["planet"]]
            bits.append(f"{n} of {x}'s {m} transits" if n != m else f"both of {x}'s" if n == 2 else f"all {n} of {x}'s transits")
        parts.append("found " + " and ".join(bits))
    missing = [p for p in planets if not p.get("recovered_transits") and p.get("predicted_transits")]
    if missing:
        parts.append(", ".join(short[p["planet"]] for p in missing) + " not found")
    noper = [p for p in found if not ((p.get("setuhq") or {}).get("period_days") or p.get("periods_each"))]
    for p in noper:
        parts.append(f"{short[p['planet']]} seen {'twice' if p['recovered_transits'] == 2 else str(p['recovered_transits']) + ' times'}, "
                     "no period (one transit per 13-day piece of the light curve)")
    wrong = [p for p in found if p["period_wrong"]]
    if wrong:
        parts.append(("neither published period was recovered" if len(wrong) == 2 and len(planets) == 2
                      else ", ".join(short[p["planet"]] for p in wrong) + ": published period not recovered")
                     + " (the BLS period on those dips is not the planet's)")
    if not parts:
        return ""
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def _f(x, d=3):
    return "n/a" if x is None else f"{x:,.{d}f}"


def markdown(e: dict, reference: dict) -> str:
    lines = [f"# {e['star']} against the literature", "", f"*{e['kind']}.* {e['summary']}", "",
             f"Run `runs/{e['run']}` (TESS SPOC 2-minute, sector{'s' if len(e['sectors']) != 1 else ''} "
             f"{', '.join(map(str, e['sectors']))}; config `{e['config']}`, sha256 `{(e['config_sha256'] or '')[:16]}…`; "
             f"code `{e.get('code') or 'not recorded'}`). Light curves: public TESS data from MAST "
             + "; ".join(f"`{i['file']}` (sha256 `{(i['file_sha256'] or '')[:16]}…`)" for i in e["inputs"]) + ".",
             "", f"**Probes only; Sentinels not run on this example.** {e['count'].capitalize()}.", "", e["why"], ""]
    if e.get("false_positive"):
        fp = e["false_positive"]
        p = fp["published"]
        lines += ["## The TOI table's values, and what SetuHQ did", "",
                  f"Source: {fp['toi_source']}.", "",
                  "| quantity | TOI table | SetuHQ |", "|---|---:|---:|",
                  f"| disposition | {fp['disposition']} | {e['outcome']} |",
                  f"| period (d) | {_f(p['period_days'], 5)} | {_f(fp['setuhq']['period_days'], 4)} (BLS) |",
                  f"| depth (ppm) | {_f(p['depth_ppm'], 0)} | {_f(fp['setuhq']['depth_ppm'], 0)} (box) |",
                  f"| T14 (h) | {_f(p['t14_hours'], 2)} | {_f(fp['setuhq']['t14_hours'], 2)} (fit) |",
                  f"| transits predicted in the data / with a dip | {fp['predicted_transits']} | {fp['recovered_transits']} |",
                  f"| dips on the ephemeris, by vetting outcome | | {', '.join(f'{v} {k}' for k, v in fp['outcomes'].items()) or 'none'} |",
                  f"| vetting flags on those dips | | {', '.join(f'`{x}`' for x in fp['flags']) or 'none'} |",
                  f"| secondary eclipse at phase 0.5, SNR (vetting's search) | | {_f(fp['setuhq']['secondary_snr'], 1)} |", ""]
        return "\n".join(lines) + "\n"
    lines += ["## Against the discovery paper", "",
              f"Published values: {reference['source']}, fetched {reference['fetched_at'][:10]} "
              "(`docs/results/showcase_reference.json`). Each planet's transits are predicted from the archive row named "
              "below; SetuHQ's values are the medians over the dips on that ephemeris that were not rejected (the "
              "limb-darkened fit's Rp/R★, T14 and mid-transit depth, and the BLS period). Depth definitions differ between "
              "papers and this fit, so compare Rp/R★ and T14 first. A blank published value is one the archive does not "
              "hold for that paper; it is not compared.", ""]
    for p in e["planets"]:
        ref = p.get("reference") or {}
        lines += [f"### {p['planet']}", ""]
        if p.get("note"):
            lines += [p["note"], ""]
            continue
        lines += [f"Ephemeris from {p['ephemeris_from']['label']}; compared with {ref.get('label') or 'no row of the discovery paper'}"
                  + (f" ({ref['url']})" if ref.get("url") else "") + ".", "",
                  ]
        dflt = p.get("archive_default")
        paper = (ref.get("label") or "discovery paper")
        head = f"| quantity | SetuHQ | {paper} | ratio |" + (f" archive default ({dflt['reference']['label']}) | ratio |" if dflt else "")
        lines += [head, "|---|---:|---:|---:|" + ("---:|---:|" if dflt else "")]
        names = {"period_days": ("P (d)", 5), "rp_rs": ("Rp/R★", 4), "t14_hours": ("T14 (h)", 2), "depth_ppm": ("depth (ppm)", 0)}
        for k, (lab, d) in names.items():
            ours = (", ".join(f"{x:.4f}" for x in p["periods_each"]) + " (one per dip, BLS; not one period)"
                    if k == "period_days" and p.get("periods_each") else _f(p['setuhq'].get(k), d))
            row = (f"| {lab} | {ours} | {_f(p['published'].get(k), d) if p['published'].get(k) else ''} | "
                   f"{_f(p['ratio'].get(k), 3) if p['ratio'].get(k) else ''} |")
            if dflt:
                v = dflt["values"].get(k)
                row += f" {_f(v, d) if v else ''} | {_f(dflt['ratio'].get(k), 3) if dflt['ratio'].get(k) else ''} |"
            lines.append(row)
        if not p["dips_on_ephemeris"]:
            lines += ["", "The panel marked no dip on this planet's transits in this run, so nothing is compared."]
        elif p.get("period_wrong"):
            got = ", ".join(f"{x:.4f}" for x in p["periods_each"]) if p.get("periods_each") else _f(p["setuhq"]["period_days"], 4)
            lines += ["", f"The BLS period stored on these dips ({got} d) is not this planet's: within a "
                          "13-day subject the search paired dips that belong to different transits (another planet's, or an alias), "
                          "so the period ratio is a miss, not a recovery, and the fit that used it (Rp/R★, depth) is less reliable "
                          "than its T14. The dips sit on the published ephemeris; the period does not."]
        elif p["setuhq"].get("period_days") is None:
            lines += ["", "Each 13-day subject holds only one of its transits, so the search found no period for these dips; vetting "
                          "flags each `off_ephemeris` (open, not a candidate). The period is not compared."]
        lines += ["", f"Transits predicted in the stored light curve: {p['predicted_transits']}; with a dip on them: "
                      f"{p['recovered_transits']} ({p['dips_on_ephemeris']} dip{'s' if p['dips_on_ephemeris'] != 1 else ''}; "
                      + (", ".join(f"{v} {k}" for k, v in p["outcomes"].items()) or "none")
                      + (f"; mean offset {p['mean_offset_min']:+.1f} min" if p.get("mean_offset_min") is not None else "") + ").", ""]
    lines += [f"A known planet found again is a check of the pipeline, not a discovery. {e['outcome']}", ""]
    return "\n".join(lines) + "\n"


def docs_page(entries: list[dict], reference: dict) -> str:
    """docs/SHOWCASE.md: each example, why it was chosen, its sectors, its comparison and how to reproduce it."""
    out = ["# Worked examples", "",
           "SetuHQ searches any TESS star. The site (setuhq.com) shows these stored runs as worked examples, each on public "
           "TESS SPOC 2-minute light curves from MAST, with its data hash, configuration hash and code fingerprint in its "
           "manifest. pi Men is one of them: the reference check against Huang et al. 2018.", "",
           "Every run but pi Men is **Probes only; Sentinels not run on this example**: its configuration names only the "
           "three Probes, and its manifest records `\"panel\": {\"mode\": \"probes_only\"}`. Sentinels run on Claude "
           "(Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter "
           "detectors.", "",
           "Dips are counted by their vetting outcome: a candidate (passed vetting) stays unconfirmed, a flagged dip is "
           "open, and a rejected dip is not a candidate. A known planet found again is a check of the pipeline, not a "
           "discovery; each planet is named with its reference.", "",
           f"Published values: {reference['source']}, fetched {reference['fetched_at'][:10]} "
           "(`docs/results/showcase_reference.json`); the comparisons are written by `scripts/showcase_compare.py`.", "",
           "| star | kind | sectors | dips | against the literature | site |", "|---|---|---|---|---|---|"]
    for e in entries:
        slug = re.sub(r"[^a-z0-9]+", "-", e["star"].lower()).strip("-")
        page = "/candidates/case-file/" if e.get("validation") else f"/candidates/{slug}/case-file/"
        out.append(f"| {e['star']} | {e['kind']} | {', '.join(map(str, e['sectors']))} | {e['count']} | {e['outcome']} | "
                   f"[case file](https://setuhq.com{page}) |")
    out.append("")
    for e in entries:
        detail = e.get("validation") or f"docs/results/showcase/{e['run']}.md"
        out += [f"## {e['star']}: {e['kind'].lower()}", "", e["summary"], "", f"**Why:** {e['why']}", "",
                f"**Run:** `runs/{e['run']}`, TESS sector{'s' if len(e['sectors']) != 1 else ''} {', '.join(map(str, e['sectors']))}; "
                f"{'Probes and Sentinels' if e['panel'] != 'probes_only' else 'Probes only; Sentinels not run on this example'}. "
                f"{e['count'].capitalize()}.", "",
                f"**Against the literature** ({e.get('reference') or 'see the table'}): {e['outcome']} The full comparison: "
                f"[{detail}]({detail}).", "",
                "**Reproduce:**", "", "```", e["reproduce"], "```", ""]
    out += ["Build the site from every run (the lead run first):", "", "```",
            "setuhq site " + " ".join(f"runs/{e['run']}" for e in [x for x in entries if x.get("validation")] + [x for x in entries if not x.get("validation")])
            + " --catalog docs/discoveries/catalog.json --out site", "```", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true", help="query the archive and store the rows first")
    ap.add_argument("--check", action="store_true", help="write nothing; fail when a stored output is not what the runs give")
    ap.add_argument("--partial", action="store_true", help="leave out the runs that are not stored yet (a preview)")
    args = ap.parse_args(argv)
    reference = fetch() if args.fetch and not args.check else json.loads(REFERENCE.read_text())
    missing = [spec["run"] for spec in RUNS if not (ROOT / "runs" / spec["run"] / "manifest.json").exists()]
    if missing and not args.partial:
        print(f"showcase_compare: runs not stored: {', '.join(missing)} (run them, or pass --partial)", file=sys.stderr)
        return 1
    entries = [run_entry(spec, reference) for spec in RUNS if spec["run"] not in missing]
    outputs = {MD_DIR / f"{e['run']}.md": markdown(e, reference) for e in entries if not e.get("validation")}
    doc = {"note": ("The worked examples the site shows, in its order, each compared with the literature "
                    "(scripts/showcase_compare.py). Probes only on every run but the lead (pi Men), which has the "
                    "Sentinels too. Known planets are named with their reference; SetuHQ's dips stay candidates."),
           "reference": str(REFERENCE.relative_to(ROOT)), "runs": entries}
    outputs[SHOWCASE] = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    outputs[ROOT / "docs/SHOWCASE.md"] = docs_page(entries, reference)
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p, text in outputs.items() if not p.exists() or p.read_text() != text]
        if stale:
            print(f"showcase_compare --check: not current: {', '.join(stale)} (run scripts/showcase_compare.py)", file=sys.stderr)
            return 1
        print(f"showcase_compare --check: {len(outputs)} files current")
        return 0
    MD_DIR.mkdir(parents=True, exist_ok=True)
    for p, text in outputs.items():
        p.write_text(text)
    for e in entries:
        print(f"{e['star']:10s} {e['count']:45s} {e['outcome']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
