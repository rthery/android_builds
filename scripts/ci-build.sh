#!/bin/bash
set -euo pipefail
if [[ "${ROM_RUNNER_CONTAINER:-}" == 1 ]]; then
  exec bash "$(dirname "$0")/ci-build-inner.sh" "$@"
fi
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
script_dir=$(cd "$(dirname "$0")" && pwd)
workspace=${ROM_WORKSPACE:-$(cd "$script_dir/../../.." && pwd)}
case "$script_dir/" in
  "$workspace/"*) relative=${script_dir#"$workspace/"} ;;
  *) echo 'Recipe checkout must be inside ROM_WORKSPACE.' >&2; exit 1 ;;
esac
exec docker exec "${ROM_CONTAINER:-rom-build}" bash "/work/$relative/ci-build-inner.sh" "$@"
