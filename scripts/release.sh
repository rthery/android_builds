#!/bin/bash
# Build, sign and publish a prerelease: asks the signing passwords first, then runs unattended.
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
script_dir=$(cd "$(dirname "$0")" && pwd)
exec python3 "$script_dir/release.py" "$@"
