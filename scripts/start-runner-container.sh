#!/bin/bash
set -euo pipefail
root=${EOS_WORKSPACE:-/Volumes/eOS-Build}
repo=${EOS_RUNNER_REPO:-rthery/android_builds}
name=eos-actions-runner
# Extract the official checksum-verified linux-x64 runner here; never configure it.
dist=$root/.local/github-runner-dist
for directory in .local/github-runner-dist .local/build-lock src/android/out ccache logs/actions-builds; do
  [[ -d "$root/$directory" ]] || { echo "Missing $directory" >&2; exit 1; }
done
[[ -x "$dist/run.sh" && ! -e "$dist/.runner" ]] || { echo 'Runner directory must be a pristine, unconfigured extract' >&2; exit 1; }
trap 'docker rm -f "$name" >/dev/null 2>&1 || true; exit 130' INT TERM
while true; do
  # A just-in-time runner accepts one job, then GitHub removes its registration.
  if ! JITCONFIG=$(GH_TOKEN=$(gh auth token -u "${repo%%/*}") gh api -X POST \
      "repos/$repo/actions/runners/generate-jitconfig" \
      -f name="eos-builder-$(date -u +%Y%m%dT%H%M%SZ)" -F runner_group_id=1 -f work_folder=_work \
      -f 'labels[]=self-hosted' -f 'labels[]=Linux' -f 'labels[]=X64' -f 'labels[]=eos-builder' \
      --jq .encoded_jit_config); then
    sleep 60
    continue
  fi
  export JITCONFIG
  docker run --rm --name "$name" --platform linux/amd64 \
    --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --init \
    -e HOME=/home/ubuntu -e EOS_RUNNER_CONTAINER=1 -e JITCONFIG \
    --mount "type=bind,src=$dist,dst=/runner-dist,readonly" \
    --mount "type=bind,src=$root/src/android,dst=/eos/src/android,readonly" \
    --mount "type=bind,src=$root/src/android/out,dst=/eos/src/android/out" \
    --mount "type=bind,src=$root/ccache,dst=/eos/ccache" \
    --mount "type=bind,src=$root/.local/build-lock,dst=/eos/build-lock" \
    --mount "type=bind,src=$root/logs/actions-builds,dst=/eos/logs/actions-builds" \
    --mount "type=bind,src=$root/scripts/libmap32.so,dst=/eos/scripts/libmap32.so,readonly" \
    --workdir /home/ubuntu --entrypoint /bin/bash \
    registry.gitlab.e.foundation:5000/e/os/docker-lineage-cicd@sha256:786a3e13b33249109e74741abef42bcc2fdf00ca0b619145b82eabe7f3ad4d84 \
    -c 'cp -a /runner-dist runner && cd runner && exec ./run.sh --jitconfig "$JITCONFIG"' || sleep 10
  unset JITCONFIG
done
