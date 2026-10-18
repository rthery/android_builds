#!/bin/bash
set -euo pipefail
if [[ "${EOS_RUNNER_CONTAINER:-}" == 1 ]]; then
  exec bash "$(dirname "$0")/ci-build-inner.sh" "$@"
fi
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
workspace=${EOS_WORKSPACE:-/Volumes/eOS-Build}
script_dir=$(cd "$(dirname "$0")" && pwd)
case "$script_dir/" in
  "$workspace/"*) relative=${script_dir#"$workspace/"} ;;
  *) echo 'Recipe checkout must be inside EOS_WORKSPACE.' >&2; exit 1 ;;
esac
exec docker exec "${EOS_CONTAINER:-eos-bullhead-work}" bash "/eos/$relative/ci-build-inner.sh" "$@"
