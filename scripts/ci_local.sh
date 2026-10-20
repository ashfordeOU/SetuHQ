#!/usr/bin/env bash
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
"$VENV/bin/python" -m pip install --quiet -e ".[dev]"
ok

step "tests (python -m pytest -q, same as ci.yml)"
"$VENV/bin/python" -m pytest -q -W ignore 2>&1 | tee -a "$LOG"
step "slow tests (marker 'slow': the 200-trial FAP case; ci.yml leaves them out)"
"$VENV/bin/python" -m pytest -q -W ignore -m slow 2>&1 | tee -a "$LOG"
# Name what pyproject's addopts (-m 'not network') leaves out, and why.
echo "   deselected (marker 'network': needs internet access to MAST or the ESA CHEOPS archive):" | tee -a "$LOG"
"$VENV/bin/python" -m pytest -q --collect-only -m network -o addopts="" 2>/dev/null | grep '::' | sed 's/^/     /' | tee -a "$LOG"
ok

if [[ "$QUICK" -eq 1 ]]; then
  echo "quick check passed" | tee -a "$LOG"
  exit 0
fi

RUN="runs/tess-pi-men-s1"
CAT="docs/discoveries/catalog.json"
EX="$VENV/bin/exoplan"

step "sweep catalogue: only ingested, intact contributions, and catalogue.json rebuilds from them"
# The ingest ledger may only grow against its merge-base with the base branch (EXOPLAN_BASE, else the
# remote's default branch). A missing base is a note locally and a failure when CI is set.
"$EX" check-sweep --sweep-dir docs/sweep --ledger-base auto >> "$LOG" 2>&1
grep "check-sweep: note:" "$LOG" | tail -n 1 || true
ok

step "app shell builds from the stored run"
"$EX" app "$RUN" --catalog "$CAT" --out site/app --title "exoplan" --landing site/index.html >> "$LOG" 2>&1
ok

step "docket builds from the stored run"
"$EX" docket "$RUN" --out site/docket --title "exoplan docket: pi Men (TESS sector 1)" >> "$LOG" 2>&1
ok

step "plate builds from the stored run"
"$EX" plate "$RUN" --catalog "$CAT" --out site/plate --title "exoplan plates" >> "$LOG" 2>&1
ok

step "archived run report builds from the stored run"
"$EX" report "$RUN" --out site/report --title "exoplan: pi Men (TESS sector 1)" \
  --validation docs/results/pi_men_validation.md --benchmark docs/results/injection_recovery_simulated_panel.md >> "$LOG" 2>&1
ok

step "no built page loads fonts or scripts from another site"
if grep -rl "fonts.googleapis\|fonts.gstatic" site --include=*.html; then echo "external fonts found" | tee -a "$LOG"; exit 1; fi
ok

step "site files exist"
for f in site/index.html site/app/index.html site/docket/index.html site/plate/index.html site/report/index.html; do
  test -s "$f" || { echo "missing $f" | tee -a "$LOG"; exit 1; }
done
ok

echo "full local check passed" | tee -a "$LOG"
