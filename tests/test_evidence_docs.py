# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Phase 4 of the redesign: the Evidence pages (the panel's input to the ring, the benchmark's counters, the
leaderboard's interval bars, the runs' star discs), Docs, How the pictures are drawn, 404 and the forwarding pages."""
import re

from setuhq import app as A
from setuhq import site as S
from setuhq.design import TOKENS
from setuhq.looks import LOOKS
from setuhq.names import ATTRIBUTION


def test_the_benchmark_card_counts_with_intervals():
    b = A._load_benchmark()
    card = A._benchmark_card(b)
    assert "90 of 150 (52–67%)" in card and 'data-odo="60%"' in card
    h = b["summary"]["held_out"]
    for key in ("fp_seen", "fp_flagged_of_seen"):
        r = h[key]
        assert f"{r['k']} of {r['n']} ({100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)" in card
    assert f'data-odo="{sum(b["sample"]["counts"].values()):,}"' in card
    assert "not discoveries" in card


def test_the_leaderboard_bars_are_the_stored_intervals():
    lb = A._load_leaderboard()
    page = A._leaderboard(lb)
    bars = re.findall(r'<svg class="lbbar"[^>]*data-lo="([-\d.]+)" data-hi="([-\d.]+)" data-a="([-\d.]+)" data-b="([-\d.]+)">.*?'
                      r'<rect x="([\d.]+)" y="2" width="([\d.]+)"', page)
    assert len(bars) > 10
    for lo, hi, a, b, x, w in bars:
        lo, hi, a, b, x, w = map(float, (lo, hi, a, b, x, w))
        assert abs(x - A.LB_BAR_W * (lo - a) / (b - a)) < 0.01 and abs(x + w - A.LB_BAR_W * (hi - a) / (b - a)) < 0.02
    # Each held-out entry's clean completeness bar matches its stored lo–hi.
    for e in [x for x in lb["entries"] if x["scope"] == "held_out"]:
        r = e["scores"]["completeness_clean_searchable"]
        if r and r.get("lo") is not None:
            assert f'data-lo="{r["lo"]:.6f}" data-hi="{r["hi"]:.6f}"' in page
    assert lb["floor_note"] in page and ATTRIBUTION in page and "content-visibility:auto" in A.LEADERBOARD_CSS


def test_the_panel_ring_gets_every_stored_reviewer(tmp_path):
    story = {"reviewers": [{"id": "claude-skeptic", "name": "Sentinel · Skeptic", "role": "sentinel", "weight": 0.5},
                           {"id": "volunteer-typical", "name": "Probe · Typical", "role": "probe", "weight": 0.6}]}
    data = {"story": story, "run": {"name": "r", "reviewer_kinds": {"claude-skeptic": "claude", "volunteer-typical": "simulated"}},
            "reviewer_provenance": {"claude-skeptic": {"provider_label": "Claude (Anthropic)", "model": "m"}}, "weights_path": "w.json",
            "calibration": {"floor": 0.05, "record_path": "c.json"}}
    d = A.panel_ring_input(data)
    assert d["mode"] == "panel" and d["source"] and d["attribution"] == ATTRIBUTION and d["probes_only"] is False
    assert [r["id"] for r in d["reviewers"]] == ["claude-skeptic", "volunteer-typical"]
    assert d["reviewers"][0]["provider"] == "Claude (Anthropic)" and d["reviewers"][1]["weight"] == 0.6
    story["reviewers"] = story["reviewers"][1:]
    assert A.panel_ring_input(data)["probes_only"] is True


def test_the_runs_table_has_a_star_disc_per_run():
    data = {"showcase": [{"run": "r1", "star": "pi Men", "count": "7 dips", "inputs": [], "config_sha256": "a" * 64, "code": "x", "panel_label": "p"}],
            "run_ctx": {"r1": {"star_params": {"teff": 5992.1}}}}
    t = A._example_runs_table(data)
    assert 'class="stardisc"' in t and "TIC Teff 5,992 K" in t and ATTRIBUTION in t


def test_docs_link_the_pictures_and_the_pictures_page_is_complete():
    assert 'href="/docs/pictures/"' in S.docs_section({"run": {"name": "r"}, "showcase": []})
    p = S.pictures_section()
    rows = re.findall(r'<tr data-look="([\w-]+)">', p)
    assert rows == list(LOOKS) and len(rows) == 18
    assert p.count('data-render="planet"') == 18
    for lab in ("Artist's impression", "Model from stored values", "Real data, cited", "Illustration", "Speculative model"):
        assert lab.replace("'", "&#x27;") in p
    assert "rgb(255, 241, 234)" in p
    assert not re.search(r"\bhabitable\b(?!-zone)", p.lower().replace("not habitable", ""))  # the zone is named, never a planet
    assert "With reduced motion" in p and "two panels side by side" in p


def test_not_found_and_forwarding_pages():
    nf = S.notfound_section()
    for h in ("/", "/explore/", "/candidates/", "/how-it-works/", "/evidence/", "/docs/"):
        assert f'href="{h}"' in nf or h == "/"
    f = S.forward_page("/evidence/", "The panel")
    assert TOKENS["bg"][0] in f and TOKENS["sen"][0] in f and "This page has moved." in f
    assert "<link rel=\"stylesheet\"" not in f and "src=\"http" not in f
