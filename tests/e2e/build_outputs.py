# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Build the five CLI outputs that write HTML from the stored lead run, for tests/e2e/checks/outputs.mjs:

    python tests/e2e/build_outputs.py OUT_DIR [--deep]

writes OUT_DIR/{report,dashboard,docket,plate,discover}/index.html through the commands' own code paths
(`setuhq report`, `dashboard`, `docket`, `plate`; the search feed page `setuhq discover` writes after its batch,
built here from the committed feed without running a batch). Nothing is fetched: the stored cross-match is used.

--deep reads the run and the feed through a directory nested more than 120 characters deep (a link back to this
checkout, outside it), so every path a page prints is long and absolute: the check that no page then
scrolls sideways on a phone holds for any checkout path.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from setuhq.cli import main  # noqa: E402
from setuhq.report import build_discovery_site  # noqa: E402


RUN = str(ROOT / "runs" / "tess-pi-men-s1")
FEED = str(ROOT / "docs" / "discoveries" / "catalog.json")
DEEP = "/".join(["a-deliberately-long-checkout-folder-name"] * 4)  # 167 characters


def build(out: Path, deep: bool = False) -> None:
    global RUN, FEED
    out.mkdir(parents=True, exist_ok=True)
    if deep:
        nest = out.resolve() / DEEP
        nest.mkdir(parents=True, exist_ok=True)
        link = nest / "SetuHQ"
        if not link.exists():
            link.symlink_to(ROOT, target_is_directory=True)
        RUN, FEED = str(link / "runs" / "tess-pi-men-s1"), str(link / "docs" / "discoveries" / "catalog.json")
        assert len(RUN) > 120, RUN
    for argv in (["report", RUN, "--out", str(out / "report"), "--title", "SetuHQ: pi Men",
                  "--validation", str(Path(RUN).parents[1] / "docs/results/pi_men_validation.md"),
                  "--benchmark", str(Path(RUN).parents[1] / "docs/results/injection_recovery_simulated_panel.md")],
                 ["dashboard", RUN, "--out", str(out / "dashboard"), "--title", "SetuHQ dashboard: pi Men", "--catalog", FEED],
                 ["docket", RUN, "--out", str(out / "docket"), "--title", "SetuHQ case file: pi Men"],
                 ["plate", RUN, "--out", str(out / "plate"), "--title", "SetuHQ plates: pi Men", "--catalog", FEED]):
        if main(argv) != 0:
            raise SystemExit(f"build_outputs: setuhq {argv[0]} failed")
    build_discovery_site(FEED, out / "discover")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve(), deep="--deep" in sys.argv)
