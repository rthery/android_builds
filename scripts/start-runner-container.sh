#!/bin/bash
set -euo pipefail
root=${ROM_WORKSPACE:-$(cd "$(dirname "$0")/../../.." && pwd)}
repo=${ROM_RUNNER_REPO:-rthery/android_builds}
name=rom-actions-runner
# Build outputs live in a Docker volume owned by UID 1000, shared with local builds.
out_volume=${ROM_OUT_VOLUME:-eos-out-android}
# Extract the official checksum-verified linux-x64 runner here; never configure it.
dist=$root/.local/github-runner-dist
scripts=$(cd "$(dirname "$0")" && pwd)
hook=$scripts/runner-job-started.sh
# Runner image: scripts/runner-image/Dockerfile (adds the arm64 libraries the 22.2 JDK needs).
image=${ROM_RUNNER_IMAGE:-rom-actions-runner-image:l22}
l22=$root/src/lineage-22.2
# arm64 hosts run the tree's aarch64 ckati natively instead of the x86 one under emulation.
kati=()
if [[ $(uname -m) == arm64 && -x $l22/prebuilts/build-tools/linux_musl-arm64/bin/ckati ]]; then
  kati=(--mount "type=bind,src=$scripts/ckati-native.sh,dst=/work/src/lineage-22.2/prebuilts/build-tools/linux-x86/bin/ckati,readonly")
fi
for directory in .local/github-runner-dist .local/build-lock .local/build-jdk ccache logs/actions-builds zips/ci zips/ci-signed \
    src/lineage-22.2/out src/lineage-22.2/vendor/lge/bullhead; do
  [[ -d "$root/$directory" ]] || { echo "Missing $directory" >&2; exit 1; }
done
docker volume inspect "$out_volume" >/dev/null 2>&1 || { echo "Missing volume $out_volume" >&2; exit 1; }
[[ -x "$hook" ]] || { echo "Missing $hook" >&2; exit 1; }
docker image inspect "$image" >/dev/null 2>&1 || { echo "Missing image $image; build scripts/runner-image" >&2; exit 1; }
[[ -x "$dist/run.sh" && ! -e "$dist/.runner" ]] || { echo 'Runner directory must be a pristine, unconfigured extract' >&2; exit 1; }
trap 'docker rm -f "$name" >/dev/null 2>&1 || true; exit 130' INT TERM
while true; do
  # A just-in-time runner accepts one job, then GitHub removes its registration.
  if ! JITCONFIG=$(GH_TOKEN=$(gh auth token -u "${repo%%/*}") gh api -X POST \
      "repos/$repo/actions/runners/generate-jitconfig" \
      -f name="rom-builder-$(date -u +%Y%m%dT%H%M%SZ)" -F runner_group_id=1 -f work_folder=_work \
      -f 'labels[]=self-hosted' -f 'labels[]=Linux' -f 'labels[]=X64' -f 'labels[]=rom-builder' \
      --jq .encoded_jit_config); then
    sleep 60
    continue
  fi
  export JITCONFIG
  # Jobs inherit the runner's environment, so the registration only travels as an argument.
  docker run --rm --name "$name" --platform linux/amd64 \
    --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --init \
    -e HOME=/home/ubuntu -e ROM_RUNNER_CONTAINER=1 -e JITCONFIG \
    -e ACTIONS_RUNNER_HOOK_JOB_STARTED=/work/hooks/job-started.sh \
    --mount "type=bind,src=$hook,dst=/work/hooks/job-started.sh,readonly" \
    --mount "type=bind,src=$dist,dst=/runner-dist,readonly" \
    --mount "type=bind,src=$root/src/android,dst=/work/src/android,readonly" \
    --mount "type=volume,src=$out_volume,dst=/work/src/android/out" \
    --mount "type=bind,src=$root/ccache,dst=/work/ccache" \
    --mount "type=bind,src=$root/.local/build-lock,dst=/work/build-lock" \
    --mount "type=bind,src=$root/logs/actions-builds,dst=/work/logs/actions-builds" \
    --mount "type=bind,src=$root/scripts/libmap32.so,dst=/work/scripts/libmap32.so,readonly" \
    --mount "type=bind,src=$l22,dst=/work/src/lineage-22.2,readonly" \
    ${kati[@]+"${kati[@]}"} \
    --mount "type=bind,src=$l22/out,dst=/work/src/lineage-22.2/out" \
    --mount "type=bind,src=$l22/vendor/lge/bullhead,dst=/work/src/lineage-22.2/vendor/lge/bullhead" \
    --mount "type=bind,src=$root/.local/build-jdk,dst=/work/.local/build-jdk,readonly" \
    --mount "type=bind,src=$root/zips/ci,dst=/work/zips/ci" \
    --mount "type=bind,src=$root/zips/ci-signed,dst=/work/zips/ci-signed,readonly" \
    --workdir /home/ubuntu --entrypoint /bin/bash \
    "$image" \
    -c 'config=$JITCONFIG; unset JITCONFIG; cp -a /runner-dist runner && cd runner && exec ./run.sh --jitconfig "$config"' || sleep 10
  unset JITCONFIG
done
