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
# Writes .site-e2e.json (every failed check, and the axe totals).
set -euo pipefail
cd "$(dirname "$0")/.."
SITE="${1:-site}"
[[ $# -gt 0 ]] && shift
command -v node >/dev/null || { echo "site_e2e: node is not installed" >&2; exit 2; }
test -s "$SITE/assets/pages.json" || { echo "site_e2e: $SITE is not a built site (no assets/pages.json); run setuhq site first" >&2; exit 2; }
exec node tests/e2e/run.mjs --site "$SITE" --report .site-e2e.json "$@"
