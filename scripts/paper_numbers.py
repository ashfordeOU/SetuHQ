#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Every number in the methods paper, generated from the committed results; then the paper itself.

    python scripts/paper_numbers.py           # writes docs/paper/numbers.json and docs/paper/paper.md
    python scripts/paper_numbers.py --check   # exit 1 if either differs from what the committed JSON gives

The paper's source is docs/paper/paper.template.md. It holds no result: each number is a ``{{key}}`` placeholder
filled from this script's table, which reads only committed files (docs/results/*.json, the stored injection report,
docs/leaderboard/leaderboard.json, docs/paper/references.json, and the method constants in the code and configs).
A re-run after the results change updates the paper; tests/test_paper.py checks the paper against the JSON.

**Pending results.** Three pieces of later work will change numbers in the paper. Each has a stated file; until
that file exists its placeholders print as *pending*, never a guess:

* the clipping-fixed re-run of the stars exposed to the preprocess clipping bug
  (``docs/results/benchmark_real_tois_clipfix.json``, the benchmark report's schema);
* the stricter discovery-feed rule, chosen on the tuning half and measured once on the held-out half
  (``docs/results/feed_rule_validation.json``);
* the S2–S4 pixel-level vetting and false-positive-probability work
  (``docs/results/pixel_vetting.json`` and ``docs/results/fpp_validation.json``).

A file that exists but lacks a stated key also prints *pending*, naming the key, and the script warns.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import re
import urllib.parse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PAPER = Path("docs/paper")
TEMPLATE = PAPER / "paper.template.md"
OUT_MD = PAPER / "paper.md"
OUT_JSON = PAPER / "numbers.json"
BENCHMARK = Path("docs/results/benchmark_real_tois.json")
SAMPLE = Path("docs/results/benchmark_toi_sample.json")
PI_MEN = Path("docs/results/pi_men_validation.json")
INJECTION = Path("docs/results/injection_recovery_simulated_panel.md")
CALIBRATION = Path("docs/results/reviewer_weights_full_panel.calibration.json")
LEADERBOARD = Path("docs/leaderboard/leaderboard.json")
REFERENCES = PAPER / "references.json"

# The later work that will change the paper: where its result will be, and which keys the paper reads from it.
PENDING = {
    "clipfix": {"label": "clipping-fixed re-run", "file": "docs/results/benchmark_real_tois_clipfix.json",
                "keys": {"clipfix_completeness": ("summary.held_out.completeness", "pct"),
                         "clipfix_fp_seen": ("summary.held_out.fp_seen", "pct"),
                         "clipfix_fp_flagged": ("summary.held_out.fp_flagged_of_seen", "pct"),
                         "clipfix_feed_inverted": ("summary.held_out.feed.inverted.new_signals_per_1000", "int"),
                         "clipfix_feed_scrambled": ("summary.held_out.feed.scrambled.new_signals_per_1000", "int"),
                         "clipfix_code": ("code_commit", "commit")}},
    "feedrule": {"label": "stricter feed rule", "file": "docs/results/feed_rule_validation.json",
                 "keys": {"feedrule_rule": ("rule", "rule"),
                          "feedrule_inverted": ("held_out.inverted.new_signals_per_1000", "int"),
                          "feedrule_scrambled": ("held_out.scrambled.new_signals_per_1000", "int"),
                          "feedrule_completeness": ("held_out.completeness", "pct"),
                          "feedrule_per100": ("held_out.expected_false_per_100_targets", "f1")}},
    "pixel": {"label": "S2 pixel vetting", "file": "docs/results/pixel_vetting.json",
              "keys": {"pixel_fp_flagged": ("held_out.fp_flagged", "pct"),
                       "pixel_cpkp_flagged": ("held_out.cp_kp_flagged", "pct")}},
    "fpp": {"label": "S3 FPP", "file": "docs/results/fpp_validation.json",
            "keys": {"fpp_fp_validated": ("held_out.fp_validated", "pct"),
                     "fpp_cpkp_likely": ("held_out.cp_kp_likely_planet", "pct")}},
}


# ---------- formatting ----------
def pct(r: dict | None, ci: bool = True) -> str:
    if not r or r.get("rate") is None:
        return "n/a"
    s = f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']}"
    return s + (f"; 95% CI {100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)" if ci else ")")


class ClaimFailed(AssertionError):
    """The data no longer supports a sentence of the paper: change the text, do not print it."""


def claim(condition: bool, what: str) -> None:
    if not condition:
        raise ClaimFailed(f"the committed data no longer supports this claim in the paper: {what}")


def rate(k: int, n: int) -> dict:
    from setuhq.benchmark_toi import wilson

    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "lo": lo, "hi": hi}


