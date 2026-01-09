#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

if ! command -v npm >/dev/null 2>&1; then
  echo "sanitycheck: npm is required" 1>&2
  exit 2
fi

npm_cache="$repo_root/sanitycheck/js/.npm-cache"
mkdir -p "$npm_cache"
(cd "$repo_root/sanitycheck/js" && npm --cache "$npm_cache" install)

echo "sanitycheck: deps installed"
echo "sanitycheck: run manually with: ./sanitycheck/run"
