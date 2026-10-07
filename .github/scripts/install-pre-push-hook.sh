#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(git rev-parse --show-toplevel)"
source_hook="$repo_root/.githooks/pre-push"
hooks_dir="$(git -C "$repo_root" rev-parse --git-path hooks)"
if [[ "$hooks_dir" != /* ]]; then
  hooks_dir="$repo_root/$hooks_dir"
fi
target_hook="$hooks_dir/pre-push"

if [[ ! -x "$source_hook" ]]; then
  echo "Tracked pre-push hook is missing or not executable: $source_hook" >&2
  exit 1
fi

mkdir -p "$hooks_dir"

if [[ -L "$target_hook" && "$(readlink "$target_hook")" == "$source_hook" ]]; then
  echo "AverQel pre-push quality gate is already installed."
  exit 0
fi

if [[ -e "$target_hook" || -L "$target_hook" ]]; then
  echo "Refusing to replace an existing Git pre-push hook: $target_hook" >&2
  echo "Review that hook and install the AverQel hook manually if appropriate." >&2
  exit 1
fi

ln -s "$source_hook" "$target_hook"
echo "Installed the AverQel isolated pre-push quality gate at $target_hook"
