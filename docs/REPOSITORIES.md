# Repository organization

This repository contains build recipes for multiple devices. Android source code stays in separate component repositories.

## Device recipes

Each `devices/<codename>/` directory contains:

- `manifest.xml`: the complete pinned source manifest for that device and ROM version.
- `README.md`: build instructions, including the device product and required patches.
- `STATUS.md`: working features and known issues.
- `changes.json`: modified component repositories and their upstream revisions.
- `source-id.txt`: the source id of these pins. A build from them reports it in `ro.androidbuilds.source_id`; `scripts/source-id.py` computes it for any resolved manifest.

To add a device, create its own directory and add it to the device table in the main README. Do not copy another device's patched framework or hardware components without checking whether those changes apply.

Devices normally have separate device and vendor repositories. Kernels and common hardware repositories can be shared when compatible. Each manifest selects the exact component commits it needs, so devices can be updated independently.

Branches in component repositories identify development lines, such as `eos-4.4-t`. Create device-specific branches in shared components when devices require different changes. Supporting another device does not require a new branch of this overview repository. Additional ROM versions can use separately named manifests inside the device directory.

## Nexus 5X sources

| Component | Repository |
| --- | --- |
| Device configuration and compatibility helpers | [android_device_lge_bullhead](https://github.com/rthery/android_device_lge_bullhead), forked from [nexus5x-dev/device_lge_bullhead](https://github.com/nexus5x-dev/device_lge_bullhead) |
| Kernel | [android_kernel_lge_bullhead](https://github.com/rthery/android_kernel_lge_bullhead) |
| Proprietary inputs | [nexus5x-dev/vendor_lge_bullhead](https://github.com/nexus5x-dev/vendor_lge_bullhead), extracted with the device tree's `extract-files.sh` |
| Framework and system components | Listed in the [component inventory](../devices/bullhead/changes.json) |
| Release packages | [android_builds-releases](https://github.com/rthery/android_builds-releases) |

Upstream components come from /e/OS, LineageOS, AOSP and community device repositories. Their history and attribution are retained. The Nexus 5X repositories use the topics `android`, `bullhead` and `eos-rom`.
