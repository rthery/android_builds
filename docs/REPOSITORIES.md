# Repository organization

This repository contains build recipes for multiple devices. Android source code stays in separate component repositories.

## Device recipes

Each ROM version has its own `devices/<codename>/<tree>/` directory, for example `devices/bullhead/lineage-22.2/`:

- `<codename>.xml`: the local manifest added to the upstream LineageOS manifest; it pins every changed project to an exact commit.
- `README.md`: build instructions and the list of forked components.
- `INSTALL.md`: install and update instructions for users.
- `CHANGELOG.md`: release notes, one section per release tag.
- `build.conf`: settings for the build workflow (product, source tree, feed file).
- `releasekey.x509.pem`: the release certificate packages are checked against.

The older /e/OS 4.4 (T) recipe sits directly in `devices/<codename>/`: `manifest.xml` (complete pinned manifest), `README.md`, `STATUS.md`, `changes.json` (modified components and their upstream revisions) and `source-id.txt` (the id a build reports in `ro.androidbuilds.source_id`, computed by `scripts/source-id.py`).

To add a device, create its own directory and add it to the device table in the main README. Do not copy another device's patched framework or hardware components without checking whether those changes apply.

Devices normally have separate device and vendor repositories. Kernels and common hardware repositories can be shared when compatible. Each manifest selects the exact component commits it needs, so devices can be updated independently.

Branches in component repositories identify development lines: `lineage-22.2-bullhead` for LineageOS 22.2, `eos-4.4-t` for /e/OS 4.4. Create device-specific branches in shared components when devices require different changes. Supporting another device does not require a new branch of this overview repository. Additional ROM versions can use separately named manifests inside the device directory.

## Nexus 5X sources

| Component | Repository |
| --- | --- |
| Device configuration and compatibility helpers | [android_device_lge_bullhead](https://github.com/rthery/android_device_lge_bullhead), forked from [nexus5x-dev/device_lge_bullhead](https://github.com/nexus5x-dev/device_lge_bullhead) |
| Kernel | [android_kernel_lge_bullhead](https://github.com/rthery/android_kernel_lge_bullhead) |
| Proprietary inputs | [nexus5x-dev/vendor_lge_bullhead](https://github.com/nexus5x-dev/vendor_lge_bullhead), extracted with the device tree's `extract-files.py` (`extract-files.sh` for /e/OS 4.4) |
| Framework and system components | Pinned in the [LineageOS 22.2 local manifest](../devices/bullhead/lineage-22.2/bullhead.xml) ([/e/OS 4.4 inventory](../devices/bullhead/changes.json)) |
| Release packages | [Releases](https://github.com/rthery/android_builds/releases) of this repository |

Upstream components come from LineageOS, /e/OS, AOSP and community device repositories. Their history and attribution are retained. The Nexus 5X repositories use the topics `android`, `bullhead` and `eos-rom`.
