# GitHub Actions build runner

The `Android build` workflow is a manually started build for this repository. It runs only when `rthery` starts or reruns it against `main`. It has no push or pull request trigger. The workflow checks out the exact recipe commit and calls the same `scripts/ci-build.sh` wrapper used for local work. This does not mean the Android sources inside the existing build container match that recipe's pinned manifest; development mode uses the existing local source state.

## What the workflow does

Choose a device codename, a source tree and one operation:

- `verify` checks the requested recipe and environment without compiling.
- `development` (`eos-t` only) uses the existing Android source checkout and output directory.
- `release` (trees whose `build.conf` sets `BUILD_RELEASE_ALLOWED=1`, today `lineage-22.2`) runs three jobs: `build` builds a release target-files from the pinned public sources and attests it; `testing` waits for the `testing` environment, then publishes the signed package as a prerelease; `release` waits for the `release` environment, then marks it as the latest release and updates the Updater feed.

The `eos-t` tree reads `devices/<codename>/build.conf`; any other tree reads `devices/<codename>/<tree>/build.conf`. Source provisioning is manual; the workflow never syncs or replaces a shared tree. `release-candidate` stays refused for `eos-t`.

### Release builds

A `release` run, under the shared build lock:

1. Saves `repo manifest -r` as `resolved.xml`, the exact revision of every project.
2. Runs `scripts/check-tree-pins.py`: every project pinned in the tree's manifest (`devices/bullhead/lineage-22.2/bullhead.xml`) must be at its pin, every other project at or behind what `repo sync` fetched from the upstream manifest branch, and no project may have local changes. The build stops on any mismatch, so it cannot use unpublished commits.
3. Empties `vendor/lge/bullhead` and regenerates it with the device tree's `extract-files.py` from the blob commit pinned in that manifest; `vendor-tree.txt` lists every resulting file hash.
4. Runs `installclean` and `m target-files-package otatools-package` with a new build number, copies the target-files to `zips/ci/<run id>/`, writes `release.json` (hashes, fingerprint, recipe commit) and attests the target-files with `actions/attest-build-provenance`.

Builds reuse the shared `out/` and compiler cache (incremental, `installclean` first), like local builds.

### Signing and publishing

Release keys never reach the runner or GitHub. From the workspace root the maintainer runs:

```bash
bash public/android_builds/scripts/release.sh bullhead lineage-22.2
```

It asks for the key passwords first and checks them against the key files, starts the `release` run, waits for its build job, signs the target-files on the host (`sign-local-candidate.sh`), checks the package with `verify-signed-candidate.py` (which writes `independent-verification.json`), and approves the run's `testing` environment. The passwords only live in that process and are dropped once signing is done; stopping it publishes nothing.

The `testing` job refuses the package unless the signing report's input hash equals the attested target-files hash, the verification file covers this package, and its whole-file signature verifies against `devices/<codename>/<tree>/releasekey.x509.pem`. It attests the package and creates a prerelease with the release's section of `devices/<codename>/<tree>/CHANGELOG.md` (required) and the package, its checksum, `resolved.xml`, `release.json` and `vendor-tree.txt`. The Updater is not offered a prerelease.

After the OTA test on a phone, the maintainer approves the `release` environment on the run page. That job repeats the package checks, refuses a release whose package or checksum differs, marks it as the latest release and replaces the feed asset named by `BUILD_FEED_ASSET`. Both environments require the maintainer's approval; a run can wait up to 30 days for each. Uploads use the job's `GITHUB_TOKEN`; only the two publishing jobs get contents write.

### Test reports

Each release gets a test report page on the `test-reports` branch, which GitHub Pages serves at `https://rthery.github.io/android_builds/<tree>/<release tag>/`; the release notes link it. The page shows the phone, the ROM version, build date and security patch, the build run, the test date and the ROM Bench version, then one table per area (calls and SIM, network, audio, camera, sensors and so on) with a plain status for each item: Works, Works with limits, Doesn't work or Not tested. A tester verdict overrides the automatic outcome. An item set to work with limits shows the tester's note under its label, saying when it works. `scripts/test-report-areas.json` lists the items and their labels; maintainer-only and not-applicable requirements are left out.

Export the reports from ROM Bench (it masks MAC and IP addresses, phone numbers, IMEI, ICCID, serials, emails, SSIDs, the carrier, scanned Bluetooth names and coordinates), pull `report.json`, then in a checkout of `test-reports`:

```bash
python3 scripts/publish-test-report.py <export dir> <test-reports checkout> --release <zips/ci/<run>/release.json> [--private-values <file>]
```

The page depends only on these inputs and `scripts/test-report-areas.json`, so the same export always gives the same page. The phone, codename and tree come from the report and `release.json`. The script refuses an export that still contains such identifiers or any value from the private values file, and one whose fingerprint is not the release's, and rewrites the index. Commit and push the branch normally; a page is updated by new commits as testing continues, never by rewriting the branch, since rewritten commits stay fetchable on GitHub.

Anyone can check a package with `gh attestation verify <package>.zip -R rthery/android_builds`. The package attestation and the target-files attestation both name the same run and recipe commit, which the release notes link. The runner is the maintainer's machine, so this shows which run built and published a file from which public sources, not an independent rebuild.

## Runner setup