def small_rate_of(summary: dict) -> dict:
    sel = [b for b in summary["completeness_by_radius"] if b["bin"][1] <= 4]
    return rate(sum(b["k"] for b in sel), sum(b["n"] for b in sel))


def p0(x: float) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def get(d, path: str):
    for part in path.split("."):
        if not isinstance(d, dict) or part not in d:
            raise KeyError(path)
        d = d[part]
    return d


def fmt(v, kind: str) -> str:
    if kind == "pct":
        return pct(v)
    if kind == "int":
        return f"{v:.0f}"
    if kind == "f1":
        return f"{v:.1f}"
    if kind == "commit":
        return str(v)[:7]
    if kind == "rule" and isinstance(v, dict):  # a feed rule as stored in docs/results/feed_rule_validation.json
        two = (f"the signal in both reviewed sectors, periods within {100 * v['period_tol']:g}%; "
               if v.get("name") == "two_sector" else "")
        return f"{two}FAP < {v['fap_cut']:g} over {v['fap_trials']:,} trials"
    return str(v)


def pending_numbers(root: Path) -> tuple[dict, dict]:
    """The pending placeholders: filled from their file when it exists and has the key, else marked pending."""
    out, status = {}, {}
    for name, spec in PENDING.items():
        path = root / spec["file"]
        data = json.loads(path.read_text()) if path.exists() else None
        status[name] = {"label": spec["label"], "file": spec["file"], "present": data is not None, "missing_keys": []}
        for key, (jpath, kind) in spec["keys"].items():
            if data is None:
                out[key] = f"*pending: {spec['label']}*"
                continue
            try:
                out[key] = fmt(get(data, jpath), kind)
            except KeyError:
                status[name]["missing_keys"].append(jpath)
                out[key] = f"*pending: {spec['label']} (no `{jpath}` yet)*"
        status[name]["filled"] = data is not None and not status[name]["missing_keys"]
        if data is not None and status[name]["missing_keys"]:
            print(f"warning: {spec['file']} lacks {', '.join(status[name]['missing_keys'])}; those numbers stay pending",
                  file=sys.stderr)
    return out, status


def injection_table(text: str) -> dict:
    """The committed injection-recovery report's grid (depth, duration → k/n) and its false-positive line."""
    grid = {}
    for m in re.finditer(r"^\| (\d+) \| ([\d.]+) \| (\d+) \| (\d+) \| [\d.]+ \|$", text, re.M):
        grid[(int(m.group(1)), float(m.group(2)))] = (int(m.group(4)), int(m.group(3)))
    fp = re.search(r"False positives: ([\d.]+) vetted candidates per empty subject \((\d+) empty subjects\)", text)
    return {"grid": grid, "fp_per_empty": float(fp.group(1)), "n_empty": int(fp.group(2))}


