#!/bin/bash
# Runner job-started hook: refuse every job except a dispatch of build.yml on main by the owner.
set -u
owner=${EOS_RUNNER_OWNER:-rthery}
repository=${EOS_RUNNER_REPO:-rthery/android_builds}
expected=(
  "GITHUB_REPOSITORY=$repository"
  "GITHUB_EVENT_NAME=workflow_dispatch"
  "GITHUB_REF=refs/heads/main"
  "GITHUB_WORKFLOW_REF=$repository/.github/workflows/build.yml@refs/heads/main"
  "GITHUB_ACTOR=$owner"
  "GITHUB_TRIGGERING_ACTOR=$owner"
)
status=0
for pair in "${expected[@]}"; do
  name=${pair%%=*}
  if [[ "${!name-}" != "${pair#*=}" ]]; then
    echo "Refused: $name is '${!name-<unset>}', expected '${pair#*=}'" >&2
    status=1
  fi
done
[[ $status -eq 0 ]] && echo "Job accepted: $GITHUB_WORKFLOW_REF by $GITHUB_ACTOR"
exit "$status"
