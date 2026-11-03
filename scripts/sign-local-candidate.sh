#!/bin/bash
# Prompts for the two key passwords with hidden input.
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
script_dir=$(cd "$(dirname "$0")" && pwd)
exec python3 "$script_dir/sign-local-candidate-host.py" "$@"
