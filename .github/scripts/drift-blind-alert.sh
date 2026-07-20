#!/usr/bin/env bash
set -euo pipefail

# Single-issue alert for when the weekly drift check can't reach SNIRH.
#
# CI runs on GitHub-hosted (non-Portuguese) IPs, and SNIRH returns 403 to
# those, so the live drift suite skips and the job goes green — blind. A
# permanently green-but-blind check is worse than a red one: it hides drift.
# This keeps exactly ONE open tracking issue while the blind spot persists,
# so it is visible and GitHub emails the maintainer. It self-resolves (closes
# the issue) once SNIRH is reachable again. Each skipped run adds a dated
# comment, so the comment count is the number of consecutive blind weeks.
#
# Needs only the default GITHUB_TOKEN with `issues: write`.
#
# Usage: drift-blind-alert.sh open|close   (GH_TOKEN must be set)

action="${1:?usage: drift-blind-alert.sh open|close}"
title="Drift check blind: SNIRH unreachable from CI"
run_url="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
today="$(date -u +%Y-%m-%d)"

# Newest open issue whose title matches exactly (search is fuzzy, so re-filter
# with jq). Empty string when there is none.
number="$(gh issue list --state open --search "in:title \"$title\"" \
  --json number,title \
  --jq "map(select(.title == \"$title\")) | (first // {}) | .number // empty")"

case "$action" in
  open)
    if [ -n "$number" ]; then
      gh issue comment "$number" --body "Still blind: $today — $run_url"
      echo "Updated tracking issue #$number."
    else
      gh issue create --title "$title" --body \
"The weekly **Live drift** check could not reach SNIRH (\`403\`/network error),
so it ran no drift coverage this week. This is expected from GitHub-hosted
runners: SNIRH blocks non-Portuguese IPs. Run the live suite from a Portuguese
vantage point to restore coverage.

Consecutive blind weeks are tracked as comments below (one per skipped run).
This issue closes automatically once SNIRH is reachable from CI again.

- $today — $run_url"
      echo "Opened tracking issue."
    fi
    ;;
  close)
    if [ -n "$number" ]; then
      gh issue close "$number" \
        --comment "SNIRH reachable from CI again on $today — drift coverage restored. $run_url"
      echo "Closed tracking issue #$number."
    else
      echo "No open tracking issue; nothing to resolve."
    fi
    ;;
  *)
    echo "usage: drift-blind-alert.sh open|close" >&2
    exit 2
    ;;
esac
