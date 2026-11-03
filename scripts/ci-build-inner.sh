#!/bin/bash
set -euo pipefail
fail() { echo "$*" >&2; exit 1; }
device=${1:?device required}
mode=${2:?mode required}
tree=${3:-eos-t}
[[ "$device" =~ ^[a-z0-9_]+$ ]] || fail 'Invalid device'
[[ "$tree" =~ ^[a-z0-9.-]+$ ]] || fail 'Invalid tree'
case "$mode" in verify|development|release-candidate|release|publish|promote) ;; *) fail 'Invalid mode';; esac
recipe=$(cd "$(dirname "$0")/.." && pwd)
if [[ "$tree" == eos-t ]]; then config_dir="$recipe/devices/$device"; else config_dir="$recipe/devices/$device/$tree"; fi
config="$config_dir/build.conf"
[[ -f "$config" ]] || fail 'Device has no build configuration'
# Configuration is trusted code from the reviewed recipe commit.
source "$config"
if [[ "$mode" == publish || "$mode" == promote ]]; then
  [[ "${BUILD_RELEASE_ALLOWED:-}" == 1 ]] || fail 'This tree has no release builds'
  exec python3 -I "$recipe/scripts/ci-publish.py" "$@"
fi
mkdir -p /work/build-lock
[[ ! -L /work/build-lock/build.lock ]] || fail 'Refusing symlinked build lock'
exec 9>>/work/build-lock/build.lock
flock -n 9 || fail 'Another local or Actions build holds the shared lock'
source_dir=${BUILD_SOURCE_DIR:-/work/src/android}
cd "$source_dir"
[[ -d .repo && -f build/envsetup.sh ]] || fail 'Android sources unavailable'
if [[ "$tree" == eos-t ]]; then
  [[ -s "$recipe/devices/$device/manifest.xml" ]] || fail 'Manifest missing'
else
  [[ -s "$config_dir/$BUILD_RECIPE_MANIFEST" ]] || fail 'Manifest missing'
fi
export GIT_TERMINAL_PROMPT=0 USE_CCACHE=1 CCACHE_EXEC=/usr/local/bin/ccache
export CCACHE_DIR=/work/ccache CCACHE_BASEDIR="$source_dir" CCACHE_COMPILERCHECK=content
export RELEASE_TYPE=UNOFFICIAL
[[ "$mode" != verify ]] || { echo "Environment verified for $device ($tree); no compilation or source changes."; exit 0; }
# soong_ui drops LD_PRELOAD from build actions without this.
export ALLOW_NINJA_ENV=true
if [[ "$mode" == release-candidate ]]; then
  # A runner-local setting, never user-controlled workflow input.
  out=${ROM_RELEASE_OUT:-/work/src/android/out-release}
  [[ "$out" == /work/src/android/out-release ]] || fail 'Unexpected release output path'
  [[ ! -e "$out" ]] || fail 'Release output exists. Preserve needed files and remove it manually before retrying.'
  fail 'Release builds are gated until source-manifest matching, vendor patch provenance and signing are audited. Use development for incremental builds.'
