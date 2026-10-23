#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
# End-to-end test of the built site in Chromium (tests/e2e/run.mjs): every page at 1440 x 900 and 390 x 844, dark
# and light, served at the domain root the way GitHub Pages serves it, plus the top bar, the phone menu, search,
# Back and Forward, every old address, the 404 page, a crawl of every internal link and an axe-core scan.
#
#   scripts/site_e2e.sh                 # the committed site/
#   scripts/site_e2e.sh path/to/site    # another build
#   scripts/site_e2e.sh site --quick    # one page of each kind instead of every page
#
# Needs Node.js 18+ and the playwright package with Chromium: `npm install playwright` next to the repository (or
# globally), or SETUHQ_PLAYWRIGHT=<its folder>. It never downloads a browser; PLAYWRIGHT_BROWSERS_PATH picks one.
# The test runs on a copy of the site with the deploy-time pages added (python -m setuhq.stubs: a small page for every
# catalogue planet and star, as pages.yml writes them before upload), so site/ itself is never changed.
# Writes .site-e2e.json (every failed check, and the axe totals) and .site-e2e-visuals.json (the visual system's checks).
# SETUHQ_E2E_BROWSERS=chromium,webkit adds a WebKit pass of the visual checks when Playwright's WebKit is installed.
set -euo pipefail
cd "$(dirname "$0")/.."
SITE="${1:-site}"
[[ $# -gt 0 ]] && shift
command -v node >/dev/null || { echo "site_e2e: node is not installed" >&2; exit 2; }
test -s "$SITE/assets/pages.json" || { echo "site_e2e: $SITE is not a built site (no assets/pages.json); run setuhq site first" >&2; exit 2; }
PY="${PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -R "$SITE" "$WORK/site"
PYTHONPATH=src "$PY" -m setuhq.stubs "$WORK/site"
node tests/e2e/run.mjs --site "$WORK/site" --report .site-e2e.json "$@"
# The CLI outputs that write HTML (report, dashboard, docket, plate, the search feed page), built from the stored lead run
# for checks/outputs.mjs; they need the package's dependencies, so the repository's venv when there is one.
OPY="${PYTHON:-}"; [[ -z "$OPY" && -x .venv/bin/python ]] && OPY=.venv/bin/python
"${OPY:-$PY}" tests/e2e/build_outputs.py "$WORK/outputs" > /dev/null
# The visual system (tests/e2e/visuals.mjs: the renderer, the motion budget, labels, stages, layout shift, the outputs), in Chromium.
node tests/e2e/visuals.mjs --site "$WORK/site" --outputs "$WORK/outputs" --report .site-e2e-visuals.json
# Optional: the same checks in WebKit (Safari's engine), when SETUHQ_E2E_BROWSERS names it and Playwright's WebKit is
# installed. It is never downloaded; without it the owner checks an iPhone and Safari on macOS by hand.
if [[ ",${SETUHQ_E2E_BROWSERS:-}," == *",webkit,"* ]]; then
  if node -e "import('./tests/e2e/lib.mjs').then(m=>m.loadPlaywright()).then(p=>{process.exit(require('node:fs').existsSync(p.webkit.executablePath())?0:1)}).catch(()=>process.exit(1))" 2>/dev/null; then
    node tests/e2e/visuals.mjs --site "$WORK/site" --outputs "$WORK/outputs" --browser webkit --report .site-e2e-webkit.json
  else
    echo "site_e2e: SETUHQ_E2E_BROWSERS names webkit, but Playwright's WebKit is not installed: the WebKit pass was skipped" >&2
  fi
fi
