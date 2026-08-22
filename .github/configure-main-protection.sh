#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${GITHUB_REPOSITORY:-sainibhaowal/AverQel}"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

if [[ -z "$TOKEN" ]]; then
  echo "Set GH_TOKEN or GITHUB_TOKEN to a repository-admin token before running this script." >&2
  exit 1
fi

curl --fail-with-body --silent --show-error \
  --request PUT \
  --url "https://api.github.com/repos/${REPOSITORY}/branches/main/protection" \
  --header "Accept: application/vnd.github+json" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "X-GitHub-Api-Version: 2022-11-28" \
  --header "Content-Type: application/json" \
  --data @- <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["CI Passed"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false
}
JSON

echo "Protected ${REPOSITORY}:main; required check: CI Passed"