Each job runs in a fresh `rom-actions-runner` container started by `scripts/start-runner-container.sh`, from an image built with `docker build --platform linux/amd64 -t rom-actions-runner-image:l22 scripts/runner-image`: the pinned build image plus the arm64 libraries the native aarch64 JDK of LineageOS 22.2 builds needs. The script requests a just-in-time runner configuration from the GitHub API, starts the container, and repeats when the job ends. A just-in-time runner accepts a single job and GitHub then removes its registration, so nothing a job writes to the runner directory, workspace or container filesystem reaches the next job. The container runs the official Linux x64 runner as UID 1000 in the same pinned amd64 image as local compilation. No macOS Full Disk Access permission is required; Docker must already have access to the mounted build directories.

Extract the official checksum-verified Linux x64 runner into `.local/github-runner-dist` and leave it unconfigured; the script refuses a configured directory. Each container copies it into its own filesystem. Run the script from a terminal session with `gh` signed in as the repository owner (repository administration access is needed to create runner configurations). It stays in the foreground, and the runner is offline while it is stopped. Jobs require the `self-hosted`, `Linux`, `X64` and `rom-builder` labels, which the script sets on each runner.

Only these host paths are bind-mounted, plus the build output volume:

| Host path under the workspace | Container path | Access |
| --- | --- | --- |
| `.local/github-runner-dist` | `/runner-dist` | Read only |
| `scripts/runner-job-started.sh` (this repository) | `/work/hooks/job-started.sh` | Read only |
| `src/android` | `/work/src/android` | Read only |
| Docker volume `eos-out-android` (`ROM_OUT_VOLUME`) | `/work/src/android/out` | Read/write build outputs, owned by UID 1000 |
| `ccache` | `/work/ccache` | Read/write shared compiler cache |
| `.local/build-lock` | `/work/build-lock` | Read/write shared build lock |
| `logs/actions-builds` | `/work/logs/actions-builds` | Read/write dedicated build evidence |
| `scripts/libmap32.so` | `/work/scripts/libmap32.so` | Read only |
| `src/lineage-22.2` | `/work/src/lineage-22.2` | Read only |
| `scripts/ckati-native.sh` (this repository, arm64 hosts only) | `/work/src/lineage-22.2/prebuilts/build-tools/linux-x86/bin/ckati` | Read only; runs the tree's aarch64 `ckati` natively, since Soong always calls the linux-x86 one |
| `src/lineage-22.2/out` | `/work/src/lineage-22.2/out` | Read/write build outputs |
| `src/lineage-22.2/vendor/lge/bullhead` | same under `/work/src/lineage-22.2` | Read/write, regenerated by release builds |
| `.local/build-jdk` | `/work/.local/build-jdk` | Read only (aarch64 JDK preload shim, Conscrypt JNI) |
| `zips/ci` | `/work/zips/ci` | Read/write release target-files and publish files |
| `zips/ci-signed` | `/work/zips/ci-signed` | Read only, packages signed on the host |

A job cannot change the Android sources, their Git history or the `repo` metadata, except the generated `vendor/lge/bullhead` files of the 22.2 tree. It can still change build outputs and the compiler cache, which later local and Actions builds reuse, so only trusted jobs may reach this runner (see the repository settings below). The container has no Docker socket, privileged mode, host networking, host home directory, backup directories or release-key volume. The image can declare additional anonymous volumes; these are empty container storage removed with the container.

The read-only source tree has been checked with `lunch` and the evidence steps of `development` mode. A build step that writes into the source tree instead of `out/` fails, and should be fixed in that component rather than by making the tree writable again. Release builds of `eos-t` need their own output mount before they are enabled.

Local helper scripts and Actions acquire `/work/build-lock/build.lock`. In the existing local container, the workspace's `build-lock` symlink points to `.local/build-lock`, so both containers lock the same file. Direct build commands and source edits still require coordination. The workflow also serializes all devices through one concurrency group.

There is one existing source tree and cache, with no second Android checkout. Per-device `build.conf` sets `BUILD_PRODUCT` and `BUILD_SOURCE_DIR`. Provision additional source/output paths and explicit mounts before enabling another device. Source provisioning is manual; the workflow never syncs or replaces the shared tree.

## Repository settings and use

The workflow's `if:` conditions only protect this workflow. Any workflow file that reaches GitHub Actions in this repository, including one added by a pull request from a fork, can request the `rom-builder` labels. Runner groups restricted to selected workflows are not available to repositories owned by a personal account, so the runner enforces this itself: `scripts/runner-job-started.sh` runs as the runner's job-started hook before any step and fails every job unless it is a `workflow_dispatch` of `.github/workflows/build.yml` on `refs/heads/main` in this repository, started and triggered by the owner. The values it checks come from GitHub's job message and cannot be overridden by a workflow (`GITHUB_*` variables are read-only). A refused job still uses up one just-in-time runner, then the script starts the next one.

Public repositories cannot turn off fork pull request workflows, so also keep these settings:

- **Settings → General → Pull requests**: pull request creation limited to collaborators.
- **Settings → Actions → General → Fork pull request workflows from outside collaborators**: require approval for all outside collaborators. Never approve a run that adds or changes a workflow file.
- **Settings → Actions → General → Workflow permissions**: read repository contents only, and do not allow Actions to approve pull requests.
- Do not add collaborators with write access while this runner is attached; they can push workflows that run without approval.

After the workflow is committed to `main` and the runner is online, open **Actions → Android build → Run workflow**. Public visitors can read workflow runs and logs until they are deleted; only an account with repository write access can start it. `development` is for incremental local work and reuses existing outputs. Do not treat it as a release build. Preserve generated files and record their checksums and device test results before any separate publication decision.

The runner host and shared cache are persistent. A successful build can reuse cached compilation work, but that does not establish a clean-room or byte-for-byte reproducible build. Record the source revision, manifest, environment and actual validation for each candidate.
