#!/bin/bash
set -euo pipefail
fail() { echo "$*" >&2; exit 1; }
device=${1:?device required}
mode=${2:?mode required}
[[ "$device" =~ ^[a-z0-9_]+$ ]] || fail 'Invalid device'
case "$mode" in verify|development|release-candidate) ;; *) fail 'Invalid mode';; esac
recipe=$(cd "$(dirname "$0")/.." && pwd)
config="$recipe/devices/$device/build.conf"
[[ -f "$config" ]] || fail 'Device has no build configuration'
# Configuration is trusted code from the reviewed recipe commit.
source "$config"
mkdir -p /eos/build-lock
exec 9>/eos/build-lock/build.lock
flock -n 9 || fail 'Another local or Actions build holds the shared lock'
source_dir=${BUILD_SOURCE_DIR:-/eos/src/android}
cd "$source_dir"
[[ -d .repo && -f build/envsetup.sh ]] || fail 'Android sources unavailable'
[[ -s "$recipe/devices/$device/manifest.xml" ]] || fail 'Manifest missing'
export GIT_TERMINAL_PROMPT=0 USE_CCACHE=1 CCACHE_EXEC=/usr/local/bin/ccache
export CCACHE_DIR=/eos/ccache CCACHE_BASEDIR="$source_dir" CCACHE_COMPILERCHECK=content
export RELEASE_TYPE=UNOFFICIAL
[[ "$mode" != verify ]] || { echo "Environment verified for $device; no compilation or source changes."; exit 0; }
export LD_PRELOAD=/eos/scripts/libmap32.so
if [[ "$mode" == release-candidate ]]; then
  # A runner-local setting, never user-controlled workflow input.
  out=${EOS_RELEASE_OUT:-/eos/src/android/out-release}
  [[ "$out" == /eos/src/android/out-release ]] || fail 'Unexpected release output path'
  [[ ! -e "$out" ]] || fail 'Release output exists. Preserve needed files and remove it manually before retrying.'
  fail 'Release builds are gated until source-manifest matching, vendor patch provenance and signing are audited. Use development for incremental builds.'
fi
evidence="/eos/logs/actions-builds/${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$evidence"
# The Actions runner mounts the sources read-only, so keep repo and git-lfs from writing there.
lfs_storage=$(mktemp -d)
export REPO_TRACE=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=lfs.storage GIT_CONFIG_VALUE_0="$lfs_storage"
repo manifest -r -o "$evidence/resolved.xml"
python3 -c 'import sys, xml.etree.ElementTree as E
for p in E.parse(sys.argv[1]).iter("project"): print(p.get("path") or p.get("name"))' "$evidence/resolved.xml" |
  while read -r project; do
    printf 'project %s\n' "$project"
    git -C "$project" status --porcelain
  done > "$evidence/source-status.txt"
echo "Development build uses existing local sources; source snapshot retained privately."
# envsetup.sh and lunch read unset variables.
set +u
source build/envsetup.sh
lunch "$BUILD_PRODUCT"
mka -j6 bacon
