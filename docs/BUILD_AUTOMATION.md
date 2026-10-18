# GitHub Actions build runner

The `Android build` workflow is a manually started build for this repository. It runs only when `rthery` starts or reruns it against `main`. It has no push or pull request trigger. The workflow checks out the exact recipe commit and calls the same `scripts/ci-build.sh` wrapper used for local work. This does not mean the Android sources inside the existing build container match that recipe's pinned manifest; development mode uses the existing local source state.

## What the workflow does

Choose a device codename and one operation:

- `verify` checks the requested recipe and environment without compiling.
- `development` uses the existing Android source checkout and output directory.

The `release-candidate` mode is intentionally unavailable in the workflow while source-manifest matching, vendor patch provenance and signing are audited. The wrapper fails closed for that mode. It must also use a separate output directory that is absent before a candidate build; it must never delete existing outputs automatically.

The first configured device is `bullhead`. The workflow accepts a codename as text so additional `devices/<codename>/` recipes can be used as they are added; the build wrapper validates that the device and mode are supported. Add a reviewed `build.conf` with `BUILD_PRODUCT` and `BUILD_SOURCE_DIR` for each device. Source provisioning is manual; the workflow never syncs or replaces the shared tree. Use a distinct output directory for each device and provision the container mount before using another source path.

The workflow does not upload build outputs, publish a release, sign a package, or create an attestation. Run history is not kept as a build record; delete runs once they are no longer needed. Build success alone does not mean the result was installed or tested on a device.

## Runner setup

Each job runs in a fresh `eos-actions-runner` container started by `scripts/start-runner-container.sh`. The script requests a just-in-time runner configuration from the GitHub API, starts the container, and repeats when the job ends. A just-in-time runner accepts a single job and GitHub then removes its registration, so nothing a job writes to the runner directory, workspace or container filesystem reaches the next job. The container runs the official Linux x64 runner as UID 1000 in the same pinned amd64 image as local compilation. No macOS Full Disk Access permission is required; Docker must already have access to the mounted build directories.

Extract the official checksum-verified Linux x64 runner into `.local/github-runner-dist` and leave it unconfigured; the script refuses a configured directory. Each container copies it into its own filesystem. Run the script from a terminal session with `gh` signed in as the repository owner (repository administration access is needed to create runner configurations). It stays in the foreground, and the runner is offline while it is stopped. Jobs require the `self-hosted`, `Linux`, `X64` and `eos-builder` labels, which the script sets on each runner.

Only these host paths are bind-mounted:

| Host path under the workspace | Container path | Access |
| --- | --- | --- |
| `.local/github-runner-dist` | `/runner-dist` | Read only |
| `src/android` | `/eos/src/android` | Read only |
| `src/android/out` | `/eos/src/android/out` | Read/write build outputs |
| `ccache` | `/eos/ccache` | Read/write shared compiler cache |
| `.local/build-lock` | `/eos/build-lock` | Read/write shared build lock |
| `logs/actions-builds` | `/eos/logs/actions-builds` | Read/write dedicated build evidence |
| `scripts/libmap32.so` | `/eos/scripts/libmap32.so` | Read only |

A job cannot change the Android sources, their Git history or the `repo` metadata. It can still change build outputs and the compiler cache, which later local and Actions builds reuse, so only trusted jobs may reach this runner (see the repository settings below). The container has no Docker socket, privileged mode, host networking, host home directory, backup directories or release-key volume. The image can declare additional anonymous volumes; these are empty container storage removed with the container.

The read-only source tree has been checked with `lunch` and the evidence steps of `development` mode. A build step that writes into the source tree instead of `out/` fails, and should be fixed in that component rather than by making the tree writable again. `release-candidate` needs its own output mount before it is enabled.

Local helper scripts and Actions acquire `/eos/build-lock/build.lock`. In the existing local container, the workspace's `build-lock` symlink points to `.local/build-lock`, so both containers lock the same file. Direct build commands and source edits still require coordination. The workflow also serializes all devices through one concurrency group.

There is one existing source tree and cache, with no second Android checkout. Per-device `build.conf` sets `BUILD_PRODUCT` and `BUILD_SOURCE_DIR`. Provision additional source/output paths and explicit mounts before enabling another device. Source provisioning is manual; the workflow never syncs or replaces the shared tree.

## Repository settings and use

The workflow's `if:` condition only protects this workflow. Any workflow file that reaches GitHub Actions in this repository, including one added by a pull request from a fork, can request the `eos-builder` labels. Public repositories cannot turn off fork pull request workflows, so keep these settings:

- **Settings → General → Pull requests**: pull request creation limited to collaborators.
- **Settings → Actions → General → Fork pull request workflows from outside collaborators**: require approval for all outside collaborators. Never approve a run that adds or changes a workflow file.
- **Settings → Actions → General → Workflow permissions**: read repository contents only, and do not allow Actions to approve pull requests.
- Do not add collaborators with write access while this runner is attached; they can push workflows that run without approval.

After the workflow is committed to `main` and the runner is online, open **Actions → Android build → Run workflow**. Public visitors can read workflow runs and logs until they are deleted; only an account with repository write access can start it. `development` is for incremental local work and reuses existing outputs. Do not treat it as a release build. Preserve generated files and record their checksums and device test results before any separate publication decision.

The runner host and shared cache are persistent. A successful build can reuse cached compilation work, but that does not establish a clean-room or byte-for-byte reproducible build. Record the source revision, manifest, environment and actual validation for each candidate.
