#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
# Local CI: runs what .github/workflows/ci.yml runs, then rebuilds the public
# pages from the stored run and checks they build. Use it when hosted Actions
# minutes are unavailable (private repository). Exits non-zero on the first failure.
#
#   scripts/ci_local.sh            # full check: tests, then site builds
#   scripts/ci_local.sh --quick    # tests only
#
# Writes the outcome of each step to .ci-local.log so the result can be shown.

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
VENV=".venv"
LOG=".ci-local.log"
QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

: > "$LOG"
step() { echo "== $*" | tee -a "$LOG"; }
ok()   { echo "   ok" | tee -a "$LOG"; }

step "install into a venv (same as ci.yml)"
if [[ ! -x "$VENV/bin/python" ]]; then "$PY" -m venv "$VENV"; fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e ".[dev]" -r requirements-readme.txt
ok

step "tests (python -m pytest -q, same as ci.yml)"
"$VENV/bin/python" -m pytest -q -W ignore 2>&1 | tee -a "$LOG"
step "slow tests (marker 'slow': the 200-trial FAP case; ci.yml leaves them out)"
"$VENV/bin/python" -m pytest -q -W ignore -m slow 2>&1 | tee -a "$LOG"
# Name what pyproject's addopts (-m 'not network') leaves out, and why.
echo "   deselected (marker 'network': needs internet access to MAST or the ESA CHEOPS archive):" | tee -a "$LOG"
"$VENV/bin/python" -m pytest -q --collect-only -m network -o addopts="" 2>/dev/null | grep '::' | sed 's/^/     /' | tee -a "$LOG"
ok

step "methods paper numbers match the committed JSON (scripts/paper_numbers.py --check)"
"$VENV/bin/python" scripts/paper_numbers.py --check 2>&1 | tee -a "$LOG"
ok

step "the renderer's stills were drawn by the current renderer and look table (tools/render_stills.mjs --check)"
if command -v node >/dev/null; then
  PYTHON="$VENV/bin/python" node tools/render_stills.mjs --check 2>&1 | tee -a "$LOG"
  test "${PIPESTATUS[0]}" -eq 0
else
  echo "   node is not installed: the stills check runs in pytest (tests/test_renderer.py) instead" | tee -a "$LOG"
fi
ok

step "README figures, brand files and screenshots are current (tools/gen_readme_assets.py --check)"
"$VENV/bin/python" tools/gen_readme_assets.py --check 2>&1 | tee -a "$LOG"
ok

if [[ "$QUICK" -eq 1 ]]; then
  echo "quick check passed" | tee -a "$LOG"
  exit 0
fi

RUN="runs/tess-pi-men-s1"
# The worked examples, shown beside the lead run (docs/SHOWCASE.md): each gets its dips' pages, case file, plates and report.
SHOWCASE_RUNS="runs/tess-wasp-126-s1 runs/tess-toi-270-s5 runs/tess-hd-15337-s4 runs/tess-toi-236-s2"
CAT="docs/discoveries/catalog.json"
EX="$VENV/bin/setuhq"

step "sweep catalogue: only ingested, intact contributions, and catalogue.json rebuilds from them"
# The ingest ledger may only grow against its merge-base with the base branch (SETUHQ_BASE, else the
# remote's default branch). A missing base is a note locally and a failure when CI is set.
"$EX" check-sweep --sweep-dir docs/sweep --ledger-base auto >> "$LOG" 2>&1
grep "check-sweep: note:" "$LOG" | tail -n 1 || true
ok

step "the worked examples' comparison with the literature is current (scripts/showcase_compare.py --check)"
"$VENV/bin/python" scripts/showcase_compare.py --check 2>&1 | tee -a "$LOG"
ok

step "the site builds from the stored runs (setuhq site: every page, and each run's report, plates and case file)"
# shellcheck disable=SC2086
"$EX" site "$RUN" $SHOWCASE_RUNS --catalog "$CAT" --out site --title "SetuHQ" \
  --validation docs/results/pi_men_validation.md --benchmark docs/results/injection_recovery_simulated_panel.md >> "$LOG" 2>&1
ok

step "no built page loads fonts or scripts from another site"
if grep -rl "fonts.googleapis\|fonts.gstatic" site --include=*.html; then echo "external fonts found" | tee -a "$LOG"; exit 1; fi
if grep -rlE '<script[^>]+src="(https?:)?//' site --include=*.html; then echo "external script found" | tee -a "$LOG"; exit 1; fi
ok

step "site files exist, and no site-wide banner"
for f in site/index.html site/404.html site/sitemap.xml site/robots.txt site/explore/index.html site/candidates/index.html \
         site/how-it-works/index.html site/evidence/index.html site/docs/index.html site/candidates/case-file/index.html \
         site/evidence/plates/index.html site/evidence/report/index.html site/app/index.html \
         site/candidates/wasp-126/case-file/index.html site/evidence/plates/toi-270/index.html site/evidence/report/hd-15337/index.html \
         site/candidates/toi-236/dip-1/index.html; do
  test -s "$f" || { echo "missing $f" | tee -a "$LOG"; exit 1; }
done
if grep -rl 'id="codenote"' site --include=*.html; then echo "a site-wide banner is back" | tee -a "$LOG"; exit 1; fi
ok

step "end-to-end: every page in Chromium, both sizes and themes, axe-core (scripts/site_e2e.sh)"
if command -v node >/dev/null; then
  scripts/site_e2e.sh site 2>&1 | tail -n 40 | tee -a "$LOG"
  test "${PIPESTATUS[0]}" -eq 0
else
  echo "   node is not installed: the end-to-end test was not run" | tee -a "$LOG"
  [[ -n "${CI:-}" ]] && exit 1
fi
ok

echo "full local check passed" | tee -a "$LOG"
