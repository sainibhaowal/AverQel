#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/averqel-pre-push-test.XXXXXX")"
fixture="$temp_root/repository"
shim_dir="$temp_root/shims"
log_file="$temp_root/gate.log"
output_file="$temp_root/output.log"

cleanup() {
  rm -rf -- "$temp_root"
}
trap cleanup EXIT

mkdir -p "$fixture/.githooks" "$fixture/.github/scripts" "$shim_dir"
cp "$repo_root/.githooks/pre-push" "$fixture/.githooks/pre-push"
cp "$repo_root/.github/scripts/pre-push-checks.sh" "$fixture/.github/scripts/pre-push-checks.sh"
chmod +x "$fixture/.githooks/pre-push" "$fixture/.github/scripts/pre-push-checks.sh"
printf 'fixture\n' > "$fixture/README.md"

git -C "$fixture" init --quiet
git -C "$fixture" config user.name "AverQel Hook Test"
git -C "$fixture" config user.email "hook-test@example.invalid"
git -C "$fixture" add .
git -C "$fixture" commit --quiet -m "test fixture"
fixture_sha="$(git -C "$fixture" rev-parse HEAD)"

cat > "$shim_dir/pre-commit" <<'SHIM'
#!/usr/bin/env bash
set -Eeuo pipefail
printf 'pre-commit %s\n' "$PWD" >> "$AVERQEL_GATE_TEST_LOG"
if [[ "${AVERQEL_GATE_TEST_FORMAT:-0}" == 1 ]]; then
  printf 'formatter change\n' >> README.md
  exit 1
fi
SHIM

cat > "$shim_dir/actionlint" <<'SHIM'
#!/usr/bin/env bash
set -Eeuo pipefail
printf 'actionlint %s\n' "$PWD" >> "$AVERQEL_GATE_TEST_LOG"
exit "${AVERQEL_GATE_TEST_ACTIONLINT_STATUS:-0}"
SHIM

chmod +x "$shim_dir/pre-commit" "$shim_dir/actionlint"
export PATH="$shim_dir:$PATH"
export AVERQEL_GATE_TEST_LOG="$log_file"

run_gate() {
  local input="$1"
  : > "$log_file"
  local status=0
  printf '%s\n' "$input" | (cd "$fixture" && .githooks/pre-push origin test://remote) > "$output_file" 2>&1 || status=$?
  if (( status != 0 )) && [[ "${AVERQEL_GATE_TEST_DEBUG:-0}" == 1 ]]; then
    cat "$output_file" >&2
  fi
  return "$status"
}

push_line="refs/heads/feature $fixture_sha refs/heads/feature 0000000000000000000000000000000000000000"
second_push_line="refs/heads/alias $fixture_sha refs/heads/alias 0000000000000000000000000000000000000000"

# Multiple refs at the same commit should trigger one validation pass.
run_gate "$push_line
$second_push_line"
[[ "$(wc -l < "$log_file")" -eq 2 ]]
[[ "$(git -C "$fixture" status --porcelain)" == "" ]]

# A formatter may change its disposable checkout, but must block the push and
# leave the user's source checkout untouched.
export AVERQEL_GATE_TEST_FORMAT=1
if run_gate "$push_line"; then
  echo "Expected formatter changes to block the push." >&2
  exit 1
fi
unset AVERQEL_GATE_TEST_FORMAT
grep -q "Hooks changed files in the disposable worktree" "$output_file"
[[ "$(git -C "$fixture" status --porcelain)" == "" ]]
[[ "$(git -C "$fixture" worktree list --porcelain | grep -c '^worktree ')" -eq 1 ]]

# Workflow lint failures must also block the push.
export AVERQEL_GATE_TEST_ACTIONLINT_STATUS=1
if run_gate "$push_line"; then
  echo "Expected Actionlint failures to block the push." >&2
  exit 1
fi
unset AVERQEL_GATE_TEST_ACTIONLINT_STATUS
grep -q "Actionlint failed" "$output_file"

# Deleting a ref has no commit to validate.
delete_line="refs/heads/feature 0000000000000000000000000000000000000000 refs/heads/feature $fixture_sha"
run_gate "$delete_line"
[[ ! -s "$log_file" ]]

echo "Pre-push gate regression checks passed."
