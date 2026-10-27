#!/bin/bash
# Builds otatools.zip for release signing in an output directory the Actions runner never mounts.
# Runs inside the local build container; ccache is off because Actions jobs can write it.
set -eo pipefail
product=${1:?usage: build-signing-toolchain.sh <lunch product> [source dir] [output dir]}
source_dir=${2:-/eos/src/android}
out_dir=${3:-$source_dir/out-signing}
mkdir -p /eos/build-lock
# The runner can write the lock directory: never follow or truncate what it leaves there.
[[ ! -L /eos/build-lock/build.lock ]] || { echo "Refusing symlinked build lock" >&2; exit 1; }
exec 9>>/eos/build-lock/build.lock
flock -n 9 || { echo "Another build holds the shared lock" >&2; exit 1; }
unset USE_CCACHE CCACHE_EXEC
export CCACHE_DISABLE=1 GIT_TERMINAL_PROMPT=0 OUT_DIR=$out_dir
[[ -f /eos/scripts/libmap32.so ]] && export LD_PRELOAD=/eos/scripts/libmap32.so
# soong_ui drops LD_PRELOAD from build actions without this.
export ALLOW_NINJA_ENV=true
cd "$source_dir"
source build/envsetup.sh >/dev/null
lunch "$product" >/dev/null
m -j6 otatools-package
zip=$(get_build_var PRODUCT_OUT)/otatools.zip
[[ -f "$zip" ]] || { echo "otatools.zip not produced" >&2; exit 1; }
sha256sum "$zip"