fi
# The Actions runner mounts the sources read-only, so keep repo and git-lfs from writing there.
lfs_storage=$(mktemp -d)
export REPO_TRACE=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=lfs.storage GIT_CONFIG_VALUE_0="$lfs_storage"
if [[ "$mode" == release ]]; then
  [[ "${BUILD_RELEASE_ALLOWED:-}" == 1 ]] || fail 'This tree has no release builds'
  run=${GITHUB_RUN_ID:-}
  [[ "$run" =~ ^[0-9]+$ ]] || fail 'Release builds run only from Actions'
  release_dir=/work/zips/ci/$run
  [[ ! -e "$release_dir" ]] || fail "$release_dir exists"
  mkdir -p "$release_dir"
  # The tree's own launcher matches its repo version; the image ships an older one.
  .repo/repo/repo manifest -r -o "$release_dir/resolved.xml"
  python3 -I "$recipe/scripts/check-tree-pins.py" "$release_dir/resolved.xml" "$config_dir/$BUILD_RECIPE_MANIFEST" \
    --tree "$source_dir" --branch "$BUILD_MANIFEST_BRANCH" --generated "$BUILD_VENDOR_PATH" \
    --overlay "prebuilts/build-tools/linux-x86/bin/ckati=$recipe/scripts/ckati-native.sh"
  blobs_revision=$(python3 -I -c 'import sys, xml.etree.ElementTree as E
print(next(p.get("revision") for p in E.parse(sys.argv[1]).iter("project") if p.get("path") == sys.argv[2]))' \
    "$config_dir/$BUILD_RECIPE_MANIFEST" "$BUILD_VENDOR_PATH")
  blobs=$(mktemp -d)
  git -C "$BUILD_VENDOR_PATH" archive "$blobs_revision" proprietary | tar -x -C "$blobs"
  # Start empty so every file comes from the blobs and the device tree's fixups, not the previous output.
  find "$BUILD_VENDOR_PATH" -mindepth 1 -maxdepth 1 ! -name '.*' -exec rm -rf {} +
  # The script's shebang sets PYTHONPATH relative to its own directory.
  (cd "$(dirname "$BUILD_EXTRACT")" && PYTHONDONTWRITEBYTECODE=1 "./$(basename "$BUILD_EXTRACT")" "$blobs/proprietary")
  python3 -I "$recipe/scripts/tree-hash.py" "$BUILD_VENDOR_PATH" > "$release_dir/vendor-tree.txt"
  echo "Vendor tree regenerated from $blobs_revision: $(tail -1 "$release_dir/vendor-tree.txt")"
  build_env
  build_number=$(date -u +eng.%Y%m%d.%H%M%S)
  echo "$build_number" > "$BUILD_NUMBER_FILE"
  export BUILD_NUMBER=$build_number
  set +u
  source build/envsetup.sh
  lunch "$BUILD_PRODUCT"
  m installclean
  m -j12 target-files-package otatools-package
  set -u
  target_files="$release_dir/${BUILD_PRODUCT%%-*}-target_files-$build_number.zip"
  cp "$OUT/obj/PACKAGING/target_files_intermediates/${BUILD_PRODUCT%%-*}-target_files.zip" "$target_files"
  python3 -I "$recipe/scripts/ci-release-info.py" "$target_files" --run "$run" --commit "${GITHUB_SHA:?}" \
    --build-number "$build_number" --vendor-revision "$blobs_revision" --out "$release_dir/release.json"
  [[ -z "${GITHUB_OUTPUT:-}" ]] || echo "target_files=$target_files" >> "$GITHUB_OUTPUT"
  exit 0
fi
[[ "$tree" == eos-t ]] || fail 'Development builds of this tree run locally'
export LD_PRELOAD=/work/scripts/libmap32.so
evidence="/work/logs/actions-builds/${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$evidence"
.repo/repo/repo manifest -r -o "$evidence/resolved.xml"
python3 -c 'import sys, xml.etree.ElementTree as E
for p in E.parse(sys.argv[1]).iter("project"): print(p.get("path") or p.get("name"))' "$evidence/resolved.xml" |
  while read -r project; do
    printf 'project %s\n' "$project"
    git -C "$project" status --porcelain
  done > "$evidence/source-status.txt"
echo "Development build uses existing local sources; source snapshot retained privately."
ANDROID_BUILDS_SOURCE_ID=$(python3 "$recipe/scripts/source-id.py" "$evidence/resolved.xml" --changes "$recipe/devices/$device/changes.json" --tree "$source_dir")
export ANDROID_BUILDS_SOURCE_ID
echo "$ANDROID_BUILDS_SOURCE_ID" > "$evidence/source-id.txt"
# envsetup.sh and lunch read unset variables.
set +u
source build/envsetup.sh
lunch "$BUILD_PRODUCT"
mka -j12 bacon
