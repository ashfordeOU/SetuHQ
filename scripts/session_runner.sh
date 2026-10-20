#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
# Run this repository's GitHub Actions jobs from a short-lived cloud session.
#
# Needs EXOPLAN_RUNNER_PAT in the environment: a fine-grained token limited to
# ashfordeOU/EXOPLAN with "Administration: Read and write" (the minimum GitHub
# requires to register a runner). The token is never printed.
#
# Each loop mints a registration token, registers an ephemeral runner (it takes
# one job and removes itself), runs it, and repeats while jobs are queued, up to
# a time limit. Usage:
#
#   scripts/session_runner.sh            # serve queued jobs, at most 90 minutes
#   scripts/session_runner.sh --minutes 30

set -euo pipefail

REPO="ashfordeOU/EXOPLAN"
API="https://api.github.com/repos/$REPO"
DIR="${RUNNER_DIR:-$HOME/actions-runner}"
MINUTES=90
[[ "${1:-}" == "--minutes" ]] && MINUTES="${2:?minutes}"

if [[ -z "${EXOPLAN_RUNNER_PAT:-}" ]]; then
  echo "EXOPLAN_RUNNER_PAT is not set; add it to the cloud environment's settings." >&2
  exit 2
fi

gh_api() {  # method path [json]
  curl -fsS -X "$1" -H "Authorization: Bearer $EXOPLAN_RUNNER_PAT" \
    -H "Accept: application/vnd.github+json" "$API$2" ${3:+-d "$3"}
}

queued() {
  gh_api GET "/actions/runs?status=queued&per_page=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total_count"])'
}

install_runner() {
  [[ -x "$DIR/run.sh" ]] && return
  mkdir -p "$DIR"
  local ver
  ver=$(curl -fsS https://api.github.com/repos/actions/runner/releases/latest \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')
  curl -fsSL "https://github.com/actions/runner/releases/download/v$ver/actions-runner-linux-x64-$ver.tar.gz" \
    | tar -xz -C "$DIR"
}

install_runner
deadline=$(( $(date +%s) + MINUTES * 60 ))
while (( $(date +%s) < deadline )); do
  if [[ "$(queued)" == "0" ]]; then
    echo "no queued jobs"
    break
  fi
  token=$(gh_api POST /actions/runners/registration-token | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
  (cd "$DIR" && ./config.sh --url "https://github.com/$REPO" --token "$token" \
     --name "exoplan-session-$(date +%s)" --labels self-hosted,linux \
     --unattended --ephemeral --replace >/dev/null)
  unset token
  (cd "$DIR" && ./run.sh) || echo "runner exited with status $?"
done
