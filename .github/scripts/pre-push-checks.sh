#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"

if [[ "$#" -ne 2 ]]; then
  echo "Git pre-push hook must receive the remote name and URL." >&2
  exit 2
fi

run_actionlint() {
  local checkout="$1"

  if command -v actionlint >/dev/null 2>&1; then
    (cd "$checkout" && actionlint -color)
  else
    docker run --rm \
      --volume "$checkout:/repo:ro" \
      --workdir /repo \
      rhysd/actionlint:1.7.12 \
      -color
  fi
}

validate_commit() (
  set -Eeuo pipefail

  local commit="$1"
  local temp_root
  local checkout
  local precommit_status=0
  local actionlint_status=0

  temp_root="$(mktemp -d "${TMPDIR:-/tmp}/averqel-pre-push.XXXXXX")"
  checkout="$temp_root/checkout"

  cleanup() {
    git -C "$repo_root" worktree remove --force "$checkout" >/dev/null 2>&1 || true
    rm -rf -- "$temp_root"
  }
  trap cleanup EXIT

  if ! git -C "$repo_root" worktree add --quiet --detach "$checkout" "$commit"; then
    echo "Could not create an isolated validation worktree for $commit" >&2
    exit 1
  fi

  # Reuse installed local tool environments without exposing the live source
  # tree to hooks that format or otherwise modify files.
  for dependency_dir in backend/.venv frontend/node_modules; do
    source_dir="$repo_root/$dependency_dir"
    target_dir="$checkout/$dependency_dir"
    if [[ -d "$source_dir" && ! -e "$target_dir" && ! -L "$target_dir" ]]; then
      mkdir -p "$(dirname "$target_dir")"
      ln -s "$source_dir" "$target_dir"
    fi
  done

  echo "Running the full pre-commit suite against $commit in an isolated worktree..."
  if (cd "$checkout" && pre-commit run --all-files); then
    precommit_status=0
  else
    precommit_status=$?
  fi

  echo "Linting every GitHub Actions workflow for $commit..."
  if run_actionlint "$checkout"; then
    actionlint_status=0
  else
    actionlint_status=$?
  fi

  if (( precommit_status != 0 )); then
    echo "::error::The full pre-commit suite failed for $commit (exit $precommit_status)." >&2
    changed_files="$(git -C "$checkout" status --short)"
    if [[ -n "$changed_files" ]]; then
      echo "Hooks changed files in the disposable worktree; update and recommit them before pushing:" >&2
      printf '%s\n' "$changed_files" >&2
    fi
  fi

  if (( actionlint_status != 0 )); then
    echo "::error::Actionlint failed for $commit (exit $actionlint_status)." >&2
  fi

  if (( precommit_status != 0 || actionlint_status != 0 )); then
    exit 1
  fi
)

declare -a commits_to_check=()
while IFS=' ' read -r local_ref local_sha remote_ref remote_sha extra; do
  [[ -n "${local_ref:-}" ]] || continue
  if [[ -n "${extra:-}" || -z "${local_sha:-}" || -z "${remote_ref:-}" || -z "${remote_sha:-}" ]]; then
    echo "Invalid input from Git's pre-push hook." >&2
    exit 2
  fi

  # A zero local SHA means the ref is being deleted; there is no commit to validate.
  if [[ "$local_sha" =~ ^0+$ ]]; then
    continue
  fi

  if ! git -C "$repo_root" cat-file -e "${local_sha}^{commit}" 2>/dev/null; then
    echo "The pushed object is not an available commit: $local_sha ($local_ref)" >&2
    exit 1
  fi

  case " ${commits_to_check[*]} " in
    *" $local_sha "*) ;;
    *) commits_to_check+=("$local_sha") ;;
  esac
done

if (( ${#commits_to_check[@]} == 0 )); then
  echo "No commits are being pushed; validation is not needed."
  exit 0
fi

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "pre-commit is required for the push gate. Install it with: python -m pip install pre-commit" >&2
  exit 1
fi

if ! command -v actionlint >/dev/null 2>&1 && ! command -v docker >/dev/null 2>&1; then
  echo "Actionlint or Docker is required to validate GitHub Actions workflows." >&2
  exit 1
fi

for commit in "${commits_to_check[@]}"; do
  validate_commit "$commit"
done

echo "All pushed commits passed the pre-push quality gates."
