#!/bin/bash
# Runner job-started hook: refuse every job except a dispatch or the weekly schedule of build.yml on main by the owner.
set -u
owner=${ROM_RUNNER_OWNER:-rthery}
repository=${ROM_RUNNER_REPO:-rthery/android_builds}
expected=(
  "GITHUB_REPOSITORY=$repository"
  "GITHUB_REF=refs/heads/main"
  "GITHUB_WORKFLOW_REF=$repository/.github/workflows/build.yml@refs/heads/main"
  "GITHUB_ACTOR=$owner"
  "GITHUB_TRIGGERING_ACTOR=$owner"
)
status=0
# A scheduled run's actor is whoever last changed the cron, so the actor checks below still apply.
if [[ "${GITHUB_EVENT_NAME-}" != workflow_dispatch && "${GITHUB_EVENT_NAME-}" != schedule ]]; then
  echo "Refused: GITHUB_EVENT_NAME is '${GITHUB_EVENT_NAME-<unset>}', expected workflow_dispatch or schedule" >&2
  status=1
fi
for pair in "${expected[@]}"; do
  name=${pair%%=*}
  if [[ "${!name-}" != "${pair#*=}" ]]; then
    echo "Refused: $name is '${!name-<unset>}', expected '${pair#*=}'" >&2
    status=1
  fi
done
[[ $status -eq 0 ]] && echo "Job accepted: $GITHUB_WORKFLOW_REF by $GITHUB_ACTOR"
exit "$status"