# ---------- the table ----------
def numbers(root: Path = ROOT) -> tuple[dict, dict]:
    from setuhq import aggregate, calibrate, discover, search, transitfit, vet
    from setuhq import leaderboard as L
    from setuhq.benchmark_toi import FEED_SECTORS_PER_TARGET, wilson
    from setuhq.reviewers.claude import PROMPT_VERSION

    B = json.loads((root / BENCHMARK).read_text())
    P = json.loads((root / PI_MEN).read_text())
    C = json.loads((root / CALIBRATION).read_text())
    LB = json.loads((root / LEADERBOARD).read_text())
    R = json.loads((root / REFERENCES).read_text())
    inj = injection_table((root / INJECTION).read_text())
    cfg = tomllib.loads((root / "configs/default.toml").read_text())
    disc = tomllib.loads((root / "configs/discovery.toml").read_text())
    h, t, a = B["summary"]["held_out"], B["summary"]["tuning"], B["summary"]["all"]
    hu = B["summary_unaffected"]["held_out"]
    s = B["sample"]
    n = {}

    # The sample and the split.
    n.update(sample_total=sum(s["counts"].values()), sample_pos=s["counts"]["positive"], sample_fp=s["counts"]["fp"],
             sample_fa=s["counts"]["fa"], sample_seed=s["seed"], sample_fetched=s["fetched_at"][:10],
             sample_sha=s["sha256"], sample_sha16=s["sha256"][:16], stars_run=B["stars_run"])
    lo_p, hi_p = re.search(r"([\d.]+) ≤ P ≤ ([\d.]+) d", s["rule"]).groups()
    n.update(period_lo=lo_p, period_hi=hi_p)
    loss = B["loss"]
    for half in ("held_out", "tuning"):
        for c in ("positive", "fp", "fa"):
            lc = loss[half][c]
            n[f"{half}_{c}_n"], n[f"{half}_{c}_data"], n[f"{half}_{c}_ns"] = lc["n"], lc["data"], lc["not_searchable"]
            n[f"{half}_{c}_ns_pct"] = p0(lc["not_searchable"] / lc["n"]) if lc["n"] else "n/a"
    n["held_out_total"] = sum(loss["held_out"][c]["n"] for c in ("positive", "fp", "fa"))
    n["held_out_searched"] = sum(loss["held_out"][c]["data"] for c in ("positive", "fp", "fa"))
    n["held_out_not_searchable"] = h["no_data"]
    n["held_out_failed"] = h["failed"]

    # Held-out headline results.
    n.update(ho_completeness=pct(h["completeness"]), ho_completeness_all=pct(h["completeness_all_stars"]),
             ho_completeness_rate=p0(h["completeness"]["rate"]), ho_fp_seen=pct(h["fp_seen"]),
             ho_fp_flagged=pct(h["fp_flagged_of_seen"]), ho_pos_flagged=pct(h["pos_flagged"]), ho_fa_seen=pct(h["fa_seen"]),
             ho_fp_passed=pct(h["fp_passed_unflagged"]),
             ho_depth_ratio=f"{h['depth_ratio_median']:.2f}", ho_duration_ratio=f"{h['duration_ratio_median']:.2f}")

    # From the per-star rows: how the recovered CP/KP signals were found, and completeness in the radius bins
    # Planet Hunters TESS used (3–4 R⊕ and above 4 R⊕).
    tois = {t["toi"]: t for t in json.loads((root / SAMPLE).read_text())["tois"]}
    pos = [r for r in B["per_star"] if r.get("real") and tois[r["toi"]]["half"] == "held_out" and tois[r["toi"]]["class"] == "positive"]
    rec = [r for r in pos if r["real"]["recovered"]]
    n.update(ho_rec_at_p=sum(r["real"]["period_alias"] == "P" for r in rec),
             ho_rec_alias=sum(r["real"]["period_alias"] not in ("P", None) for r in rec),
             ho_rec_noperiod=sum(r["real"]["period_alias"] is None for r in rec),
             ho_rec_total=len(rec), ho_not_rec=len(pos) - len(rec), ho_pos_searched=len(pos))
    claim(len(pos) == h["completeness"]["n"] and len(rec) == h["completeness"]["k"], "per-star rows disagree with the summary")

    def radius_rate(lo_r, hi_r):
        sel = [r for r in pos if tois[r["toi"]].get("radius_re") is not None and lo_r <= tois[r["toi"]]["radius_re"] < hi_r]
        return rate(sum(r["real"]["recovered"] for r in sel), len(sel))

    pht_mid, pht_large = radius_rate(3, 4), radius_rate(4, math.inf)
    n.update(ho_rad_3to4=pct(pht_mid), ho_rad_above4=pct(pht_large))
    vals = R["values"]

    def against(ours: dict, ref_key: str) -> str:
        """How an SetuHQ rate stands against a published one: below or above only when its interval excludes it."""
        ref = vals[ref_key]["value"]
        claim(ours["rate"] is not None, f"no stars in the bin compared with {ref_key}")
        if ours["hi"] < ref:
            return "significantly below"
        if ours["lo"] > ref:
            return "significantly above"
        return "consistent with"

    n.update(cmp_pht_mid=against(pht_mid, "pht_mid"), cmp_pht_large=against(pht_large, "pht_large"),
             cmp_robo=against(h["completeness"], "robovetter_completeness"))
    rows = {"3 to 4 R⊕": n["cmp_pht_mid"], "above 4 R⊕": n["cmp_pht_large"]}
    n["cmp_pht_sentence"] = "; ".join(f"{k}, {v} Planet Hunters TESS's rate" for k, v in rows.items())
    n["cmp_pht_note"] = (f" With {pht_mid['n']} stars in the 3 to 4 R⊕ bin the interval cannot tell the two apart."
                         if n["cmp_pht_mid"] == "consistent with" else "")
    # The qualitative claims the text makes about these numbers: the script fails rather than print them untrue.
    small = small_rate_of(h)
    claim(small["rate"] is not None and small["rate"] < h["completeness"]["rate"] - 0.2,
          "the text says completeness is low for small planets")
    claim(n["cmp_robo"] == "significantly below", "the text says completeness is below the Robovetter's")
    names = {(0, 2): "r0", (2, 4): "r1", (4, 8): "r2", (8, 30): "r3"}
    for b in h["completeness_by_radius"]:
        n[f"ho_rad_{names[tuple(b['bin'])]}"] = pct(b)
        n[f"ho_rad_{names[tuple(b['bin'])]}_rate"] = p0(b["rate"])
        n[f"ho_rad_{names[tuple(b['bin'])]}_bin"] = (f"below {b['bin'][1]:g} R⊕" if b["bin"][0] == 0
                                                       else f"{b['bin'][0]:g} to {b['bin'][1]:g} R⊕")
    small = [b for b in h["completeness_by_radius"] if b["bin"][1] <= 4]
    k4, n4 = sum(b["k"] for b in small), sum(b["n"] for b in small)
    pr, lo, hi = wilson(k4, n4)
    n["ho_rad_small"] = pct({"k": k4, "n": n4, "rate": pr, "lo": lo, "hi": hi})
    n["ho_rad_small_bin"] = f"below {small[-1]['bin'][1]:g} R⊕"
    n["ho_rad_small_bin_cap"] = f"Below {small[-1]['bin'][1]:g} R⊕"
    for i, b in enumerate(h["completeness_by_period"]):
        n[f"ho_per_{i}"] = pct(b)
        n[f"ho_per_{i}_bin"] = f"{b['bin'][0]:g}–{b['bin'][1]:g} d"
    for v in ("inverted", "scrambled"):
        c = h["controls"][v]
        n.update({f"ho_{v}_dips": c["vetted_false_alarms"], f"ho_{v}_ss": c["star_sectors"],
                  f"ho_{v}_per1000": f"{c['per_1000_star_sectors']:.0f}", f"ho_{v}_any": pct(c["stars_with_any"]),
                  f"ho_{v}_periodic": c["kinds"]["periodic"], f"ho_{v}_single": c["kinds"]["single"]})
        f = h["feed"][v]
        n.update({f"feed_{v}_new": f["new_signals"], f"feed_{v}_per1000": f"{f['new_signals_per_1000']:.0f}",
                  f"feed_{v}_any": pct(f["stars_with_new"]), f"feed_{v}_admitted": f["admitted"], f"feed_{v}_prefap": f["pre_fap"]})
    fr = h["feed"]["real"]
    n.update(feed_real_new=fr["new_signals"], feed_real_per1000=f"{fr['new_signals_per_1000']:.0f}", feed_real_admitted=fr["admitted"],
             feed_real_known=fr["known_toi_entries"], feed_ss=fr["star_sectors"])
    imp = B["feed_implication"]
    n.update(feed_expected_per100=f"{imp['expected_false_per_100_targets']:.1f}",
             feed_live_per100=f"{imp['live_new_signals_per_100_targets']:.1f}",
             feed_live_ci=f"{imp['live_ci_per_100_targets'][0]:.0f}–{imp['live_ci_per_100_targets'][1]:.0f}",
             feed_live_new=imp["live"]["new_signals"], feed_live_targets=imp["live"]["targets_reviewed"],
             feed_live_updated=imp["live"]["updated"][:10], feed_sectors_per_target=FEED_SECTORS_PER_TARGET,
             feed_worst_per1000=f"{max(imp['control_new_signals_per_1000'].values()):.0f}",
             feed_bad="consistent with noise" if imp["bad"] else "not explained by noise alone",
             feed_fap_trials=f"{disc['search']['fap_trials']:,}")
    # The rule the benchmark's feed-level table applied: the earlier one, as the feed-rule evaluation records it once the
    # feed has moved on to the pre-registered rule; until then, the discovery config's own.
    fr_path = root / "docs/results/feed_rule_validation.json"
    old = json.loads(fr_path.read_text())["held_out_old_rule"]["rule"] if fr_path.exists() else None
    if fr_path.exists():
        v = json.loads(fr_path.read_text())
        ho, oo = v["held_out"], v["held_out_old_rule"]
        n["feedrule_intro"] = (f"It was chosen on the tuning half only, pre-registered at commit `{v['preregistration_commit'][:7]}`, and "
                               "measured once on the held-out half with the discovery config itself "
                               "(docs/results/feed_rule_validation.json):")
        claim(ho["expected_false_per_100_targets"] > ho["real_new_per_100_targets"],
              "the feed-rule sentence says noise still outnumbers the real new signals")
        n["feedrule_after"] = (
            f"On the same evaluation the earlier rule gives {oo['expected_false_per_100_targets']:.1f} false signals per 100 targets: "
            f"the new rule lowers the noise {oo['expected_false_per_100_targets'] / ho['expected_false_per_100_targets']:.1f}-fold"
            + (" (the 95% intervals do not overlap)" if v.get("fix_clearly_lowers_noise") else " (the 95% intervals overlap)")
            + f", but noise still outnumbers the {ho['real_new_per_100_targets']:.1f} real new signals per 100 targets, and "
            f"feed-level completeness falls from {100 * oo['completeness']['rate']:.0f}% to {100 * ho['completeness']['rate']:.0f}%. "
            "A feed admission is a lead for review, not a candidate of any confirmed status.")
    else:
        n["feedrule_intro"] = "It is to be chosen on the tuning half and measured once on the held-out half:"
        n["feedrule_after"] = ""
    n.update(bench_feed_fap_trials=f"{(old or {}).get('fap_trials', disc['search']['fap_trials']):,}",
             bench_feed_fap=f"{(old or {}).get('fap_cut', discover.MAX_FEED_FAP):g}")
    ratio = imp["expected_false_per_100_targets"] / imp["live_new_signals_per_100_targets"]
    claim(imp["bad"] == (ratio >= 0.5), "the report's 'bad' verdict is expected ≥ half the live rate")
    n["feed_ratio"] = f"{ratio:.2f}"
    n["feed_half_sentence"] = (
        f"Noise alone would account for {ratio:.2f} of that rate, at least half, so a `new_candidate` on the feed is more "
        "likely noise than a signal." if ratio >= 0.5 else
        f"Noise alone would account for {ratio:.2f} of that rate, less than half.")
    ns = B["loss"]["held_out"]
    skew = ns["fp"]["not_searchable"] / ns["fp"]["n"] - ns["positive"]["not_searchable"] / ns["positive"]["n"]
    claim(skew >= 0.10, "the text says the unsearchable stars are skewed toward FP")
    n["skew_points"] = f"{100 * skew:.0f}"

    # Tuning half and whole sample (reported, never used to choose a threshold).
    n.update(tu_completeness=pct(t["completeness"]), all_completeness=pct(a["completeness"]),
             all_fp_seen=pct(a["fp_seen"]), all_fp_flagged=pct(a["fp_flagged_of_seen"]), all_no_data=a["no_data"])

    # The clipping bug.
    cl = B["clipping"]
    ch = cl["held_out"]
    n.update(clip_ratio=f"{cl['ratio']:g}", clip_pos=ch["affected"]["positive"], clip_fp=ch["affected"]["fp"],
             clip_fa=ch["affected"]["fa"], clip_measured=ch["measured"], clip_recovered=ch["cp_kp_affected_recovered"],
             clip_missed=ch["cp_kp_affected_missed"], clip_explained=ch["cp_kp_misses_explained"],
             clip_tois=", ".join(ch["explained_tois"]), clip_median_removed=p0(ch["median_removed_fraction_affected"]),
             clip_unaff_completeness=pct(hu["completeness"]), clip_unaff_fp_seen=pct(hu["fp_seen"]),
             clip_unaff_fp_flagged=pct(hu["fp_flagged_of_seen"]),
             clip_unaff_feed_inverted=f"{hu['feed']['inverted']['new_signals_per_1000']:.0f}",
             clip_unaff_feed_scrambled=f"{hu['feed']['scrambled']['new_signals_per_1000']:.0f}",
             clip_tuning_explained=B["clipping"]["tuning"]["cp_kp_misses_explained"],
             clip_tuning_missed=B["clipping"]["tuning"]["cp_kp_affected_missed"])

    # The Sentinels.
    se = B["sentinels"]
    for pid, key in (("claude-volunteer", "vol"), ("claude-skeptic", "skp")):
        v = se["personas"][pid]
        n.update({f"sen_{key}_cpkp": pct(v["cp_kp_marked"]), f"sen_{key}_fp": pct(v["fp_marked_as_planet"]),
                  f"sen_{key}_errors": v["errors"]})
    n.update(sen_n=se["n_stars"], sen_agree=se["agreement"]["agree"], sen_agree_n=se["agreement"]["n"],
             sen_phi=f"{se['agreement']['phi']:.2f}", sen_per_class=se["n_stars"] // 2, sen_prompt=PROMPT_VERSION)
    claim(se["agreement"]["phi"] >= 0.7, "the text says the two personas count as one correlated voter (φ ≥ 0.7)")

    # Code version and the threshold audit.
    ta, cp = B["threshold_audit"], B["code_provenance"]
    n.update(code_commit=B["code_commit"][:7], code_commit_full=B["code_commit"], audit_values=ta["values_checked"],
             audit_frozen=ta["frozen_after"], audit_changed=len(ta["changed"]), audit_clean="clean" if ta["clean"] else "NOT clean",
             audit_commits=len(ta["commits_since"]), generated_at=B["generated_at"][:10],
             code_fingerprints="; ".join(f"`{fp}` = commit {c}" + (" (HEAD differs only in comments and docstrings)"
                                                                  if cp["head_same_behaviour"].get(fp) else "")
                                         for fp, c in cp["commit"].items()))

    # pi Men c.
    jf, jp, hu18 = P["joint_fit"], P["joint_fit_density_prior"], P["huang_2018"]
    rh = P["ratios_vs_huang_2018"]
    n.update(pm_epochs=P["epochs_recovered"], pm_epochs_pred=P["epochs_predicted"],
             pm_k=f"{jf['k']:.4f} ± {jf['k_err']:.4f}", pm_k_ratio=f"{rh['k']:.2f}", pm_k_huang=f"{hu18['pl_ratror']:.5f}",
             pm_t14=f"{jf['t14_hours']:.2f} ± {jf['t14_err_hours']:.2f}", pm_t14_ratio=f"{rh['duration']:.2f}",
             pm_t14_huang=f"{hu18['pl_trandur']:.3f}",
             pm_depth=f"{jf['depth_ppm']:.0f} ± {jf['depth_err_ppm']:.0f}", pm_depth_ratio=f"{rh['depth']:.2f}",
             pm_depth_huang=f"{1e6 * hu18['pl_trandep'] / 100:.0f}",
             pm_period=f"{jf['period_days']:.4f} ± {jf['period_err']:.4f}", pm_period_huang=f"{hu18['pl_orbper']:.5f}",
             pm_b_upper=f"{jf['b_range'][1]:.2f}", pm_b_prior=f"{jp['b']:.2f} ± {jp['b_err']:.2f}", pm_b_huang=f"{hu18['pl_imppar']:.2f}",
             pm_ars_prior=f"{jp['a_rs']:.2f}", pm_ars_range=f"{jp['a_rs_range'][0]:.1f} to {jp['a_rs_range'][1]:.1f}",
             pm_ars_huang=f"{hu18['pl_ratdor']:.2f}", pm_t23=f"{jp['t23_over_t14']:.2f}",
             pm_rho_range=f"{jf['rho_range'][0]:.2f} to {jf['rho_range'][1]:.1f}",
             pm_rho_prior=f"{jp['rho_prior'][0]:.2f} ± {jp['rho_prior'][1]:.2f}",
             pm_box_depth=f"{rh['box_depth']:.2f}", pm_box_duration=f"{rh['box_duration']:.2f}",
             pm_u1=f"{P['ld'][0]:.3f}", pm_u2=f"{P['ld'][1]:.3f}", pm_teff=f"{P['star']['teff']:.0f}",
             pm_logg=f"{P['star']['logg']:.2f}")
    cands = json.loads((root / "runs/tess-pi-men-s1/candidates.json").read_text())
    faps = [c for c in cands if c.get("fap_trials")]
    n.update(pm_fap_trials=f"{max(c['fap_trials'] for c in faps):,}", pm_fap_bound="10" + str(round(math.log10(min(c["fap"] for c in faps)))).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")),
             pm_fap_exceed=max(c["fap_exceed"] for c in faps))

    # Injection recovery and calibration.
    g = inj["grid"]
    durs = sorted({d for _, d in g})
    n["inj_grid"] = "; ".join(f"{dep:,} ppm: " + ", ".join(f"{g[(dep, d)][0]}/{g[(dep, d)][1]}" for d in durs)
                              for dep in sorted({dep for dep, _ in g}))
    n["inj_durations"] = ", ".join(f"{d:g}" for d in durs[:-1]) + f" and {durs[-1]:g} h"
    n.update(inj_fp=f"{inj['fp_per_empty']:.3f}", inj_empty=inj["n_empty"])
    claim(1000 * inj["fp_per_empty"] < h["controls"]["inverted"]["per_1000_star_sectors"],
          "the text says the synthetic empty-subject rate is below the real-data controls'")
    claim(min(h["controls"][v]["per_1000_star_sectors"] for v in ("inverted", "scrambled")) > 1
          and min(h["feed"][v]["new_signals_per_1000"] for v in ("inverted", "scrambled")) > 1,
          "the text says the control false-alarm rates are far above one per 1,000")
    cr = C["reviewers"]
    n.update(cal_n_inj=cr["claude-skeptic"]["n_injected"], cal_n_empty=cr["claude-skeptic"]["n_empty"],
             cal_sen_w=f"{cr['claude-skeptic']['weight']:.1f}",
             cal_probe_w=f"{min(cr[r]['weight'] for r in cr if r.startswith('volunteer-')):.1f} to "
                         f"{max(cr[r]['weight'] for r in cr if r.startswith('volunteer-')):.1f}",
             cal_floor=f"{C['floor']:g}")

    # Method constants, from the code and configs.
    ag = inspect.signature(aggregate.aggregate).parameters
    vt = inspect.signature(vet.vet_event).parameters
    n.update(m_subject_days=f"{cfg['run']['subject_days']:g}", m_bin=f"{cfg['run']['bin_minutes']:g}",
             m_detrend=f"{cfg['run']['detrend_window_days']:g}", m_gap=f"{ag['gap_days'].default:g}",
             m_min_score=f"{ag['min_score'].default:g}", m_min_planet=f"{ag['min_planet_fraction'].default:g}",
             m_min_snr=f"{vt['min_snr'].default:g}", m_min_dur=f"{vt['min_duration_minutes'].default:g}",
             m_edge=f"{vt['edge_days'].default:g}", m_sigma=f"{vt['sigma_threshold'].default:g}",
             m_rho_lo=f"{transitfit.RHO_BOUNDS[0]:g}", m_rho_hi=f"{transitfit.RHO_BOUNDS[1]:g}",
             m_fap_block=f"{search.FAP_BLOCK_DAYS:g}", m_fap_default=search.FAP_TRIALS, m_tail_floor="10⁻⁶" if search.FAP_TAIL_FLOOR == 1e-6 else f"{search.FAP_TAIL_FLOOR:g}",
             m_weight_floor=f"{calibrate.WEIGHT_FLOOR:g}", m_feed_depth=f"{discover.MAX_FEED_DEPTH_PPM:,.0f}",
             m_feed_transits=discover.MIN_FEED_TRANSITS, m_feed_fap=f"{discover.MAX_FEED_FAP:g}",
             m_feed_two_sector=(f", and the same signal (periods within {100 * discover.TWO_SECTOR_PERIOD_TOL:g}%) reaches these parts "
                                "of the rule in both reviewed sectors" if hasattr(discover, "TWO_SECTOR_PERIOD_TOL") else ""))

    # How the benchmark configured the panel (scripts/benchmark_real_tois.py).
    sys.path.insert(0, str(ROOT / "scripts"))
    import benchmark_real_tois as BR

    bc = BR._config()
    claim(bc.stellar == "none", "the text says the benchmark took stellar parameters from the TOI table, not a TIC query")
    # run_star writes stellar.json from the TOI table's own columns: Teff, log g, R★, and ρ★ when log g and R★ exist.
    searched = [tois[r["toi"]] for r in B["per_star"] if r.get("real") and tois[r["toi"]]["half"] == "held_out"]
    with_rho = sum(1 for t in searched if t.get("logg") and t.get("star_radius"))
    with_teff = sum(1 for t in searched if t.get("teff"))
    n.update(bench_with_rho=with_rho, bench_with_teff=with_teff, bench_searched=len(searched))
    n["bench_stellar_sentence"] = (
        "The benchmark runs did not query the TIC: each star's parameters came from the TOI table's own columns "
        f"(Teff, log g, R★). Limb darkening used Teff and log g (the Sun's values where missing; Teff was published for "
        f"{with_teff} of {len(searched)} searched held-out stars), and ρ★ was computed from log g and R★, so the density "
        f"test could act only on the {with_rho} stars with both.")
    n["bench_density_limit"] = (f"**The density test could act only on {with_rho} of {len(searched)} searched held-out stars,** those "
                                "whose TOI-table entry gives both log g and R★.")

    # The leaderboard's seeded scores.
    for e in LB["entries"]:
        key = f"lb_{e['id'].replace('-', '_')}"
        sc = e["scores"]
        sm = [b for b in sc["completeness_by_radius"] if b["bin"][1] <= 4]
        ks, ns = sum(b["k"] for b in sm), sum(b["n"] for b in sm)
        prs, los, his = wilson(ks, ns)
        ctl = lambda v: pct(sc["controls"][v]["stars_with_any"]) if sc["controls"][v] else "not measured"  # noqa: E731
        n.update({f"{key}_compl": pct(sc["completeness_all_stars"]), f"{key}_small": pct({"k": ks, "n": ns, "rate": prs, "lo": los, "hi": his}) if ns else "n/a",
                  f"{key}_fprej": pct(sc["fp_rejection"]), f"{key}_fprej_all": pct(sc["fp_rejection_all_stars"]),
                  f"{key}_rel": pct(sc["reliability"]), f"{key}_j": L.jtext(sc["youden_j"]),
                  f"{key}_j_all": L.jtext(sc["youden_j_all_stars"]), f"{key}_ccs": pct(sc["completeness_clean_searchable"]),
                  f"{key}_fprs": pct(sc["fp_rejection_searchable"]),
                  f"{key}_inv": ctl("inverted"), f"{key}_scr": ctl("scrambled"),
                  f"{key}_rank": e["rank"] if e["ranked"] else f"unranked ({e['unranked_reason']})"})
    claim(all(e["rank"] is None for e in LB["entries"] if e["scope"] == "sentinel_subsample"),
          "the text says the subsample is never ranked")
    fl = LB.get("floor")
    claim(fl is not None, "the text compares the Probes with the metadata-only floor")
    # The interpretation rests on the paired ΔJ (floor − Probes) over the same stars, not on whether the two marginal
    # intervals overlap; the sentence is the leaderboard's own, so the paper and the page cannot disagree.
    claim(fl["verdict"] == ("floor_ahead" if fl["paired"]["lo"] > 0 else "probes_ahead" if fl["paired"]["hi"] < 0 else "not_shown"),
          "the floor verdict follows the paired ΔJ interval")
    claim(LB["floor_note"] == L.floor_note(fl), "the leaderboard's floor note is the one the paper prints")
    n["floor_sentence"] = LB["floor_note"]
    n["floor_dj"] = L.dj_text(fl["paired"])
    n["floor_short"] = {"floor_ahead": "the floor is significantly ahead of the Probes",
                        "probes_ahead": "the Probes are significantly ahead of the floor",
                        "not_shown": "the benchmark cannot show that the Probes beat it"}[fl["verdict"]]
    n["floor_draws"] = f"{fl['paired']['draws']:,}"
    n.update(lb_inputs_sha=LB["inputs_sha256"], lb_entries=len(LB["entries"]), lb_refused=len(LB["refused"]),
             lb_mix_pos=next(e for e in LB["entries"] if e["id"] == "probes")["scores"]["reliability_mix"]["positive"],
             lb_mix_fp=next(e for e in LB["entries"] if e["id"] == "probes")["scores"]["reliability_mix"]["fp"],
             lb_mix_fa=next(e for e in LB["entries"] if e["id"] == "probes")["scores"]["reliability_mix"]["fa"])
    # Do the subsample entries' completeness intervals all overlap? (Then the subsample cannot order them.)
    sub = [e["scores"]["completeness_all_stars"] for e in LB["entries"] if e["scope"] == "sentinel_subsample"]
    overlap = all(a["lo"] <= b["hi"] and b["lo"] <= a["hi"] for a in sub for b in sub)
    n["lb_subsample_overlap"] = ("every pair of their completeness intervals overlaps"
                                 if overlap else "not every pair of their completeness intervals overlaps")

    # Published reference values, with their citations.
    for k, v in R["values"].items():
        n[f"ref_{k}"] = v["text"]
    for k, v in R["refs"].items():
        n[f"cite_{k}"] = v["cite"]
    n["references"] = bibliography(R)

    pend, status = pending_numbers(root)
    n.update(pend)
    n["pending_list"] = "\n".join(f"* **{s['label']}**: " + ("filled from " if s["filled"] else "pending; will be read from ")
                                  + f"`{s['file']}`." for s in status.values())
    return n, status


def bibliography(R: dict) -> str:
    rows = []
    for k, v in sorted(R["refs"].items(), key=lambda kv: (kv[1]["authors"], kv[1]["year"])):
        where = ", ".join(x for x in (v["journal"], v["volume"], v["page"]) if x)
        doi = (f" doi:[{v['doi']}](https://doi.org/{urllib.parse.quote(v['doi'], safe='/:;().-_')})" if v["doi"] else "")
        rows.append(f"* {v['authors']} {v['year']}, {v['title']}. {where}.{doi}")
    return "\n".join(rows)


PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")


def render(template: str, n: dict) -> str:
    missing = sorted({m for m in PLACEHOLDER.findall(template) if m not in n})
    if missing:
        raise KeyError(f"the template uses unknown numbers: {', '.join(missing)}")
    return PLACEHOLDER.sub(lambda m: str(n[m.group(1)]), template)


def build(root: Path = ROOT) -> tuple[str, str]:
    n, status = numbers(root)
    paper = render((root / TEMPLATE).read_text(), n)
    used = sorted(set(PLACEHOLDER.findall((root / TEMPLATE).read_text())))
    payload = {"generated_from": [str(p) for p in (BENCHMARK, PI_MEN, INJECTION, CALIBRATION, LEADERBOARD, REFERENCES)],
               "pending": status, "numbers": {k: n[k] for k in used}}
    return paper, json.dumps(payload, indent=1, ensure_ascii=False, default=str) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="fail when the committed paper or numbers differ from the JSON")
    args = ap.parse_args(argv)
    paper, nums = build(ROOT)
    if args.check:
        bad = [str(p) for p, text in ((OUT_MD, paper), (OUT_JSON, nums)) if (ROOT / p).read_text() != text]
        if bad:
            print(f"out of date: {', '.join(bad)}; run scripts/paper_numbers.py", file=sys.stderr)
            return 1
        print("paper numbers match the committed JSON")
        return 0
    (ROOT / OUT_MD).write_text(paper)
    (ROOT / OUT_JSON).write_text(nums)
    print(f"wrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
